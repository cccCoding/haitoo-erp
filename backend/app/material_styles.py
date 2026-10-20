"""公司内按模板共享的永久素材风格，不开放独立创建、改名或删除。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import MaterialAsset, MaterialStyle, Role, User, UserTemplateWhiteImage
from .schemas import MaterialStyleBatchInput
from .security import current_internal_user
from .supply_common import lock_company, timestamp


router = APIRouter()


def style_for_white_image(db, image):
    style = db.scalar(select(MaterialStyle).where(MaterialStyle.source_white_image_id == image.id))
    if style is None:
        style = MaterialStyle(company_id=image.company_id, template_id=image.template_id,
            source_white_image_id=image.id, name=image.name, created_by=image.user_id)
        db.add(style)
        db.flush()
    return style


def validate_style(db, style_id, company_id, template_id):
    if style_id is None:
        return None
    style = db.get(MaterialStyle, style_id)
    if not style or style.company_id != company_id or style.template_id != template_id:
        raise HTTPException(400, "风格不存在或不属于当前公司和产品模板")
    return style


def task_style_id(db, task):
    style_id = (task.parameters or {}).get("style_id")
    if not isinstance(style_id, int) or isinstance(style_id, bool):
        return None
    style = db.get(MaterialStyle, style_id)
    return style.id if style and style.company_id == task.company_id and style.template_id == task.template_id else None


@router.get("/material-styles")
def list_material_styles(template_id: int | None = Query(default=None, ge=1), search: str = "",
                         user: User = Depends(current_internal_user), db: Session = Depends(get_db)):
    counts = select(MaterialAsset.style_id.label("style_id"), func.count().label("count")).where(
        MaterialAsset.company_id == user.company_id).group_by(MaterialAsset.style_id).subquery()
    white_image_url = UserTemplateWhiteImage.image_url if user.role in {Role.COMPANY_ADMIN, Role.SUPER_ADMIN} else case(
        (UserTemplateWhiteImage.user_id == user.id, UserTemplateWhiteImage.image_url), else_=None)
    query = select(MaterialStyle, User.name, UserTemplateWhiteImage.id, counts.c.count, white_image_url).outerjoin(
        User, (User.id == MaterialStyle.created_by) & (User.company_id == MaterialStyle.company_id)).outerjoin(
        UserTemplateWhiteImage, (UserTemplateWhiteImage.id == MaterialStyle.source_white_image_id)
        & (UserTemplateWhiteImage.company_id == MaterialStyle.company_id)
        & UserTemplateWhiteImage.deleted_at.is_(None)).outerjoin(
        counts, counts.c.style_id == MaterialStyle.id).where(MaterialStyle.company_id == user.company_id)
    if template_id is not None:
        query = query.where(MaterialStyle.template_id == template_id)
    if search.strip():
        query = query.where(MaterialStyle.name.contains(search.strip(), autoescape=True))
    return {"items": [{"id": style.id, "template_id": style.template_id, "name": style.name,
        "created_by": style.created_by, "created_by_name": owner_name or "历史记录缺失",
        "source_exists": source_id is not None, "material_count": count or 0,
        "white_image_url": image_url,
        "created_at": timestamp(style.created_at)}
        for style, owner_name, source_id, count, image_url in db.execute(query.order_by(MaterialStyle.id.desc()))]}


@router.patch("/material-assets/style")
def set_material_styles(payload: MaterialStyleBatchInput,
                        user: User = Depends(current_internal_user), db: Session = Depends(get_db)):
    if user.role not in {Role.SUPER_ADMIN, Role.COMPANY_ADMIN, Role.MEMBER, Role.TEAM_LEADER}:
        raise HTTPException(403, "当前账号不能修改素材风格")
    if user.role != Role.SUPER_ADMIN:
        lock_company(db, user.company_id)
    ids = list(dict.fromkeys(payload.material_asset_ids))
    query = select(MaterialAsset).where(MaterialAsset.id.in_(ids))
    if user.role != Role.SUPER_ADMIN:
        query = query.where(MaterialAsset.company_id == user.company_id)
    if user.role in {Role.MEMBER, Role.TEAM_LEADER}:
        query = query.where(MaterialAsset.claimed_by == user.id)
    assets = db.scalars(query.with_for_update()).all()
    if len(assets) != len(ids):
        raise HTTPException(404, "素材不存在或无权修改，整批操作未执行")
    if payload.style_id is not None:
        template_ids = {asset.template_id for asset in assets}
        company_ids = {asset.company_id for asset in assets}
        if len(template_ids) != 1 or None in template_ids or len(company_ids) != 1:
            raise HTTPException(400, "设置风格请选择同一产品模板的素材，整批操作未执行")
        validate_style(db, payload.style_id, next(iter(company_ids)), next(iter(template_ids)))
    for asset in assets:
        asset.style_id = payload.style_id
    db.commit()
    return {"ids": ids, "count": len(ids), "style_id": payload.style_id}
