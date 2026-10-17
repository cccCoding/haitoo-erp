from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import SupplyJob, SupplyJobMaterial
from app.schema_version import alembic_config


class SupplySchemaTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")

    def tearDown(self):
        self.engine.dispose()

    def test_upgrade_preserves_legacy_rows_and_defaults_to_private(self):
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "20261013_36")
            connection.execute(text("INSERT INTO companies (id, name, is_active, created_at) VALUES (1, 'Existing', 1, CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO users (id, company_id, email, name, password_hash, role, token_version, is_active, created_at) VALUES (1, 1, 'old@example.com', 'Existing', 'hash', 'MEMBER', 0, 1, CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO material_assets (id, company_id, url, name, claimed_by, usage_status, created_at) VALUES (1, 1, 'https://example.com/sku.png', 'Existing', 1, 'used', CURRENT_TIMESTAMP)"))
            command.upgrade(config, "head")
            self.assertEqual(tuple(connection.execute(text("SELECT role, supply_admin, supply_agent_id, supply_expires_at FROM users WHERE id=1")).one()), ("MEMBER", 0, None, None))
            self.assertEqual(tuple(connection.execute(text("SELECT url, usage_status, supply_listed FROM material_assets WHERE id=1")).one()), ("https://example.com/sku.png", "used", 0))
            self.assertEqual(connection.scalar(text("SELECT supply_ai_model FROM companies WHERE id=1")), "deepseek-chat")
            self.assertNotIn("download_revoked", {column["name"] for column in inspect(connection).get_columns("supply_jobs")})
            for table in ("supply_agents", "supply_strategies", "supply_jobs", "image_files", "image_addresses", "supply_job_materials", "supply_audits"):
                self.assertIn(table, inspect(connection).get_table_names())
                self.assertEqual(inspect(connection).get_foreign_keys(table), [])

    def test_remove_revocation_upgrade_and_downgrade_preserve_job_data(self):
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "20261014_37")
            connection.execute(text("""INSERT INTO supply_jobs
                (id, company_id, user_id, idempotency_key, request_hash, template_id,
                 category_catalog_id, snapshot, category_blob, checkpoint, progress, export_blob,
                 state, stage, lease_epoch, output_key, created_at)
                VALUES (1, 1, 1, 'existing-request', 'hash', 1, 1, '{}', :category, '{}', '{}',
                        :export, 'completed', 'completed', 3, 'existing-file', CURRENT_TIMESTAMP)"""),
                {"category": b"category snapshot", "export": b"pending export"})
            expected = tuple(connection.execute(text("SELECT id, state, stage, lease_epoch, category_blob, export_blob, output_key FROM supply_jobs")).one())
            command.upgrade(config, "head")
            self.assertNotIn("download_revoked", {column["name"] for column in inspect(connection).get_columns("supply_jobs")})
            self.assertEqual(tuple(connection.execute(text("SELECT id, state, stage, lease_epoch, category_blob, export_blob, output_key FROM supply_jobs")).one()), expected)
            command.downgrade(config, "20261014_37")
            column = next(column for column in inspect(connection).get_columns("supply_jobs") if column["name"] == "download_revoked")
            self.assertFalse(column["nullable"])
            self.assertEqual(connection.scalar(text("SELECT download_revoked FROM supply_jobs WHERE id=1")), 0)
            command.upgrade(config, "head")
            self.assertEqual(tuple(connection.execute(text("SELECT id, state, stage, lease_epoch, category_blob, export_blob, output_key FROM supply_jobs")).one()), expected)

    def test_listing_history_upgrade_recovers_past_publications_and_preserves_never_listed(self):
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "20261016_38")
            for identity, listed in ((1, 1), (2, 0), (3, 0), (4, 0)):
                connection.execute(text("""INSERT INTO material_assets
                    (id, company_id, url, name, claimed_by, usage_status, supply_listed, created_at)
                    VALUES (:id, 1, 'https://example.com/image.png', 'Existing', 1, 'unused', :listed, CURRENT_TIMESTAMP)"""),
                    {"id": identity, "listed": listed})
            for identity, company, listed in ((2, 1, 'true'), (3, 1, 'false'), (4, 2, 'true')):
                connection.execute(text("""INSERT INTO supply_audits
                    (company_id, user_id, action, target_type, target_id, details, created_at)
                    VALUES (:company, 1, 'material_listing', 'material', :id, :details, '2026-10-15 12:00:00')"""),
                    {"company": company, "id": identity, "details": '{"listed": ' + listed + '}'})
            command.upgrade(config, "head")
            rows = dict(connection.execute(text("SELECT id, supply_listed_at FROM material_assets")).all())
            self.assertIsNotNone(rows[1])
            self.assertEqual(rows[2], '2026-10-15 12:00:00')
            self.assertIsNone(rows[3])
            self.assertIsNone(rows[4])
            command.downgrade(config, "20261016_38")
            self.assertNotIn("supply_listed_at", {column["name"] for column in inspect(connection).get_columns("material_assets")})
            self.assertEqual(connection.scalar(text("SELECT count(*) FROM material_assets")), 4)

    def test_downgrade_disables_external_accounts_and_retains_internal_users(self):
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "head")
            connection.execute(text("INSERT INTO users (id, company_id, email, name, password_hash, role, token_version, is_active, created_at) VALUES (1, 1, 'supply@example.com', 'Supply', 'hash', 'SUPPLY_USER', 2, 1, CURRENT_TIMESTAMP), (2, 1, 'member@example.com', 'Member', 'hash', 'MEMBER', 0, 1, CURRENT_TIMESTAMP)"))
            command.downgrade(config, "20261013_36")
            self.assertEqual(tuple(connection.execute(text("SELECT role, token_version, is_active FROM users WHERE id=1")).one()), ("MEMBER", 3, 0))
            self.assertEqual(tuple(connection.execute(text("SELECT role, token_version, is_active FROM users WHERE id=2")).one()), ("MEMBER", 0, 1))
            self.assertNotIn("supply_jobs", inspect(connection).get_table_names())
            self.assertNotIn("supply_admin", {column["name"] for column in inspect(connection).get_columns("users")})

    def test_mysql_sql_uses_uppercase_role_and_medium_blobs(self):
        for dialect in ("mysql", "mariadb"):
            output = StringIO()
            config = alembic_config()
            config.output_buffer = output
            with patch("app.config.get_settings", return_value=SimpleNamespace(database_url=f"{dialect}+pymysql://test@localhost/test")):
                command.upgrade(config, "20261013_36:head", sql=True)
            sql = output.getvalue()
            self.assertIn("'SUPPLY_USER'", sql)
            self.assertIn("category_blob MEDIUMBLOB NOT NULL", sql)
            self.assertIn("export_blob MEDIUMBLOB", sql)
            self.assertIn("link_index INTEGER NOT NULL DEFAULT -1", sql)
            self.assertIn("ALTER TABLE supply_jobs DROP COLUMN download_revoked", sql)
            self.assertNotIn("FOREIGN KEY", sql)

    def test_job_and_candidate_associations_are_unique(self):
        Base.metadata.create_all(self.engine)
        with sessionmaker(bind=self.engine)() as db:
            arguments = dict(company_id=1, user_id=1, idempotency_key="request", request_hash="a" * 64,
                             template_id=1, category_catalog_id=1, category_blob=b"snapshot")
            db.add(SupplyJob(**arguments))
            db.commit()
            db.add(SupplyJob(**arguments))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()
            material = dict(company_id=1, job_id=1, material_id=1, version_hash="b" * 64)
            db.add(SupplyJobMaterial(**material))
            db.commit()
            self.assertEqual(db.query(SupplyJobMaterial).one().link_index, -1)
            db.add(SupplyJobMaterial(**material))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()
            db.add(SupplyJobMaterial(**material, link_index=0))
            db.commit()
            self.assertEqual(db.query(SupplyJobMaterial).count(), 2)


if __name__ == "__main__":
    unittest.main()
