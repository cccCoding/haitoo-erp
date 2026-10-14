"""内部草稿最终导出检查：只报告问题图片，不自动替换用户选图。"""
from __future__ import annotations

import asyncio

from fastapi import HTTPException
from sqlalchemy import select, update

from .models import SupplyImageHealth
from .supply_common import digest, lock_company, now
from .supply_images import check_image


EXPORT_CHECK_TIMEOUT = 240
EXPORT_CHECK_CONCURRENCY = 4
EXPORT_CHECK_ATTEMPTS = 3
RETRY_DELAYS = (2, 5)


def _export_urls(products: list[dict]) -> list[str]:
    urls = []
    for product in products:
        urls.extend(product.get("image_urls") or [])
        urls.extend(item.get("image_url") for item in product.get("sku_images") or [])
        if product.get("size_chart_url"):
            urls.append(product["size_chart_url"])
    return list(dict.fromkeys(str(url).strip() for url in urls if url and str(url).strip()))


def _begin_batch(db, company_id: int, urls: list[str]) -> dict[str, int]:
    """与货盘及手动检查共用公司锁，在一个短事务内保留所有检查序号。"""
    lock_company(db, company_id)
    hashes = [digest(url) for url in urls]
    existing = {}
    for offset in range(0, len(hashes), 500):
        records = db.scalars(select(SupplyImageHealth).where(
            SupplyImageHealth.company_id == company_id,
            SupplyImageHealth.url_hash.in_(hashes[offset:offset + 500]))).all()
        existing.update({record.url_hash: record for record in records})
    sequences = {}
    for url, url_hash in zip(urls, hashes):
        record = existing.get(url_hash)
        if record is None:
            record = SupplyImageHealth(company_id=company_id, url_hash=url_hash, url=url, status="unchecked", check_sequence=0)
            db.add(record)
            existing[url_hash] = record
        if record.url != url:
            db.rollback()
            raise ValueError("图片地址摘要冲突")
        record.check_sequence += 1
        sequences[url] = record.check_sequence
    db.commit()  # 网络请求之前释放数据库事务和锁。
    return sequences


async def _check_batch(urls: list[str]) -> dict[str, dict]:
    semaphore = asyncio.Semaphore(EXPORT_CHECK_CONCURRENCY)
    results = {}

    async def probe(url):
        async with semaphore:
            for attempt in range(EXPORT_CHECK_ATTEMPTS):
                try:
                    result = await check_image(url)
                    if not isinstance(result, dict) or result.get("status") not in {"available", "invalid", "check_failed"}:
                        raise ValueError("图片检查结果无效")
                except Exception:
                    result = {"status": "check_failed", "reason": "图片检查服务暂不可用"}
                if result["status"] != "check_failed" or attempt + 1 == EXPORT_CHECK_ATTEMPTS:
                    results[url] = result
                    return
                await asyncio.sleep(RETRY_DELAYS[attempt])

    try:
        async with asyncio.timeout(EXPORT_CHECK_TIMEOUT):
            await asyncio.gather(*(probe(url) for url in urls))
    except TimeoutError:
        pass
    for url in urls:
        results.setdefault(url, {"status": "check_failed", "reason": "导出前图片检查超过时间预算，请减少草稿数量后重试"})
    return results


def validate_export_images(db, company_id: int, products: list[dict]) -> None:
    """仅从同步 FastAPI 导出函数调用；成功后才允许写表和增加导出计数。"""
    urls = _export_urls(products)
    if not urls:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("validate_export_images 必须从同步导出函数调用")
    sequences = _begin_batch(db, company_id, urls)
    results = asyncio.run(_check_batch(urls))
    checked_at = now()
    for url in urls:
        result = results[url]
        db.execute(update(SupplyImageHealth).where(
            SupplyImageHealth.company_id == company_id,
            SupplyImageHealth.url_hash == digest(url),
            SupplyImageHealth.url == url,
            SupplyImageHealth.check_sequence == sequences[url],
        ).values(status=result["status"], reason=str(result.get("reason") or "")[:500], checked_at=checked_at))
    db.commit()
    bad = [url for url in urls if results[url]["status"] != "available"]
    if bad:
        details = "\n".join(f"{url}（{results[url].get('reason') or '图片不可用'}）" for url in bad)
        raise HTTPException(400, f"导出前发现不可用图片，请修复后重试：\n{details}")
