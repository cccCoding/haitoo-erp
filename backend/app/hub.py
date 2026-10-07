"""任务按 ERP 账号排队，领取时由本机指定唯一环境；不保存同步环境列表。"""
from datetime import datetime, timedelta, timezone
import secrets
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from .models import Company, HubAgent, HubRuntimeLock, HubUploadAttempt, HubUploadTask, ProductDraft, User
from .schemas import HubTaskClaimInput, HubTaskAction

PROTOCOL = "3"
LEASE_SECONDS = 90
MAX_XLSX_BYTES = 64 * 1024 * 1024

def file_expired(task):
    return bool(task.export_deleted_at or (task.export_expires_at and task.export_expires_at <= datetime.utcnow()))

def require_file(task):
    if file_expired(task):
        raise HTTPException(410, "Excel 已超过 7 天有效期，请重新生成任务")


def milliseconds(value):
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000) if value else None


def record_view(record):
    return {c.name: milliseconds(v) if isinstance(v := getattr(record, c.name), datetime) else v for c in record.__table__.columns}


def task_view(db, task, detail=False):
    result = record_view(task)
    for key in ("export_blob", "claim_token"):
        result.pop(key, None)
    result["file_expired"] = file_expired(task)
    agent = db.get(HubAgent, task.agent_id) if task.agent_id else None
    result["agent_name"] = agent.name if agent else None
    if not detail:
        result.pop("logs", None)
    else:
        result["attempts"] = []
        attempts = db.scalars(select(HubUploadAttempt).where(HubUploadAttempt.task_id == task.id).order_by(HubUploadAttempt.number)).all()
        for attempt in attempts:
            worker = db.get(HubAgent, attempt.agent_id) if attempt.agent_id else None
            result["attempts"].append(record_view(attempt) | {"agent_name": worker.name if worker else None})
    return result


def lock_row(db, model, identity):
    # SQLite 忽略 FOR UPDATE；先获得写锁。生产 MySQL/MariaDB 使用行锁。
    pk = next(iter(model.__table__.primary_key.columns))
    if db.bind.dialect.name == "sqlite":
        db.execute(update(model).where(pk == identity).values({pk.name: identity}))
    return db.scalar(select(model).where(pk == identity).with_for_update().execution_options(populate_existing=True))


def runtime_guard(db, company_id, container_code, create=False):
    # 公司锁保证首次插入唯一运行键和所有任务状态变更遵循同一锁顺序。
    lock_row(db, Company, company_id)
    if not container_code:
        return None
    guard = db.scalar(select(HubRuntimeLock).where(
        HubRuntimeLock.company_id == company_id, HubRuntimeLock.container_code == container_code).with_for_update())
    if not guard and create:
        guard = HubRuntimeLock(company_id=company_id, container_code=container_code)
        db.add(guard); db.flush()
    return guard


def append_log(db, task, stage, message):
    entry = {"at": milliseconds(datetime.utcnow()), "stage": stage, "message": message}
    task.logs = list(task.logs or []) + [entry]
    if task.attempt_id:
        attempt = db.get(HubUploadAttempt, task.attempt_id)
        if attempt:
            attempt.logs = list(attempt.logs or []) + [entry]


def finish_attempt(db, task, status):
    if task.attempt_id:
        attempt = db.get(HubUploadAttempt, task.attempt_id)
        if attempt:
            attempt.status, attempt.completed_at = status, datetime.utcnow()


def expire_locked_task(db, task):
    if task.status == "running" and task.lease_expires_at and task.lease_expires_at <= datetime.utcnow():
        task.status, task.stage = "awaiting_attention", "connection_lost"
        task.failure_reason = "执行器失联，提交结果未知；请核对平台后人工处理"
        task.claim_token, task.lease_expires_at = None, None
        append_log(db, task, task.stage, task.failure_reason)
        finish_attempt(db, task, "awaiting_attention")


