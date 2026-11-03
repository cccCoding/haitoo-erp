"""标题词库管理权限独立授予，不扩大成员的其他业务权限。"""
from fastapi import Depends, HTTPException

from .models import Role, User
from .security import current_user


def is_title_manager(user):
    return user.role == Role.COMPANY_ADMIN or (
        user.role in (Role.MEMBER, Role.TEAM_LEADER) and user.title_library_admin)


def require_title_manager(user: User = Depends(current_user)) -> User:
    if not is_title_manager(user):
        raise HTTPException(403, '没有标题词库管理权限')
    return user
