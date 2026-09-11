import unittest

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.admin_cli import (
    AdminCLIError,
    create_super_admin,
    list_super_admins,
    reset_super_admin_password,
    set_super_admin_active,
    validate_password,
)
from app.database import Base
from app.models import Company, Role, User
from app.main import initialize_system_defaults
from app.security import create_access_token, current_user, verify_password


class AdminCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)

    def test_create_super_admin_normalizes_email_and_sets_platform_scope(self) -> None:
        with Session(self.engine) as db:
            user = create_super_admin(db, " Owner@Example.COM ", " 平台管理员 ", "SecurePass123!")
            db.commit()

            self.assertEqual(user.email, "owner@example.com")
            self.assertEqual(user.name, "平台管理员")
            self.assertEqual(user.role, Role.SUPER_ADMIN)
            self.assertIsNone(user.company_id)
            self.assertTrue(user.is_active)
            self.assertTrue(verify_password("SecurePass123!", user.password_hash))

    def test_system_defaults_do_not_create_company_or_user(self) -> None:
        with Session(self.engine) as db:
            initialize_system_defaults(db)

            self.assertEqual(len(db.scalars(select(Company)).all()), 0)
            self.assertEqual(len(db.scalars(select(User)).all()), 0)

    def test_create_never_promotes_an_existing_user(self) -> None:
        with Session(self.engine) as db:
            company = Company(name="现有公司")
            db.add(company)
            db.flush()
            db.add(User(
                company_id=company.id,
                email="owner@example.com",
                name="现有成员",
                password_hash="unused",
                role=Role.MEMBER,
            ))
            db.commit()

            with self.assertRaisesRegex(AdminCLIError, "不会自动修改"):
                create_super_admin(db, "OWNER@example.com", "管理员", "SecurePass123!")
            existing = db.scalar(select(User).where(User.email == "owner@example.com"))
            self.assertEqual(existing.role, Role.MEMBER)

    def test_password_policy(self) -> None:
        for password in ("Short1!", "onlyletters!!", "12345678901!", "LettersAnd123"):
            with self.subTest(password=password), self.assertRaises(AdminCLIError):
                validate_password(password)

    def test_reset_password_invalidates_existing_tokens(self) -> None:
        with Session(self.engine) as db:
            user = create_super_admin(db, "owner@example.com", "管理员", "SecurePass123!")
            db.commit()
            token = create_access_token(user)
            reset_super_admin_password(db, user.email, "Replacement456!")
            db.commit()

            self.assertEqual(user.token_version, 1)
            self.assertTrue(verify_password("Replacement456!", user.password_hash))
            with self.assertRaises(HTTPException) as context:
                current_user(
                    credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
                    db=db,
                )
            self.assertEqual(context.exception.status_code, 401)

    def test_cannot_disable_last_active_super_admin(self) -> None:
        with Session(self.engine) as db:
            user = create_super_admin(db, "first@example.com", "第一管理员", "SecurePass123!")
            db.commit()
            with self.assertRaisesRegex(AdminCLIError, "最后一个"):
                set_super_admin_active(db, user.email, False)

            second = create_super_admin(db, "second@example.com", "第二管理员", "SecurePass456!")
            db.commit()
            set_super_admin_active(db, user.email, False)
            db.commit()
            self.assertFalse(user.is_active)
            self.assertEqual(user.token_version, 1)
            self.assertEqual(len(list_super_admins(db)), 2)


if __name__ == "__main__":
    unittest.main()
