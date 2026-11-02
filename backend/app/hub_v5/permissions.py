"""公司开关、成员操作授权和数据查看范围分别校验。"""
from fastapi import HTTPException
from ..models import Role
from .models import MatrixMemberPermission

ROLES = {Role.COMPANY_ADMIN, Role.MEMBER, Role.TEAM_LEADER}


def access(db, user):
    if user is None:return {"enabled":False,"collect_enabled":False,"listing_enabled":False,"view_scope":"own","revision":0,"is_admin":False}
    administrator = user.role == Role.COMPANY_ADMIN
    row = db.get(MatrixMemberPermission, user.id)
    valid = bool(user.is_active and user.role in ROLES and user.company_id)
    granted = bool(valid and (administrator or row and row.company_id == user.company_id and row.enabled))
    return {"enabled": granted, "collect_enabled": granted and bool(administrator or row.collect_enabled),
        "listing_enabled": granted and bool(administrator or row.listing_enabled),
        "view_scope": "company" if administrator else row.view_scope if granted else "own",
        "revision": row.revision if row and row.company_id == user.company_id else 0, "is_admin": administrator}


def require_access(db, user):
    value = access(db, user)
    if not value["enabled"]:
        raise HTTPException(403, "尚未获得矩阵使用授权，请联系公司管理员")
    return value


def tasks_allowed(db, user, tasks):
    value = access(db, user)
    return value["enabled"] and all(value["collect_enabled"] if task == "shop.collect" else value["listing_enabled"] for task in tasks)


def require_tasks(db, user, tasks):
    value = require_access(db, user)
    if "shop.collect" in tasks and not value["collect_enabled"]:
        raise HTTPException(403, "未获店铺采集授权")
    if "listing.catalog" in tasks and not value["listing_enabled"]:
        raise HTTPException(403, "未获自动上品授权")


def company_view(db, user):
    value = access(db, user)
    return value["enabled"] and value["view_scope"] == "company"
