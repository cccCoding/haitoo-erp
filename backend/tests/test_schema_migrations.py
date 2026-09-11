import json
import unittest

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.db_migrate import upgrade_database
from app.schema_version import alembic_config, assert_schema_current, schema_heads


class SchemaMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_unmigrated_database_is_rejected_by_application_check(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "请先执行 python -m app.db_migrate"):
            assert_schema_current(self.engine)

    def test_baseline_migration_creates_schema_and_records_current_head(self) -> None:
        with self.engine.connect() as connection:
            command.upgrade(alembic_config(connection), "head")
            current, expected = schema_heads(connection)

        self.assertEqual(current, {"20260912_03"})
        self.assertEqual(current, expected)
        self.assertIn("users", inspect(self.engine).get_table_names())
        self.assertIn("alembic_version", inspect(self.engine).get_table_names())
        assert_schema_current(self.engine)

    def test_running_upgrade_again_is_a_no_op(self) -> None:
        with self.engine.connect() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "head")
            first_tables = set(inspect(connection).get_table_names())
            command.upgrade(config, "head")
            second_tables = set(inspect(connection).get_table_names())

        self.assertEqual(first_tables, second_tables)
        with self.engine.connect() as connection:
            self.assertEqual(schema_heads(connection)[0], {"20260912_03"})

    def test_existing_unversioned_database_requires_explicit_adoption(self) -> None:
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            with self.assertRaisesRegex(RuntimeError, "--adopt-legacy"):
                upgrade_database(connection)

            upgrade_database(connection, adopt_legacy=True)
            current, expected = schema_heads(connection)

        self.assertEqual(current, {"20260912_03"})
        self.assertEqual(current, expected)

    def test_main_image_column_is_migrated_into_ordered_images_then_removed(self) -> None:
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "20260911_02")
            connection.execute(text("""
                INSERT INTO product_drafts (
                    id, company_id, title, status, image_urls, sku_items, carousel_items,
                    export_count, created_at, updated_at, main_image_url
                ) VALUES (
                    1, 1, 'Legacy draft', 'pending_publish', '[]', :sku_items, '[]',
                    0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :main_image_url
                )
            """), {
                "sku_items": json.dumps([{"sku": "SKU1", "image_url": "https://img.example/sku.png"}]),
                "main_image_url": "https://img.example/main.png",
            })
            command.upgrade(config, "head")
            row = connection.execute(text(
                "SELECT carousel_items, image_urls FROM product_drafts WHERE id = 1"
            )).mappings().one()

        self.assertNotIn("main_image_url", {column["name"] for column in inspect(self.engine).get_columns("product_drafts")})
        items = json.loads(row["carousel_items"])
        self.assertEqual([item["image_url"] for item in items], [
            "https://img.example/main.png",
            "https://img.example/sku.png",
        ])
        self.assertEqual(json.loads(row["image_urls"]), [
            "https://img.example/main.png",
            "https://img.example/sku.png",
        ])


if __name__ == "__main__":
    unittest.main()
