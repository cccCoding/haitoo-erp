import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.models import Company, MaterialAsset, OperatorGroup, PodTask, ProductDraft, ProductTemplate, Role, Shop, User, UserShop
from app.security import create_access_token


class OperatorGroupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([
                Company(id=1, name="公司一"), Company(id=2, name="公司二"),
                User(id=1, company_id=1, email="admin@example.com", name="管理员", user_code="AD", password_hash="x", role=Role.COMPANY_ADMIN),
                User(id=2, company_id=1, email="first@example.com", name="甲", user_code="AA", password_hash="x", role=Role.MEMBER),
                User(id=3, company_id=1, email="second@example.com", name="乙", user_code="BB", password_hash="x", role=Role.MEMBER),
                User(id=4, company_id=1, email="third@example.com", name="丙", user_code="CC", password_hash="x", role=Role.MEMBER),
                User(id=5, company_id=2, email="foreign@example.com", name="外部", user_code="DD", password_hash="x", role=Role.MEMBER),
                User(id=6, company_id=2, email="foreign-admin@example.com", name="外部管理员", user_code="EE", password_hash="x", role=Role.COMPANY_ADMIN),
                ProductTemplate(id=1, company_id=1, name="模板"),
                Shop(id=1, company_id=1, name="店铺一"), Shop(id=2, company_id=1, name="店铺二"),
                UserShop(user_id=2, shop_id=1), UserShop(user_id=3, shop_id=2),
                MaterialAsset(id=1, company_id=1, template_id=1, claimed_by=2, url="https://example.com/1.jpg", name="甲素材", sku="AA01"),
                MaterialAsset(id=2, company_id=1, template_id=1, claimed_by=3, url="https://example.com/2.jpg", name="乙素材", sku="BB01"),
                PodTask(id=1, company_id=1, template_id=1, created_by=2, parameters={}, result_urls=[]),
                PodTask(id=2, company_id=1, template_id=1, created_by=3, parameters={}, result_urls=[]),
                ProductDraft(id=1, company_id=1, template_id=1, title="甲草稿", created_by=2, updated_by=2),
                ProductDraft(id=2, company_id=1, template_id=1, title="乙草稿", created_by=3, updated_by=3),
            ])
            db.commit()
            self.tokens = {user_id: create_access_token(db.get(User, user_id)) for user_id in (1, 2, 3, 5, 6)}

        def override_get_db():
            with self.sessions() as db:
                yield db

        main.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def request(self, method: str, path: str, *, user_id: int = 1, json=None):
        return self.client.request(method, path, json=json, headers={"Authorization": f"Bearer {self.tokens[user_id]}"})

    def create_group(self, name="一组", leader_id=2):
        response = self.request("POST", "/operator-groups", json={"name": name, "leader_user_id": leader_id})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def test_group_lifecycle_and_leader_handover(self) -> None:
        group_id = self.create_group()
        self.assertEqual(self.request("POST", "/operator-groups", json={"name": "一组", "leader_user_id": 3}).status_code, 400)
        self.assertEqual(self.request("PATCH", f"/operator-groups/{group_id}", json={"name": "新一组"}).json()["name"], "新一组")
        self.assertEqual(self.request("PUT", "/members/3", json={"group_id": group_id}).status_code, 200)
        self.assertEqual(self.request("PUT", "/members/2", json={"is_active": False}).status_code, 400)
        self.assertEqual(self.request("PUT", "/members/2", json={"role": "member"}).status_code, 400)
        self.assertEqual(self.request("PUT", "/members/3", json={"role": "team_leader", "group_id": group_id}).status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.get(User, 2).role, Role.MEMBER)
            self.assertEqual(db.get(User, 2).group_id, group_id)
            self.assertEqual(db.get(User, 3).role, Role.TEAM_LEADER)
            self.assertEqual(db.get(OperatorGroup, group_id).leader_user_id, 3)
        self.assertEqual(self.request("DELETE", f"/operator-groups/{group_id}").json()["affected_members"], 2)
        with self.sessions() as db:
            self.assertIsNone(db.get(OperatorGroup, group_id))
            for user_id in (2, 3):
                self.assertEqual(db.get(User, user_id).role, Role.MEMBER)
                self.assertIsNone(db.get(User, user_id).group_id)

    def test_company_isolation_and_group_assignment(self) -> None:
        group_id = self.create_group()
        self.assertEqual(self.request("POST", "/operator-groups", user_id=6, json={"name": "一组", "leader_user_id": 5}).status_code, 200)
        self.assertEqual(self.request("POST", "/operator-groups", json={"name": "跨公司", "leader_user_id": 5}).status_code, 400)
        self.assertEqual(len(self.request("GET", "/operator-groups", user_id=6).json()), 1)
        self.assertEqual(self.request("PATCH", f"/operator-groups/{group_id}", user_id=6, json={"name": "越权"}).status_code, 404)
        self.assertEqual(self.request("DELETE", f"/operator-groups/{group_id}", user_id=6).status_code, 404)
        self.assertEqual(self.request("PUT", "/members/5", json={"role": "team_leader", "group_id": group_id}).status_code, 404)
        self.assertEqual(self.request("PUT", "/members/3", user_id=6, json={"group_id": group_id}).status_code, 404)
        self.assertEqual(self.request("GET", "/operator-groups", user_id=2).status_code, 403)
        self.assertEqual(self.request("PUT", "/members/1", json={"group_id": group_id}).status_code, 404)

    def test_new_member_can_join_or_lead_existing_group(self) -> None:
        group_id = self.create_group()
        created = self.request("POST", "/members", json={
            "name": "新成员", "user_code": "NM", "email": "new@example.com", "password": "Password123",
            "role": "member", "group_id": group_id,
        })
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["group_id"], group_id)
        promoted = self.request("POST", "/members", json={
            "name": "新组长", "user_code": "NL", "email": "new-leader@example.com", "password": "Password123",
            "role": "team_leader", "group_id": group_id,
        })
        self.assertEqual(promoted.status_code, 200, promoted.text)
        with self.sessions() as db:
            self.assertEqual(db.get(OperatorGroup, group_id).leader_user_id, promoted.json()["id"])
            self.assertEqual(db.get(User, 2).role, Role.MEMBER)
            self.assertEqual(db.get(User, promoted.json()["id"]).role, Role.TEAM_LEADER)
        self.assertEqual(self.request("POST", "/members", json={
            "name": "无组长", "user_code": "NG", "email": "invalid@example.com", "password": "Password123",
            "role": "team_leader",
        }).status_code, 400)

    def test_leader_keeps_member_business_scope(self) -> None:
        group_id = self.create_group()
        self.assertEqual(self.request("PUT", "/members/3", json={"group_id": group_id}).status_code, 200)
        self.assertEqual(self.request("GET", "/me", user_id=2).json()["user"]["group_name"], "一组")
        self.assertEqual([item["id"] for item in self.request("GET", "/shops", user_id=2).json()], [1])
        self.assertEqual([item["id"] for item in self.request("GET", "/tasks", user_id=2).json()["items"]], [1])
        self.assertEqual([item["id"] for item in self.request("GET", "/material-assets", user_id=2).json()["items"]], [1])
        self.assertEqual([item["id"] for item in self.request("GET", "/drafts", user_id=2).json()["items"]], [1])
        self.assertEqual(self.request("GET", "/product-library/stagnant", user_id=2).status_code, 200)
        self.assertEqual(self.request("GET", "/product-library/new-images", user_id=2).status_code, 200)
        self.assertEqual(self.request("GET", "/members", user_id=2).status_code, 403)
        self.assertEqual(self.request("GET", "/shops/manage", user_id=2).status_code, 403)
        self.assertEqual(self.request("PUT", "/shops/1/managers", json={"member_ids": [2, 3]}).status_code, 200)
        self.assertEqual(len(self.request("GET", "/shops/manage").json()[0]["manager_users"]), 2)


if __name__ == "__main__":
    unittest.main()
