"""素材侵权标记的创建、修改权限和迁移回归。"""
import unittest

from alembic import command
from sqlalchemy import create_engine, event, inspect, select, text

from app import main
from app.image_files import file_ticket
from app.models import MaterialAsset, PodTask, ProductTemplate, TaskStatus, User
from app.schema_version import alembic_config
from tests.image_file_helpers import index_urls
from tests.test_supply_catalog import SupplyFixture


class MaterialInfringementTests(SupplyFixture, unittest.TestCase):
    def test_library_flag_updates_are_visible_in_supply_and_new_job_candidates(self):
        def supply_flags():
            response = self.request("GET", "/supply/materials", uid=1)
            self.assertEqual(response.status_code, 200, response.text)
            return {row["id"]: row["is_infringing"] for row in response.json()["items"]}
        self.assertFalse(supply_flags()[1])
        response = self.request("PATCH", "/material-assets/infringement", uid=2,
            json={"material_asset_ids": [1, 2, 3, 4, 5], "is_infringing": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(all(supply_flags()[identity] for identity in range(1, 6)))
        job_id = self.submit(self.create_strategy(infringement_filter="only"))
        response = self.request("PATCH", "/material-assets/1/infringement", uid=2,
            json={"is_infringing": False})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(supply_flags()[1])
        self.assertTrue(supply_flags()[2])
        with self.sessions() as db:
            from app.models import SupplyJob
            candidates = db.get(SupplyJob, job_id).snapshot["candidates"]
            self.assertEqual({item["id"] for item in candidates}, set(range(1, 6)))
            self.assertTrue(all(item["is_infringing"] for item in candidates))

    def setUp(self):
        super().setUp()
        self.app.include_router(main.app.router)
        with self.sessions() as db:
            db.get(ProductTemplate, 1).name = "Y1"
            db.get(User, 2).user_code = "AA"
            db.commit()
            self.urls = [f"https://img.example/new{i}.png" for i in range(6)]
            files = index_urls(db, 1, self.urls)
            self.file_tokens = [file_ticket(db.get(User, 2), image) for image in files]
            db.add(PodTask(id=1, company_id=1, template_id=1, created_by=2,
                status=TaskStatus.AWAITING_SELECTION, result_urls=self.urls[4:]))
            db.commit()

    def test_all_creation_entries_and_replays_preserve_independent_sku_flags(self):
        created = []
        for index, flag in enumerate((True, False)):
            response = self.request("POST", "/material-assets/commit", uid=2, json={"template_id": 1,
                "items": [{"file_token": self.file_tokens[index], "request_key": f"upload-key-{index}",
                    "is_infringing": flag}]})
            self.assertEqual(response.status_code, 200, response.text)
            created.append((response.json()["items"][0]["asset_id"], flag))
            response = self.request("POST", "/material-assets/import-confirm", uid=2, json={"template_id": 1,
                "urls": [self.urls[index + 2]], "request_key": f"import-key-{index}", "is_infringing": flag})
            self.assertEqual(response.status_code, 200, response.text)
            created.append((response.json()["items"][0]["asset_id"], flag))
            response = self.request("POST", "/tasks/1/claim-materials", uid=2, json={
                "result_urls": [self.urls[index + 4]], "request_key": f"claim-key-{index}", "is_infringing": flag})
            self.assertEqual(response.status_code, 200, response.text)
            created.append((response.json()["items"][0]["asset_id"], flag))
        # 重试已创建的请求时，即使标记不同也不能覆写先前结果。
        replay = self.request("POST", "/material-assets/commit", uid=2, json={"template_id": 1,
            "items": [{"file_token": self.file_tokens[0], "request_key": "upload-key-0", "is_infringing": False}]}).json()
        self.assertTrue(replay["items"][0]["replayed"])
        self.assertEqual(replay["items"][0]["asset_id"], created[0][0])
        for force in (False, True):
            result = self.request("POST", "/material-assets/commit", uid=2, json={"template_id": 1,
                "items": [{"file_token": self.file_tokens[0], "request_key": f"duplicate-key-{force}",
                    "force_create": force}]}).json()["items"][0]
            self.assertEqual(result["outcome"], "created" if force else "duplicate")
            if force:
                created.append((result["asset_id"], False))
        with self.sessions() as db:
            for identity, flag in created:
                self.assertEqual(db.get(MaterialAsset, identity).is_infringing, flag)
        rows = self.request("GET", "/material-assets", uid=2, params={"page_size": 1000}).json()["items"]
        by_id = {row["id"]: row["is_infringing"] for row in rows}
        for identity, flag in created:
            self.assertEqual(by_id[identity], flag)

    def test_single_batch_permissions_and_invalid_batch_atomicity(self):
        # 运营成员只能修改本人；组长即使具有货盘管理权限也不能修改其他人的素材。
        with self.sessions() as db:
            db.get(MaterialAsset, 3).claimed_by = 3
            db.commit()
        for uid, identity, status in ((2, 1, 200), (3, 1, 404), (3, 3, 200), (2, 3, 404),
                                      (1, 1, 200), (5, 1, 404), (4, 1, 403)):
            response = self.request("PATCH", f"/material-assets/{identity}/infringement", uid=uid,
                json={"is_infringing": True})
            self.assertEqual(response.status_code, status, response.text)
        for invalid in (99, 999):
            response = self.request("PATCH", "/material-assets/infringement", uid=2,
                json={"material_asset_ids": [2, invalid], "is_infringing": True})
            self.assertEqual(response.status_code, 404)
            with self.sessions() as db:
                self.assertFalse(db.get(MaterialAsset, 2).is_infringing)
        response = self.request("PATCH", "/material-assets/infringement", uid=2,
            json={"material_asset_ids": [1, 2, 2], "is_infringing": True})
        self.assertEqual(response.json(), {"ids": [1, 2], "count": 2, "is_infringing": True})
        for ids in ([], [0], [-1], list(range(1, 1002))):
            self.assertEqual(self.request("PATCH", "/material-assets/infringement", uid=2,
                json={"material_asset_ids": ids, "is_infringing": True}).status_code, 422)
        with self.sessions() as db:
            self.assertTrue(db.get(MaterialAsset, 2).is_infringing)
            self.assertFalse(db.get(MaterialAsset, 99).is_infringing)

    def test_batch_accepts_1000_materials_in_one_commit(self):
        ids = list(range(1000, 2000))
        with self.sessions() as db:
            db.add_all(MaterialAsset(id=identity, company_id=1, claimed_by=2, name="批量",
                url=f"https://img.example/batch{identity}.png") for identity in ids)
            db.commit()
        commits = []
        def committed(session):
            commits.append(session)
        event.listen(self.sessions.class_, "after_commit", committed)
        try:
            result = self.request("PATCH", "/material-assets/infringement", uid=2,
                json={"material_asset_ids": ids, "is_infringing": True})
        finally:
            event.remove(self.sessions.class_, "after_commit", committed)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(commits), 1)
        self.assertEqual(result.json()["count"], 1000)
        with self.sessions() as db:
            self.assertTrue(all(db.scalars(select(MaterialAsset.is_infringing).where(MaterialAsset.id.in_(ids)))))


class MaterialInfringementMigrationTests(unittest.TestCase):
    def test_upgrade_defaults_and_downgrade_preserve_existing_materials(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, "20261017_40")
            connection.execute(text("""INSERT INTO material_assets
                (id, company_id, name, url, claimed_by, usage_status, created_at)
                VALUES (1, 1, 'Existing', 'https://img.example/a.png', 1, 'used', CURRENT_TIMESTAMP)"""))
            command.upgrade(config, "head")
            self.assertEqual(tuple(connection.execute(text("SELECT name, usage_status, is_infringing FROM material_assets")).one()),
                ("Existing", "used", 0))
            column = next(item for item in inspect(connection).get_columns("material_assets") if item["name"] == "is_infringing")
            self.assertFalse(column["nullable"])
            connection.execute(text("""INSERT INTO material_assets
                (id, company_id, name, url, claimed_by, usage_status, created_at)
                VALUES (2, 1, 'New', 'https://img.example/b.png', 1, 'unused', CURRENT_TIMESTAMP)"""))
            self.assertEqual(connection.scalar(text("SELECT is_infringing FROM material_assets WHERE id=2")), 0)
            command.downgrade(config, "20261017_40")
            self.assertEqual(connection.scalar(text("SELECT count(*) FROM material_assets")), 2)
            command.upgrade(config, "head")
            self.assertEqual(connection.scalar(text("SELECT is_infringing FROM material_assets")), 0)
