"""数据库租约驱动的导入与批量标题 Worker；不需要额外消息队列。"""
import asyncio
import copy
import logging
import secrets
import signal
from contextlib import suppress
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update

from .ai_providers import ProviderError
from .config import get_settings
from .database import SessionLocal
from .logging_config import configure_logging
from .models import Company, Role, User
from .title_import import extract_row
from .title_models import TitleImportWord, TitleMarket, TitleRecord, TitleTask
from .title_permissions import is_title_manager
from .title_service import credential, digest, generate_record, normalize, record_payload

logger = logging.getLogger(__name__)


class LostTitleLease(Exception):
    pass


def claim_task(session_factory=SessionLocal, *, exclude_ids=()):
    with session_factory() as db:
        now = datetime.utcnow()
        # 领取时只锁定 ID，避免历史任务的大 JSON 结果进入 MySQL 排序缓冲。
        query = select(TitleTask.id).where(or_(TitleTask.state == 'queued',
            (TitleTask.state == 'running') & (TitleTask.lease_expires_at <= now))).order_by(TitleTask.id).limit(1)
        if exclude_ids:
            query = query.where(TitleTask.id.not_in(exclude_ids))
        identity = db.scalar(query.with_for_update(skip_locked=True))
        if identity is None:
            return None
        owner = secrets.token_hex(16)
        changed = db.execute(update(TitleTask).where(TitleTask.id == identity, or_(TitleTask.state == 'queued',
            (TitleTask.state == 'running') & (TitleTask.lease_expires_at <= now))).values(state='running',
                lease_owner=owner, lease_expires_at=now + timedelta(seconds=120), error=None))
        if not changed.rowcount:
            db.rollback()
            return None
        # 只有成功接管过期任务的 Worker 可以回收它所属的记录租约。
        db.execute(update(TitleRecord).where(TitleRecord.task_id == identity,
            TitleRecord.title.is_(None)).values(lease_owner=None, lease_expires_at=None))
        db.commit()
        logger.info('标题任务已领取 | task_id=%s', identity)
        return identity, owner


def change_task(identity, owner, callback, session_factory=SessionLocal):
    with session_factory() as db:
        task = db.scalar(select(TitleTask).where(TitleTask.id == identity).with_for_update())
        if not task or task.state != 'running' or task.lease_owner != owner or task.lease_expires_at <= datetime.utcnow():
            raise LostTitleLease()
        market = db.get(TitleMarket, task.market_id)
        user = db.get(User, task.user_id)
        company = db.get(Company, market.company_id)
        if not user or not user.is_active or user.company_id != market.company_id or not company or not company.is_active or user.role not in {Role.COMPANY_ADMIN, Role.MEMBER, Role.TEAM_LEADER}:
            raise ProviderError('任务账号或公司已停用')
        if task.kind == 'import' and not is_title_manager(user):
            raise ProviderError('导入账号不再具有标题词库管理权限')
        result = callback(db, task, market)
        task.updated_at = datetime.utcnow()
        db.commit()
        return result


