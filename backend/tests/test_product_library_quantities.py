"""数量、SKU 汇总、快照及重置迁移的业务回归。"""
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest import TestCase

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import MetaData, create_engine, func, select

from app import main, product_library_rankings
from app.database import Base
from app.models import (Company, MaterialAsset, OperatorGroup, ProductDraft, Shop, ProductLibraryOrder,
    ProductLibraryOrderProduct, ProductLibraryOrderSkuQuantity, ProductLibraryProduct,
    ProductLibrarySource, ProductLibrarySnapshotOrderProduct, ProductTemplate, Role, User)
from app.schemas import ProductLibraryBatchTemplateInput
import test_product_library as fixtures
HEADERS, row, xlsx = fixtures.HEADERS, fixtures.row, fixtures.xlsx


class ProductLibraryQuantityTests(TestCase):
    setUp = fixtures.ProductLibraryTests.setUp
    tearDown = fixtures.ProductLibraryTests.tearDown
    import_bytes = fixtures.ProductLibraryTests.import_bytes
    list_items = fixtures.ProductLibraryTests.list_items

    def test_sizes_sum_and_partial_reimport_replaces_without_accumulating(self):
        self.import_bytes(xlsx([row(sku="ABC-S", quantity=2), row(sku="ABC-M", quantity=3)]))
        self.assertEqual((self.list_items()["items"][0]["order_count"], self.list_items()["items"][0]["sales_quantity"]), (1, 5))
        correction = xlsx([row(sku="ABC-S", quantity=4)])
        self.import_bytes(correction)
        self.import_bytes(correction)
        item = self.list_items()["items"][0]
        self.assertEqual((item["order_count"], item["sales_quantity"]), (1, 7))
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ProductLibraryOrderSkuQuantity)), 2)

    def test_duplicate_rows_deduplicate_and_conflicts_roll_back(self):
        self.import_bytes(xlsx([row(quantity=2), row(quantity=2)]))
        self.assertEqual(self.list_items()["items"][0]["sales_quantity"], 2)
        with self.assertRaisesRegex(HTTPException, "数量冲突"):
            self.import_bytes(xlsx([row(shop="new"), row(quantity=4), row(quantity=5)]))
        self.assertEqual(self.list_items()["items"][0]["sales_quantity"], 2)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ProductLibrarySource)), 1)

    def test_quantity_required_and_validated(self):
        for quantity in (None, "", 0, -1, 1.5, True, "abc", 2147483648):
            with self.subTest(quantity=quantity), self.assertRaisesRegex(HTTPException, "数量"):
                self.import_bytes(xlsx([row(quantity=quantity)]))
        with self.assertRaisesRegex(HTTPException, "缺少必需列：数量"):
            self.import_bytes(xlsx([row()], headers=[name for name in HEADERS if name != "数量"]))
        self.assertEqual(self.list_items()["total"], 0)

    def test_sku_aggregates_product_ids_and_sources_with_distinct_orders(self):
        self.import_bytes(xlsx([row(sku="ABC-S", quantity=2, product_id="p1"),
            row(sku="ABC-M", quantity=3, product_id="p2"),
            row(sku="ABC-S", quantity=4, product_id="p1", shop="second")]))
        item = self.list_items()["items"][0]
        self.assertEqual((self.list_items()["total"], item["order_count"], item["sales_quantity"]), (1, 2, 9))
        self.assertEqual(len(item["shop_data"]), 3)
        self.assertEqual(sum(shop["sales_quantity"] for shop in item["shop_data"]), 9)
        with self.sessions() as db:
            ids = db.scalars(select(ProductLibrarySource.id).order_by(ProductLibrarySource.id)).all()
            details = main.list_product_library_orders(item["id"], page=1, source_ids=ids, user=db.get(User, 1), db=db)
            self.assertEqual((details["total"], details["order_count"]), (3, 2))
            self.assertEqual(sum(detail["quantity"] for detail in details["items"]), 9)
        filtered = self.list_items(source_ids=[ids[0]])["items"][0]
        self.assertEqual((filtered["order_count"], filtered["sales_quantity"]), (1, 5))

    def test_sales_sort_before_pagination(self):
        self.import_bytes(xlsx([row(sku="ABC-S", quantity=10),
            row(sku="DEF-S", order="o2", quantity=1), row(sku="DEF-S", order="o3", quantity=1)]))
        with self.sessions() as db:
            result = main.list_product_library(page=1, page_size=1, template_id=None, user=db.get(User, 1), db=db)
        self.assertEqual((result["total"], result["items"][0]["sku"]), (2, "ABC"))
        self.assertEqual(result["items"][0]["order_count"], 1)

    def test_snapshot_sales_tiers_filters_and_detail_freeze(self):
        self.import_bytes(xlsx([row(sku="ABC-S", quantity=40, product_id="p1"),
            row(sku="ABC-M", quantity=40, product_id="p2", shop="second"),
            row(sku="OLD-S", quantity=100, order="old", ordered_at="2026-09-20 10:00:00"),
            row(sku="TODAY-S", quantity=100, order="today", ordered_at="2026-09-30 10:00:00")]))
        with self.sessions() as db:
            product_library_rankings.create_daily_snapshot(db, 1, date(2026, 9, 30))
            user=db.get(User, 1)
            ids=db.scalars(select(ProductLibrarySource.id).order_by(ProductLibrarySource.id)).all()
            hot=main.list_product_library_rankings(category="hot", page=1, page_size=20, source_ids=ids, user=user, db=db)
            item=hot["items"][0]
            self.assertEqual((item["sku"], item["order_count"], item["sales_quantity"]), ("ABC", 2, 80))
            potential=main.list_product_library_rankings(category="potential", page=1, page_size=20, source_ids=[ids[0]], user=user, db=db)
            self.assertEqual(potential["items"][0]["sales_quantity"], 40)
            self.assertEqual(main.list_product_library_rankings(category="hot", page=1, page_size=20, source_ids=[ids[0]], user=user, db=db)["total"], 0)
            top15=main.list_product_library_rankings(category="top15", page=1, page_size=50, user=user, db=db)
            self.assertEqual([item["sku"] for item in top15["items"]], ["OLD", "ABC"])
        self.import_bytes(xlsx([row(sku="ABC-S", quantity=2, product_id="p1")]))
        with self.sessions() as db:
            details=main.list_product_library_orders(item["id"], page=1, source_ids=ids, category="hot",
                snapshot_date="2026-09-30", user=db.get(User, 1), db=db)
            self.assertEqual(sum(detail["quantity"] for detail in details["items"]), 80)
            self.assertEqual(details["order_count"], 2)
            product_library_rankings.refresh_company_snapshot(db, 1, snapshot_date=date(2026, 9, 30))
            top=main.list_product_library_rankings(category="top7", page=1, page_size=50, user=db.get(User, 1), db=db)
            self.assertEqual(top["items"][0]["sales_quantity"], 42)
            self.assertEqual(db.scalar(select(func.count()).select_from(ProductLibrarySnapshotOrderProduct)), 3)

    def test_same_sku_permissions_and_selected_sources(self):
        self.import_bytes(xlsx([row(sku="ABC-S", quantity=40),
            row(sku="ABC-S", quantity=90, shop="second"), row(sku="ABC-S", quantity=150, shop="third")]))
        with self.sessions() as db:
            db.add(OperatorGroup(id=1, company_id=1, name="G", leader_user_id=3))
            db.add_all([User(id=3, company_id=1, email="leader@example.com", name="Leader", password_hash="x", role=Role.TEAM_LEADER, group_id=1),
                User(id=4, company_id=1, email="member@example.com", name="Member", password_hash="x", role=Role.MEMBER, group_id=1)])
            sources=db.scalars(select(ProductLibrarySource).order_by(ProductLibrarySource.id)).all()
            sources[0].assigned_user_id=3; sources[1].assigned_user_id=4
            ids=[source.id for source in sources]
            db.commit()
            product_library_rankings.create_daily_snapshot(db, 1, date(2026, 9, 30))
            for user_id, visible, sales in ((1, 3, 280), (3, 2, 130), (4, 1, 90)):
                user=db.get(User, user_id)
                self.assertEqual(len(main.product_library_filters(user=user, db=db)["shops"]), visible)
                result=main.list_product_library_rankings(category="top7", page=1, page_size=50, source_ids=ids, user=user, db=db)
                self.assertEqual(result["items"][0]["sales_quantity"], sales)
                self.assertEqual(len(result["items"][0]["shop_data"]), visible)
                detail=main.list_product_library_orders(result["items"][0]["id"], page=1, source_ids=ids,
                    category="top7", snapshot_date="2026-09-30", user=user, db=db)
                self.assertEqual(sum(row["quantity"] for row in detail["items"]), sales)
            self.assertEqual(main.list_product_library_rankings(category="top7",page=1,page_size=50,source_ids=[ids[2]],user=db.get(User,4),db=db)["total"],0)

    def test_template_assignment_updates_all_company_sku_records(self):
        self.import_bytes(xlsx([row(sku="ABC-S"),row(sku="ABC-M",shop="second")]))
        item=self.list_items()["items"][0]
        with self.sessions() as db:
            main.set_product_library_templates(ProductLibraryBatchTemplateInput(product_ids=[item["id"]],template_id=1), user=db.get(User,1),db=db)
            self.assertEqual(db.scalars(select(ProductLibraryProduct.template_id)).all(),[1,1])

    def test_new_source_inherits_company_sku_template(self):
        self.import_bytes(xlsx([row()]))
        item=self.list_items()["items"][0]
        with self.sessions() as db:
            main.set_product_library_templates(ProductLibraryBatchTemplateInput(product_ids=[item["id"]],template_id=2),user=db.get(User,1),db=db)
        self.import_bytes(xlsx([row(shop="second")]))
        with self.sessions() as db:
            self.assertEqual(db.scalars(select(ProductLibraryProduct.template_id)).all(),[2,2])



