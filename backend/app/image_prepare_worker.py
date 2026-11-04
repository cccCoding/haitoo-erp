"""按图片领取、独立续租的 R2 复制 Worker；全局并发通过队列设置行串行分配。"""
import asyncio
from datetime import timedelta
import json
import logging
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from . import ai_image_storage as storage
from .ai_images import check_access, now, register_formal
from .config import get_settings
from .database import SessionLocal
from .models import AIImageCandidate, Company, TaskQueueSetting, User

logger = logging.getLogger(__name__)
RETRY_DELAYS = (2, 5, 15)


class LostLease(Exception):
    pass


def claim_one(session_factory=SessionLocal):
    settings = get_settings()
    with session_factory() as db:
        # 该单例在初始化时已建立；与结果并发配置共用短时分配锁。
        if db.scalar(select(TaskQueueSetting).where(TaskQueueSetting.id == 1).with_for_update()) is None:
            return None
        at = now()
        live = (AIImageCandidate.state == "preparing", AIImageCandidate.lease_expires_at > at)
        if db.scalar(select(func.count()).select_from(AIImageCandidate).where(*live)) >= settings.image_prepare_concurrency:
            return None
        active = aliased(AIImageCandidate)
        company_occupied = select(func.count()).select_from(active).where(
            active.company_id == AIImageCandidate.company_id, active.state == "preparing",
            active.lease_expires_at > at).correlate(AIImageCandidate).scalar_subquery()
        rows = db.scalars(select(AIImageCandidate).where(company_occupied < settings.image_prepare_company_concurrency, or_(
            (AIImageCandidate.state == "queued") & (AIImageCandidate.available_at <= at),
            (AIImageCandidate.state == "preparing") & (AIImageCandidate.lease_expires_at <= at),
        )).order_by(AIImageCandidate.available_at, AIImageCandidate.id).limit(1).with_for_update()).all()
        for candidate in rows:
            occupied = db.scalar(select(func.count()).select_from(AIImageCandidate).where(*live,
                AIImageCandidate.company_id == candidate.company_id))
            if occupied >= settings.image_prepare_company_concurrency:
                continue
            candidate.state, candidate.lease_owner = "preparing", uuid4().hex
            candidate.lease_epoch += 1
            candidate.lease_expires_at = at + timedelta(seconds=settings.image_prepare_lease_seconds)
            candidate.attempts += 1
            identity = (candidate.id, candidate.lease_owner, candidate.lease_epoch)
            db.commit()
            return identity
    return None


def locked(db, identity):
    candidate_id, owner, epoch = identity
    candidate = db.scalar(select(AIImageCandidate).where(AIImageCandidate.id == candidate_id).with_for_update())
    if (not candidate or candidate.state != "preparing" or candidate.lease_owner != owner
            or candidate.lease_epoch != epoch or not candidate.lease_expires_at or candidate.lease_expires_at <= now()):
        raise LostLease()
    return candidate


def authorized(db, candidate):
    user, company = db.get(User, candidate.requested_by), db.get(Company, candidate.company_id)
    if not user or not user.is_active or not company or not company.is_active:
        raise HTTPException(403, "操作账号或公司已停用")
    check_access(db, candidate, user)


def read_copy(identity, session_factory=SessionLocal, with_metrics=False):
    with session_factory() as db:
        candidate = locked(db, identity)
        authorized(db, candidate)
        values = {"source_bucket": candidate.bucket, "source_key": candidate.object_key,
            "etag": candidate.etag, "size": candidate.size_bytes, "mime": candidate.mime_type,
            "target_key": f"images/company/{candidate.company_id}/ai/{candidate.storage_uid or candidate.id}{storage.IMAGE_SUFFIXES[candidate.mime_type]}",
            "source_type": "grsai_generated", "source_ref": str(candidate.id), "expires_at": candidate.expires_at}
        wait = max(0, (now() - candidate.available_at).total_seconds()) if candidate.available_at else 0
        return (values, wait) if with_metrics else values


def renew(identity, session_factory=SessionLocal):
    with session_factory() as db:
        candidate = locked(db, identity)
        candidate.lease_expires_at = now() + timedelta(seconds=get_settings().image_prepare_lease_seconds)
        db.commit()


