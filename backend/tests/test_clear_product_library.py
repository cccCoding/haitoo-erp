import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from io import StringIO
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Company, ProductTemplate
from scripts.clear_product_library import TABLES, main


class ClearProductLibraryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.addCleanup(self.engine.dispose)
        with self.sessions.begin() as db:
            db.add(ProductTemplate(id=1, company_id=1, name="保留模板"))
            for company_id in (1, 2):
                db.add(Company(id=company_id, name=f"公司{company_id}"))
                values = {
                    "product_library_sources": dict(platform="tiktok", site="MY", shop_name="店铺"),
                    "product_library_products": dict(source_id=company_id, external_product_id="product", sku="sku"),
                    "product_library_orders": dict(source_id=company_id, order_number="order", ordered_at=datetime.now()),
                    "product_library_order_products": dict(order_id=company_id, product_id=company_id, quantity=2),
                    "product_library_order_sku_quantities": dict(order_product_id=company_id, platform_sku="sku-M", quantity=2),
                    "product_library_snapshot_order_products": dict(snapshot_id=company_id, order_id=company_id,
                        product_id=company_id, order_number="order", ordered_at=datetime.now(), quantity=2),
                    "product_library_daily_snapshots": dict(snapshot_date=date.today(), is_complete=True),
                    "product_library_daily_snapshot_items": dict(snapshot_id=company_id, product_id=company_id,
                        count_7=2, count_15=2, count_30=2),
                    "product_library_ranking_tasks": dict(task_id=f"task-{company_id}", status="completed",
                        snapshot_date=date.today(), requested_at=datetime.now()),
                }
                for model in reversed(TABLES):
                    row = values[model.__tablename__].copy()
                    if "company_id" in model.__table__.c:
                        row["company_id"] = company_id
                    if "id" in model.__table__.c:
                        row["id"] = company_id
                    db.execute(model.__table__.insert().values(**row))

    def counts(self, db):
        return [db.scalar(select(func.count()).select_from(model)) for model in TABLES]

    def test_global_cleanup_includes_orphans_and_preserves_other_tables(self):
        with self.sessions.begin() as db:
            table = Base.metadata.tables["product_library_order_sku_quantities"]
            db.execute(table.insert().values(order_product_id=999, platform_sku="orphan", quantity=1))
        with patch("scripts.clear_product_library.SessionLocal", self.sessions), redirect_stdout(StringIO()):
            main()
        with self.sessions() as db:
            self.assertEqual(self.counts(db), [0] * 9)
            self.assertEqual(db.scalar(select(func.count()).select_from(Company)), 2)
            self.assertIsNotNone(db.get(ProductTemplate, 1))

    def test_failure_rolls_back_every_table(self):
        original_execute = Session.execute

        def fail_on_products(db, statement, *args, **kwargs):
            if getattr(statement, "is_delete", False) and statement.table.name == "product_library_products":
                raise ValueError("模拟删除失败")
            return original_execute(db, statement, *args, **kwargs)

        with patch("scripts.clear_product_library.SessionLocal", self.sessions), \
                patch.object(Session, "execute", fail_on_products), \
                self.assertRaisesRegex(ValueError, "模拟删除失败"):
            main()
        with self.sessions() as db:
            self.assertEqual(self.counts(db), [2] * 9)



if __name__ == "__main__":
    unittest.main()
