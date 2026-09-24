import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.models import Company, Role, User
from app.security import create_access_token, hash_password, verify_password


class AdminPasswordUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            db.add_all([Company(id=1, name="公司一"), Company(id=2, name="公司二")])
            db.add_all([
                User(id=1, company_id=None, email="super@example.com", name="Super", password_hash=hash_password("SuperPass123"), role=Role.SUPER_ADMIN),
                User(id=2, company_id=1, email="admin@example.com", name="Admin", password_hash=hash_password("OldPassword123"), role=Role.COMPANY_ADMIN),
                User(id=3, company_id=1, email="member@example.com", name="Member", password_hash=hash_password("MemberPass123"), role=Role.MEMBER),
                User(id=4, company_id=2, email="other@example.com", name="Other", password_hash=hash_password("OtherPass123"), role=Role.COMPANY_ADMIN),
            ])
            db.commit()
            self.super_token = create_access_token(db.get(User, 1))
            self.admin_token = create_access_token(db.get(User, 2))

        def override_get_db():
            with self.session_factory() as db:
                yield db

        main.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(main.app)
        self.url = "/admin/companies/1/admins/2/password"

    def tearDown(self) -> None:
        self.client.close()
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def put(self, url: str, password: str, token: str | None = None):
        return self.client.put(url, json={"password": password}, headers={"Authorization": f"Bearer {token or self.super_token}"})

    def test_super_admin_can_reset_password_and_old_session_expires(self) -> None:
        response = self.put(self.url, "NewPassword456")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"id": 2})
        with self.session_factory() as db:
            admin = db.get(User, 2)
            self.assertTrue(verify_password("NewPassword456", admin.password_hash))
            self.assertEqual(admin.token_version, 1)
        self.assertEqual(self.client.get("/me", headers={"Authorization": f"Bearer {self.admin_token}"}).status_code, 401)
        self.assertEqual(self.client.post("/auth/login", json={"email": "admin@example.com", "password": "OldPassword123"}).status_code, 401)
        self.assertEqual(self.client.post("/auth/login", json={"email": "admin@example.com", "password": "NewPassword456"}).status_code, 200)

    def test_rejects_wrong_role_company_and_short_password(self) -> None:
        self.assertEqual(self.put(self.url, "NewPassword456", self.admin_token).status_code, 403)
        self.assertEqual(self.put("/admin/companies/2/admins/2/password", "NewPassword456").status_code, 404)
        self.assertEqual(self.put("/admin/companies/1/admins/3/password", "NewPassword456").status_code, 404)
        self.assertEqual(self.put("/admin/companies/1/admins/4/password", "NewPassword456").status_code, 404)
        self.assertEqual(self.put(self.url, "short").status_code, 422)
        with self.session_factory() as db:
            self.assertTrue(verify_password("OldPassword123", db.get(User, 2).password_hash))


if __name__ == "__main__":
    unittest.main()