def finish(identity, result=None, error=None, session_factory=SessionLocal):
    from .image_files import add_address
    with session_factory() as db:
        candidate = locked(db, identity)
        if error is None:
            authorized(db, candidate)
            key, url = result
            image = register_formal(db, candidate.company_id, key, url, candidate.size_bytes,
                candidate.mime_type, "grsai_generated", str(candidate.id))
            add_address(db, candidate.company_id, candidate.source_url, image)
            candidate.image_file_id, candidate.state, candidate.error = image.id, "ready", None
        else:
            if isinstance(error, storage.InvalidCandidate):
                candidate.state, candidate.error = error.state, str(error)
            elif isinstance(error, HTTPException):
                candidate.state, candidate.error = "failed", "任务权限或执行批次已经变化，请刷新后检查"
            else:
                info = storage.failure_context(error)
                candidate.error = ("R2 访问被拒绝（403），请检查 ERP AI 凭据是否对候选桶和正式桶均有对象读写权限"
                    if info["http_status"] == 403 or info["error_code"] in {"403", "AccessDenied"}
                    else "R2 图片准备暂时失败，请重试")
                if candidate.attempts <= len(RETRY_DELAYS):
                    candidate.state = "queued"
                    candidate.available_at = now() + timedelta(seconds=RETRY_DELAYS[candidate.attempts - 1])
                else:
                    candidate.state = "failed"
        candidate.lease_owner, candidate.lease_expires_at = None, None
        db.commit()
        return candidate.state


async def process_one(identity, session_factory=SessionLocal, metrics=None):
    async def heartbeat():
        while True:
            await asyncio.sleep(15)
            await asyncio.to_thread(renew, identity, session_factory)
    beat = asyncio.create_task(heartbeat())
    started = time.monotonic()
    outcome = "interrupted"
    timings = {}
    values = {}
    try:
        values, timings["queue_wait_ms"] = await asyncio.to_thread(read_copy, identity, session_factory, True)
        copy_started = time.monotonic()
        copy_task = asyncio.create_task(asyncio.to_thread(storage.copy_object, **values))
        done, _ = await asyncio.wait((copy_task, beat), return_when=asyncio.FIRST_COMPLETED)
        if beat in done:
            copy_task.cancel()
            await asyncio.gather(copy_task, return_exceptions=True)
            beat.result()
            raise LostLease()
        result = copy_task.result()
        timings["copy_ms"] = time.monotonic() - copy_started
        outcome = await asyncio.to_thread(finish, identity, result, None, session_factory)
    except LostLease:
        outcome = "lease_lost"
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        try:
            outcome = await asyncio.to_thread(finish, identity, None, exc, session_factory)
        except LostLease:
            outcome = "lease_lost"
        logger.warning("AI 图片准备失败 | %s", json.dumps({
            "candidate_id": identity[0], "outcome": outcome, "exception_type": type(exc).__name__,
            **storage.failure_context(exc), "source_bucket": values.get("source_bucket"),
            "target_bucket": get_settings().r2_bucket, "source_key": values.get("source_key"),
            "target_key": values.get("target_key"),
        }, ensure_ascii=False))
    finally:
        beat.cancel()
        await asyncio.gather(beat, return_exceptions=True)
        if metrics:
            metrics.requests += 1
            metrics.outcomes[outcome] += 1
            timings["processing_ms"] = time.monotonic() - started
            for name, duration in timings.items():
                metrics.add(name, duration)
        logger.info("AI 图片准备处理 | candidate_id=%s outcome=%s duration_ms=%.2f", identity[0], outcome, (time.monotonic() - started) * 1000)
    return outcome


async def run_worker():
    from .result_worker import QueryMetrics
    metrics = QueryMetrics()
    active = set()
    try:
        while True:
            for task in list(active):
                if task.done():
                    active.remove(task)
                    try:
                        task.result()
                    except Exception as exc:
                        logger.error("AI 准备任务执行异常 | exception_type=%s", type(exc).__name__)
            if len(active) < get_settings().image_prepare_concurrency:
                identity = await asyncio.to_thread(claim_one)
                if identity:
                    active.add(asyncio.create_task(process_one(identity, metrics=metrics)))
                    continue
            if time.monotonic() - metrics.started_at >= 60:
                queued = await asyncio.to_thread(queue_size)
                logger.info("AI 图片准备统计 | %s", json.dumps(metrics.summary(queued=queued, active=len(active),
                    concurrency=get_settings().image_prepare_concurrency, interval=1), ensure_ascii=False))
                metrics.reset()
            await asyncio.sleep(1)
    finally:
        for task in active:
            task.cancel()
        await asyncio.gather(*active, return_exceptions=True)


def queue_size():
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(AIImageCandidate).where(AIImageCandidate.state == "queued")) or 0
