"""只读统计三类图片任务的数量与采用率。"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import re
import sys
from typing import TextIO
import unicodedata
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Company, PodTask, User


TASK_TYPES = {"sku_image": "SKU 图", "carousel": "轮播图", "main_image": "首图"}
HONG_KONG = ZoneInfo("Asia/Hong_Kong")
HEADERS = ("统计范围", "公司 ID", "公司名称", "人员 ID", "姓名", "任务类型", "任务数", "采用任务数", "采用率")


@dataclass(frozen=True)
class StatisticsRow:
    task_type: str
    total: int
    adopted: int
    company_id: int | None = None
    company_name: str = ""
    creator_id: int | None = None
    creator_name: str = ""

    def cells(self) -> tuple[str, ...]:
        rate = f"{self.adopted / self.total * 100:.2f}%" if self.total else "0.00%"
        return (
            "汇总" if self.company_id is None else "人员明细",
            "" if self.company_id is None else str(self.company_id), self.company_name,
            "" if self.creator_id is None else str(self.creator_id), self.creator_name,
            TASK_TYPES[self.task_type], str(self.total), str(self.adopted), rate,
        )


def utc_boundary(value: date) -> datetime:
    return datetime.combine(value, time.min, HONG_KONG).astimezone(timezone.utc).replace(tzinfo=None)


def collect_statistics(
    db: Session, *, company_id: int | None = None, creator_id: int | None = None,
    start_date: date | None = None, end_date: date | None = None,
) -> list[StatisticsRow]:
    filters = [PodTask.task_type.in_(TASK_TYPES)]
    if company_id is not None:
        filters.append(PodTask.company_id == company_id)
    if creator_id is not None:
        filters.append(PodTask.created_by == creator_id)
    if start_date is not None:
        filters.append(PodTask.created_at >= utc_boundary(start_date))
    if end_date is not None:
        filters.append(PodTask.created_at < utc_boundary(end_date + timedelta(days=1)))

    # 先按任务聚合，再关联名称；不读取候选图片或关联素材，不会放大任务数量。
    grouped = select(
        PodTask.company_id, PodTask.created_by, PodTask.task_type,
        func.count(PodTask.id).label("total"),
        func.sum(case((func.length(PodTask.selected_result_url) > 0, 1), else_=0)).label("adopted"),
    ).where(*filters).group_by(PodTask.company_id, PodTask.created_by, PodTask.task_type).subquery()
    statement = select(
        grouped, Company.name.label("company_name"), User.name.label("creator_name"),
    ).outerjoin(Company, Company.id == grouped.c.company_id).outerjoin(User, User.id == grouped.c.created_by)

    details = [StatisticsRow(
        task_type=row.task_type, total=row.total, adopted=row.adopted,
        company_id=row.company_id, company_name=row.company_name or "历史公司信息缺失",
        creator_id=row.created_by, creator_name=row.creator_name or "历史人员信息缺失",
    ) for row in db.execute(statement)]
    type_order = {kind: index for index, kind in enumerate(TASK_TYPES)}
    details.sort(key=lambda row: (row.company_id, row.creator_id, type_order[row.task_type]))
    totals = {kind: [0, 0] for kind in TASK_TYPES}
    for row in details:
        totals[row.task_type][0] += row.total
        totals[row.task_type][1] += row.adopted
    return [StatisticsRow(kind, *counts) for kind, counts in totals.items()] + details


def display_width(value: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in value)


def write_report(rows: list[StatisticsRow], output: TextIO, output_format: str = "table") -> None:
    cells = [HEADERS, *(row.cells() for row in rows)]
    if output_format == "csv":
        csv.writer(output).writerows(cells)
        return
    # 名称中的换行和制表符仅在终端显示时替换，CSV 保留原值并正确引用。
    cells = [tuple(" ".join(cell.split()) for cell in row) for row in cells]
    widths = [max(display_width(row[index]) for row in cells) for index in range(len(HEADERS))]
    for index, row in enumerate(cells):
        output.write(" | ".join(cell + " " * (width - display_width(cell)) for cell, width in zip(row, widths)) + "\n")
        if index == 0:
            output.write("-+-".join("-" * width for width in widths) + "\n")


def parse_date(value: str) -> date:
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError
        result = date.fromisoformat(value)
        utc_boundary(result)
        return result
    except (ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError("日期须为有效的 YYYY-MM-DD，且可转换为 UTC") from exc


def positive_id(value: str) -> int:
    try:
        result = int(value)
        if result > 0:
            return result
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("ID 必须为正整数")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读统计图片任务：采用字段非空的任务数 / 全部任务数")
    parser.add_argument("--company-id", type=positive_id, help="仅统计指定公司，默认全部公司")
    parser.add_argument("--creator-id", type=positive_id, help="仅统计指定创建人")
    parser.add_argument("--start-date", type=parse_date, help="任务创建开始日期（香港时区，包含当天）")
    parser.add_argument("--end-date", type=parse_date, help="任务创建结束日期（香港时区，包含当天）")
    parser.add_argument("--format", choices=("table", "csv"), default="table", help="输出格式，默认中文终端表格")
    args = parser.parse_args(argv)
    if args.start_date and args.end_date and args.start_date > args.end_date:
        parser.error("开始日期不能晚于结束日期")
    if args.end_date == date.max:
        parser.error("结束日期不能为 9999-12-31，无法计算下一日边界")
    try:
        with SessionLocal() as db:
            rows = collect_statistics(
                db, company_id=args.company_id, creator_id=args.creator_id,
                start_date=args.start_date, end_date=args.end_date,
            )
    except SQLAlchemyError as exc:
        print(f"数据库查询失败，请检查数据库配置与连接（{type(exc).__name__}）", file=sys.stderr)
        return 1
    write_report(rows, sys.stdout, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