def sweep_expired(db):
    expired = db.execute(select(HubUploadTask.company_id, HubUploadTask.id).where(
        HubUploadTask.status == "queued", HubUploadTask.export_expires_at <= datetime.utcnow()).order_by(HubUploadTask.company_id, HubUploadTask.id)).all()
    for company_id, task_id in expired:
        runtime_guard(db, company_id, None)
        task = lock_row(db, HubUploadTask, task_id)
        if task and task.status == "queued" and file_expired(task):
            task.status, task.stage = "expired", "file_expired"
            task.failure_reason = "Excel 已超过 7 天有效期，请重新生成任务"
            task.completed_at = datetime.utcnow()
            append_log(db, task, task.stage, task.failure_reason)
    rows = db.execute(select(HubUploadTask.company_id, HubUploadTask.container_code, HubUploadTask.id).where(
        HubUploadTask.status == "running", HubUploadTask.lease_expires_at <= datetime.utcnow()
    ).order_by(HubUploadTask.company_id, HubUploadTask.container_code, HubUploadTask.id)).all()
    for company_id, code, task_id in rows:
        runtime_guard(db, company_id, code)
        # 升级时同环境可能有多条历史活动任务，不能只处理锁指向的第一条。
        task = lock_row(db, HubUploadTask, task_id)
        if task:
            expire_locked_task(db, task)
    db.commit()


