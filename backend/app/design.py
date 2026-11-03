"""美工权限、模板公开、结果审核和创作统计。"""
from datetime import datetime, time, timedelta, timezone
import hashlib
from tempfile import SpooledTemporaryFile
from zoneinfo import ZoneInfo
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from .database import get_db
from .models import (CreativeImageEvent, DesignGroup, DesignTemplateVisibility, ImageFile,
                     MaterialAsset, PodTask, ProductTemplate, Role, TaskResultReview, User)
from .schemas import OperatorGroupCreate, OperatorGroupUpdate
from .security import current_creative_user, require_roles
from .storage import StorageError, read_image_object
from .supply_common import lock_company, timestamp

router = APIRouter(tags=['美工与运营统计'])
DESIGN_ROLES = (Role.DESIGNER, Role.DESIGN_LEADER)
CREATIVE_ROLES = (Role.COMPANY_ADMIN, Role.MEMBER, Role.TEAM_LEADER, *DESIGN_ROLES)
HK = ZoneInfo('Asia/Hong_Kong')


def public_template_ids(company_id):
    return select(DesignTemplateVisibility.template_id).where(
        DesignTemplateVisibility.company_id == company_id, DesignTemplateVisibility.is_public.is_(True))


def visible_template_ids(user):
    stmt = select(ProductTemplate.id).where(or_(ProductTemplate.is_platform.is_(True),
        ProductTemplate.company_id == user.company_id))
    if user.role == Role.DESIGNER:
        stmt = stmt.where(ProductTemplate.id.in_(public_template_ids(user.company_id)))
    return stmt


def sku_values(query):
    if not isinstance(query, str):
        return []
    return list(dict.fromkeys(line.strip() for line in (query or '').splitlines() if line.strip()))


def design_member_ids(user):
    # 不仅校验 group_id，还校验该组确实由当前账号负责。
    return select(User.id).join(DesignGroup, DesignGroup.id == User.design_group_id).where(
        User.company_id == user.company_id, User.role.in_(DESIGN_ROLES),
        DesignGroup.company_id == user.company_id, DesignGroup.leader_user_id == user.id)


def task_read_filters(user, sku_query=None):
    filters = [] if user.role == Role.SUPER_ADMIN else [PodTask.company_id == user.company_id]
    skus = sku_values(sku_query)
    if user.role in (Role.MEMBER, Role.TEAM_LEADER):
        filters.append(PodTask.created_by == user.id)
    elif user.role == Role.DESIGNER and not skus:
        filters.append(PodTask.created_by == user.id)
    elif user.role == Role.DESIGN_LEADER and not skus:
        filters.append(or_(PodTask.created_by == user.id, PodTask.created_by.in_(design_member_ids(user))))
    if skus:
        filters.extend([PodTask.task_type == 'sku_image', PodTask.id.in_(select(MaterialAsset.source_task_id).where(
            MaterialAsset.company_id == user.company_id, MaterialAsset.sku.in_(skus),
            MaterialAsset.source_task_id.is_not(None)))])
    return filters


def readable_task(db, user, task_id, sku_query=None):
    task = db.scalar(select(PodTask).where(PodTask.id == task_id, *task_read_filters(user, sku_query)))
    if task is None:
        raise HTTPException(404, '任务不存在')
    return task


def can_manage_task(user, task):
    return user.role == Role.SUPER_ADMIN or (task.company_id == user.company_id and (
        user.role == Role.COMPANY_ADMIN or task.created_by == user.id))


def can_review_task(db, user, task):
    if task.company_id != user.company_id or task.task_type != 'sku_image':
        return False
    if user.role == Role.COMPANY_ADMIN:
        return True
    if user.role != Role.DESIGN_LEADER:
        return False
    return db.scalar(select(User.id).where(User.id == task.created_by,
        User.id.in_(design_member_ids(user)))) is not None


