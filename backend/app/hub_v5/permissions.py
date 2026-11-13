"""公司开关、统一矩阵授权和数据查看范围分别校验。"""
from fastapi import HTTPException
from ..models import Role
from ..supply_accounts import supply_user_is_expired
from .models import MatrixMemberPermission

ROLES = {Role.COMPANY_ADMIN, Role.MEMBER, Role.TEAM_LEADER, Role.SUPPLY_USER}


def access(db, user):
    if user is None:return {"enabled":False,"collect_enabled":False,"listing_enabled":False,"view_scope":"own","revision":0,"is_admin":False}
    administrator = user.role == Role.COMPANY_ADMIN
    row = db.get(MatrixMemberPermission, user.id)
    valid = bool(user.is_active and user.role in ROLES and user.company_id
                 and (user.role != Role.SUPPLY_USER or not supply_user_is_expired(user)))
    granted = bool(valid and (administrator or row and row.company_id == user.company_id and row.enabled))
    return {"enabled": granted, "collect_enabled": granted,
        "listing_enabled": granted,
        "view_scope": "own",
        "revision": row.revision if row and row.company_id == user.company_id else 0, "is_admin": administrator}


def require_access(db, user):
    value = access(db, user)
    if not value["enabled"]:
        raise HTTPException(403, "尚未获得矩阵使用授权，请联系公司管理员")
    return value


def tasks_allowed(db, user, tasks):
    return access(db, user)["enabled"]


def require_tasks(db, user, tasks):
    require_access(db, user)
