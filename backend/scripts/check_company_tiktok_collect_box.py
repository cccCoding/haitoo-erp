"""只读检查指定公司的妙手 TikTok 采集箱列表接口。

示例：
    DATABASE_URL='mysql+pymysql://…' python scripts/check_company_tiktok_collect_box.py --company-id 3
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 允许通过 `python scripts/check_company_tiktok_collect_box.py` 直接执行。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.main import miaoshou_post
from app.models import Company


TIKTOK_COLLECT_BOX_LIST_PATH = "/open/v1/product/collect_box/tiktok/collect_box/search_collect_box_detail_list"


async def check(company_id: int, page_size: int) -> int:
    """仅调用第三方读取接口；不提交或修改任何本地数据。"""
    with SessionLocal() as db:
        company = db.get(Company, company_id)
        if not company:
            print(json.dumps({"error": f"公司 {company_id} 不存在"}, ensure_ascii=False), file=sys.stderr)
            return 2
        if not company.miaoshou_app_id or not company.miaoshou_secret_encrypted:
            print(json.dumps({"error": f"公司 {company_id} 未配置妙手 API 凭据"}, ensure_ascii=False), file=sys.stderr)
            return 2
        try:
            response = await miaoshou_post(company, TIKTOK_COLLECT_BOX_LIST_PATH, {
                "pageNo": 1,
                "pageSize": page_size,
                "filter": {},
            })
        except Exception as exc:
            print(json.dumps({"company_id": company_id, "path": TIKTOK_COLLECT_BOX_LIST_PATH, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 1
    print(json.dumps({"company_id": company_id, "path": TIKTOK_COLLECT_BOX_LIST_PATH, "response": response}, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="只读检查妙手 TikTok 采集箱列表接口")
    parser.add_argument("--company-id", type=int, default=3)
    parser.add_argument("--page-size", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.page_size <= 500:
        parser.error("--page-size 必须介于 1 和 500 之间")
    raise SystemExit(asyncio.run(check(args.company_id, args.page_size)))


if __name__ == "__main__":
    main()