def enrich_task_views(db, user, tasks, views):
    ids = [task.id for task in tasks]
    if not ids:
        return views
    assets = db.scalars(select(MaterialAsset).where(MaterialAsset.source_task_id.in_(ids),
        MaterialAsset.company_id.in_({task.company_id for task in tasks}), MaterialAsset.sku.is_not(None))).all()
    reviews = db.execute(select(TaskResultReview, User.name).outerjoin(User, User.id == TaskResultReview.marked_by)
        .where(TaskResultReview.task_id.in_(ids))).all()
    reviewable_ids = set(db.scalars(select(PodTask.id).where(PodTask.id.in_(ids),
        PodTask.company_id == user.company_id, PodTask.created_by.in_(design_member_ids(user))))) if user.role == Role.DESIGN_LEADER else set()
    public_ids = set(db.scalars(public_template_ids(user.company_id)))
    for task, view in zip(tasks, views):
        view['design_public'] = task.template_id in public_ids
        view['can_manage'] = can_manage_task(user, task)
        view['can_review'] = task.task_type == 'sku_image' and (user.role == Role.COMPANY_ADMIN or task.id in reviewable_ids)
        view['adopted_images'] = [{'asset_id': a.id, 'sku': a.sku, 'url': a.url} for a in assets
                                  if a.source_task_id == task.id and a.company_id == task.company_id]
        view['result_reviews'] = [{'url': row.result_url, 'rejected': row.rejected, 'marked_by': row.marked_by,
            'marked_by_name': name or '历史成员', 'marked_at': timestamp(row.marked_at)}
            for row, name in reviews if row.task_id == task.id and row.result_url in (task.result_urls or [])]
        view['rejected_count'] = sum(row['rejected'] for row in view['result_reviews'])
    return views


class VisibilityInput(BaseModel):
    is_public: bool


@router.patch('/templates/{template_id}/design-visibility')
def set_visibility(template_id: int, payload: VisibilityInput,
                   user=Depends(require_roles(Role.COMPANY_ADMIN, Role.DESIGN_LEADER)), db: Session = Depends(get_db)):
    lock_company(db, user.company_id)
    if db.scalar(select(ProductTemplate.id).where(ProductTemplate.id == template_id,
            ProductTemplate.id.in_(visible_template_ids(user)))) is None:
        raise HTTPException(404, '产品模板不存在')
    row = db.get(DesignTemplateVisibility, (user.company_id, template_id))
    if row is None:
        row = DesignTemplateVisibility(company_id=user.company_id, template_id=template_id)
        db.add(row)
    row.is_public = payload.is_public
    db.commit()
    return {'id': template_id, 'design_public': row.is_public}


def company_design_group(db, company_id, group_id):
    group = db.scalar(select(DesignGroup).where(DesignGroup.id == group_id,
        DesignGroup.company_id == company_id).with_for_update())
    if not group:
        raise HTTPException(404, '美工组不存在')
    return group


def apply_design_membership(db, member, role, group_id, active):
    if member.role == Role.DESIGN_LEADER and member.design_group_id is not None and (role != Role.DESIGN_LEADER or group_id != member.design_group_id):
        raise HTTPException(400, '请先为原美工组更换组长')
    if role not in DESIGN_ROLES:
        if group_id is not None:
            raise HTTPException(400, '运营成员不能加入美工组')
        member.design_group_id = None
        return
    group = company_design_group(db, member.company_id, group_id) if group_id else None
    if role == Role.DESIGN_LEADER:
        if not group or not active:
            raise HTTPException(400, '美工组长必须启用且选择美工组')
        old_leader = db.get(User, group.leader_user_id)
        if old_leader and old_leader.id != member.id:
            old_leader.role = Role.DESIGNER
        group.leader_user_id = member.id
    member.design_group_id = group_id


