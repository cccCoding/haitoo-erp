from datetime import datetime, timedelta
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.models import Company, Role, User
from app.security import create_access_token


class MyAccountTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.user_ids = {}
        self.tokens = {}
        with self.sessions() as db:
            db.add(Company(id=1, name="测试公司"))
            for user_id, role in enumerate(Role, start=1):
                user = User(
                    id=user_id, company_id=None if role == Role.SUPER_ADMIN else 1,
                    email=f"{role.value}@example.com", name=role.value, user_code=f"{user_id:02}",
                    password_hash="unused", role=role,
                    supply_expires_at=datetime.utcnow() + timedelta(days=30),
                )
                db.add(user)
                self.user_ids[role] = user_id
            db.commit()
            for role, user_id in self.user_ids.items():
                self.tokens[role] = create_access_token(db.get(User, user_id))

        def override_get_db():
            with self.sessions() as db:
                yield db

        main.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def patch_account(self, role, payload):
        return self.client.patch("/me", json=payload, headers={"Authorization": f"Bearer {self.tokens[role]}"})

    def test_company_admin_can_update_own_account(self):
        response = self.patch_account(Role.COMPANY_ADMIN, {"name": "新管理员", "user_code": "AD"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "新管理员")
        self.assertEqual(response.json()["user_code"], "AD")
        with self.sessions() as db:
            user = db.get(User, self.user_ids[Role.COMPANY_ADMIN])
            self.assertEqual((user.name, user.user_code), ("新管理员", "AD"))

    def test_other_roles_cannot_change_name_or_user_code(self):
        for role in Role:
            if role == Role.COMPANY_ADMIN:
                continue
            for payload in ({"name": "越权修改"}, {"user_code": "ZZ"}, {"name": "越权修改", "user_code": "ZZ"}):
                with self.subTest(role=role, payload=payload):
                    response = self.patch_account(role, payload)
                    self.assertEqual(response.status_code, 403, response.text)
                    with self.sessions() as db:
                        user = db.get(User, self.user_ids[role])
                        self.assertEqual((user.name, user.user_code), (role.value, f"{user.id:02}"))

    def test_admin_cannot_use_a_member_code(self):
        response = self.patch_account(Role.COMPANY_ADMIN, {"name": "新管理员", "user_code": f"{self.user_ids[Role.MEMBER]:02}"})
        self.assertEqual(response.status_code, 400, response.text)
        with self.sessions() as db:
            self.assertEqual(db.get(User, self.user_ids[Role.COMPANY_ADMIN]).name, Role.COMPANY_ADMIN.value)


if __name__ == "__main__":
    unittest.main()
