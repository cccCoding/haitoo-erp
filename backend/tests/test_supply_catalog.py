"""货盘 HTTP 权限、快照和账号管理行为；所有第三方能力使用替身。"""
from datetime import datetime, timedelta, timezone
import copy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.credentials import decrypt_secret, encrypt_secret
from app.models import (Company, MaterialAsset, OperatorGroup, ProductDraft, ProductTemplate, Role, SupplyAgent, SupplyAudit,
                        SupplyImageHealth, SupplyJob, SupplyStrategy, TemplateGroup, TiktokCategoryCatalog, User)
from app.security import create_access_token, hash_password
from app.supply_accounts import add_calendar_months
from app.supply_catalog import router
from app.supply_common import digest
from app.tiktok_export import TEMPLATE_PATH, listing_options


TEST_PASSWORD_HASH = hash_password("Password123")


class SupplyFixture:
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([Company(id=1, name="公司一"), Company(id=2, name="公司二")])
            for identity, role, company, manager in ((1, Role.COMPANY_ADMIN, 1, False), (2, Role.MEMBER, 1, False),
                (3, Role.TEAM_LEADER, 1, True), (4, Role.SUPPLY_USER, 1, False), (5, Role.COMPANY_ADMIN, 2, False),
                (6, Role.SUPPLY_USER, 2, False), (7, Role.SUPPLY_USER, 1, False)):
                db.add(User(id=identity, company_id=company, email=f"user{identity}@example.com", name=f"用户{identity}",
                    role=role, supply_admin=manager, password_hash=TEST_PASSWORD_HASH,
                    supply_agent_id=company if role == Role.SUPPLY_USER else None,
                    supply_expires_at=datetime.utcnow() + timedelta(days=30) if role == Role.SUPPLY_USER else None))
            db.add_all([SupplyAgent(id=1, company_id=1, name="原代理"), SupplyAgent(id=2, company_id=2, name="其他公司代理")])
            for identity in (1, 2):
                db.add(ProductTemplate(id=identity, company_id=identity, name=f"模板{identity}",
                    cover_url=f"https://img.example/template{identity}.png", description=f"模板{identity}的款式描述",
                    product_description="Printed long sleeve dress",
                    size_chart_url=f"https://img.example/size{identity}.png", package_weight=.3, package_length=30,
                    package_width=20, package_height=2, sku_specifications={"size": {"options": ["S", "M"]}},
                    supply_public=True, supply_fallback_title="Printed Long Sleeve Nursing Maxi Dress"))
                db.add(TiktokCategoryCatalog(id=identity, company_id=identity, name=f"类目库{identity}",
                    source_filename=TEMPLATE_PATH.name, template_type="tiktok_local", template_blob=TEMPLATE_PATH.read_bytes(),
                    parsed_options=copy.deepcopy(listing_options())))
            for identity in range(1, 21):
                db.add(MaterialAsset(id=identity, company_id=1, template_id=1, claimed_by=2, name=f"素材{identity}",
                    sku=f"SOURCE{identity:03d}", url=f"https://img.example/{identity}.png", supply_listed=True))
            db.add(MaterialAsset(id=99, company_id=2, template_id=2, claimed_by=5, name="其他素材", sku="FOREIGN",
                                 url="https://img.example/foreign.png", supply_listed=True))
            db.commit()
            self.tokens = {identity: create_access_token(db.get(User, identity)) for identity in range(1, 8)}
        self.app = FastAPI()
        self.app.include_router(router)
        self.override_db(self.app)
        self.client = TestClient(self.app)
        self.image_mock = self.enterContext(patch("app.supply_images.check_image", new_callable=AsyncMock))
        self.upload_mock = self.enterContext(patch("app.supply_files.upload_supply_export"))

    def override_db(self, app):
        def override():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = override

    def tearDown(self):
        self.client.close()
        self.app.dependency_overrides.clear()
        self.engine.dispose()

    def request(self, method, path, *, uid=1, json=None, **kwargs):
        return self.client.request(method, path, json=json,
            headers={"Authorization": f"Bearer {self.tokens[uid]}"}, **kwargs)

    def strategy_input(self, **extra):
        return {"name": "生成策略", "category_catalog_id": 1, "category_name": "女士上装/女士衬衫", "template_id": 1,
                "price": "19.99", "attributes": {"product_property/100198": "花朵"}, "sku_count": 5, "link_count": 10, **extra}

    def create_strategy(self, uid=4, **extra):
        response = self.request("POST", "/supply/strategies", uid=uid, json=self.strategy_input(**extra))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def submit(self, strategy=None, uid=4, key="submit-request-01"):
        if strategy is None:
            strategy = self.create_strategy(uid)
        response = self.request("POST", "/supply/jobs", uid=uid, json={"strategy_id": strategy, "idempotency_key": key})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]


