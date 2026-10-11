"""按白底图历史版本统计最近最多 2000 张 SKU 生成图的平均大小。"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import dataclass, field
from pathlib import Path
import sys
from time import monotonic
from typing import TextIO

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import Company, PodTask, ProductTemplate, User
from app.storage import StorageError, r2_object_key
from scripts.r2_image_statistics import create_client, readable_size
from scripts.white_image_statistics import WhiteImageRow, load_records


SAMPLE_LIMIT = 2000
HEADERS = ("公司 ID", "公司名称", "白底图 ID", "白底图名称", "创作人 ID", "创作人姓名", "创作人信息来源",
           "模板 ID", "模板名称", "白底图链接", "白底图大小", "白底图读取状态", "关联生成图总数",
           "取样数量", "成功读取数量", "无法读取数量", "生成图平均大小", "生成图读取状态")


@dataclass
class GenerationRow:
    company_id: int
    company_name: str
    white_image_id: int | None
    white_image_name: str
    creator_id: int
    creator_name: str
    creator_source: str
    template_id: int
    template_name: str
    white_image_url: str
    generated_urls: set[str] = field(default_factory=set)
    sample_urls: list[str] = field(default_factory=list)
    white_size: int | None = None
    white_status: str = "待查询"
    successful_count: int = 0
    sample_total_bytes: int = 0
    sample_status: str = "待查询"

    def cells(self) -> tuple[str, ...]:
        average = readable_size(self.sample_total_bytes / self.successful_count) if self.successful_count else "—"
        return (str(self.company_id), self.company_name,
                str(self.white_image_id) if self.white_image_id is not None else "—", self.white_image_name,
                str(self.creator_id), self.creator_name, self.creator_source, str(self.template_id), self.template_name,
                self.white_image_url, readable_size(self.white_size) if self.white_size is not None else "—",
                self.white_status, str(len(self.generated_urls)), str(len(self.sample_urls)),
                str(self.successful_count), str(len(self.sample_urls) - self.successful_count), average, self.sample_status)


@dataclass
class GenerationReport:
    rows: list[GenerationRow]
    task_count: int
    unassociated_task_count: int


def row_from_white(image: WhiteImageRow, url: str | None = None) -> GenerationRow:
    return GenerationRow(
        company_id=image.company_id, company_name=image.company_name, white_image_id=image.image_id,
        white_image_name=image.name, creator_id=image.creator_id, creator_name=image.creator_name,
        creator_source="白底图所属人员", template_id=image.template_id, template_name=image.template_name,
        white_image_url=url if url is not None else image.image_url,
    )


def white_id(value) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal() and int(value) > 0:
        return int(value)
    return None


def load_report(
    db: Session, *, company_id: int | None = None, creator_id: int | None = None,
    template_id: int | None = None, white_image_id: int | None = None,
) -> GenerationReport:
    current = {(image.company_id, image.image_id): image for image in load_records(db, company_id=company_id)}
    groups: dict[tuple[int, int | None, str], GenerationRow] = {}
    for image in current.values():
        if ((creator_id is None or image.creator_id == creator_id)
                and (template_id is None or image.template_id == template_id)
                and (white_image_id is None or image.image_id == white_image_id)):
            groups[(image.company_id, image.image_id, image.image_url)] = row_from_white(image)

    # 只取所需列，按生成时间排序逐批读取；首遇链接就是该链接的最新结果。
    statement = select(
        PodTask.id, PodTask.company_id, PodTask.template_id, PodTask.created_by,
        PodTask.parameters, PodTask.result_urls,
        Company.name.label("company_name"), User.name.label("creator_name"), ProductTemplate.name.label("template_name"),
    ).outerjoin(Company, Company.id == PodTask.company_id).outerjoin(
        User, User.id == PodTask.created_by,
    ).outerjoin(ProductTemplate, ProductTemplate.id == PodTask.template_id).where(PodTask.task_type == "sku_image")
    if company_id is not None:
        statement = statement.where(PodTask.company_id == company_id)
    if template_id is not None:
        statement = statement.where(PodTask.template_id == template_id)
    statement = statement.order_by(func.coalesce(PodTask.completed_at, PodTask.created_at).desc(), PodTask.id.desc())
    task_count, unassociated = 0, 0
    named_groups = set()
    for task in db.execute(statement.execution_options(yield_per=1000)):
        parameters = task.parameters if isinstance(task.parameters, dict) else {}
        image_id = white_id(parameters.get("white_image_id"))
        image = current.get((task.company_id, image_id))
        owner_id = image.creator_id if image else task.created_by
        if ((creator_id is not None and owner_id != creator_id)
                or (white_image_id is not None and image_id != white_image_id)):
            continue
        task_count += 1
        url = parameters.get("white_image_url")
        if not isinstance(url, str) or not url.strip():
            unassociated += 1
            continue
        url = url.strip()
        key = (task.company_id, image_id, url)
        if key not in groups:
            groups[key] = row_from_white(image, url) if image else GenerationRow(
                company_id=task.company_id, company_name=task.company_name or "历史公司信息缺失",
                white_image_id=image_id, white_image_name="历史白底图名称缺失", creator_id=task.created_by,
                creator_name=task.creator_name or "历史人员信息缺失", creator_source="来源 SKU 任务创作人",
                template_id=task.template_id, template_name=task.template_name or "历史模板信息缺失", white_image_url=url,
            )
        group = groups[key]
        if key not in named_groups:
            name = parameters.get("white_image_name")
            if isinstance(name, str) and name.strip():
                group.white_image_name = name.strip()
            named_groups.add(key)
        results = task.result_urls if isinstance(task.result_urls, list) else []
        for result in results:
            if not isinstance(result, str) or not result.strip():
                continue
            result = result.strip()
            if result in group.generated_urls:
                continue
            group.generated_urls.add(result)
            if len(group.sample_urls) < SAMPLE_LIMIT:
                group.sample_urls.append(result)
    rows = sorted(groups.values(), key=lambda row: (
        row.company_id, row.creator_id, row.template_id, row.white_image_id or 0, row.white_image_url,
    ))
    return GenerationReport(rows, task_count, unassociated)


def read_sizes(rows: list[GenerationRow], settings: Settings, *, progress: TextIO | None = None) -> None:
    if rows and not settings.r2_public_base_url:
        raise StorageError("未配置 R2_PUBLIC_BASE_URL，无法匹配图片链接")
    targets: dict[str, set[str]] = {}
    links: dict[tuple[int, str, bool], tuple[str | None, str]] = {}

    def register(company_id: int, url: str, generated: bool) -> tuple[str | None, str]:
        identity = (company_id, url, generated)
        if identity in links:
            return links[identity]
        key = r2_object_key(url, settings)
        prefix = "generated/" if generated else f"template-white/company/{company_id}/"
        if key is None:
            info = (None, "链接不属于当前 R2")
        elif not key.startswith(prefix) or (generated and f"/company/{company_id}/" not in key):
            info = (None, "图片目录或公司不匹配")
        else:
            targets.setdefault(prefix, set()).add(key)
            info = (key, "R2 对象不存在")
        links[identity] = info
        return info

    for row in rows:
        register(row.company_id, row.white_image_url, False)
        for url in row.sample_urls:
            register(row.company_id, url, True)
    target_count = sum(len(keys) for keys in targets.values())
    sizes: dict[str, int] = {}
    started_at = monotonic()
    page_count, scanned = 0, 0
    if progress is not None:
        print(f"开始 R2 扫描：{len(rows)} 个白底图版本，{sum(len(row.sample_urls) for row in rows)} 个生成图样本，"
              f"{target_count} 个目标文件。", file=progress, flush=True)
    if targets:
        client = create_client(settings)
        # 白底图按公司读取；generated/ 只扫描一次，所有版本复用目标文件大小。
        for prefix in sorted(targets, key=lambda prefix: (prefix == "generated/", prefix)):
            pending = set(targets[prefix])
            pages = client.get_paginator("list_objects_v2").paginate(
                Bucket=settings.r2_bucket, Prefix=prefix, PaginationConfig={"PageSize": 1000},
            )
            for page in pages:
                page_count += 1
                items = page.get("Contents", [])
                scanned += len(items)
                for item in items:
                    key = item["Key"]
                    if key in pending:
                        sizes[key] = item["Size"]
                        pending.remove(key)
                if progress is not None:
                    print(f"已读取 {page_count} 页（{prefix}）；扫描 {scanned} 个对象；"
                          f"已匹配 {len(sizes)}/{target_count} 个目标文件；耗时 {monotonic() - started_at:.1f} 秒。",
                          file=progress, flush=True)
                if not pending:
                    break

    def resolve(company_id: int, url: str, generated: bool) -> tuple[int | None, str]:
        key, status = links[(company_id, url, generated)]
        return (sizes[key], "正常") if key in sizes else (None, status)

    for row in rows:
        row.white_size, row.white_status = resolve(row.company_id, row.white_image_url, False)
        failures = Counter()
        row.successful_count, row.sample_total_bytes = 0, 0
        for url in row.sample_urls:
            size, status = resolve(row.company_id, url, True)
            if size is None:
                failures[status] += 1
            else:
                row.successful_count += 1
                row.sample_total_bytes += size
        row.sample_status = ("；".join(f"{status}：{count}" for status, count in sorted(failures.items()))
                             if failures else "全部成功" if row.sample_urls else "无生成结果")
    if progress is not None:
        print(f"统计完成：{len(rows)} 个白底图版本；成功读取 {sum(row.successful_count for row in rows)} 个生成图样本；"
              f"耗时 {monotonic() - started_at:.1f} 秒。", file=progress, flush=True)


def write_report(rows: list[GenerationRow], output: TextIO, output_format: str) -> None:
    if output_format == "csv":
        writer = csv.writer(output)
        writer.writerow(HEADERS)
        writer.writerows(row.cells() for row in rows)
        return
    output.write("\t".join(HEADERS) + "\n")
    for row in rows:
        output.write("\t".join(" ".join(cell.split()) for cell in row.cells()) + "\n")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按白底图统计最近最多 2000 张 SKU 生成图的平均大小（只读）")
    for option, help_text in (("company-id", "仅统计指定公司"), ("creator-id", "仅统计指定白底图所属创作人"),
                              ("template-id", "仅统计指定模板"), ("white-image-id", "仅统计指定白底图 ID 的各历史版本")):
        parser.add_argument(f"--{option}", type=int, help=help_text)
    parser.add_argument("--format", choices=("table", "csv"), default="table", help="默认中文终端表格")
    parser.add_argument("--no-progress", action="store_true", help="关闭进度；未关联任务提醒仍输出到 stderr")
    args = parser.parse_args(argv)
    filters = {option: getattr(args, option) for option in ("company_id", "creator_id", "template_id", "white_image_id")}
    for option, value in filters.items():
        if value is not None and value <= 0:
            parser.error(f"--{option.replace('_', '-')} 必须为正整数")
    try:
        if not args.no_progress:
            print("正在只读查询白底图和 SKU 任务记录……", file=sys.stderr, flush=True)
        with SessionLocal() as db:
            report = load_report(db, **filters)
        if not args.no_progress:
            print(f"数据库读取完成：{report.task_count} 个 SKU 任务、{len(report.rows)} 个白底图版本；"
                  f"生成图样本 {sum(len(row.sample_urls) for row in report.rows)} 张（每版本最多 {SAMPLE_LIMIT} 张）。",
                  file=sys.stderr, flush=True)
        if report.unassociated_task_count:
            print(f"未关联任务：{report.unassociated_task_count} 个 SKU 任务缺少历史白底图链接，未纳入统计。",
                  file=sys.stderr, flush=True)
        # 所有数据已转为普通对象，数据库连接在 R2 扫描之前关闭。
        read_sizes(report.rows, get_settings(), progress=None if args.no_progress else sys.stderr)
    except SQLAlchemyError as exc:
        print(f"数据库查询失败（{type(exc).__name__}），请检查配置与连接。", file=sys.stderr)
        return 1
    except StorageError as exc:
        print(f"R2 配置错误：{exc}", file=sys.stderr)
        return 1
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "未知错误")
        print(f"R2 列表读取失败（{code}），请检查桶名称及对象列表权限。", file=sys.stderr)
        return 1
    except BotoCoreError as exc:
        print(f"R2 连接失败（{type(exc).__name__}），请检查连接与配置。", file=sys.stderr)
        return 1
    write_report(report.rows, sys.stdout, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
