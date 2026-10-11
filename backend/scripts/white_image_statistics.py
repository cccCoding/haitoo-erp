"""只读统计已登记白底图的大小及所属创作人，批量读取 R2 对象列表。"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import sys
from time import monotonic
from typing import TextIO

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import Company, ProductTemplate, User, UserTemplateWhiteImage
from app.storage import StorageError, r2_object_key
from scripts.r2_image_statistics import create_client, readable_size


HEADERS = ("白底图 ID", "白底图名称", "公司 ID", "公司名称", "创作人 ID", "创作人姓名",
           "模板 ID", "模板名称", "图片大小", "读取状态", "图片链接")


@dataclass
class WhiteImageRow:
    image_id: int
    name: str
    company_id: int
    company_name: str
    creator_id: int
    creator_name: str
    template_id: int
    template_name: str
    image_url: str
    size_bytes: int | None = None
    status: str = "待查询"

    def cells(self) -> tuple[str, ...]:
        return (str(self.image_id), self.name, str(self.company_id), self.company_name,
                str(self.creator_id), self.creator_name, str(self.template_id), self.template_name,
                readable_size(self.size_bytes) if self.size_bytes is not None else "—",
                self.status, self.image_url)


def load_records(
    db: Session, *, company_id: int | None = None, creator_id: int | None = None,
    template_id: int | None = None,
) -> list[WhiteImageRow]:
    image = UserTemplateWhiteImage
    statement = select(image, Company.name, User.name, ProductTemplate.name).outerjoin(
        Company, Company.id == image.company_id,
    ).outerjoin(User, User.id == image.user_id).outerjoin(ProductTemplate, ProductTemplate.id == image.template_id)
    for column, value in ((image.company_id, company_id), (image.user_id, creator_id), (image.template_id, template_id)):
        if value is not None:
            statement = statement.where(column == value)
    statement = statement.order_by(image.company_id, image.user_id, image.template_id, image.id)
    return [WhiteImageRow(
        image_id=item.id, name=item.name, company_id=item.company_id,
        company_name=company_name or "历史公司信息缺失", creator_id=item.user_id,
        creator_name=creator_name or "历史人员信息缺失", template_id=item.template_id,
        template_name=template_name or "历史模板信息缺失", image_url=item.image_url,
    ) for item, company_name, creator_name, template_name in db.execute(statement)]


def read_sizes(rows: list[WhiteImageRow], settings: Settings, *, progress: TextIO | None = None) -> None:
    if rows and not settings.r2_public_base_url:
        raise StorageError("未配置 R2_PUBLIC_BASE_URL，无法匹配白底图链接")
    targets: dict[int, dict[str, list[WhiteImageRow]]] = {}
    for row in rows:
        key = r2_object_key(row.image_url, settings)
        if key is None:
            row.status = "链接不属于当前 R2"
        elif not key.startswith(f"template-white/company/{row.company_id}/"):
            row.status = "白底图目录或公司不匹配"
        else:
            targets.setdefault(row.company_id, {}).setdefault(key, []).append(row)

    started_at = monotonic()
    total_keys = sum(len(keys) for keys in targets.values())
    matched_keys, page_count, scanned = 0, 0, 0
    if progress is not None:
        print(f"开始统计：{len(rows)} 条白底图记录、{total_keys} 个目标文件；按公司批量读取 R2 列表。",
              file=progress, flush=True)
    if targets:
        client = create_client(settings)
        for company_id, keys in sorted(targets.items()):
            pending = set(keys)
            pages = client.get_paginator("list_objects_v2").paginate(
                Bucket=settings.r2_bucket, Prefix=f"template-white/company/{company_id}/",
                PaginationConfig={"PageSize": 1000},
            )
            for page in pages:
                page_count += 1
                items = page.get("Contents", [])
                scanned += len(items)
                for item in items:
                    key = item["Key"]
                    if key not in pending:
                        continue
                    for row in keys[key]:
                        row.size_bytes = item["Size"]
                        row.status = "正常"
                    pending.remove(key)
                    matched_keys += 1
                if progress is not None:
                    print(f"已读取 {page_count} 页（公司 {company_id}）；扫描 {scanned} 个对象；"
                          f"已匹配 {matched_keys}/{total_keys} 个目标文件；耗时 {monotonic() - started_at:.1f} 秒。",
                          file=progress, flush=True)
                if not pending:
                    break
            for key in pending:
                for row in keys[key]:
                    row.status = "R2 对象不存在"
    if progress is not None:
        found = sum(row.size_bytes is not None for row in rows)
        print(f"统计完成：共 {len(rows)} 条记录，成功读取 {found} 条，无法读取 {len(rows) - found} 条；"
              f"耗时 {monotonic() - started_at:.1f} 秒。", file=progress, flush=True)


def write_report(rows: list[WhiteImageRow], output: TextIO, output_format: str) -> None:
    if output_format == "csv":
        writer = csv.writer(output)
        writer.writerow(HEADERS)
        writer.writerows(row.cells() for row in rows)
        return
    for cells in (HEADERS, *(row.cells() for row in rows)):
        output.write("\t".join(" ".join(cell.split()) for cell in cells) + "\n")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读统计每张已登记白底图的大小与所属创作人")
    parser.add_argument("--company-id", type=int, help="仅统计指定公司，默认全部公司")
    parser.add_argument("--creator-id", type=int, help="仅统计指定所属创作人")
    parser.add_argument("--template-id", type=int, help="仅统计指定产品模板")
    parser.add_argument("--format", choices=("table", "csv"), default="table", help="默认中文终端表格")
    parser.add_argument("--no-progress", action="store_true", help="关闭 stderr 进度")
    args = parser.parse_args(argv)
    for option in ("company_id", "creator_id", "template_id"):
        value = getattr(args, option)
        if value is not None and value <= 0:
            parser.error(f"--{option.replace('_', '-')} 必须为正整数")
    try:
        with SessionLocal() as db:
            rows = load_records(db, company_id=args.company_id, creator_id=args.creator_id, template_id=args.template_id)
        # 数据库连接在 R2 扫描前关闭，不长期持有数据库事务。
        read_sizes(rows, get_settings(), progress=None if args.no_progress else sys.stderr)
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
    write_report(rows, sys.stdout, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
