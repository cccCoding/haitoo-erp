import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base
from app.models import Company, Role, User
from app.schemas import MiaoshouAccountUpdate


class MiaoshouAccountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            db.add_all([
                Company(id=1, name="Test Company"),
                User(
                    id=1,
                    company_id=1,
                    email="admin@example.com",
                    name="Admin",
                    password_hash="x",
                    role=Role.COMPANY_ADMIN,
                ),
            ])
            db.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_company_admin_configures_own_account_without_exposing_secret(self) -> None:
        with self.session_factory() as db:
            admin = db.get(User, 1)
            response = main.update_miaoshou_account(
                MiaoshouAccountUpdate(app_id=" app-id ", app_secret=" app-secret "), user=admin, db=db,
            )
            company = db.get(Company, 1)
            me_response = main.me(user=admin, db=db)
            self.assertEqual(company.miaoshou_app_id, "app-id")
            self.assertNotIn("app-secret", company.miaoshou_secret_encrypted)

        self.assertEqual(response, {"company_id": 1, "configured": True})
        self.assertEqual(
            me_response["company"],
            {"id": 1, "name": "Test Company", "miaoshou_configured": True},
        )
        self.assertNotIn("miaoshou_app_id", me_response["company"])


if __name__ == "__main__":
    unittest.main()