class ProductLibraryResetMigrationTests(TestCase):
    def test_upgrade_clears_only_product_library_and_supports_downgrade(self):
        engine=create_engine("sqlite://")
        metadata=MetaData()
        for table in Base.metadata.sorted_tables:
            if table.name not in ("product_library_order_sku_quantities","product_library_snapshot_order_products"):
                table.to_metadata(metadata)
        metadata.tables["product_library_order_products"]._columns.remove(metadata.tables["product_library_order_products"].c.quantity)
        metadata.create_all(engine)
        with engine.begin() as connection:
            # 每张旧产品库表插入一个最小记录，另留独立业务数据验证清空边界。
            connection.execute(metadata.tables["companies"].insert(), [{"id":1,"name":"Keep"},{"id":2,"name":"Keep second company"}])
            connection.execute(metadata.tables["product_templates"].insert(), {"id":1,"company_id":1,"name":"Keep"})
            for model, values in ((MaterialAsset, {"id":1,"company_id":1,"url":"https://example.com/a.jpg","name":"Keep","claimed_by":1}),
                (ProductDraft, {"id":1,"company_id":1,"template_id":1,"title":"Keep"}),
                (Shop, {"id":1,"company_id":1,"name":"Keep","region":"MY"})):
                connection.execute(metadata.tables[model.__tablename__].insert(),values)
            for name, table in metadata.tables.items():
                if not name.startswith("product_library_"):
                    continue
                values={}
                from datetime import datetime
                from sqlalchemy import Boolean, Date, DateTime, Integer
                for column in table.columns:
                    if not column.nullable and column.default is None and column.server_default is None:
                        if isinstance(column.type,DateTime): values[column.name]=datetime(2026,9,30)
                        elif isinstance(column.type,Date): values[column.name]=date(2026,9,30)
                        elif isinstance(column.type,Boolean): values[column.name]=True
                        elif isinstance(column.type,Integer): values[column.name]=1
                        else: values[column.name]="test"
                connection.execute(table.insert(),values)
                second = dict(values)
                for key in ("id", "company_id", "source_id", "order_id", "product_id", "snapshot_id"):
                    if key in table.c:
                        second[key] = 2
                if "task_id" in second:
                    second["task_id"] = "second-task"
                connection.execute(table.insert(), second)
            path=Path(__file__).parents[1]/"migrations/versions/20261005_25_product_library_quantities.py"
            spec=spec_from_file_location("quantity_migration",path);migration=module_from_spec(spec);spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                for name,table in metadata.tables.items():
                    if name.startswith("product_library_"):
                        self.assertEqual(connection.scalar(select(func.count()).select_from(table)),0,name)
                self.assertEqual(connection.scalar(select(func.count()).select_from(metadata.tables["companies"])),2)
                self.assertEqual(connection.scalar(select(func.count()).select_from(metadata.tables["product_templates"])),1)
                for model in (MaterialAsset,ProductDraft,Shop):
                    self.assertEqual(connection.scalar(select(func.count()).select_from(metadata.tables[model.__tablename__])),1)
                migration.downgrade()
        engine.dispose()