async def run_task(identity, owner, session_factory=SessionLocal, *, item_semaphore=None):
    stopped = asyncio.Event()
    item_limit = get_settings().title_item_concurrency
    item_semaphore = item_semaphore if item_semaphore is not None else asyncio.Semaphore(item_limit)
    group_workers = []

    async def heartbeat():
        while not stopped.is_set():
            await asyncio.sleep(20)
            try:
                def renew(db, task, market):
                    task.lease_expires_at = datetime.utcnow() + timedelta(seconds=120)
                    db.execute(update(TitleRecord).where(TitleRecord.task_id == task.id,
                        TitleRecord.lease_owner.is_not(None)).values(lease_expires_at=datetime.utcnow() + timedelta(minutes=6)))
                change_task(identity, owner, renew, session_factory)
            except (LostTitleLease, ProviderError):
                stopped.set()
                return

    pulse = asyncio.create_task(heartbeat())
    try:
        snapshot, kind, done, market_company, user_id = change_task(identity, owner, lambda db, task, market:
            (copy.deepcopy(task.snapshot), task.kind, copy.deepcopy(task.result), market.company_id, task.user_id), session_factory)
        logger.info('标题任务开始处理 | task_id=%s kind=%s', identity, kind)
        if kind == 'import':
            for row in snapshot['rows']:
                row_key = str(row['row'])
                if row_key in done.get('completed_rows', []):
                    continue
                if stopped.is_set():
                    raise LostTitleLease()
                with session_factory() as db:
                    api_key = credential(db, user_id, market_company) if snapshot['kind'] == 'titles' else None
                try:
                    async with item_semaphore:
                        if stopped.is_set():
                            raise LostTitleLease()
                        change_task(identity, owner, lambda db, task, market: None, session_factory)
                        words = await extract_row(row, snapshot['kind'], api_key, allowed_tags=snapshot.get('allowed_tags'),
                                                  tag_semantics=snapshot.get('tag_semantics'),
                                                  site=snapshot.get('site', 'MY'), language=snapshot.get('language', 'ms'))
                    def save_words(db, task, market):
                        result = copy.deepcopy(task.result)
                        if row_key not in result.setdefault('completed_rows', []):
                            unique = {digest([normalize(w['phrase']), w['tag']]): w for w in words}
                            for key, word in unique.items():
                                db.add(TitleImportWord(task_id=task.id, row_number=row['row'], identity_hash=key, word=word))
                            db.flush()
                            result['word_total'] = db.scalar(select(func.count()).select_from(TitleImportWord).where(TitleImportWord.task_id == task.id))
                            result['completed_rows'].append(row_key)
                        result.setdefault('failed_rows', {}).pop(row_key, None)
                        task.result = result
                        task.progress = {'total': len(snapshot['rows']), 'completed': len(result['completed_rows']),
                                         'failed': len(result.get('failed_rows', {}))}
                        return copy.deepcopy(result)
                    done = change_task(identity, owner, save_words, session_factory)
                except (ProviderError, ValueError) as exc:
                    def save_error(db, task, market):
                        result = copy.deepcopy(task.result)
                        result.setdefault('failed_rows', {})[row_key] = str(exc)
                        task.result = result
                        task.progress = {'total': len(snapshot['rows']), 'completed': len(result.get('completed_rows', [])),
                                         'failed': len(result['failed_rows'])}
                    change_task(identity, owner, save_error, session_factory)
            def finish_import(db, task, market):
                task.state = 'review' if task.result.get('word_total') else 'failed'
                task.error = '部分行提词失败，可重试失败行或审核成功结果' if task.result.get('failed_rows') else None
                task.lease_owner = None
                task.lease_expires_at = None
            change_task(identity, owner, finish_import, session_factory)
        else:
            async def generate_group(group):
                if stopped.is_set():
                    raise LostTitleLease()
                change_task(identity, owner, lambda db, task, market: None, session_factory)
                with session_factory() as db:
                    record = db.get(TitleRecord, group['generation_id'])
                    try:
                        payload = record_payload(record) if record.title else await generate_record(db, record.id)
                        item = {'key': group['key'], **payload}
                    except ProviderError as exc:
                        item = {'key': group['key'], 'generation_id': record.id, 'state': 'failed', 'error': str(exc)}
                def save_item(db, task, market):
                    result = copy.deepcopy(task.result)
                    result.setdefault('items', {})[group['key']] = item
                    task.result = result
                    items = list(result['items'].values())
                    task.progress = {'total': len(snapshot['groups']), 'completed': len(items),
                        'succeeded': sum(bool(i.get('title')) for i in items), 'failed': sum(not i.get('title') for i in items)}
                change_task(identity, owner, save_item, session_factory)
            groups = iter(snapshot['groups'])
            async def group_worker():
                for group in groups:
                    async with item_semaphore:
                        await generate_group(group)
            # 每个任务只创建固定数量的协程，共享进程级信号量，避免并发数按任务倍增。
            group_workers = [asyncio.create_task(group_worker()) for _ in range(min(item_limit, len(snapshot['groups'])))]
            await asyncio.gather(*group_workers)
            def finish_batch(db, task, market):
                task.state = 'completed_with_errors' if task.progress.get('failed') else 'completed'
                task.lease_owner = None
                task.lease_expires_at = None
            change_task(identity, owner, finish_batch, session_factory)
    except LostTitleLease:
        pass
    except Exception as exc:
        with session_factory() as db:
            db.execute(update(TitleTask).where(TitleTask.id == identity, TitleTask.lease_owner == owner,
                TitleTask.state == 'running').values(state='failed', lease_owner=None, lease_expires_at=None,
                    error=str(exc) if isinstance(exc, ProviderError) else '任务处理失败，请重试'))
            db.commit()
        logger.exception('标题任务失败 | task_id=%s type=%s', identity, type(exc).__name__)
    finally:
        stopped.set()
        for worker in group_workers:
            if not worker.done():
                worker.cancel()
        if group_workers:
            await asyncio.gather(*group_workers, return_exceptions=True)
        pulse.cancel()
        with suppress(asyncio.CancelledError):
            await pulse


async def serve(*, stop_event=None, session_factory=SessionLocal):
    settings = get_settings()
    stop = stop_event if stop_event is not None else asyncio.Event()
    loop = asyncio.get_running_loop()
    if stop_event is None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
    running = {}
    item_semaphore = asyncio.Semaphore(settings.title_item_concurrency)
    stop_waiter = asyncio.create_task(stop.wait())
    logger.info('标题 Worker 启动 | task_concurrency=%s item_concurrency=%s',
                settings.title_worker_concurrency, settings.title_item_concurrency)
    try:
        while not stop.is_set():
            while len(running) < settings.title_worker_concurrency and not stop.is_set():
                try:
                    claimed = claim_task(session_factory, exclude_ids=tuple(running.values()))
                except Exception:
                    logger.exception('标题任务领取失败，将稍后重试')
                    break
                if not claimed:
                    break
                worker = asyncio.create_task(run_task(*claimed, session_factory=session_factory, item_semaphore=item_semaphore))
                running[worker] = claimed[0]
            done, _ = await asyncio.wait([stop_waiter, *running], timeout=2, return_when=asyncio.FIRST_COMPLETED)
            for worker in done:
                if worker is stop_waiter:
                    continue
                identity = running.pop(worker)
                try:
                    await worker
                except Exception:
                    logger.exception('标题任务执行异常 | task_id=%s', identity)
    finally:
        # 停止领取新任务，已领取任务继续续租并完成，避免主动丢失正在生成的结果。
        if running:
            await asyncio.gather(*running, return_exceptions=True)
        stop_waiter.cancel()
        with suppress(asyncio.CancelledError):
            await stop_waiter


if __name__ == '__main__':
    configure_logging()
    asyncio.run(serve())
