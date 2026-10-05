"""产品库销量快照与手动统计任务。日期按香港时间，订单时间在数据库中为 UTC naive。"""

import logging
import threading
from uuid import uuid4
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import (
    Company, ProductLibraryDailySnapshot, ProductLibraryDailySnapshotItem, ProductLibraryRankingTask,
    ProductLibraryOrder, ProductLibraryOrderProduct, ProductLibraryProduct, ProductLibrarySnapshotOrderProduct,
)


logger = logging.getLogger(__name__)
HONG_KONG = ZoneInfo("Asia/Hong_Kong")
RETENTION_DAYS = 30
_local_run_locks: dict[tuple[int, int], threading.Lock] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SnapshotAlreadyRunning(Exception):
    """同公司的统计事务已持有数据库行锁。"""


def _is_nowait_conflict(exc: OperationalError) -> bool:
    return bool(getattr(exc.orig, "args", ()) and exc.orig.args[0] == 3572)


@contextmanager
def company_run_lock(db: Session, company_id: int):
    """整个公司任务持锁；MySQL 命名锁跨 API/Worker 进程生效。"""
    bind = db.get_bind()
    if bind.dialect.name != "mysql":
        lock = _local_run_locks.setdefault((id(bind), company_id), threading.Lock())
        if not lock.acquire(blocking=False):
            raise SnapshotAlreadyRunning
        try:
            yield
        finally:
            lock.release()
        return

    lock_name = f"product-library-rankings:{company_id}"
    with bind.connect() as connection:
        acquired = connection.scalar(text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name})
        if acquired == 0:
            raise SnapshotAlreadyRunning
        if acquired != 1:
            raise RuntimeError("无法获取产品库统计锁")
        try:
            yield
        finally:
            try:
                released = connection.scalar(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
            except Exception:
                connection.invalidate()
                logger.exception("产品库统计锁释放失败 | company_id=%s", company_id)
                raise
            if released != 1:
                connection.invalidate()
                logger.error("产品库统计锁释放失败 | company_id=%s", company_id)


def _utc_boundary(local_date: date) -> datetime:
    return datetime.combine(local_date, time.min, HONG_KONG).astimezone(timezone.utc).replace(tzinfo=None)


def create_daily_snapshot(
    db: Session, company_id: int, snapshot_date: date, *, replace_existing: bool = False,
    fail_if_running: bool = False, commit: bool = True,
) -> bool:
    """单个公司、单个统计日原子写入；手动统计可替换当天快照。"""
    # 公司行锁与任务锁共同保护快照替换。
    try:
        locked_company_id = db.scalar(select(Company.id).where(Company.id == company_id)
                                      .with_for_update(nowait=fail_if_running))
    except OperationalError as exc:
        db.rollback()
        if fail_if_running and _is_nowait_conflict(exc):
            raise SnapshotAlreadyRunning from exc
        raise
    if locked_company_id is None:
        raise ValueError("公司不存在")
    existing = db.scalar(select(ProductLibraryDailySnapshot).where(
        ProductLibraryDailySnapshot.company_id == company_id,
        ProductLibraryDailySnapshot.snapshot_date == snapshot_date,
    ).with_for_update())
    if existing is not None:
        if not replace_existing:
            if commit:
                db.commit()
            return False
        db.execute(delete(ProductLibrarySnapshotOrderProduct).where(ProductLibrarySnapshotOrderProduct.snapshot_id == existing.id))
        db.execute(delete(ProductLibraryDailySnapshotItem).where(ProductLibraryDailySnapshotItem.snapshot_id == existing.id))
        db.execute(delete(ProductLibraryDailySnapshot).where(ProductLibraryDailySnapshot.id == existing.id))
    end = _utc_boundary(snapshot_date)
    start_30 = _utc_boundary(snapshot_date - timedelta(days=30))
    snapshot = ProductLibraryDailySnapshot(company_id=company_id, snapshot_date=snapshot_date, is_complete=True)
    db.add(snapshot)
    db.flush()
    facts = db.execute(select(ProductLibraryOrderProduct, ProductLibraryOrder)
        .join(ProductLibraryOrder, ProductLibraryOrder.id == ProductLibraryOrderProduct.order_id)
        .join(ProductLibraryProduct, ProductLibraryProduct.id == ProductLibraryOrderProduct.product_id)
        .where(ProductLibraryProduct.company_id == company_id, ProductLibraryOrder.company_id == company_id,
               ProductLibraryOrder.ordered_at >= start_30, ProductLibraryOrder.ordered_at < end)).all()
    db.add_all(ProductLibrarySnapshotOrderProduct(snapshot_id=snapshot.id, order_id=order.id,
        product_id=link.product_id, order_number=order.order_number, ordered_at=order.ordered_at,
        quantity=link.quantity) for link, order in facts)
    if commit:
        db.commit()
    return True


def refresh_company_snapshot(db: Session, company_id: int, now: datetime | None = None,
                             *, snapshot_date: date | None = None) -> date:
    """按请求时固定的统计日期原子替换快照。"""
    snapshot_date = snapshot_date or (now or datetime.now(timezone.utc)).astimezone(HONG_KONG).date()
    with company_run_lock(db, company_id):
        try:
            create_daily_snapshot(db, company_id, snapshot_date, replace_existing=True,
                                  fail_if_running=True, commit=False)
            cleanup_old_snapshots(db, company_id, snapshot_date, commit=False)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return snapshot_date


def task_payload(task: ProductLibraryRankingTask | None, *, existing: bool = False) -> dict:
    if task is None:
        return {"task": None}
    return {"task": {
        "task_id": task.task_id, "status": task.status,
        "snapshot_date": task.snapshot_date.isoformat(),
        "through_date": (task.snapshot_date - timedelta(days=1)).isoformat(),
        "requested_at": task.requested_at.isoformat() + "Z",
        "started_at": task.started_at.isoformat() + "Z" if task.started_at else None,
        "finished_at": task.finished_at.isoformat() + "Z" if task.finished_at else None,
        "error": task.error,
    }, "existing": existing, "message": "已有统计任务正在排队或执行" if existing else "统计任务已提交"}


def enqueue_ranking_task(db: Session, company_id: int, now: datetime | None = None) -> dict:
    """锁定公司行后提交任务，跨 API 进程只允许每公司一个活动任务。"""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    requested_at = instant.astimezone(timezone.utc).replace(tzinfo=None)
    snapshot_date = instant.astimezone(HONG_KONG).date()
    try:
        if db.scalar(select(Company.id).where(Company.id == company_id).with_for_update()) is None:
            raise ValueError("公司不存在")
        task = db.get(ProductLibraryRankingTask, company_id)
        if task is not None and task.status in ("queued", "running"):
            result = task_payload(task, existing=True)
            db.commit()
            return result
        if task is None:
            task = ProductLibraryRankingTask(company_id=company_id)
            db.add(task)
        task.task_id = str(uuid4())
        task.status = "queued"
        task.snapshot_date = snapshot_date
        task.requested_at = requested_at
        task.started_at = None
        task.finished_at = None
        task.error = None
        db.flush()
        result = task_payload(task)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def recover_interrupted_tasks(session_factory=SessionLocal) -> int:
    """Worker 启动时重新排队上次进程中断的任务。"""
    with session_factory() as db:
        tasks = db.scalars(select(ProductLibraryRankingTask).where(ProductLibraryRankingTask.status == "running")).all()
        for task in tasks:
            task.status = "queued"
            task.started_at = None
        db.commit()
        return len(tasks)


def run_ranking_task_cycle(session_factory=SessionLocal) -> bool:
    """领取并处理一个手动任务；成功后发布快照，失败时保留原快照。"""
    with session_factory() as db:
        task = db.scalar(select(ProductLibraryRankingTask)
                         .where(ProductLibraryRankingTask.status == "queued")
                         .order_by(ProductLibraryRankingTask.requested_at, ProductLibraryRankingTask.company_id)
                         .with_for_update(skip_locked=True).limit(1))
        if task is None:
            return False
        company_id, task_id, snapshot_date = task.company_id, task.task_id, task.snapshot_date
        task.status = "running"
        task.started_at = _utc_now()
        db.commit()
    try:
        with session_factory() as db:
            refresh_company_snapshot(db, company_id, snapshot_date=snapshot_date)
    except SnapshotAlreadyRunning:
        # 另一 Worker 正在处理同一公司，稍后重试此排队任务。
        with session_factory() as db:
            task = db.get(ProductLibraryRankingTask, company_id)
            if task and task.task_id == task_id and task.status == "running":
                task.status = "queued"
                task.started_at = None
                db.commit()
        return True
    except Exception as exc:
        logger.exception("产品库统计失败 | company_id=%s | task_id=%s", company_id, task_id)
        with session_factory() as db:
            task = db.get(ProductLibraryRankingTask, company_id)
            if task and task.task_id == task_id:
                task.status = "failed"
                task.finished_at = _utc_now()
                task.error = str(exc)[:2000] or "统计失败"
                db.commit()
        return True
    with session_factory() as db:
        task = db.get(ProductLibraryRankingTask, company_id)
        if task and task.task_id == task_id:
            task.status = "succeeded"
            task.finished_at = _utc_now()
            db.commit()
    return True


def cleanup_expired_snapshots(session_factory=SessionLocal, now: datetime | None = None) -> None:
    target_date = (now or datetime.now(timezone.utc)).astimezone(HONG_KONG).date()
    with session_factory() as db:
        company_ids = db.scalars(select(Company.id)).all()
    for company_id in company_ids:
        try:
            with session_factory() as db:
                cleanup_old_snapshots(db, company_id, target_date, commit=False)
                db.commit()
        except Exception:
            logger.exception("产品库过期快照清理失败 | company_id=%s", company_id)


def cleanup_old_snapshots(db: Session, company_id: int, target_date: date, *, commit: bool = True) -> None:
    cutoff = target_date - timedelta(days=RETENTION_DAYS - 1)
    old_ids = db.scalars(select(ProductLibraryDailySnapshot.id).where(
        ProductLibraryDailySnapshot.company_id == company_id,
        ProductLibraryDailySnapshot.snapshot_date < cutoff,
    )).all()
    if old_ids:
        db.execute(delete(ProductLibrarySnapshotOrderProduct).where(ProductLibrarySnapshotOrderProduct.snapshot_id.in_(old_ids)))
        db.execute(delete(ProductLibraryDailySnapshotItem).where(ProductLibraryDailySnapshotItem.snapshot_id.in_(old_ids)))
        db.execute(delete(ProductLibraryDailySnapshot).where(ProductLibraryDailySnapshot.id.in_(old_ids)))
        if commit:
            db.commit()
