"""只读统计图片重复引用和 R2 重复对象候选，不下载或删除图片。"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.database import SessionLocal
from app.models import Company, ImageAddress, ImageFile, MaterialAsset
from app.schema_version import assert_schema_current
from app.storage import StorageError, r2_object_key
from scripts.r2_image_statistics import create_client, readable_size


LABELS = {
    "files": "公司内唯一图片数", "file_bytes": "登记文件大小",
    "materials": "素材记录数", "unlinked_materials": "未关联素材数",
    "duplicate_material_groups": "相同图片的素材组数", "extra_materials": "额外素材记录数",
    "candidate_objects": "重复 R2 对象候选数", "candidate_bytes": "候选重复空间",
    "missing_candidates": "列表核对已不存在的候选数",
    "changed_candidates": "列表核对大小已变化的候选数",
    "invalid_canonical_files": "列表核对正式对象缺失或大小变化数",
}


def collect(db, settings, *, company_id=None, object_sizes=None):
    # 所有公司的正式对象均受保护；筛选公司时也不能把其他公司的正式对象算作浪费。
    files = db.execute(select(ImageFile.id, ImageFile.company_id, ImageFile.sha256,
        ImageFile.object_key, ImageFile.size_bytes)).all()
    protected = {row.object_key for row in files}
    selected = {row.id: row for row in files if company_id is None or row.company_id == company_id}
    if selected and not settings.r2_public_base_url:
        raise StorageError("未配置 R2_PUBLIC_BASE_URL，无法识别历史 R2 地址")
    stats = defaultdict(Counter)
    keys = {identity: {row.object_key} for identity, row in selected.items()}
    addresses = select(ImageAddress.image_file_id, ImageAddress.company_id, ImageAddress.url)
    if company_id is not None:
        addresses = addresses.where(ImageAddress.company_id == company_id)
    for identity, company, url in db.execute(addresses).yield_per(1000):
        row = selected.get(identity)
        if row is None or row.company_id != company:
            continue
        key = r2_object_key(url, settings)
        if key and not key.startswith("image-upload-tmp/"):
            keys[identity].add(key)  # 同一对象的多个 URL、重复引用只算一次。
    owners = defaultdict(set)
    for identity, values in keys.items():
        for key in values:
            owners[key].add(identity)
    material_query = select(MaterialAsset.company_id, MaterialAsset.image_file_id,
        func.count()).group_by(MaterialAsset.company_id, MaterialAsset.image_file_id)
    if company_id is not None:
        material_query = material_query.where(MaterialAsset.company_id == company_id)
    duplicate_groups = []
    for company, identity, count in db.execute(material_query):
        values = stats[company]
        values["materials"] += count
        row = selected.get(identity)
        if row is None or row.company_id != company:
            values["unlinked_materials"] += count
        elif count > 1:
            values["duplicate_material_groups"] += 1
            values["extra_materials"] += count - 1
            duplicate_groups.append({"company_id": company, "image_file_id": identity,
                "sha256": row.sha256, "material_count": count})
    candidates = []
    for identity, row in selected.items():
        values = stats[row.company_id]
        values["files"] += 1
        values["file_bytes"] += row.size_bytes
        canonical_valid = object_sizes is None or object_sizes.get(row.object_key) == row.size_bytes
        if not canonical_valid:
            values["invalid_canonical_files"] += 1
        for key in sorted(keys[identity] - protected):
            # 地址映射跨公司或对应多个内容时，不能认定为本公司的重复实体对象。
            if len(owners[key]) != 1 or f"/company/{row.company_id}/" not in f"/{key}":
                continue
            if object_sizes is not None:
                if key not in object_sizes:
                    values["missing_candidates"] += 1
                    continue
                if object_sizes[key] != row.size_bytes:
                    values["changed_candidates"] += 1
                    continue
            if not canonical_valid:
                continue
            values["candidate_objects"] += 1
            values["candidate_bytes"] += row.size_bytes
            candidates.append({"company_id": row.company_id, "image_file_id": identity,
                "sha256": row.sha256, "object_key": key, "canonical_key": row.object_key,
                "size_bytes": row.size_bytes})
    names = dict(db.execute(select(Company.id, Company.name)).all())
    total = Counter()
    companies = []
    for company, values in sorted(stats.items()):
        total.update(values)
        companies.append({"company_id": company, "company_name": names.get(company, "历史公司信息缺失"),
            **{key: values[key] for key in LABELS}})
    return {"mode": "R2对象存在和大小已核对，内容依据回填哈希" if object_sizes is not None else "仅依据数据库估算，未核对R2对象是否仍存在",
        "totals": {key: total[key] for key in LABELS}, "companies": companies,
        "duplicate_material_groups": duplicate_groups, "r2_candidates": candidates}


def list_sizes(settings):
    sizes = {}
    pages = create_client(settings).get_paginator("list_objects_v2").paginate(
        Bucket=settings.r2_bucket, PaginationConfig={"PageSize": 1000})
    for page_number, page in enumerate(pages, 1):
        sizes.update((item["Key"], item["Size"]) for item in page.get("Contents", []))
        print(f"R2 列表核对：第 {page_number} 页，已扫描 {len(sizes)} 个对象", file=sys.stderr, flush=True)
    return sizes


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-id", type=int, help="仅统计指定公司；默认按公司隔离汇总全部公司")
    parser.add_argument("--verify-r2", action="store_true", help="只读取对象列表核对存在和大小，不下载图片")
    parser.add_argument("--format", choices=("table", "json"), default="table")
    args = parser.parse_args(argv)
    if args.company_id is not None and args.company_id < 1:
        parser.error("公司 ID 必须为正整数")
    settings = get_settings()
    try:
        with SessionLocal() as db:
            assert_schema_current(db.get_bind())
        sizes = list_sizes(settings) if args.verify_r2 else None
        with SessionLocal() as db:
            report = collect(db, settings, company_id=args.company_id, object_sizes=sizes)
    except (StorageError, SQLAlchemyError, RuntimeError, BotoCoreError, ClientError) as exc:
        print(f"统计失败：{exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"统计口径：{report['mode']}")
        print("按公司隔离统计；重复素材引用不等于重复存储。候选不是可直接删除清单，未索引图片和孤立对象未纳入内容去重。")
        for values in [*(report["companies"]), {"company_name": "合计", **report["totals"]}]:
            print(f"\n{values['company_name']}" + (f"（公司 {values['company_id']}）" if "company_id" in values else ""))
            for key, label in LABELS.items():
                value = readable_size(values[key]) if key.endswith("bytes") else values[key]
                print(f"{label}\t{value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
