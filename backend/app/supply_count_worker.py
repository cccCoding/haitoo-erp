"""每五分钟发布货盘素材数量快照，模板列表只读取汇总。"""
import logging
import time
from datetime import datetime

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.orm import Session

from .database import engine
from .models import (Company, MaterialAsset, ProductTemplate, SupplyJob,
                     SupplyJobMaterial, SupplyTemplateCount, SupplyUserExhaustedCount)
from .supply_quota import SKU_USE_LIMIT

logger = logging.getLogger(__name__)
REFRESH_SECONDS = 300
LOCK_NAME = "haitoo_supply_template_counts"


def refresh_company(db, company_id):
    """调用方提供同一读取快照和事务，两张汇总表一起替换。"""
    started_at = datetime.utcnow()
    # 生成快照会 strip SKU，历史额度也保存去空白后的 SKU。
    if db.get_bind().dialect.name == "sqlite":
        whitespace = (" \t\n\r\v\f\x1c\x1d\x1e\x1f\x85\xa0\u1680"
                      "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
                      "\u2028\u2029\u202f\u205f\u3000")
        sku = func.trim(MaterialAsset.sku, whitespace)
    else:
        sku = func.regexp_replace(MaterialAsset.sku, r"^\s+|\s+$", "")
    eligible = select(MaterialAsset.template_id, sku.label("sku")).join(
        ProductTemplate, ProductTemplate.id == MaterialAsset.template_id).where(
            MaterialAsset.company_id == company_id, ProductTemplate.company_id == company_id,
            MaterialAsset.supply_listed.is_(True),
            MaterialAsset.sku.regexp_match(r"\S"), MaterialAsset.url.regexp_match(r"\S")).subquery()
    totals = db.execute(select(ProductTemplate.id, func.count(eligible.c.template_id)).outerjoin(
        eligible, eligible.c.template_id == ProductTemplate.id).where(
            ProductTemplate.company_id == company_id).group_by(ProductTemplate.id)).all()

    # 与 sku_use_counts 一致，按最终成功链接去重，永久使用历史 SKU。
    links = select(SupplyJob.user_id, SupplyJobMaterial.sku,
        SupplyJobMaterial.job_id, SupplyJobMaterial.link_index).join(
            SupplyJob, SupplyJob.id == SupplyJobMaterial.job_id).where(
                SupplyJob.company_id == company_id, SupplyJobMaterial.company_id == company_id,
                SupplyJob.state == "completed", SupplyJobMaterial.successful.is_(True),
                SupplyJobMaterial.link_index >= 0).distinct().subquery()
    exhausted = select(links.c.user_id, links.c.sku).group_by(
        links.c.user_id, links.c.sku).having(func.count() >= SKU_USE_LIMIT).subquery()
    counts = db.execute(select(exhausted.c.user_id, eligible.c.template_id, func.count()).join(
        eligible, eligible.c.sku == exhausted.c.sku).group_by(
            exhausted.c.user_id, eligible.c.template_id)).all()

    for model in (SupplyUserExhaustedCount, SupplyTemplateCount):
        db.execute(delete(model).where(model.company_id == company_id))
    if totals:
        db.execute(insert(SupplyTemplateCount), [dict(company_id=company_id, template_id=template_id,
            material_count=count, updated_at=started_at) for template_id, count in totals])
    # 分块写入，避免大公司账号较多时生成过大的单次请求。
    for offset in range(0, len(counts), 1000):
        db.execute(insert(SupplyUserExhaustedCount), [dict(company_id=company_id,
            user_id=user_id, template_id=template_id, exhausted_count=count)
            for user_id, template_id, count in counts[offset:offset + 1000]])


def run_cycle(bind=engine):
    started = time.monotonic()
    with bind.connect() as connection:
        mysql = connection.dialect.name in ("mysql", "mariadb")
        if mysql:
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
            acquired = connection.scalar(text("SELECT GET_LOCK(:name, 0)"), {"name": LOCK_NAME})
            connection.commit()
            if acquired != 1:
                return
        try:
            with Session(bind=connection) as db:
                companies = db.scalars(select(Company.id)).all()
                db.rollback()
                for company_id in companies:
                    company_started = time.monotonic()
                    try:
                        with db.begin():
                            last_refresh = db.scalar(select(func.min(SupplyTemplateCount.updated_at)).where(
                                SupplyTemplateCount.company_id == company_id))
                            if last_refresh and (datetime.utcnow() - last_refresh).total_seconds() < REFRESH_SECONDS:
                                continue
                            refresh_company(db, company_id)
                        elapsed = time.monotonic() - company_started
                        logger.info("货盘素材统计完成 company_id=%s duration=%.2fs", company_id, elapsed)
                        if elapsed > REFRESH_SECONDS:
                            logger.warning("货盘素材统计耗时超过五分钟 company_id=%s", company_id)
                    except Exception:
                        logger.exception("货盘素材统计失败，保留上一轮快照 company_id=%s", company_id)
        finally:
            if mysql:
                connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": LOCK_NAME})
                connection.commit()
    elapsed = time.monotonic() - started
    if elapsed > REFRESH_SECONDS:
        logger.warning("货盘素材统计整轮耗时超过五分钟 duration=%.2fs", elapsed)


def main():
    from .logging_config import configure_logging
    from .schema_version import assert_schema_current
    configure_logging()
    assert_schema_current(engine)
    while True:
        try:
            run_cycle()
        except Exception:
            logger.exception("货盘素材统计轮询失败")
        time.sleep(30)


if __name__ == "__main__":
    main()
