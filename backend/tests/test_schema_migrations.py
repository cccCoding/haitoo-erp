import json
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

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

    def test_mysql_hub_xlsx_migration_emits_mediumblob_not_blob(self):
        for dialect in ("mysql", "mariadb"):
            output = StringIO()
            config = alembic_config()
            config.output_buffer = output
            with patch("app.config.get_settings", return_value=SimpleNamespace(database_url=f"{dialect}+pymysql://test@localhost/test")):
                command.upgrade(config, "20261007_28:20261007_29", sql=True)
            self.assertIn("ALTER TABLE hub_upload_tasks MODIFY export_blob MEDIUMBLOB NOT NULL", output.getvalue())

    def test_mysql_r2_migration_retains_nullable_legacy_blob(self):
        for dialect in ("mysql", "mariadb"):
            output = StringIO()
            config = alembic_config(); config.output_buffer = output
            with patch("app.config.get_settings", return_value=SimpleNamespace(database_url=f"{dialect}+pymysql://test@localhost/test")):
                command.upgrade(config, "20261007_29:20261007_30", sql=True)
            sql = output.getvalue()
            self.assertIn("MODIFY export_blob MEDIUMBLOB NULL", sql)
            self.assertIn("ADD COLUMN export_url VARCHAR(1024)", sql)
            self.assertIn("export_expires_at", sql)

    def test_baseline_migration_creates_schema_and_records_current_head(self) -> None:
        with self.engine.begin() as connection:
            upgrade_database(connection)
            current, expected = schema_heads(connection)

        self.assertEqual(current, expected)
        self.assertIn("users", inspect(self.engine).get_table_names())
        self.assertIn("alembic_version", inspect(self.engine).get_table_names())
        self.assertIn("login_rate_limits", inspect(self.engine).get_table_names())
        self.assertIn("product_library_ranking_tasks", inspect(self.engine).get_table_names())
        task_columns = {column["name"] for column in inspect(self.engine).get_columns("product_library_ranking_tasks")}
        self.assertTrue({"company_id", "task_id", "status", "snapshot_date", "requested_at",
                         "started_at", "finished_at", "error"}.issubset(task_columns))
        self.assertTrue({
            "product_library_sources", "product_library_products", "product_library_orders",
            "product_library_order_products",
        }.issubset(inspect(self.engine).get_table_names()))
        draft_columns = {column["name"]: column for column in inspect(self.engine).get_columns("product_drafts")}
        self.assertIn("pending", str(draft_columns["workflow_stage"]["default"]))
        assert_schema_current(self.engine)

    def test_title_requirements_use_revision_25_without_confirmed_info(self) -> None:
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "20261005_25")
            connection.execute(text("INSERT INTO companies (id, name, is_active, created_at) VALUES (900, 'Existing Company', 1, CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO product_templates (id, company_id, name, title_template, is_platform, status, color_count, sku_count) VALUES (900, 900, 'TEST', 'Existing title rules', 0, 'published', 1, 1)"))
            command.upgrade(config, "head")
            current, expected = schema_heads(connection)
            self.assertEqual(current, expected)
            self.assertEqual(current, {"20261007_30"})
            columns = {column['name'] for column in inspect(connection).get_columns('product_templates')}
            self.assertNotIn('confirmed_product_info', columns)
            self.assertEqual(connection.execute(text("SELECT title_template FROM product_templates WHERE id=900")).scalar_one(), 'Existing title rules')
            self.assertEqual(connection.execute(text("SELECT name FROM companies WHERE id=900")).scalar_one(), 'Existing Company')
        assert_schema_current(self.engine)

    def test_hub_upgrade_preserves_history_without_granting_access(self):
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "20261006_26")
            connection.execute(text("INSERT INTO companies (id, name, is_active, created_at) VALUES (1, 'Legacy', 1, CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO shops (id, company_id, name, region, auth_status, shop_type, hubstudio_container_code, hub_agent_id) VALUES (1, 1, 'Legacy Local', 'MY', 'local', 'local', 'env-1', 1)"))
            for identity, status in ((1, 'queued'), (2, 'running'), (3, 'completed')):
                connection.execute(text("INSERT INTO hub_upload_tasks (id, company_id, shop_id, agent_id, created_by, draft_ids, export_filename, export_blob, parameters, status, stage, logs, claim_token, created_at) VALUES (:id, 1, 1, 1, 1, '[1]', 'snapshot.xlsx', :blob, '{}', :status, :status, '[]', 'old-token', CURRENT_TIMESTAMP)"), {"id": identity, "status": status, "blob": b'PKsnapshot'})
            command.upgrade(config, "head")
            env = connection.execute(text("SELECT id, auto_upload_enabled, synced_at FROM hub_environments")).one()
            self.assertFalse(env.auto_upload_enabled)
            self.assertIsNone(env.synced_at)
            self.assertEqual(connection.scalar(text("SELECT COUNT(*) FROM hub_environment_access")), 0)
            records = connection.execute(text("SELECT status, claim_token, environment_id, export_blob, lease_expires_at FROM hub_upload_tasks ORDER BY id")).all()
            self.assertEqual([r.status for r in records], ['awaiting_attention', 'awaiting_attention', 'completed'])
            self.assertIsNone(records[0].claim_token)
            self.assertIsNone(records[1].claim_token)
            self.assertIsNone(records[1].lease_expires_at)
            self.assertTrue(all(r.environment_id == env.id and r.export_blob == b'PKsnapshot' for r in records))
            self.assertEqual(connection.scalar(text("SELECT task_id FROM hub_environment_locks")), 1)
            self.assertEqual(connection.scalar(text("SELECT COUNT(*) FROM shops")), 1)
            self.assertEqual(connection.scalar(text("SELECT task_id FROM hub_runtime_locks")), 1)
            self.assertEqual(connection.scalar(text("SELECT container_code FROM hub_upload_tasks WHERE id=2")), "env-1")

    def test_running_upgrade_again_is_a_no_op(self) -> None:
        with self.engine.connect() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "head")
            first_tables = set(inspect(connection).get_table_names())
            command.upgrade(config, "head")
            second_tables = set(inspect(connection).get_table_names())

        self.assertEqual(first_tables, second_tables)
        with self.engine.connect() as connection:
            current, expected = schema_heads(connection)
            self.assertEqual(current, expected)

    def test_queue_intervals_migrate_seconds_to_milliseconds_once(self) -> None:
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "20261005_25")
            connection.execute(text("INSERT INTO task_queue_settings "
                                    "(id, submit_interval_seconds, result_interval_seconds) VALUES (1, 2, 7)"))
            command.upgrade(config, "head")
            command.upgrade(config, "head")
            self.assertEqual(tuple(connection.execute(text(
                "SELECT submit_interval_ms, result_interval_ms FROM task_queue_settings WHERE id=1"
            )).one()), (2000, 7000))
            command.downgrade(config, "20261005_25")
            self.assertEqual(tuple(connection.execute(text(
                "SELECT submit_interval_seconds, result_interval_seconds FROM task_queue_settings WHERE id=1"
            )).one()), (2, 7))

    def test_shop_identity_constraint_and_hub_upload_task_indexes_are_migrated(self) -> None:
        with self.engine.begin() as connection:
            upgrade_database(connection)
            inspector = inspect(connection)
            shop_constraints = inspector.get_unique_constraints("shops")
            hub_upload_indexes = {item["name"] for item in inspector.get_indexes("hub_upload_tasks")}
            pod_task_indexes = {item["name"] for item in inspector.get_indexes("pod_tasks")}
            material_indexes = {item["name"] for item in inspector.get_indexes("material_assets")}

        self.assertTrue(any(
            item["name"] == "uq_shops_company_external_shop_type"
            and item["column_names"] == ["company_id", "external_shop_id", "shop_type"]
            for item in shop_constraints
        ))
        self.assertTrue({
            "ix_hub_upload_tasks_status",
            "ix_hub_upload_tasks_created_by",
            "ix_hub_upload_tasks_claim_token",
        }.issubset(hub_upload_indexes))
        self.assertIn("ix_pod_tasks_status_created_at_id", pod_task_indexes)
        self.assertIn("ix_material_assets_company_created_id", material_indexes)
        self.assertIn("ix_material_assets_company_creator_created_id", material_indexes)

    def test_shop_identity_migration_rejects_existing_duplicate_cross_border_shops(self) -> None:
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "20260920_15")
            connection.execute(text("""
                INSERT INTO companies (id, name, is_active, created_at)
                VALUES (1, 'Test Company', 1, CURRENT_TIMESTAMP)
            """))
            connection.execute(text("""
                INSERT INTO shops (id, company_id, name, region, external_shop_id, auth_status, shop_type)
                VALUES
                    (1, 1, 'First', 'MY', 'external-1', 'active', 'cross_border'),
                    (2, 1, 'Second', 'MY', 'external-1', 'active', 'cross_border')
            """))

            with self.assertRaisesRegex(RuntimeError, "发现重复跨境店"):
                command.upgrade(config, "head")

    def test_existing_unversioned_database_requires_explicit_adoption(self) -> None:
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "20260911_01")
            connection.execute(text("""
                INSERT INTO companies (id, name, is_active, created_at)
                VALUES (1, 'Legacy company', 1, CURRENT_TIMESTAMP)
            """))
            connection.execute(text("DROP TABLE alembic_version"))

            with self.assertRaisesRegex(RuntimeError, "--adopt-legacy"):
                upgrade_database(connection)

            upgrade_database(connection, adopt_legacy=True)
            current, expected = schema_heads(connection)
            company_name = connection.scalar(text("SELECT name FROM companies WHERE id = 1"))

        self.assertEqual(current, expected)
        self.assertEqual(company_name, "Legacy company")

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
