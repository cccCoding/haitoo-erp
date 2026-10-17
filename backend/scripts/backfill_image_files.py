"""补建图片文件索引和历史地址映射；默认只预览，不写数据库或 R2。"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
import json
from pathlib import Path
import sys
from threading import BoundedSemaphore
import time
from urllib.parse import urlsplit

from sqlalchemy import func, select, update

from app.database import SessionLocal, engine
from app.models import MaterialAsset, PodTask, ProductDraft, ProductTemplate, UserTemplateWhiteImage
from app.image_files import by_url, ingest_url, product_library_image_urls, register_bytes
from app.schema_version import assert_schema_current, schema_heads
from app.storage import r2_object_key
from scripts.image_backfill_cache import ImageBackfillCache


# 只读 36 版已有字段，允许迁移前在旧系统运行时预缓存；不得加载整个新版 ORM。
REFERENCE_FIELDS = {
    MaterialAsset: ("url",),
    ProductTemplate: ("cover_url", "size_chart_url"),
    UserTemplateWhiteImage: ("image_url",),
    ProductDraft: ("template_id", "image_urls", "size_chart_url", "sku_items", "carousel_items"),
    PodTask: ("result_urls", "selected_result_url", "parameters"),
}


def assert_prepare_schema(bind):
    with bind.connect() as connection:
        current, expected = schema_heads(connection)
    supported = {"20261013_36", "20261014_37", "20261016_38", "20261016_39"} | expected
    if len(current) != 1 or not current <= supported:
        raise RuntimeError("预缓存要求数据库为 20261013_36 至当前版本；不会自动执行迁移")


def references(db, company_id=None):
    for model, fields in REFERENCE_FIELDS.items():
        last_id = 0
        upper_id = db.scalar(select(func.max(model.id))) or 0
        while last_id < upper_id:
            stmt = select(model.id, model.company_id, *(getattr(model, name) for name in fields)).where(
                model.id > last_id, model.id <= upper_id).order_by(model.id).limit(500)
            if company_id is not None:
                stmt = stmt.where(model.company_id == company_id)
            records = db.execute(stmt).all()
            if not records:
                break
            last_id = records[-1].id
            for record in records:
                yield from _record_references(db, model, record)
            # 分页短事务，不在下载阶段保留游标或旧系统的长事务快照。
            db.rollback()


def _record_references(db, model, record):
    if record.company_id is None:
        return
    if model is MaterialAsset:
        urls = [record.url]
    elif model is ProductTemplate:
        urls = [record.cover_url, record.size_chart_url]
    elif model is UserTemplateWhiteImage:
        urls = [record.image_url]
    elif model is ProductDraft:
        template_size = db.scalar(select(ProductTemplate.size_chart_url).where(
            ProductTemplate.id == record.template_id,
            ProductTemplate.company_id == record.company_id)) if record.template_id else None
        urls = list(record.image_urls or []) + [record.size_chart_url or template_size]
        urls += [item.get("image_url") for item in (record.sku_items or []) + (record.carousel_items or [])]
        original_urls = product_library_image_urls(db, record.company_id, [url for url in urls if url])
        original_urls.update(item["product_library_image_url"] for item in record.sku_items or []
            if item.get("product_library_image_url"))
        urls = [url for url in urls if url not in original_urls]
    else:
        urls = list(record.result_urls or []) + [record.selected_result_url]
        parameters = record.parameters or {}
        urls += list(parameters.get("print_urls") or []) + [parameters.get("print_url")]
    for url in dict.fromkeys(url.strip() for url in urls if isinstance(url, str) and url.strip()):
        yield {"model": model.__name__, "id": record.id, "company_id": record.company_id, "url": url}


def _failed_addresses(path):
    latest = {}
    with Path(path).open("rb") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                if not line.endswith(b"\n"):
                    break  # 进程中断时最后一条可能尚未写完整；重新全量运行可补齐。
                raise
            latest[(row["company_id"], row["url"])] = row.get("result")
    return {key for key, result in latest.items() if result == "error"}


def _open_report(path):
    path = Path(path)
    # 仅修复末尾尚未完成的 JSON 行，避免中断后追加报告把两条 JSON 拼在一起。
    with path.open("a+b") as stream:
        end = stream.tell()
        if end:
            stream.seek(end - 1)
            if stream.read(1) != b"\n":
                start, tail = end, b""
                while start:
                    offset = max(0, start - 8192)
                    stream.seek(offset)
                    tail = stream.read(start - offset) + tail
                    start = offset
                    newline = tail.rfind(b"\n")
                    if newline >= 0:
                        start += newline + 1
                        tail = tail[newline + 1:]
                        break
                try:
                    json.loads(tail)
                except (ValueError, UnicodeDecodeError):
                    stream.truncate(start)
                else:
                    stream.write(b"\n")
    return path.open("a", encoding="utf-8")


def _process_group(rows, *, apply, prepare, cache, session_factory):
    first = rows[0]
    company, url = first["company_id"], first["url"]
    try:
        if prepare:
            hit = cache.prepare(company, url)
            values = {"result": "cached" if hit else "prepared"}
        else:
            with session_factory() as db:
                image_file = by_url(db, company, url)
                if apply:
                    indexed = image_file is not None
                    cached = False
                    if image_file is None:
                        # 下载或读取缓存前释放查询事务，登记复用现有图片服务。
                        db.commit()
                        content = cache.read(company, url) if cache else None
                        if content is not None:
                            key = r2_object_key(url)
                            owned = key and f"/company/{company}/" in f"/{key}"
                            image_file = register_bytes(db, company, content, source_url=url,
                                preserve_url=url if owned else None)
                            cached = True
                        else:
                            image_file = ingest_url(db, company, url)
                    file_id = image_file.id
                    asset_ids = [row["id"] for row in rows if row["model"] == "MaterialAsset"]
                    for offset in range(0, len(asset_ids), 400):
                        current_assets = db.execute(select(MaterialAsset.id, MaterialAsset.url).where(
                            MaterialAsset.company_id == company,
                            MaterialAsset.id.in_(asset_ids[offset:offset + 400]))).all()
                        # 与旧脚本一致按 Python strip 匹配，兼容历史换行、制表符等空白。
                        matching = {}
                        for asset_id, stored_url in current_assets:
                            if stored_url and stored_url.strip() == url:
                                matching.setdefault(stored_url, []).append(asset_id)
                        for stored_url, ids in matching.items():
                            db.execute(update(MaterialAsset).where(MaterialAsset.company_id == company,
                                MaterialAsset.id.in_(ids), MaterialAsset.url == stored_url).values(image_file_id=file_id))
                    db.commit()
                    values = {"result": "saved", "image_file_id": file_id,
                        "source": "indexed" if indexed else "cache" if cached else "network"}
                else:
                    values = {"result": "indexed" if image_file else "would_save"}
    except Exception as exc:
        values = {"result": "error", "error": str(getattr(exc, "detail", exc))}
    return [{**row, **values} for row in rows]


def run(*, apply=False, prepare=False, cache_dir=None, company_id=None, report=None,
        retry_from=None, session_factory=SessionLocal, workers=1, per_host=4,
        limit=None, progress_seconds=5, verbose=True, collect_results=True):
    if prepare and (apply or not cache_dir):
        raise ValueError("预缓存需要 --cache-dir，且不能与 --apply 同时使用")
    if not 1 <= workers <= 32 or per_host < 1 or progress_seconds <= 0 or (limit is not None and limit < 1):
        raise ValueError("并发数须为 1–32；域名并发、进度间隔及数量限制须为正数")
    started = time.monotonic()
    groups = {}
    with session_factory() as db:
        for row in references(db, company_id):
            groups.setdefault((row["company_id"], row["url"]), []).append(row)
    if retry_from:
        failures = _failed_addresses(retry_from)
        groups = {key: rows for key, rows in groups.items() if key in failures}
    total_available = len(groups)
    batches = list(groups.values())[:limit]
    cache = ImageBackfillCache(cache_dir) if cache_dir else None

    def host(rows):
        try:
            return urlsplit(rows[0]["url"]).hostname
        except ValueError:
            return None  # 非法 URL 交由逐项下载校验报告，不能中止其他图片。

    semaphores = {host(rows): BoundedSemaphore(per_host) for rows in batches}

    def process(rows):
        with semaphores[host(rows)]:
            return _process_group(rows, apply=apply, prepare=prepare, cache=cache, session_factory=session_factory)

    counts = Counter()
    output = []
    summary = {"total_urls": len(batches), "total_references": sum(map(len, batches)),
        "available_urls": total_available, "limited": total_available > len(batches),
        "company_id": company_id, "retry_only": bool(retry_from),
        "completed_urls": 0, "completed_references": 0, "errors": 0}

    def progress(event):
        elapsed = max(time.monotonic() - started, 0.001)
        rate = summary["completed_urls"] / elapsed
        payload = {"event": event, "mode": "prepare" if prepare else "apply" if apply else "preview",
            **summary, "counts": dict(counts), "elapsed_seconds": round(elapsed, 1),
            "urls_per_second": round(rate, 2),
            "eta_seconds": round((len(batches) - summary["completed_urls"]) / rate) if rate else None}
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)

    progress("start")
    stream = _open_report(report) if report else None
    executor = ThreadPoolExecutor(max_workers=workers)
    pending = set()
    iterator = iter(batches)
    last_progress = time.monotonic()
    try:
        while True:
            while len(pending) < workers:
                rows = next(iterator, None)
                if rows is None:
                    break
                pending.add(executor.submit(process, rows))
            if not pending:
                break
            done, pending = wait(pending, timeout=min(progress_seconds, 1), return_when=FIRST_COMPLETED)
            for future in done:
                results = future.result()
                first = results[0]
                summary["completed_urls"] += 1
                summary["completed_references"] += len(results)
                summary["errors"] += first["result"] == "error"
                counts[first.get("source", first["result"])] += 1
                for result in results:
                    line = json.dumps(result, ensure_ascii=False)
                    if stream:
                        stream.write(line + "\n")
                    if verbose:
                        print(line, flush=True)
                if stream:
                    stream.flush()
                if collect_results:
                    output.extend(results)
            if time.monotonic() - last_progress >= progress_seconds:
                progress("progress")
                last_progress = time.monotonic()
    finally:
        for future in pending:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        if stream:
            stream.close()
    progress("complete")
    return output if collect_results else summary


def configure_temporary_lifecycle():
    """只追加临时区规则，保留桶内其他生命周期配置。"""
    from botocore.exceptions import ClientError
    from app.config import get_settings
    from app.storage import _configuration, _r2_client
    endpoint, access, secret, bucket, _ = _configuration(get_settings())
    client = _r2_client(endpoint, access, secret)
    try:
        rules = client.get_bucket_lifecycle_configuration(Bucket=bucket).get("Rules", [])
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {"NoSuchLifecycleConfiguration", "NoSuchLifecycle"}:
            raise
        rules = []
    rule = {"ID": "haitoo-image-upload-tmp-24h", "Status": "Enabled",
        "Filter": {"Prefix": "image-upload-tmp/"}, "Expiration": {"Days": 1}}
    rules = [existing for existing in rules if existing.get("ID") != rule["ID"]] + [rule]
    client.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration={"Rules": rules})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="实际转存并写入索引；默认仅预览")
    parser.add_argument("--prepare", action="store_true", help="迁移前只读旧数据库、预下载并校验图片到磁盘；不写数据库或 R2")
    parser.add_argument("--cache-dir", help="持久化图片缓存目录；预缓存和正式回填须挂载同一目录")
    parser.add_argument("--workers", type=int, default=8, help="并行处理的不同图片地址数，默认 8，最多 32")
    parser.add_argument("--per-host", type=int, default=4, help="同一来源域名的最大并发，默认 4")
    parser.add_argument("--limit", type=int, help="本次最多处理多少个不同的公司/地址，用于小批量测速；不表示全量完成")
    parser.add_argument("--progress-seconds", type=float, default=5, help="进度、吞吐和预计剩余时间的输出间隔，默认 5 秒")
    parser.add_argument("--verbose", action="store_true", help="同时向标准输出打印逐项结果；完整结果始终保存在报告中")
    parser.add_argument("--company-id", type=int)
    parser.add_argument("--report", default=f"/tmp/image-backfill-{datetime.now():%Y%m%d-%H%M%S}.jsonl")
    parser.add_argument("--retry-from", help="只处理此前报告中的失败地址")
    parser.add_argument("--configure-temp-lifecycle", action="store_true", help="与 --apply 一起使用，追加临时上传区清理规则")
    args = parser.parse_args()
    if args.prepare and (args.apply or not args.cache_dir):
        parser.error("--prepare 需要 --cache-dir，且不能与 --apply 同时使用")
    if not 1 <= args.workers <= 32 or args.per_host < 1 or args.progress_seconds <= 0 or (args.limit is not None and args.limit < 1):
        parser.error("--workers 须为 1–32，其余数量及间隔须为正数")
    if args.prepare:
        assert_prepare_schema(engine)
    else:
        assert_schema_current(engine)
    if args.configure_temp_lifecycle:
        if not args.apply:
            parser.error("配置临时区清理需要 --apply")
        configure_temporary_lifecycle()
    if args.prepare or args.apply:
        # boto3 默认 Session 不应在多个线程中同时初始化；提前创建缓存客户端。
        from app.config import get_settings
        from app.storage import StorageError, _configuration, _r2_client
        try:
            configuration = _configuration(get_settings())
        except StorageError:
            pass  # 由逐项处理报告缺失配置；只有磁盘缓存命中的预缓存无需 R2。
        else:
            _r2_client(*configuration[:3])
    summary = run(apply=args.apply, prepare=args.prepare, cache_dir=args.cache_dir,
        company_id=args.company_id, report=args.report, retry_from=args.retry_from,
        workers=args.workers, per_host=args.per_host, limit=args.limit,
        progress_seconds=args.progress_seconds, verbose=args.verbose, collect_results=False)
    if summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