class SupplyCatalogTests(SupplyFixture, unittest.TestCase):
    def test_material_pagination_supports_500_and_1000_without_cross_company_rows(self):
        with self.sessions() as db:
            db.add_all([MaterialAsset(id=identity, company_id=1, template_id=1, claimed_by=2,
                sku=f"PAGE{identity}", name=f"分页素材{identity}",
                url=f"https://img.example/page-{identity}.png", supply_listed=True)
                for identity in range(1000, 2000)])
            db.commit()
        for page_size in (500, 1000):
            with self.subTest(page_size=page_size):
                response = self.request("GET", "/supply/materials", params={"page_size": page_size})
                self.assertEqual(response.status_code, 200, response.text)
                first = response.json()
                self.assertEqual(first["page_size"], page_size)
                self.assertEqual(first["total"], 1020)
                self.assertEqual(len(first["items"]), page_size)
                last = self.request("GET", "/supply/materials", params={
                    "page_size": page_size, "page": 1020 // page_size + 1}).json()
                self.assertEqual(len(last["items"]), 20)
                self.assertTrue({row["id"] for row in first["items"]}.isdisjoint(
                    row["id"] for row in last["items"]))
                self.assertNotIn(99, [row["id"] for row in first["items"] + last["items"]])
        self.assertEqual(self.request("GET", "/supply/materials", params={"page_size": 1001}).status_code, 422)

    def test_listing_lifecycle_separates_library_listed_and_delisted_materials(self):
        with self.sessions() as db:
            db.add(MaterialAsset(id=21, company_id=1, template_id=1, claimed_by=2, sku="NEW",
                name="新素材", url="https://img.example/new.png"))
            db.commit()
        self.assertEqual(self.request("GET", "/supply/materials").json()["total"], 20)
        self.assertEqual(self.request("GET", "/supply/materials?listed=false").json()["total"], 0)
        candidates = self.request("GET", "/supply/materials?source=library").json()
        self.assertEqual([row["id"] for row in candidates["items"]], [21])
        # 对从未上架的素材调用下架接口，不能把它变成历史货盘素材。
        self.assertEqual(self.request("PATCH", "/supply/materials/21", json={"supply_listed": False}).status_code, 200)
        self.assertEqual(self.request("GET", "/supply/materials?listed=false").json()["total"], 0)
        self.assertEqual(self.request("PATCH", "/supply/materials/21", json={"supply_listed": True}).status_code, 200)
        with self.sessions() as db:
            first_listing = db.get(MaterialAsset, 21).supply_listed_at
            self.assertIsNotNone(first_listing)
        self.assertEqual(self.request("GET", "/supply/materials?source=library").json()["total"], 0)
        self.assertEqual(self.request("GET", "/supply/materials").json()["total"], 21)
        for identity in (1, 21):
            self.assertEqual(self.request("PATCH", f"/supply/materials/{identity}", json={"supply_listed": False}).status_code, 200)
        self.assertEqual(self.request("GET", "/supply/materials").json()["total"], 19)
        removed = self.request("GET", "/supply/materials?listed=false&page_size=1").json()
        self.assertEqual(removed["total"], 2)
        self.assertEqual([row["id"] for row in removed["items"]], [21])
        self.assertEqual(self.request("GET", "/supply/materials?listed=false&search=NEW").json()["total"], 1)
        self.assertEqual(self.request("GET", "/supply/materials?source=library&template_id=1&health=unchecked").json()["total"], 2)
        self.assertEqual(self.request("PATCH", "/supply/materials/21", json={"supply_listed": True}).status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.get(MaterialAsset, 21).supply_listed_at, first_listing)
        self.image_mock.assert_not_called()

    def test_listing_candidates_require_management_and_stay_in_company(self):
        with self.sessions() as db:
            db.get(MaterialAsset, 99).supply_listed = False
            db.add(MaterialAsset(id=21, company_id=1, template_id=1, claimed_by=2, sku="NEW",
                name="新素材", url="https://img.example/new.png"))
            db.commit()
        for uid in (2, 4):
            self.assertEqual(self.request("GET", "/supply/materials?source=library", uid=uid).status_code, 403)
        for uid in (1, 3):
            response = self.request("GET", "/supply/materials?source=library", uid=uid)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([row["id"] for row in response.json()["items"]], [21])
        self.assertEqual([row["id"] for row in self.request("GET", "/supply/materials?source=library", uid=5).json()["items"]], [99])
        self.assertEqual(self.request("GET", "/supply/materials?listed=false", uid=5).json()["total"], 0)

    def test_supply_users_cannot_access_materials_but_can_generate_from_templates(self):
        for uid in (4, 6, 7):
            self.assertFalse(self.request("GET", "/supply/context", uid=uid).json()["can_view_materials"])
            for path in ("/supply/materials", "/supply/materials?template_id=1&search=SOURCE&health=unchecked",
                         "/supply/materials/1/usage", "/supply/materials/99/usage", "/supply/materials/999/usage"):
                with self.subTest(uid=uid, path=path):
                    response = self.request("GET", path, uid=uid)
                    self.assertEqual(response.status_code, 403, response.text)
                    self.assertEqual(response.json()["detail"], "货盘用户不能查看货盘素材")
            for identity in (1, 99, 999):
                self.assertEqual(self.request("PATCH", f"/supply/materials/{identity}", uid=uid,
                                              json={"supply_listed": False}).status_code, 403)
                self.assertEqual(self.request("POST", f"/supply/materials/{identity}/recheck", uid=uid).status_code, 403)
        templates = self.request("GET", "/supply/templates", uid=4)
        self.assertEqual(templates.status_code, 200, templates.text)
        self.assertEqual(templates.json()[0]["available_count"], 20)
        self.assertEqual(templates.json()[0]["cover_url"], "https://img.example/template1.png")
        self.assertEqual(templates.json()[0]["description"], "模板1的款式描述")
        identity = self.submit()
        self.assertEqual(self.request("GET", f"/supply/jobs/{identity}", uid=4).status_code, 200)
        self.image_mock.assert_not_called()

    def test_template_groups_include_empty_and_unpublished_categories_without_other_companies(self):
        with self.sessions() as db:
            db.add_all([TemplateGroup(id=1, company_id=1, name="空分类"),
                        TemplateGroup(id=2, company_id=1, name="未公开模板分类"),
                        TemplateGroup(id=3, name="平台分类", is_platform=True),
                        TemplateGroup(id=4, company_id=2, name="其他公司分类")])
            db.add(ProductTemplate(company_id=1, group_id=2, name="未公开模板", supply_public=False))
            db.commit()
        for uid in (1, 2, 3, 4):
            with self.subTest(uid=uid):
                response = self.request("GET", "/supply/template-groups", uid=uid)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual({row["id"] for row in response.json()}, {1, 2, 3})
                self.assertEqual(response.json()[0], {"id": 3, "name": "平台分类"})
        foreign = self.request("GET", "/supply/template-groups", uid=6)
        self.assertEqual({row["id"] for row in foreign.json()}, {3, 4})
        self.assertEqual(self.client.get("/supply/template-groups").status_code, 403)

    def test_template_categories_preserve_company_and_publication_visibility(self):
        with self.sessions() as db:
            db.add_all([TemplateGroup(id=1, company_id=1, name="女士衬衫"),
                        TemplateGroup(id=2, company_id=2, name="其他公司分类"),
                        TemplateGroup(id=3, name="平台分类", is_platform=True)])
            db.get(ProductTemplate, 1).group_id = 1
            db.get(ProductTemplate, 2).group_id = 2
            db.add_all([ProductTemplate(id=3, company_id=1, group_id=3, name="未公开模板", supply_public=False),
                        ProductTemplate(id=4, company_id=1, group_id=2, name="错误分类关联", supply_public=True)])
            db.commit()
        manager_items = self.request("GET", "/supply/templates").json()
        self.assertEqual([(row["id"], row["group_id"], row["group_name"]) for row in manager_items],
                         [(1, 1, "女士衬衫"), (3, 3, "平台分类"), (4, None, None)])
        public_items = self.request("GET", "/supply/templates", uid=4).json()
        self.assertEqual([row["id"] for row in public_items], [1, 4])
        self.assertEqual(public_items[0]["group_name"], "女士衬衫")
        foreign_items = self.request("GET", "/supply/templates", uid=6).json()
        self.assertEqual([(row["id"], row["group_name"]) for row in foreign_items], [(2, "其他公司分类")])

    def test_internal_roles_keep_material_access_and_company_isolation(self):
        for uid in (1, 2, 3):
            self.assertTrue(self.request("GET", "/supply/context", uid=uid).json()["can_view_materials"])
            response = self.request("GET", "/supply/materials", uid=uid)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["total"], 20)
            self.assertEqual(self.request("GET", "/supply/materials/1/usage", uid=uid).status_code, 200)
            self.assertEqual(self.request("GET", "/supply/materials/99/usage", uid=uid).status_code, 404)
        response = self.request("GET", "/supply/materials", uid=5)
        self.assertEqual([item["id"] for item in response.json()["items"]], [99])

    def test_ai_config_only_accepts_key_and_uses_fixed_model(self):
        with self.sessions() as db:
            db.get(Company, 1).supply_ai_model = "legacy-custom-model"
            db.commit()
        self.assertEqual(self.request("GET", "/supply/ai-config").json(),
                         {"configured": False, "model": "deepseek-flash"})
        for path, method in (("/supply/ai-config", "PUT"), ("/supply/ai-config/test", "POST")):
            response = self.request(method, path, json={"api_key": "new-key", "model": "deepseek-chat"})
            self.assertEqual(response.status_code, 422, response.text)
        response = self.request("PUT", "/supply/ai-config", json={"api_key": "  supply-test-key  "})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"configured": True, "model": "deepseek-flash"})
        with self.sessions() as db:
            company = db.get(Company, 1)
            self.assertNotEqual(company.supply_ai_secret_encrypted, "supply-test-key")
            self.assertEqual(decrypt_secret(company.supply_ai_secret_encrypted), "supply-test-key")
        self.assertEqual(self.request("GET", "/supply/ai-config", uid=5).json()["configured"], False)
        for uid in (2, 3, 4):
            self.assertEqual(self.request("GET", "/supply/ai-config", uid=uid).status_code, 403)
            self.assertEqual(self.request("PUT", "/supply/ai-config", uid=uid,
                                          json={"api_key": "forbidden"}).status_code, 403)
            self.assertEqual(self.request("POST", "/supply/ai-config/test", uid=uid, json={}).status_code, 403)

    def test_ai_connection_uses_saved_key_or_unsaved_replacement(self):
        self.assertEqual(self.request("POST", "/supply/ai-config/test", json={}).status_code, 400)
        with self.sessions() as db:
            company = db.get(Company, 1)
            company.supply_ai_secret_encrypted = encrypt_secret("saved-key")
            company.supply_ai_model = "legacy-custom-model"
            db.commit()
        title = "Printed Long Sleeve Nursing Maxi Dress"
        with patch("app.supply_worker.request_title", new_callable=AsyncMock, return_value=title) as request:
            for payload, key in (({}, "saved-key"), ({"api_key": "replacement-key"}, "replacement-key")):
                response = self.request("POST", "/supply/ai-config/test", json=payload)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["title"], title)
                self.assertEqual(request.await_args.args, (key,
                    {"name": "Printed dress", "product_description": "Printed long sleeve maxi dress"}, ""))
        with self.sessions() as db:
            self.assertEqual(decrypt_secret(db.get(Company, 1).supply_ai_secret_encrypted), "saved-key")

    def test_revoke_api_is_removed_and_jobs_omit_revocation_field(self):
        self.assertEqual(self.request("POST", "/supply/revoke",
            json={"target_type": "material", "target_id": 1}).status_code, 404)
        schema = self.app.openapi()
        self.assertNotIn("/supply/revoke", schema["paths"])
        self.assertNotIn("RevokeInput", schema.get("components", {}).get("schemas", {}))
        identity = self.submit()
        self.assertNotIn("download_revoked", self.request("GET", f"/supply/jobs/{identity}", uid=4).json())
        self.assertNotIn("download_revoked", self.request("GET", "/supply/jobs", uid=4).json()["items"][0])

    def test_publication_and_listing_are_independent_and_never_probe_images(self):
        self.assertEqual(self.request("PATCH", "/supply/templates/1", json={"supply_public": False}).status_code, 200)
        self.assertEqual(self.request("GET", "/supply/materials", uid=2).json()["total"], 0)
        with self.sessions() as db:
            self.assertTrue(db.get(MaterialAsset, 1).supply_listed)
        self.assertEqual(self.request("PATCH", "/supply/materials/1", json={"supply_listed": False}).status_code, 200)
        self.assertEqual(self.request("PATCH", "/supply/templates/1", json={"supply_public": True}).status_code, 200)
        with self.sessions() as db:
            db.add(MaterialAsset(company_id=1, template_id=1, claimed_by=2, sku="NEW", name="新增", url="https://img.example/new.png"))
            db.commit()
        self.assertEqual(self.request("GET", "/supply/materials", uid=2).json()["total"], 19)
        self.assertEqual(self.request("PATCH", "/supply/materials/1", json={"supply_listed": True}).status_code, 200)
        self.submit()
        self.image_mock.assert_not_called()
        self.upload_mock.assert_not_called()

    def test_manager_can_publish_but_cannot_manage_users_agents_or_fallback(self):
        self.assertEqual(self.request("PATCH", "/supply/templates/1", uid=3, json={"supply_public": False}).status_code, 200)
        self.assertEqual(self.request("GET", "/supply/users", uid=3).status_code, 200)
        for method, path, payload in (("POST", "/supply/users", {"name": "新增", "email": "new@example.com", "password": "Password123", "agent_id": 1}),
            ("PATCH", "/supply/users/4", {"is_active": False}), ("POST", "/supply/users/4/renew", {"months": 1}),
            ("POST", "/supply/agents", {"name": "新增代理"}), ("POST", "/supply/grants/2", {"enabled": True}),
            ("PATCH", "/supply/templates/1", {"supply_fallback_title": "Printed Long Sleeve Nursing Maxi Dress"})):
            with self.subTest(path=path):
                self.assertEqual(self.request(method, path, uid=3, json=payload).status_code, 403)

    def test_grants_company_and_role_isolation(self):
        self.assertEqual(self.request("POST", "/supply/grants/2", json={"enabled": True}).status_code, 200)
        self.assertTrue(self.request("GET", "/supply/context", uid=2).json()["can_manage"])
        self.assertEqual(self.request("POST", "/supply/grants/4", json={"enabled": True}).status_code, 400)
        self.assertEqual(self.request("POST", "/supply/grants/5", json={"enabled": True}).status_code, 404)
        self.assertEqual(self.request("PATCH", "/supply/materials/99", json={"supply_listed": False}).status_code, 404)
        self.assertEqual(self.request("PATCH", "/supply/templates/2", json={"supply_public": False}).status_code, 404)
        self.assertEqual(self.request("GET", "/supply/catalogs/2/options").status_code, 404)
        self.assertEqual(self.request("POST", "/supply/strategies", uid=4, json=self.strategy_input(template_id=2)).status_code, 400)
        self.assertEqual(self.request("GET", "/supply/statistics", uid=4).status_code, 403)

    def test_manager_list_shows_only_granted_company_members_and_their_groups(self):
        with self.sessions() as db:
            db.add_all([OperatorGroup(id=1, company_id=1, name="运营一组", leader_user_id=3),
                        OperatorGroup(id=2, company_id=2, name="其他公司组", leader_user_id=8)])
            db.get(User, 3).group_id = 1
            db.add(User(id=8, company_id=2, name="其他公司管理人员", email="other-manager@example.com",
                        role=Role.MEMBER, supply_admin=True, group_id=2, password_hash=TEST_PASSWORD_HASH))
            db.commit()
        expected = {"id": 3, "name": "用户3", "group_name": "运营一组", "email": "user3@example.com"}
        for uid in (1, 3):
            response = self.request("GET", "/supply/managers", uid=uid)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), [expected])
        for uid in (2, 4):
            self.assertEqual(self.request("GET", "/supply/managers", uid=uid).status_code, 403)
        self.assertEqual(self.request("POST", "/supply/grants/2", json={"enabled": True}).status_code, 200)
        response = self.request("GET", "/supply/managers", uid=2)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [
            {"id": 2, "name": "用户2", "group_name": None, "email": "user2@example.com"}, expected])
        self.assertEqual(self.request("POST", "/supply/grants/3", json={"enabled": False}).status_code, 200)
        self.assertEqual(self.request("GET", "/supply/managers").json()[0]["id"], 2)
        self.assertEqual(self.request("POST", "/supply/grants/2", json={"enabled": False}).status_code, 200)
        self.assertEqual(self.request("GET", "/supply/managers").json(), [])
        self.assertEqual(self.request("GET", "/supply/managers", uid=3).status_code, 403)

    def test_user_creation_months_renewal_and_restore_are_separate(self):
        fixed = datetime(2026, 1, 30, 20)
        payload = {"name": "新货盘用户", "email": "NEW@example.com", "password": "Password123", "agent_id": 1}
        with patch("app.supply_catalog.now", return_value=fixed):
            response = self.request("POST", "/supply/users", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        identity = response.json()["id"]
        with self.sessions() as db:
            user = db.get(User, identity)
            self.assertEqual(user.role, Role.SUPPLY_USER)
            self.assertEqual(user.email, "new@example.com")
            self.assertEqual(user.supply_expires_at, add_calendar_months(fixed, 12))
            original_expiry = user.supply_expires_at
        self.assertEqual(self.request("PATCH", f"/supply/users/{identity}", json={"is_active": False}).status_code, 200)
        with patch("app.supply_catalog.now", return_value=fixed):
            response = self.request("POST", f"/supply/users/{identity}/renew", json={"months": 1})
        self.assertEqual(response.status_code, 200, response.text)
        with self.sessions() as db:
            user = db.get(User, identity)
            self.assertFalse(user.is_active)
            self.assertEqual(user.supply_expires_at, add_calendar_months(original_expiry, 1))
            user.supply_expires_at = fixed - timedelta(days=1)
            db.commit()
        with patch("app.supply_catalog.now", return_value=fixed):
            self.assertEqual(self.request("POST", f"/supply/users/{identity}/renew", json={"months": 1}).status_code, 200)
        self.assertEqual(self.request("PATCH", f"/supply/users/{identity}", json={"is_active": True}).status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.get(User, identity).supply_expires_at, add_calendar_months(fixed, 1))
        self.assertEqual(self.request("POST", "/supply/users", json={**payload, "email": "other@example.com", "agent_id": 2}).status_code, 404)
        self.assertEqual(self.request("POST", "/supply/users", json={**payload, "email": "other@example.com", "months": 0}).status_code, 422)

    def test_duplicate_agent_is_conflict(self):
        self.assertEqual(self.request("POST", "/supply/agents", json={"name": "原代理"}).status_code, 409)

    def test_agent_creation_time_is_available_and_preserved_after_rename(self):
        fixed = datetime(2026, 10, 14, 3, 15)
        expected = int(fixed.replace(tzinfo=timezone.utc).timestamp() * 1000)
        with self.sessions() as db:
            db.get(SupplyAgent, 1).created_at = fixed
            db.commit()
        response = self.request("GET", "/supply/agents")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [{"id": 1, "name": "原代理", "created_at": expected}])
        renamed = self.request("PATCH", "/supply/agents/1", json={"name": "改名代理"})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["created_at"], expected)
        users = self.request("GET", "/supply/users", uid=3)
        self.assertEqual(users.status_code, 200, users.text)
        self.assertTrue(users.json())
        for user in users.json():
            self.assertEqual(user["agent_created_at"], expected)
        created = self.request("POST", "/supply/agents", json={"name": "新代理"})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertIsInstance(created.json()["created_at"], int)

    def test_agent_changes_do_not_rewrite_history_and_suspension_cancels(self):
        identity = self.submit()
        self.assertEqual(self.request("PATCH", "/supply/agents/1", json={"name": "改名代理"}).status_code, 200)
        other = self.request("POST", "/supply/agents", json={"name": "新代理"}).json()["id"]
        self.assertEqual(self.request("PATCH", "/supply/users/4", json={"agent_id": other}).status_code, 200)
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            self.assertEqual((job.agent_id, job.agent_name), (1, "原代理"))
        self.assertEqual(self.request("PATCH", "/supply/users/4", json={"is_active": False}).status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.get(SupplyJob, identity).state, "cancelled")
        self.assertEqual(self.request("GET", "/supply/context", uid=4).status_code, 401)
        self.assertEqual(self.request("PATCH", "/supply/users/4", json={"is_active": True}).status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.get(SupplyJob, identity).state, "cancelled")

    def test_idempotency_active_limit_and_strategy_ownership(self):
        strategy = self.create_strategy()
        first = self.submit(strategy)
        self.assertEqual(self.submit(strategy), first)
        self.assertEqual(self.request("POST", "/supply/jobs", uid=4, json={"strategy_id": strategy, "idempotency_key": "other-request"}).status_code, 409)
        other = self.create_strategy(name="另一个策略")
        self.assertEqual(self.request("POST", "/supply/jobs", uid=4, json={"strategy_id": other, "idempotency_key": "submit-request-01"}).status_code, 409)
        self.assertEqual(self.request("PATCH", f"/supply/strategies/{strategy}", uid=7, json=self.strategy_input()).status_code, 404)
        self.assertEqual(self.request("GET", f"/supply/jobs/{first}", uid=7).status_code, 404)
        self.assertEqual(self.request("GET", f"/supply/jobs/{first}", uid=5).status_code, 404)
        self.assertEqual(self.request("GET", f"/supply/jobs/{first}", uid=3).status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.query(SupplyJob).count(), 1)

    def test_submission_snapshot_survives_normal_unlisting_unpublishing_and_catalog_deletion(self):
        identity = self.submit()
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            original_snapshot = copy.deepcopy(job.snapshot)
            original_blob = bytes(job.category_blob)
        self.assertEqual(self.request("PATCH", "/supply/materials/1", json={"supply_listed": False}).status_code, 200)
        self.assertEqual(self.request("PATCH", "/supply/templates/1", json={"supply_public": False}).status_code, 200)
        with self.sessions() as db:
            db.get(ProductTemplate, 1).sku_specifications = {"size": {"options": ["XL"]}}
            db.delete(db.get(TiktokCategoryCatalog, 1))
            db.commit()
            job = db.get(SupplyJob, identity)
            self.assertEqual(job.state, "queued")
            self.assertEqual(job.snapshot, original_snapshot)
            self.assertEqual(job.category_blob, original_blob)
        self.assertEqual(self.request("GET", f"/supply/jobs/{identity}", uid=4).status_code, 200)
        self.image_mock.assert_not_called()

    def test_strategy_quantity_row_limits_and_known_bad_health(self):
        for extra in ({"sku_count": 4}, {"sku_count": 10}, {"link_count": 9}, {"link_count": 51}):
            with self.subTest(extra=extra):
                self.assertEqual(self.request("POST", "/supply/strategies", uid=4, json=self.strategy_input(**extra)).status_code, 422)
        self.create_strategy(sku_count=9, link_count=50)
        with self.sessions() as db:
            db.get(ProductTemplate, 1).sku_specifications = {"size": {"options": [str(i) for i in range(12)]}}
            db.commit()
        response = self.request("POST", "/supply/strategies", uid=4, json=self.strategy_input(sku_count=9, link_count=50))
        self.assertEqual(response.status_code, 400)
        self.assertIn("4,994", response.text)
        with self.sessions() as db:
            db.get(ProductTemplate, 1).sku_specifications = {"size": {"options": ["S"]}}
            for identity in range(1, 18):
                url = db.get(MaterialAsset, identity).url
                db.add(SupplyImageHealth(company_id=1, url=url, url_hash=digest(url), status="invalid" if identity % 2 else "check_failed"))
            db.commit()
        strategy = self.create_strategy()
        response = self.request("POST", "/supply/jobs", uid=4, json={"strategy_id": strategy, "idempotency_key": "bad-pictures"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.request("GET", "/supply/materials", uid=2).json()["total"], 3)
        self.assertEqual(self.request("GET", "/supply/materials?health=invalid").json()["total"], 9)
        self.image_mock.assert_not_called()

    def test_download_authentication_recheck_and_manager_audit(self):
        identity = self.submit()
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            job.state, job.completed_at = "completed", datetime.utcnow()
            job.output_key = f"supply-exports/company/1/jobs/{identity}/1/" + "a" * 32 + ".xlsx"
            job.output_expires_at = datetime.utcnow() + timedelta(days=30)
            job.output_sha256, job.output_size = "b" * 64, 7
            db.commit()
        with patch("app.supply_files.read_supply_export", return_value=b"PKexcel") as read:
            response = self.request("GET", f"/supply/jobs/{identity}/download", uid=3)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"PKexcel")
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        read.assert_called_once()
        with self.sessions() as db:
            audit = db.scalar(select(SupplyAudit).where(SupplyAudit.action == "download"))
            self.assertEqual(audit.user_id, 3)
            self.assertTrue(audit.details["on_behalf"])
        def suspend_during_read(*args):
            with self.sessions() as db:
                db.get(User, 4).is_active = False
                db.commit()
            return b"PKexcel"
        with patch("app.supply_files.read_supply_export", side_effect=suspend_during_read):
            self.assertEqual(self.request("GET", f"/supply/jobs/{identity}/download", uid=4).status_code, 403)
        with self.sessions() as db:
            self.assertEqual(db.query(SupplyAudit).filter(SupplyAudit.action == "download").count(), 1)

    def test_expiry_blocks_access_without_granting_old_business_permissions(self):
        from app import main
        self.override_db(main.app)
        client = TestClient(main.app)
        try:
            headers = {"Authorization": f"Bearer {self.tokens[4]}"}
            for method, path in (("GET", "/material-assets"), ("DELETE", "/material-assets/1"), ("GET", "/templates"), ("GET", "/shops")):
                with self.subTest(path=path):
                    self.assertEqual(client.request(method, path, headers=headers).status_code, 403)
            self.assertEqual(client.get("/me", headers=headers).status_code, 200)
        finally:
            client.close()
            main.app.dependency_overrides.clear()
        with self.sessions() as db:
            db.get(User, 4).supply_expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.request("GET", "/supply/context", uid=4).status_code, 401)

    def test_internal_draft_creation_reads_health_without_network_checks(self):
        from app import main
        self.override_db(main.app)
        client = TestClient(main.app)
        headers = {"Authorization": f"Bearer {self.tokens[1]}"}
        with self.sessions() as db:
            for identity, status in ((1, "invalid"), (2, "check_failed")):
                url = db.get(MaterialAsset, identity).url
                db.add(SupplyImageHealth(company_id=1, url=url, url_hash=digest(url), status=status))
            db.commit()
        try:
            self.assertEqual(client.put("/templates/1", headers=headers, json={"product_description": "Updated factual dress description"}).status_code, 200)
            response = client.get("/material-assets", headers=headers, params={"usage_status": "all", "health": "invalid"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([item["id"] for item in response.json()["items"]], [1])
            title = "Printed Long Sleeve Nursing Maxi Dress"
            for path, payload in (("/drafts/from-material-assets", {"template_id": 1, "material_asset_ids": [1], "title": title}),
                ("/drafts/from-material-assets/batch", {"template_id": 1, "groups": [{"material_asset_ids": [1, 2, 3, 4, 5], "title": title}]}),
                ("/drafts/from-product-library", {"template_id": 1, "sources": [{"source_type": "material", "id": 2}], "title": title}),
                ("/drafts/from-product-library/batch", {"template_id": 1, "groups": [{"sources": [{"source_type": "material", "id": identity} for identity in range(1, 6)], "title": title}]})):
                with self.subTest(path=path):
                    response = client.post(path, headers=headers, json=payload)
                    self.assertEqual(response.status_code, 400, response.text)
            with self.sessions() as db:
                self.assertEqual(db.query(ProductDraft).count(), 0)
                self.assertEqual(db.get(MaterialAsset, 1).usage_status, "unused")
                db.get(MaterialAsset, 1).url = "https://img.example/replaced-original.png"
                db.commit()
            response = client.post("/drafts/from-material-assets", headers=headers,
                json={"template_id": 1, "material_asset_ids": [1], "title": title})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["image_urls"], ["https://img.example/replaced-original.png"])
            self.image_mock.assert_not_called()
            self.upload_mock.assert_not_called()
        finally:
            client.close()
            main.app.dependency_overrides.clear()

    def test_grant_revoked_after_authentication_is_rechecked_before_listing_write(self):
        from app import supply_catalog
        original_lock = supply_catalog.lock_company
        def revoke_before_lock(db, company_id):
            with self.sessions() as changed:
                changed.get(User, 3).supply_admin = False
                changed.commit()
            return original_lock(db, company_id)
        with patch("app.supply_catalog.lock_company", side_effect=revoke_before_lock):
            response = self.request("PATCH", "/supply/materials/1", uid=3, json={"supply_listed": False})
        self.assertEqual(response.status_code, 403, response.text)
        with self.sessions() as db:
            self.assertTrue(db.get(MaterialAsset, 1).supply_listed)

    def test_user_cancel_and_suspension_release_pending_excel_blob(self):
        cancelled = self.submit()
        with self.sessions() as db:
            db.get(SupplyJob, cancelled).export_blob = b"unfinished-export"
            db.commit()
        self.assertEqual(self.request("POST", f"/supply/jobs/{cancelled}/cancel", uid=4).status_code, 200)
        suspended = self.submit(key="suspension-request")
        with self.sessions() as db:
            db.get(SupplyJob, suspended).export_blob = b"unfinished-export"
            db.commit()
        self.assertEqual(self.request("PATCH", "/supply/users/4", json={"is_active": False}).status_code, 200)
        with self.sessions() as db:
            for identity in (cancelled, suspended):
                self.assertEqual(db.get(SupplyJob, identity).state, "cancelled")
                self.assertIsNone(db.get(SupplyJob, identity).export_blob)


if __name__ == "__main__":
    unittest.main()
