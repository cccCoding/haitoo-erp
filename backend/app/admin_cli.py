"""平台超级管理员的本地运维命令。"""

from __future__ import annotations

import argparse
from getpass import getpass
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Role, User
from .security import hash_password


class AdminCLIError(ValueError):
    """可直接展示给运维人员的命令错误。"""


def normalize_email(value: str) -> str:
    try:
        return str(TypeAdapter(EmailStr).validate_python(value.strip())).lower()
    except ValidationError as exc:
        raise AdminCLIError("邮箱格式不正确") from exc


def validate_password(value: str) -> None:
    if len(value) < 12:
        raise AdminCLIError("密码至少需要 12 个字符")
    if not any(character.isalpha() for character in value):
        raise AdminCLIError("密码必须包含字母")
    if not any(character.isdigit() for character in value):
        raise AdminCLIError("密码必须包含数字")
    if not any(not character.isalnum() for character in value):
        raise AdminCLIError("密码必须包含特殊字符")


def prompt_new_password() -> str:
    password = getpass("请输入密码：")
    confirmation = getpass("请再次输入密码：")
    if password != confirmation:
        raise AdminCLIError("两次输入的密码不一致")
    validate_password(password)
    return password


def create_super_admin(db: Session, email: str, name: str, password: str) -> User:
    normalized_email = normalize_email(email)
    normalized_name = name.strip()
    if not normalized_name:
        raise AdminCLIError("管理员姓名不能为空")
    validate_password(password)
    if db.scalar(select(User.id).where(func.lower(User.email) == normalized_email)):
        raise AdminCLIError("该邮箱已存在；不会自动修改已有账号的角色")
    user = User(
        company_id=None,
        email=normalized_email,
        name=normalized_name,
        password_hash=hash_password(password),
        role=Role.SUPER_ADMIN,
        is_active=True,
        token_version=0,
    )
    db.add(user)
    db.flush()
    return user


def get_super_admin(db: Session, email: str) -> User:
    normalized_email = normalize_email(email)
    user = db.scalar(select(User).where(func.lower(User.email) == normalized_email))
    if not user or user.role != Role.SUPER_ADMIN or user.company_id is not None:
        raise AdminCLIError("未找到该平台超级管理员")
    return user


def reset_super_admin_password(db: Session, email: str, password: str) -> User:
    validate_password(password)
    user = get_super_admin(db, email)
    user.password_hash = hash_password(password)
    user.token_version += 1
    db.flush()
    return user


def set_super_admin_active(db: Session, email: str, active: bool) -> User:
    user = get_super_admin(db, email)
    if not active and user.is_active:
        active_admins = list(db.scalars(select(User).where(
            User.role == Role.SUPER_ADMIN,
            User.company_id.is_(None),
            User.is_active.is_(True),
        ).with_for_update()).all())
        if len(active_admins) <= 1:
            raise AdminCLIError("不能停用最后一个有效的超级管理员")
    if user.is_active != active:
        user.is_active = active
        user.token_version += 1
        db.flush()
    return user


def list_super_admins(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(
        User.role == Role.SUPER_ADMIN,
        User.company_id.is_(None),
    ).order_by(User.id)).all())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理 Haitoro 平台超级管理员")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-super-admin", help="创建超级管理员")
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--name", required=True)

    subparsers.add_parser("list-super-admins", help="列出超级管理员")

    for command, help_text in (
        ("reset-super-admin-password", "重置超级管理员密码"),
        ("disable-super-admin", "停用超级管理员"),
        ("enable-super-admin", "启用超级管理员"),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument("--email", required=True)
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = SessionLocal()
    try:
        if args.command == "create-super-admin":
            user = create_super_admin(db, args.email, args.name, prompt_new_password())
            db.commit()
            print(f"超级管理员创建成功：{user.email}")
        elif args.command == "list-super-admins":
            users = list_super_admins(db)
            if not users:
                print("当前没有平台超级管理员")
            for user in users:
                status = "启用" if user.is_active else "停用"
                print(f"{user.id}\t{user.email}\t{user.name}\t{status}")
        elif args.command == "reset-super-admin-password":
            user = reset_super_admin_password(db, args.email, prompt_new_password())
            db.commit()
            print(f"密码重置成功，旧登录令牌已失效：{user.email}")
        elif args.command == "disable-super-admin":
            user = set_super_admin_active(db, args.email, False)
            db.commit()
            print(f"超级管理员已停用，旧登录令牌已失效：{user.email}")
        elif args.command == "enable-super-admin":
            user = set_super_admin_active(db, args.email, True)
            db.commit()
            print(f"超级管理员已启用：{user.email}")
        return 0
    except (AdminCLIError, KeyboardInterrupt, EOFError) as exc:
        db.rollback()
        message = str(exc) if str(exc) else "操作已取消"
        print(f"操作失败：{message}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(run())