@router.get('/design-groups')
def list_design_groups(user=Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    return [{'id': g.id, 'name': g.name, 'leader_user_id': g.leader_user_id} for g in db.scalars(
        select(DesignGroup).where(DesignGroup.company_id == user.company_id).order_by(DesignGroup.id))]


@router.post('/design-groups')
def create_design_group(payload: OperatorGroupCreate, user=Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    lock_company(db, user.company_id)
    leader = db.get(User, payload.leader_user_id)
    if not leader or leader.company_id != user.company_id or leader.role != Role.DESIGNER or not leader.is_active:
        raise HTTPException(400, '请选择本公司已启用的普通美工担任组长')
    group = DesignGroup(company_id=user.company_id, name=payload.name, leader_user_id=leader.id)
    db.add(group)
    try:
        db.flush()
        leader.design_group_id, leader.role = group.id, Role.DESIGN_LEADER
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(400, '本公司已有同名美工组') from exc
    return {'id': group.id, 'name': group.name, 'leader_user_id': group.leader_user_id}


@router.patch('/design-groups/{group_id}')
def rename_design_group(group_id: int, payload: OperatorGroupUpdate,
                        user=Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    lock_company(db, user.company_id)
    group = company_design_group(db, user.company_id, group_id)
    group.name = payload.name
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(400, '本公司已有同名美工组') from exc
    return {'id': group.id, 'name': group.name}


@router.delete('/design-groups/{group_id}')
def delete_design_group(group_id: int, user=Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    lock_company(db, user.company_id)
    group = company_design_group(db, user.company_id, group_id)
    members = db.scalars(select(User).where(User.company_id == user.company_id,
        User.design_group_id == group.id)).all()
    for member in members:
        member.design_group_id, member.role = None, Role.DESIGNER
    db.delete(group)
    db.commit()
    return {'deleted': True, 'affected_members': len(members)}


@router.get('/design-team-members')
def design_team_members(user=Depends(require_roles(Role.DESIGN_LEADER)), db: Session = Depends(get_db)):
    return [{'id': m.id, 'name': m.name, 'role': m.role.value} for m in db.scalars(select(User).where(
        or_(User.id == user.id, User.id.in_(design_member_ids(user))), User.company_id == user.company_id))]


class ReviewItem(BaseModel):
    task_id: int = Field(ge=1)
    url: str = Field(min_length=1, max_length=500)


class ReviewInput(BaseModel):
    items: list[ReviewItem] = Field(min_length=1, max_length=1000)
    rejected: bool


@router.post('/tasks/result-reviews')
def review_results(payload: ReviewInput, user=Depends(require_roles(Role.COMPANY_ADMIN, Role.DESIGN_LEADER)), db: Session = Depends(get_db)):
    lock_company(db, user.company_id)
    tasks = {task.id: task for task in db.scalars(select(PodTask).where(
        PodTask.company_id == user.company_id, PodTask.id.in_({item.task_id for item in payload.items})))}
    for item in payload.items:
        task = tasks.get(item.task_id)
        if not task or not can_review_task(db, user, task):
            raise HTTPException(404, '任务不存在或无权标记')
        if item.url not in (task.result_urls or []):
            raise HTTPException(400, '包含不属于该任务的结果图')
    for task_id, url in dict.fromkeys((item.task_id, item.url) for item in payload.items):
        key = hashlib.sha256(url.encode()).hexdigest()
        row = db.scalar(select(TaskResultReview).where(TaskResultReview.task_id == task_id, TaskResultReview.result_hash == key))
        if row is None:
            row = TaskResultReview(company_id=user.company_id, task_id=task_id, result_hash=key, result_url=url)
            db.add(row)
        row.rejected, row.marked_by, row.marked_at = payload.rejected, user.id, datetime.utcnow()
    db.commit()
    return {'updated': len(set((item.task_id, item.url) for item in payload.items))}


def record_adoption(db, asset):
    if not asset.source_task_id or not asset.sku or asset.source_type != 'ai_created':
        return
    task = db.get(PodTask, asset.source_task_id)
    if not task or task.company_id != asset.company_id or task.task_type != 'sku_image':
        return
    owner = db.get(User, task.created_by)
    if owner is None:
        return
    db.add(CreativeImageEvent(company_id=asset.company_id, user_id=owner.id, user_name=owner.name,
        kind='adopt', sku=asset.sku, task_id=task.id, asset_id=asset.id, occurred_at=asset.created_at))


class DownloadInput(BaseModel):
    task_ids: list[int] = Field(min_length=1, max_length=1000)
    sku_query: str | None = Field(default=None, max_length=10000)
    request_key: str = Field(min_length=1, max_length=128)


@router.post('/tasks/download')
def download_results(payload: DownloadInput, user=Depends(current_creative_user), db: Session = Depends(get_db)):
    task_ids = set(payload.task_ids)
    tasks = db.scalars(select(PodTask).where(PodTask.id.in_(task_ids), PodTask.task_type == 'sku_image',
        *task_read_filters(user, payload.sku_query))).all()
    if len(tasks) != len(task_ids):
        raise HTTPException(404, '任务不存在或无权下载')
    assets = db.scalars(select(MaterialAsset).where(MaterialAsset.company_id == user.company_id,
        MaterialAsset.source_task_id.in_(task_ids), MaterialAsset.sku.is_not(None)).order_by(MaterialAsset.id)).all()
    if not assets:
        raise HTTPException(400, '所选任务没有已采用且有 SKU 的图片')
    # 只从已登记的公司图片读取；不接受客户端提供的任意图片 URL。
    from .image_files import by_url
    files = []
    seen = set()
    for asset in assets:
        if asset.sku in seen:
            continue
        if (any(ord(char) < 32 or char in '<>:"/\\|?*' for char in asset.sku)
                or asset.sku.endswith((' ', '.'))):
            raise HTTPException(400, '图片 SKU 无法用于文件名')
        image = db.get(ImageFile, asset.image_file_id) if asset.image_file_id else by_url(db, user.company_id, asset.url)
        if not image or image.company_id != user.company_id or not image.object_key:
            raise HTTPException(409, f'{asset.sku} 缺少已登记图片文件，请先完成图片回填')
        extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}.get(image.mime_type)
        if extension is None:
            raise HTTPException(400, '不支持的图片格式')
        files.append((asset.id, asset.sku, asset.source_task_id, image.object_key, extension))
        seen.add(asset.sku)
    # 释放读取事务后再等待对象存储；ZIP 超过 8MB 自动落临时文件。
    db.commit()
    archive = SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as output:
            for _, sku, _, object_key, extension in files:
                output.writestr(f'{sku}.{extension}', read_image_object(object_key, max_bytes=32 * 1024 * 1024))
        # 唯一约束按成员 + SKU 保证永久去重，包括并发下载和请求重放。
        for asset_id, sku, task_id, _, _ in files:
            try:
                with db.begin_nested():
                    if db.scalar(select(CreativeImageEvent.id).where(CreativeImageEvent.company_id == user.company_id,
                            CreativeImageEvent.user_id == user.id, CreativeImageEvent.kind == 'download', CreativeImageEvent.sku == sku)) is None:
                        db.add(CreativeImageEvent(company_id=user.company_id, user_id=user.id, user_name=user.name,
                            kind='download', sku=sku, task_id=task_id, asset_id=asset_id, request_key=payload.request_key))
                        db.flush()
            except IntegrityError:
                pass
        db.commit()
        archive.seek(0)
    except Exception as exc:
        archive.close()
        db.rollback()
        if isinstance(exc, StorageError):
            raise HTTPException(503, '读取图片失败，请稍后重试') from exc
        raise

    def content():
        try:
            while chunk := archive.read(1024 * 1024):
                yield chunk
        finally:
            archive.close()
    return StreamingResponse(content(), media_type='application/zip',
        headers={'Content-Disposition': 'attachment; filename="sku-images.zip"'},
        background=BackgroundTask(archive.close))


@router.get('/operation-statistics')
def operation_statistics(period: str = Query('7', pattern='^(today|yesterday|7|15|30)$'),
                         member_id: int | None = Query(None, ge=1),
                         user=Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    today = datetime.now(HK).date()
    end = today - timedelta(days=1) if period == 'yesterday' else today
    start = end - timedelta(days=(int(period) - 1 if period.isdigit() else 0))
    utc_start = datetime.combine(start, time.min, HK).astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = datetime.combine(end + timedelta(days=1), time.min, HK).astimezone(timezone.utc).replace(tzinfo=None)
    members = db.scalars(select(User).where(User.company_id == user.company_id, User.role.in_(CREATIVE_ROLES)).order_by(User.id)).all()
    if member_id is not None and member_id not in {m.id for m in members}:
        raise HTTPException(404, '成员不存在')
    daily = {(start + timedelta(days=i)).isoformat(): {'adopted_count': 0, 'download_count': 0}
             for i in range((end - start).days + 1)}
    counts = {m.id: {'adopted_count': 0, 'download_count': 0} for m in members}
    # 按小时先聚合，避免为 30 天统计加载每张图片的事件；再按香港日期归并。
    bind = db.get_bind().dialect.name
    hour = func.strftime('%Y-%m-%d %H:00:00', CreativeImageEvent.occurred_at) if bind == 'sqlite' else func.date_format(CreativeImageEvent.occurred_at, '%Y-%m-%d %H:00:00')
    rows = db.execute(select(CreativeImageEvent.user_id, CreativeImageEvent.kind, hour, func.count()).where(
        CreativeImageEvent.company_id == user.company_id, CreativeImageEvent.user_id.in_(counts),
        CreativeImageEvent.occurred_at >= utc_start, CreativeImageEvent.occurred_at < utc_end)
        .group_by(CreativeImageEvent.user_id, CreativeImageEvent.kind, hour)).all()
    for owner, kind, at, count in rows:
        key = 'adopted_count' if kind == 'adopt' else 'download_count'
        counts[owner][key] += count
        if member_id is None or member_id == owner:
            day = datetime.strptime(at, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).astimezone(HK).date().isoformat()
            daily[day][key] += count
    return {'period': period, 'timezone': 'Asia/Hong_Kong', 'date_from': start.isoformat(), 'date_to': end.isoformat(),
        'summary': {key: sum(day[key] for day in daily.values()) for key in ('adopted_count', 'download_count')},
        'members': [{'id': m.id, 'name': m.name, 'role': m.role.value, 'is_active': m.is_active, **counts[m.id]} for m in members],
        'daily': [{'date': day, **values} for day, values in daily.items()],
        'history_note': '历史采用按仍存在的 AI SKU 素材入库时间回填；已删除素材无法恢复。下载自功能上线起记录，同一成员同一 SKU 仅首次下载计数。'}
