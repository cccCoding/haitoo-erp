"""只读核对白底图历史引用，兼容尚未迁移风格表和软删除字段的数据库。"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import TextIO

from sqlalchemy import MetaData, Table, func, inspect, select
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal


BATCH_SIZE = 500
KINDS = {
    "missing_record": "来源记录缺失（疑似物理删除）",
    "identity_mismatch": "ID 存在但归属不同（疑似 ID 复用或数据异常）",
    "url_changed": "同一来源的历史图片不同（可能曾换图，不能证明删除）",
    "unverifiable": "引用不完整，无法判断",
}
LIMITATION = (
    "本报告核对数据库记录，不检查 R2 文件是否删除。缺失引用可能来自物理删除或数据异常；"
    "仅凭当前数据库不能确认删除操作、时间和操作人。未被任务或风格引用的白底图若已删除，"
    "以及与新记录完全相同的主键复用，无法检出；未发现异常不代表从未物理删除。"
)


def positive_id(value):
    if type(value) is int and 0 < value <= 9223372036854775807:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal() and 0 < len(value) <= 20:
        identity = int(value)
        if 0 < identity <= 9223372036854775807:
            return identity
    return None


def batches(db, table, columns, filters):
    last_id = 0
    while True:
        rows = db.execute(select(*columns).where(*filters, table.c.id > last_id)
                          .order_by(table.c.id).limit(BATCH_SIZE)).mappings().all()
        if not rows:
            return
        yield rows
        last_id = rows[-1]["id"]


def load_report(db, *, company_id=None, creator_id=None, template_id=None):
    # 使用实际表结构而非当前 ORM，旧服务器无需先执行迁移。
    connection = db.connection()
    metadata = MetaData()
    tables = set(inspect(connection).get_table_names())
    if not {"user_template_white_images", "pod_tasks"} <= tables:
        raise ValueError("缺少 user_template_white_images 或 pod_tasks 表，无法核对")
    white = Table("user_template_white_images", metadata, autoload_with=connection)
    task = Table("pod_tasks", metadata, autoload_with=connection)
    style = Table("material_styles", metadata, autoload_with=connection) if "material_styles" in tables else None
    counts = Counter(scanned_tasks=0, matching_tasks=0, soft_deleted_tasks=0,
                     unreferenced_tasks=0, scanned_styles=0, matching_styles=0, soft_deleted_styles=0)
    groups = {}

    def filters(table, owner_column):
        return [column == value for column, value in (
            (table.c.company_id, company_id), (owner_column, creator_id), (table.c.template_id, template_id)
        ) if value is not None]

    def sources(ids):
        columns = [white.c.id, white.c.company_id, white.c.user_id, white.c.template_id, white.c.image_url]
        if "deleted_at" in white.c:
            columns.append(white.c.deleted_at)
        # 全局查 ID，避免把其他公司/成员持有的同 ID 误判为记录缺失。
        return {row["id"]: row for row in db.execute(select(*columns).where(white.c.id.in_(ids))).mappings()}

    def record(kind, source, row, image_id, name, url, current):
        creator = row["created_by"]
        key = (kind, source, row["company_id"], creator, row["template_id"], image_id, url)
        if key not in groups:
            groups[key] = {
                "kind": kind, "description": KINDS[kind], "source": source,
                "company_id": row["company_id"], "creator_id": creator, "template_id": row["template_id"],
                "white_image_id": image_id, "historical_name": name, "historical_url": url,
                "reference_count": 0, "example_reference_ids": [],
                "current_record": dict(current) if current else None,
            }
        group = groups[key]
        group["reference_count"] += 1
        if len(group["example_reference_ids"]) < 5:
            group["example_reference_ids"].append(row["id"])
        counts[f"{source}_{kind}"] += 1

    def classify(source, row, image_id, name, url, current):
        if image_id is None:
            kind = "unverifiable"
        elif current is None:
            kind = "missing_record"
        elif (current["company_id"], current["user_id"], current["template_id"]) != (
                row["company_id"], row["created_by"], row["template_id"]):
            kind = "identity_mismatch"
        elif source == "task" and url and url != current["image_url"]:
            kind = "url_changed"
        else:
            counts[f"soft_deleted_{source}s" if current.get("deleted_at") is not None else f"matching_{source}s"] += 1
            return
        record(kind, source, row, image_id, name, url, current)

    columns = [task.c.id, task.c.company_id, task.c.template_id, task.c.created_by, task.c.parameters]
    for rows in batches(db, task, columns, [task.c.task_type == "sku_image", *filters(task, task.c.created_by)]):
        parsed = []
        for row in rows:
            counts["scanned_tasks"] += 1
            params = row["parameters"]
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except ValueError:
                    params = None
            if not isinstance(params, dict):
                record("unverifiable", "task", row, None, "", "", None)
                continue
            if not any(key in params for key in ("white_image_id", "white_image_url", "white_image_name")):
                counts["unreferenced_tasks"] += 1
                continue
            image_id = positive_id(params.get("white_image_id"))
            parsed.append((row, params, image_id))
        current = sources({image_id for _, _, image_id in parsed if image_id is not None})
        for row, params, image_id in parsed:
            url = params.get("white_image_url")
            name = params.get("white_image_name")
            classify("task", row, image_id, name if isinstance(name, str) else "",
                     url.strip() if isinstance(url, str) else "", current.get(image_id))

    if style is not None:
        columns = [style.c.id, style.c.company_id, style.c.template_id, style.c.created_by,
                   style.c.source_white_image_id, style.c.name]
        for rows in batches(db, style, columns, filters(style, style.c.created_by)):
            current = sources({row["source_white_image_id"] for row in rows})
            for row in rows:
                counts["scanned_styles"] += 1
                image_id = positive_id(row["source_white_image_id"])
                classify("style", row, image_id, row["name"], "", current.get(image_id))

    rows = sorted(groups.values(), key=lambda row: (
        list(KINDS).index(row["kind"]), row["company_id"], row["white_image_id"] or 0, row["source"]))
    missing_ids = {row["white_image_id"] for row in rows if row["kind"] == "missing_record"}
    counts["missing_white_image_ids"] = len(missing_ids)
    white_filters = filters(white, white.c.user_id)
    counts["existing_white_images"] = db.scalar(select(func.count()).select_from(white).where(*white_filters))
    counts["soft_deleted_white_images"] = (db.scalar(select(func.count()).select_from(white).where(
        *white_filters, white.c.deleted_at.is_not(None))) if "deleted_at" in white.c else 0)
    if missing_ids:
        conclusion = "发现历史引用的白底图记录缺失，存在疑似物理删除痕迹。"
    elif any(row["kind"] == "identity_mismatch" for row in rows):
        conclusion = "发现白底图 ID 归属异常，可能曾复用 ID 或存在数据异常，需进一步核查。"
    else:
        conclusion = "未发现可追溯的物理删除痕迹；不能据此排除历史物理删除。"
    return {"conclusion": conclusion, "counts": dict(counts), "limitation": LIMITATION,
            "supports_soft_delete": "deleted_at" in white.c, "has_style_table": style is not None,
            "filters": {"company_id": company_id, "creator_id": creator_id, "template_id": template_id},
            "rows": rows}


def write_report(report, output: TextIO, *, output_format="table", limit=50):
    rows = report["rows"][:limit] if limit else report["rows"]
    if output_format == "json":
        json.dump({**report, "rows": rows, "total_groups": len(report["rows"])}, output,
                  ensure_ascii=False, indent=2, default=str)
        output.write("\n")
        return
    counts = report["counts"]
    print(report["conclusion"], file=output)
    print(f"已扫描 SKU 任务 {counts['scanned_tasks']} 条、风格 {counts['scanned_styles']} 条；"
          f"缺失白底图 ID {counts['missing_white_image_ids']} 个。", file=output)
    print(f"现存白底图 {counts['existing_white_images']} 条，其中软删除 {counts['soft_deleted_white_images']} 条"
          f"（软删除不属于物理删除）；无白底图引用的任务 {counts['unreferenced_tasks']} 条。", file=output)
    print(f"历史换图差异任务 {counts.get('task_url_changed', 0)} 条；"
          f"归属异常引用 {counts.get('task_identity_mismatch', 0) + counts.get('style_identity_mismatch', 0)} 条；"
          f"无法判断的引用 {counts.get('task_unverifiable', 0) + counts.get('style_unverifiable', 0)} 条。", file=output)
    print(f"软删除字段：{'存在' if report['supports_soft_delete'] else '不存在（旧版本）'}；"
          f"风格表：{'存在' if report['has_style_table'] else '不存在（已跳过）'}。", file=output)
    print("\n类型\t公司ID\t创作人ID\t模板ID\t白底图ID\t历史名称\t引用数\t来源及示例ID\t历史图片链接", file=output)
    for row in rows:
        values = (row["description"], row["company_id"], row["creator_id"], row["template_id"],
                  row["white_image_id"] or "—", row["historical_name"], row["reference_count"],
                  f"{'任务' if row['source'] == 'task' else '风格'}:{row['example_reference_ids']}", row["historical_url"])
        print("\t".join(" ".join(str(value).split()) for value in values), file=output)
    print(f"\n异常/历史差异分组 {len(report['rows'])} 个，本次显示 {len(rows)} 个；--limit 0 可显示全部。", file=output)
    print(report["limitation"], file=output)


def run(argv=None):
    parser = argparse.ArgumentParser(description="只读检查白底图是否留有物理删除痕迹，不要求先执行数据库迁移")
    for option, label in (("company-id", "公司"), ("creator-id", "所属创作人"), ("template-id", "模板")):
        parser.add_argument(f"--{option}", type=int, help=f"只核对指定{label} ID")
    parser.add_argument("--format", choices=("table", "json"), default="table", help="输出格式，默认中文表格")
    parser.add_argument("--limit", type=int, default=50, help="最多显示多少个明细分组，0 为全部；始终扫描全部匹配任务")
    args = parser.parse_args(argv)
    for option in ("company_id", "creator_id", "template_id"):
        if getattr(args, option) is not None and getattr(args, option) <= 0:
            parser.error(f"--{option.replace('_', '-')} 必须为正整数")
    if args.limit < 0:
        parser.error("--limit 不能小于 0")
    try:
        with SessionLocal() as db:
            report = load_report(db, company_id=args.company_id, creator_id=args.creator_id, template_id=args.template_id)
    except (SQLAlchemyError, ValueError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else f"数据库读取失败（{type(exc).__name__}），请检查数据库连接与表结构"
        print(message, file=sys.stderr)
        return 1
    write_report(report, sys.stdout, output_format=args.format, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
