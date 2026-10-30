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
from .database import SessionLocal
from .logging_config import configure_logging
from .models import Company, Role, User
from .title_import import extract_row
from .title_models import TitleImportWord, TitleMarket, TitleRecord, TitleTask
from .title_service import credential, digest, generate_record, normalize, record_payload

logger = logging.getLogger(__name__)


class LostTitleLease(Exception):
    pass


def claim_task(session_factory=SessionLocal):
    with session_factory() as db:
        now = datetime.utcnow()
        query = select(TitleTask).where(or_(TitleTask.state == 'queued',
            (TitleTask.state == 'running') & (TitleTask.lease_expires_at <= now))).order_by(TitleTask.id).limit(1)
        task = db.scalar(query.with_for_update(skip_locked=True))
        if not task:
            return None
        owner = secrets.token_hex(16)
        changed = db.execute(update(TitleTask).where(TitleTask.id == task.id, or_(TitleTask.state == 'queued',
            (TitleTask.state == 'running') & (TitleTask.lease_expires_at <= now))).values(state='running',
                lease_owner=owner, lease_expires_at=now + timedelta(seconds=120), error=None))
        if not changed.rowcount:
            db.rollback()
            return None
        # 只有成功接管过期任务的 Worker 可以回收它所属的记录租约。
        db.execute(update(TitleRecord).where(TitleRecord.task_id == task.id,
            TitleRecord.title.is_(None)).values(lease_owner=None, lease_expires_at=None))
        db.commit()
        return task.id, owner


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
        if task.kind == 'import' and user.role != Role.COMPANY_ADMIN:
            raise ProviderError('导入账号不再具有管理员权限')
        result = callback(db, task, market)
        task.updated_at = datetime.utcnow()
        db.commit()
        return result


async def run_task(identity, owner, session_factory=SessionLocal):
    stopped = asyncio.Event()

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
                    words = await extract_row(row, snapshot['kind'], api_key, allowed_tags=snapshot.get('allowed_tags'),
                                              tag_semantics=snapshot.get('tag_semantics'))
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
            for group in snapshot['groups']:
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
        logger.warning('标题任务失败 | task_id=%s type=%s', identity, type(exc).__name__)
    finally:
        stopped.set()
        pulse.cancel()
        with suppress(asyncio.CancelledError):
            await pulse


async def serve():
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    while not stop.is_set():
        claimed = claim_task()
        if claimed:
            await run_task(*claimed)
        else:
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass


if __name__ == '__main__':
    configure_logging()
    asyncio.run(serve())