def list_tasks(db, user_id, company_id, page=1, page_size=25, status=None, *, company_scope=False, creator_id=None):
    sweep_expired(db)
    condition = [HubUploadTask.company_id == company_id]
    if not company_scope:
        condition.append(HubUploadTask.created_by == user_id)
    if creator_id is not None:
        condition.append(HubUploadTask.created_by == creator_id)
    if status:
        condition.append(HubUploadTask.status == status)
    total = db.scalar(select(func.count()).select_from(HubUploadTask).where(*condition))
    tasks = db.scalars(select(HubUploadTask).where(*condition).order_by(HubUploadTask.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    creator_ids = {task.created_by for task in tasks}
    creators = dict(db.execute(select(User.id, User.name).where(User.company_id == company_id, User.id.in_(creator_ids))).all()) if creator_ids else {}
    items = [task_view(db, task) | {"created_by_name": creators.get(task.created_by), "product_count": len(task.draft_ids or [])} for task in tasks]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def own_task(db, task_id, user_id, company_id):
    task = db.get(HubUploadTask, task_id)
    if not task or task.created_by != user_id or task.company_id != company_id:
        raise HTTPException(404, "上品任务不存在或无权操作")
    return task


def detail(db, task_id, user_id, company_id):
    sweep_expired(db)
    return task_view(db, own_task(db, task_id, user_id, company_id), True)


def publish_drafts(db, task, operator_id):
    db.execute(update(ProductDraft).where(ProductDraft.id.in_(task.draft_ids), ProductDraft.company_id == task.company_id).values(status="published", workflow_stage="published", updated_by=operator_id))


def task_action(db, task_id, user_id, company_id, action, payload: HubTaskAction):
    original = own_task(db, task_id, user_id, company_id)
    guard = runtime_guard(db, company_id, original.container_code)
    task = lock_row(db, HubUploadTask, task_id)
    expire_locked_task(db, task)
    if task.status == "running":
        raise HTTPException(409, "任务仍在运行，请等待执行结束")
    finish_attempt(db, task, task.status)
    if action == "cancel":
        if task.status not in {"queued", "awaiting_attention", "failed"}:
            raise HTTPException(409, "当前任务不能取消")
        task.status, task.stage, task.completed_at = "cancelled", "cancelled", datetime.utcnow()
    elif action in {"retry", "confirm-submitted"}:
        if not payload.confirmed_platform_checked:
            raise HTTPException(400, "请先核对平台结果，避免重复提交")
        if task.status not in {"awaiting_attention", "failed"}:
            raise HTTPException(409, "当前任务不能执行此操作")
        if action == "retry":
            require_file(task)
            task.status, task.stage, task.failure_reason, task.agent_id = "queued", "queued", None, None
            task.claimed_at, task.completed_at = None, None
            task.environment_id, task.environment_name, task.container_code = None, None, None
        else:
            task.status, task.stage = "completed", "manually_confirmed"
            task.submitted_at = task.submitted_at or datetime.utcnow()
            task.completed_at = datetime.utcnow()
            publish_drafts(db, task, user_id)
    else:
        raise HTTPException(404, "未知任务操作")
    task.resolved_by, task.resolved_at = user_id, datetime.utcnow()
    task.claim_token, task.lease_expires_at = None, None
    # 人工动作只写任务日志，不能覆盖已经结束的执行尝试。
    task.attempt_id = None
    append_log(db, task, task.stage, {"retry": "已核对平台，人工重新排队", "cancel": "人工取消任务", "confirm-submitted": "已核对平台，人工确认已提交"}[action])
    if guard and guard.task_id == task.id:
        guard.task_id = None
    db.commit()
    return task_view(db, task, True)


def claim(db, agent, payload: HubTaskClaimInput):
    code = payload.container_code.strip()
    if not code or not payload.confirmed_local:
        raise HTTPException(400, "请在本地工作页选择并确认一个 TikTok 本土环境")
    sweep_expired(db)
    lock_row(db, Company, agent.company_id)
    lock_row(db, HubAgent, agent.id)
    if db.scalar(select(HubUploadTask.id).where(HubUploadTask.agent_id == agent.id, HubUploadTask.status == "running")):
        db.commit(); return {"task": None}
    task_id = db.scalar(select(HubUploadTask.id).where(HubUploadTask.company_id == agent.company_id,
        HubUploadTask.created_by == agent.user_id, HubUploadTask.status == "queued",
        HubUploadTask.environment_id.is_(None)).order_by(HubUploadTask.id).limit(1))
    if task_id is None:
        db.commit(); return {"task": None}
    guard = runtime_guard(db, agent.company_id, code, create=True)
    if guard.task_id:
        db.commit(); return {"task": None}
    if db.scalar(select(HubUploadTask.id).where(HubUploadTask.company_id == agent.company_id,
            HubUploadTask.container_code == code, HubUploadTask.status.in_(["running", "awaiting_attention"]))):
        db.commit(); return {"task": None}
    task = lock_row(db, HubUploadTask, task_id)
    if task.status != "queued":
        db.commit(); return {"task": None}
    require_file(task)
    now = datetime.utcnow()
    task.agent_id, task.status, task.stage = agent.id, "running", "claimed"
    task.container_code, task.environment_name = code, payload.environment_name.strip() or code
    task.claim_token, task.claimed_at = secrets.token_urlsafe(32), now
    task.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    number = (db.scalar(select(func.max(HubUploadAttempt.number)).where(HubUploadAttempt.task_id == task.id)) or 0) + 1
    attempt = HubUploadAttempt(task_id=task.id, agent_id=agent.id, number=number,
        container_code=code, environment_name=task.environment_name)
    db.add(attempt); db.flush(); task.attempt_id = attempt.id
    guard.task_id = task.id
    append_log(db, task, "claimed", f"本地执行器已领取任务，执行环境：{task.environment_name}（{code}）")
    db.commit()
    return {"task": task_view(db, task), "claim_token": task.claim_token, "hubstudio": {"container_code": code}}


def claimed_task(db, agent, task_id, token):
    original = db.get(HubUploadTask, task_id)
    if not original or original.company_id != agent.company_id or original.created_by != agent.user_id:
        raise HTTPException(404, "任务不存在")
    guard = runtime_guard(db, original.company_id, original.container_code)
    task = lock_row(db, HubUploadTask, task_id)
    expire_locked_task(db, task)
    if not guard or guard.task_id != task.id or task.agent_id != agent.id or task.claim_token != token or task.status != "running":
        db.commit()
        raise HTTPException(409, "任务领取已失效，请人工核对")
    return task, guard


def heartbeat(db, agent, task_id=None, token=None):
    if task_id is not None:
        task, _ = claimed_task(db, agent, task_id, token)
        task.lease_expires_at = datetime.utcnow() + timedelta(seconds=LEASE_SECONDS)
    db.commit()
    return {"status": "online"}


def report(db, agent, task_id, token, payload):
    task, guard = claimed_task(db, agent, task_id, token)
    task.status, task.stage = payload.status, payload.stage
    task.failure_reason = payload.message if payload.status in {"failed", "awaiting_attention"} else None
    append_log(db, task, payload.stage, payload.message or "")
    if payload.status != "running":
        finish_attempt(db, task, payload.status)
        task.claim_token, task.lease_expires_at = None, None
        if payload.status == "completed":
            task.submitted_at, task.completed_at = datetime.utcnow(), datetime.utcnow()
            publish_drafts(db, task, task.created_by)
            guard.task_id = None
        elif payload.status == "failed":
            task.completed_at = datetime.utcnow(); guard.task_id = None
        # 待人工处理保留环境锁，防止下一项重复提交。
    db.commit()
    return task_view(db, task, True)
