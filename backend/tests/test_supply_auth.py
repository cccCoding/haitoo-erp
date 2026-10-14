from datetime import datetime, timedelta, timezone
import unittest

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Company, Role, User
from app.security import create_access_token, current_internal_user, current_user, require_roles
from app.supply_accounts import add_calendar_months, supply_user_is_expired


class SupplyAccountCalendarTests(unittest.TestCase):
    def test_calendar_month_clamps_hong_kong_month_end_and_returns_naive_utc(self):
        # 香港 1 月 31 日 23:15 延长一个自然月到香港 2 月 28 日 23:15。
        self.assertEqual(add_calendar_months(datetime(2026, 1, 31, 15, 15), 1), datetime(2026, 2, 28, 15, 15))
        self.assertEqual(add_calendar_months(datetime(2024, 2, 29, 1, 2, tzinfo=timezone.utc), 12), datetime(2025, 2, 28, 1, 2))

    def test_utc_date_boundary_uses_local_month(self):
        # UTC 1 月 30 日 20:00 是香港 1 月 31 日 04:00。
        self.assertEqual(add_calendar_months(datetime(2026, 1, 30, 20), 1), datetime(2026, 2, 27, 20))

    def test_requires_positive_integer_months(self):
        for months in (0, -1, 1.5, True, "12"):
            with self.subTest(months=months), self.assertRaises(ValueError):
                add_calendar_months(datetime(2026, 1, 1), months)

    def test_expiry_boundary_is_inclusive(self):
        user = User(supply_expires_at=datetime(2026, 1, 1))
        self.assertTrue(supply_user_is_expired(user, datetime(2026, 1, 1, tzinfo=timezone.utc)))
        self.assertFalse(supply_user_is_expired(user, datetime(2025, 12, 31, 23, 59, 59)))
        self.assertTrue(supply_user_is_expired(User(supply_expires_at=None)))


class SupplyAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(Company(id=1, name="Company", is_active=True))
        self.user = User(id=1, company_id=1, email="supply@example.com", name="Supply", password_hash="unused", role=Role.SUPPLY_USER,
                         supply_expires_at=datetime.utcnow() + timedelta(days=30))
        self.db.add(self.user)
        self.db.commit()
        self.credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token(self.user))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def assert_unauthorized(self):
        with self.assertRaises(HTTPException) as context:
            current_user(self.credentials, self.db)
        self.assertEqual(context.exception.status_code, 401)

    def test_valid_supply_user_authenticates_but_cannot_use_internal_dependency(self):
        user = current_user(self.credentials, self.db)
        self.assertEqual(user.id, 1)
        with self.assertRaises(HTTPException) as context:
            current_internal_user(user)
        self.assertEqual(context.exception.status_code, 403)
        with self.assertRaises(HTTPException) as context:
            require_roles(Role.COMPANY_ADMIN)(user)
        self.assertEqual(context.exception.status_code, 403)

    def test_existing_roles_remain_allowed_by_internal_dependency(self):
        for role in (Role.SUPER_ADMIN, Role.COMPANY_ADMIN, Role.MEMBER, Role.TEAM_LEADER):
            with self.subTest(role=role):
                user = User(role=role)
                self.assertIs(current_internal_user(user), user)

    def test_expired_missing_expiry_and_suspended_accounts_are_rejected(self):
        self.user.supply_expires_at = datetime.utcnow() - timedelta(seconds=1)
        self.assert_unauthorized()
        self.user.supply_expires_at = None
        self.assert_unauthorized()
        self.user.supply_expires_at = datetime.utcnow() + timedelta(days=30)
        self.user.is_active = False
        self.assert_unauthorized()

    def test_inactive_or_missing_company_is_rejected(self):
        self.db.get(Company, 1).is_active = False
        self.assert_unauthorized()
        self.db.get(Company, 1).is_active = True
        self.user.company_id = None
        self.assert_unauthorized()

    def test_revoked_token_and_invalid_token_are_rejected(self):
        self.user.token_version += 1
        self.assert_unauthorized()
        self.credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="broken")
        self.assert_unauthorized()


if __name__ == "__main__":
    unittest.main()
