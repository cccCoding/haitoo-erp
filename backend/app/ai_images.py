"""Grsai 直存候选、成员配置与正式文件准备接口。"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from . import ai_image_storage as storage
from .config import get_settings
from .database import SessionLocal, get_db
from .models import (AIImageCandidate, AIImagePreparation, AIImagePreparationItem,
    Company, ImageFile, PodTask, Role, TaskStatus, User)
from .security import current_creative_user, require_roles

router = APIRouter()


def now():
    return datetime.utcnow()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def check_access(db, candidate, user):
    from .main import CREATIVE_ROLES, can_access_task
    task = db.get(PodTask, candidate.task_id)
    if user.role not in CREATIVE_ROLES or not can_access_task(task, user) or candidate.company_id != task.company_id:
        raise HTTPException(404, "候选图片不存在或无权操作")
    if (task.storage_context or {}).get("run_id") != candidate.run_id:
        raise HTTPException(409, "候选图片属于已结束的执行批次，请刷新任务")
    if task.status not in {TaskStatus.AWAITING_SELECTION, TaskStatus.COMPLETED}:
        raise HTTPException(409, "图片任务尚未进入可审核状态")
    return task


def freeze_storage_context(db, task):
    task = db.scalar(select(PodTask).where(PodTask.id == task.id).with_for_update()
        .execution_options(populate_existing=True))
    if task.storage_context is not None:
        context = dict(task.storage_context)
        db.commit()
        return context
    settings = get_settings()
    owner, company = db.get(User, task.created_by), db.get(Company, task.company_id)
    mode = owner.grsai_storage_mode if owner else "legacy"
    oss_id = owner.grsai_storage_id if mode == "custom" else company.grsai_storage_id if company and mode == "inherit" else None
    context = {"mode": "legacy", "run_id": uuid4().hex}
    if getattr(settings, "grsai_direct_storage_enabled", False) and oss_id:
        _, bucket, _, base, _ = storage.configuration(settings)
        context.update(mode="direct", oss_id=oss_id, bucket=bucket, public_base_url=base,
            path=f"pending/company/{task.company_id}/user/{task.created_by}/tasks/{task.id}/{context['run_id']}")
    task.storage_context = context
    db.commit()
    return context


def persist_candidates(task_id, provider_task_id, run_id, urls, session_factory=SessionLocal):
    """先落原地址，再 HEAD；断线后无需重新查询有两小时期限的生成结果。"""
    from .ai_providers import ProviderTaskTerminalError
    with session_factory() as db:
        task = db.scalar(select(PodTask).where(PodTask.id == task_id).with_for_update())
        if (not task or task.status != TaskStatus.RUNNING or task.provider_task_id != provider_task_id
                or (task.storage_context or {}).get("run_id") != run_id):
            return None
        if task.provider_result_urls is None:
            task.provider_result_urls = list(urls)
            db.commit()
        urls = list(task.provider_result_urls)
        context, company_id = dict(task.storage_context), task.company_id
        db.commit()
    client, _, _, _, _ = storage.configuration()
    for position, url in enumerate(urls):
        if not isinstance(url, str) or len(url) > 500:
            raise ProviderTaskTerminalError("Grsai 返回的图片地址格式或长度不受支持")
        with session_factory() as db:
            existing = db.scalar(select(AIImageCandidate).where(AIImageCandidate.task_id == task_id,
                AIImageCandidate.run_id == run_id, AIImageCandidate.url_hash == digest(url)))
            if existing:
                continue
        key = storage.key_from_url(url, context["public_base_url"])
        values = dict(company_id=company_id, task_id=task_id, run_id=run_id, position=position,
            source_url=url, url_hash=digest(url), bucket=context["bucket"], object_key=key or "", state="pending")
        try:
            if not key or not key.startswith(context["path"] + "/"):
                raise storage.InvalidCandidate("图片地址不属于当前任务的 pending 路径，请检查 Grsai 存储配置")
            info = storage.head(client, context["bucket"], key)
            size, mime, uploaded, etag = storage.metadata(info, key)
            values.update(size_bytes=size, mime_type=mime, uploaded_at=uploaded, etag=etag,
                expires_at=uploaded + timedelta(days=30))
            if values["expires_at"] <= now():
                raise storage.InvalidCandidate("候选图片已超过 30 天", "expired")
        except storage.InvalidCandidate as exc:
            values.update(state=exc.state, error=str(exc))
        with session_factory() as db:
            task = db.get(PodTask, task_id)
            if (not task or task.status != TaskStatus.RUNNING or task.provider_task_id != provider_task_id
                    or (task.storage_context or {}).get("run_id") != run_id):
                return None
            try:
                with db.begin_nested():
                    db.add(AIImageCandidate(**values))
                    db.flush()
            except IntegrityError:
                pass
            db.commit()
    return urls


def candidate_for_url(db, company_id, url):
    row = db.scalar(select(AIImageCandidate).where(AIImageCandidate.company_id == company_id,
        AIImageCandidate.url_hash == digest(url), AIImageCandidate.source_url == url).order_by(AIImageCandidate.id.desc()))
    return row


def require_prepared(db, company_id, url):
    """通用导入也经过此门禁；pending 绝不退回下载转存。"""
    candidate = candidate_for_url(db, company_id, url)
    if candidate:
        if candidate.image_file_id:
            image = db.get(ImageFile, candidate.image_file_id)
            if image and image.company_id == company_id:
                return image
            raise HTTPException(409, "候选图片的正式文件登记缺失")
        if candidate.state == "expired" or candidate.expires_at and candidate.expires_at <= now():
            raise HTTPException(410, "候选图片已过期，无法采用")
        if candidate.state == "invalid":
            raise HTTPException(422, candidate.error or "候选图片不可采用")
        raise HTTPException(409, {"code": "IMAGE_PREPARATION_REQUIRED", "candidate_ids": [candidate.id],
            "message": "请先准备选中的图片"})
    if storage.is_pending_url(url):
        raise HTTPException(409, "该 pending 图片未登记为当前公司的候选结果")
    return None


def source_result_url(db, task, url):
    if url in (task.result_urls or []):
        return url
    image_ids = select(ImageFile.id).where(ImageFile.company_id == task.company_id, ImageFile.url == url)
    candidate = db.scalar(select(AIImageCandidate).where(AIImageCandidate.company_id == task.company_id,
        AIImageCandidate.task_id == task.id, AIImageCandidate.run_id == (task.storage_context or {}).get("run_id"),
        AIImageCandidate.image_file_id.in_(image_ids)))
    return candidate.source_url if candidate and candidate.source_url in (task.result_urls or []) else None


def generation_reference(db, company_id, url):
    candidate = candidate_for_url(db, company_id, url)
    if candidate:
        if candidate.image_file_id:
            return require_prepared(db, company_id, url).url
        if candidate.state in {"invalid", "expired"} or candidate.expires_at and candidate.expires_at <= now():
            raise HTTPException(400, "参考候选图片已过期或不可用，请重新选择")
        return url
    if storage.is_pending_url(url):
        raise HTTPException(400, "参考图片不是当前公司的有效候选图")
    return url


def candidate_views(task):
    db = object_session(task)
    if db is None or not (task.storage_context or {}).get("mode") == "direct":
        return []
    key = task.id, task.storage_context["run_id"]
    if key not in db.info.get("ai_candidate_views", {}):
        prefetch_candidate_views(db, [task])
    return db.info["ai_candidate_views"][key]


def prefetch_candidate_views(db, tasks):
    """列表与批量审核按页读取，避免 1000 张图片产生逐行 SQL 查询。"""
    owners = {task.id: task for task in tasks if (task.storage_context or {}).get("mode") == "direct"}
    cache = db.info.setdefault("ai_candidate_views", {})
    for task in owners.values():
        cache[task.id, task.storage_context["run_id"]] = []
    if not owners:
        return
    rows = list(db.scalars(select(AIImageCandidate).where(AIImageCandidate.task_id.in_(owners))
        .order_by(AIImageCandidate.task_id, AIImageCandidate.position)))
    ids = [row.image_file_id for row in rows if row.image_file_id]
    files = {f.id: f for f in db.scalars(select(ImageFile).where(ImageFile.id.in_(ids)))} if ids else {}
    for row in rows:
        task = owners[row.task_id]
        if row.company_id != task.company_id or row.run_id != task.storage_context["run_id"]:
            continue
        file = files.get(row.image_file_id)
        if file and file.company_id != row.company_id:
            file = None
        state = "ready" if file else "expired" if row.expires_at and row.expires_at <= now() else row.state
        cache[task.id, row.run_id].append({"id": row.id, "source_url": row.source_url, "display_url": file.url if file else row.source_url,
            "state": state, "error": row.error, "expires_at": int(row.expires_at.replace(tzinfo=timezone.utc).timestamp() * 1000) if row.expires_at else None})


def register_formal(db, company_id, key, url, size, mime, source_type, source_ref):
    from .image_files import add_address
    image = db.scalar(select(ImageFile).where(ImageFile.company_id == company_id,
        ImageFile.source_type == source_type, ImageFile.source_ref == str(source_ref)))
    if image is None:
        try:
            with db.begin_nested():
                image = ImageFile(company_id=company_id, sha256=None, object_key=key, url=url,
                    size_bytes=size, mime_type=mime, source_type=source_type, source_ref=str(source_ref),
                    validation_method="provider_metadata")
                db.add(image)
                db.flush()
        except IntegrityError:
            image = db.scalar(select(ImageFile).where(ImageFile.company_id == company_id,
                ImageFile.source_type == source_type, ImageFile.source_ref == str(source_ref)))
            if image is None:
                raise
    add_address(db, company_id, image.url, image)
    return image


def copy_registered_file(db, company_id, source_file, source_url):
    """跨公司复制已登记的无哈希正式文件，不通过服务器传输正文。"""
    from .image_files import add_address
    ref = str(source_file.id)
    image = db.scalar(select(ImageFile).where(ImageFile.company_id == company_id,
        ImageFile.source_type == "copied_file", ImageFile.source_ref == ref))
    if image is None:
        source_key, mime, size = source_file.object_key, source_file.mime_type, source_file.size_bytes
        db.commit()
        client, _, bucket, _, _ = storage.configuration()
        info = storage.head(client, bucket, source_key)
        if info.get("ContentLength") != size:
            raise HTTPException(409, "来源正式文件大小发生变化")
        key = f"images/company/{company_id}/copies/{ref}{storage.IMAGE_SUFFIXES[mime]}"
        key, url = storage.copy_object(source_bucket=bucket, source_key=source_key, etag=info["ETag"],
            size=size, mime=mime, target_key=key, source_type="copied_file", source_ref=ref)
        image = register_formal(db, company_id, key, url, size, mime, "copied_file", ref)
    add_address(db, company_id, source_url, image)
    db.commit()
    return image


class CompanyStorageInput(BaseModel):
    storage_id: str | None = Field(default=None, max_length=120)

    @field_validator("storage_id")
    @classmethod
    def validate_id(cls, value):
        value = value.strip() if value else None
        if value and not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("存储库 ID 只能包含字母、数字、下划线或短横线")
        return value or None


class MemberStorageInput(CompanyStorageInput):
    mode: str = Field(pattern="^(inherit|custom|legacy)$")

    @model_validator(mode="after")
    def check_custom(self):
        if self.mode == "custom" and not self.storage_id:
            raise ValueError("单独配置时必须填写存储库 ID")
        return self


class PreparationInput(BaseModel):
    candidate_ids: list[int] = Field(min_length=1, max_length=1000)
    request_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


def company_config(db, user):
    from .main import CREATIVE_ROLES
    company = db.get(Company, user.company_id)
    overrides = db.scalar(select(func.count()).select_from(User).where(
        User.company_id == user.company_id, User.role.in_(CREATIVE_ROLES), User.grsai_storage_mode != "inherit"))
    return {"storage_id": company.grsai_storage_id, "direct_enabled": get_settings().grsai_direct_storage_enabled,
        "override_count": overrides}


@router.get("/company/grsai-storage")
def get_company_storage(user=Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    return company_config(db, user)


@router.put("/company/grsai-storage")
def set_company_storage(payload: CompanyStorageInput, user=Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    db.get(Company, user.company_id).grsai_storage_id = payload.storage_id
    db.commit()
    return company_config(db, user)


@router.put("/members/{member_id}/grsai-storage")
def set_member_storage(member_id: int, payload: MemberStorageInput,
                       user=Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    from .main import get_company_credential_user
    member = get_company_credential_user(db, user, member_id)
    member.grsai_storage_mode = payload.mode
    member.grsai_storage_id = payload.storage_id if payload.mode == "custom" else None
    db.commit()
    return {"member_id": member.id, "mode": member.grsai_storage_mode, "storage_id": member.grsai_storage_id}


@router.post("/members/grsai-storage/use-company-default")
def reset_members_storage(user=Depends(require_roles(Role.COMPANY_ADMIN)), db: Session = Depends(get_db)):
    from .main import CREATIVE_ROLES
    changed = db.execute(update(User).where(User.company_id == user.company_id, User.role.in_(CREATIVE_ROLES),
        or_(User.grsai_storage_mode != "inherit", User.grsai_storage_id.is_not(None))).values(
            grsai_storage_mode="inherit", grsai_storage_id=None)).rowcount
    db.commit()
    return {"updated": changed, **company_config(db, user)}


def job_candidates(db, job):
    return list(db.scalars(select(AIImageCandidate).join(AIImagePreparationItem,
        AIImagePreparationItem.candidate_id == AIImageCandidate.id).where(
        AIImagePreparationItem.job_id == job.id).order_by(AIImageCandidate.id)))


def job_view(db, job):
    items = []
    candidates = job_candidates(db, job)
    ids = [row.image_file_id for row in candidates if row.image_file_id]
    files = {file.id: file for file in db.scalars(select(ImageFile).where(ImageFile.id.in_(ids),
        ImageFile.company_id == job.company_id))} if ids else {}
    for candidate in candidates:
        state = candidate.state
        if candidate.expires_at and candidate.expires_at <= now() and not candidate.image_file_id and state not in {"queued", "preparing"}:
            state = "expired"
        image = files.get(candidate.image_file_id)
        items.append({"candidate_id": candidate.id, "state": state, "error": candidate.error,
            "source_url": candidate.source_url, "url": image.url if image else None})
    counts = Counter(item["state"] for item in items)
    ready = counts["ready"]
    failed = sum(counts[state] for state in ("failed", "invalid", "expired"))
    finished = ready + failed == len(items)
    state = "ready" if ready == len(items) else "partial_failed" if finished and ready else "failed" if finished else "running"
    return {"id": job.id, "state": state, "total": len(items), "ready": ready, "failed": failed, "items": items}


@router.post("/ai-image-preparations", status_code=202)
def create_preparation(payload: PreparationInput, user=Depends(current_creative_user), db: Session = Depends(get_db)):
    ids = sorted(set(payload.candidate_ids))
    rows = list(db.scalars(select(AIImageCandidate).where(AIImageCandidate.id.in_(ids)).with_for_update()))
    if len(rows) != len(ids):
        raise HTTPException(404, "包含不存在的候选图片")
    # 保留批量加载对象的强引用，供下面的权限校验复用 identity map。
    tasks = list(db.scalars(select(PodTask).where(PodTask.id.in_({row.task_id for row in rows}))))
    for candidate in rows:
        check_access(db, candidate, user)
    request_digest = digest(json.dumps(ids))
    job = db.scalar(select(AIImagePreparation).where(AIImagePreparation.company_id == user.company_id,
        AIImagePreparation.user_id == user.id, AIImagePreparation.request_key == payload.request_key))
    if job:
        if job.request_digest != request_digest:
            raise HTTPException(409, "请求标识已用于不同选图集合")
        return job_view(db, job)
    try:
        with db.begin_nested():
            job = AIImagePreparation(company_id=user.company_id, user_id=user.id,
                request_key=payload.request_key, request_digest=request_digest)
            db.add(job)
            db.flush()
            db.add_all([AIImagePreparationItem(job_id=job.id, candidate_id=i) for i in ids])
    except IntegrityError:
        db.rollback()
        return create_preparation(payload, user, db)
    for candidate in rows:
        if candidate.state == "pending":
            candidate.state, candidate.requested_by, candidate.available_at = "queued", user.id, now()
    db.commit()
    return job_view(db, job)


def accessible_job(db, job_id, user):
    job = db.get(AIImagePreparation, job_id)
    if not job or job.company_id != user.company_id or (job.user_id != user.id and user.role != Role.COMPANY_ADMIN):
        raise HTTPException(404, "图片准备任务不存在")
    candidates = job_candidates(db, job)
    tasks = list(db.scalars(select(PodTask).where(PodTask.id.in_({row.task_id for row in candidates}))))
    for candidate in candidates:
        check_access(db, candidate, user)
    return job


@router.get("/ai-image-preparations/{job_id}")
def get_preparation(job_id: int, user=Depends(current_creative_user), db: Session = Depends(get_db)):
    return job_view(db, accessible_job(db, job_id, user))


@router.post("/ai-image-preparations/{job_id}/retry")
def retry_preparation(job_id: int, user=Depends(current_creative_user), db: Session = Depends(get_db)):
    job = accessible_job(db, job_id, user)
    for candidate in job_candidates(db, job):
        if candidate.state == "failed":
            candidate.state, candidate.attempts, candidate.error = "queued", 0, None
            candidate.requested_by, candidate.available_at = user.id, now()
    db.commit()
    return job_view(db, job)
