"""单实例结果 Worker：持续补位、全局请求节奏、连接复用与分阶段计时。"""
from __future__ import annotations

import asyncio
from collections import Counter, deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import math
import re
import time

import httpx
from sqlalchemy import select, update

from . import task_jobs as jobs
from .ai_providers import ProviderError, ProviderRateLimitError, ProviderTaskTerminalError
from .models import AIProviderSetting, PodTask, TaskQueueSetting, TaskStatus

logger = logging.getLogger(__name__)


@contextmanager
def result_db():
    # 保持生成器存活到事务结束；Session 在同一线程创建、使用和关闭。
    with contextmanager(jobs.get_db)() as db:
        yield db


@dataclass(frozen=True)
class TaskRef:
    id: int
    provider_task_id: str
    company_id: int
    created_by: int
    credential_provider: str

    @property
    def credential_key(self) -> tuple[int, int, str]:
        return self.company_id, self.created_by, self.credential_provider


@dataclass(frozen=True)
class QueryContext:
    ref: TaskRef
    provider: str
    model: str | None
    api_key: str | None
    credential_error: str | None = None


def read_schedule() -> tuple[int, float, list[TaskRef]]:
    with result_db() as db:
        setting = db.get(TaskQueueSetting, 1)
        concurrency = min(20, max(1, setting.result_concurrency)) if setting else 5
        interval = max(1, setting.result_interval_ms) / 1000 if setting else 5.0
        rows = db.execute(select(
            PodTask.id, PodTask.provider_task_id, PodTask.company_id, PodTask.created_by,
            AIProviderSetting.credential_provider, PodTask.provider,
        ).outerjoin(AIProviderSetting, PodTask.provider == AIProviderSetting.provider).where(
            PodTask.status == TaskStatus.RUNNING, PodTask.provider_task_id.is_not(None),
        ).order_by(PodTask.created_at, PodTask.id)).all()
        return concurrency, interval, [TaskRef(*row[:4], row[4] or row[5] or "") for row in rows]


def read_context(task_id: int) -> QueryContext | None:
    with result_db() as db:
        task = db.get(PodTask, task_id)
        if not task or task.status != TaskStatus.RUNNING or not task.provider_task_id:
            return None
        setting = db.get(AIProviderSetting, task.provider)
        ref = TaskRef(task.id, task.provider_task_id, task.company_id, task.created_by,
                      setting.credential_provider if setting else task.provider or "")
        try:
            return QueryContext(ref, task.provider or "", task.provider_model, jobs._task_api_key(db, task, setting))
        except ProviderError as exc:
            return QueryContext(ref, task.provider or "", task.provider_model, None, str(exc))


def write_result(context: QueryContext, *, reason: str | None = None,
                 terminal: bool = False, urls: list[str] | None = None) -> str:
    """短事务内映射结果，原子校验状态和外部任务 ID，避免旧查询覆盖重试任务。"""
    with result_db() as db:
        task = db.get(PodTask, context.ref.id)
        if not task or task.status != TaskStatus.RUNNING or task.provider_task_id != context.ref.provider_task_id:
            return "skipped"
        values = {"failure_reason": reason}
        outcome = "retry" if reason else "pending"
        if urls is not None:
            try:
                values.update(result_map=jobs.map_task_results(task, urls), result_urls=urls,
                              status=TaskStatus.AWAITING_SELECTION, completed_at=datetime.utcnow())
                outcome = "succeeded"
            except ProviderError as exc:
                terminal, reason = True, str(exc)
        if terminal:
            values.update(status=TaskStatus.FAILED, failure_reason=reason, completed_at=datetime.utcnow())
            outcome = "failed"
        changed = db.execute(update(PodTask).where(
            PodTask.id == context.ref.id, PodTask.status == TaskStatus.RUNNING,
            PodTask.provider_task_id == context.ref.provider_task_id,
        ).values(**values).execution_options(synchronize_session=False)).rowcount
        db.commit()
        return outcome if changed else "skipped"


def safe_reason(exc: Exception, secret: str | None = None) -> str:
    message = str(exc)
    if secret:
        message = message.replace(secret, "[密钥已隐藏]")
    return re.sub(r"https?://[^\s]+", "[地址已隐藏]", message)[:500]


class MetricSamples:
    def __init__(self):
        self.samples = deque(maxlen=10000)
        self.total = 0.0
        self.count = 0

    def add(self, value: float):
        self.samples.append(value)
        self.total += value
        self.count += 1

    def report(self) -> dict:
        ordered = sorted(self.samples)
        return {"count": self.count, "avg": self.total / self.count,
                "p95": ordered[math.ceil(len(ordered) * .95) - 1], "p95_samples": len(ordered)}


class QueryMetrics:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.reset()

    def reset(self):
        self.started_at = self.clock()
        self.requests = 0
        self.outcomes = Counter()
        self.timings: dict[str, MetricSamples] = {}

    def add(self, name: str, seconds: float):
        self.timings.setdefault(name, MetricSamples()).add(seconds * 1000)

    def summary(self, *, queued: int, active: int, concurrency: int, interval: float) -> dict:
        elapsed = self.clock() - self.started_at
        return {"window_seconds": elapsed, "requests": self.requests,
                "requests_per_second": self.requests / elapsed if elapsed else 0,
                "outcomes": dict(self.outcomes), "queued": queued, "active": active,
                "concurrency": concurrency, "interval_ms": interval * 1000,
                "timings_ms": {key: value.report() for key, value in self.timings.items()}}


class QueryPacer:
    def __init__(self, interval=5.0, *, clock=time.monotonic, sleep=asyncio.sleep):
        self.interval = interval
        self.clock, self.sleep = clock, sleep
        self.last_started: float | None = None
        self.changed = asyncio.Event()
        self.cooldowns: dict[tuple[int, int, str], float] = {}

    def configure(self, interval: float):
        self.interval = interval
        self.changed.set()

    def available(self, key: tuple[int, int, str]) -> bool:
        return self.cooldowns.get(key, 0) <= self.clock()

    def cool_down(self, key: tuple[int, int, str], seconds: float):
        self.cooldowns[key] = max(self.cooldowns.get(key, 0), self.clock() + seconds)
        self.changed.set()

    async def start(self, key: tuple[int, int, str]) -> float | None:
        while True:
            if not self.available(key):
                return None
            now = self.clock()
            delay = 0 if self.last_started is None else self.last_started + self.interval - now
            if delay <= 0:
                # 单事件循环内检查和写入之间没有 await，因此无需持锁等待。
                # 各等待者独立响应冷却/配置变化，避免被队首的慢等待阻挡。
                self.last_started = now
                return now
            self.changed.clear()
            sleeper = asyncio.create_task(self.sleep(delay))
            changed = asyncio.create_task(self.changed.wait())
            try:
                await asyncio.wait((sleeper, changed), return_when=asyncio.FIRST_COMPLETED)
            finally:
                sleeper.cancel()
                changed.cancel()
                await asyncio.gather(sleeper, changed, return_exceptions=True)


async def process_result(task_id: int, *, client: httpx.AsyncClient | None = None,
                         pacer: QueryPacer | None = None, metrics: QueryMetrics | None = None,
                         enqueued_at: float | None = None, last_polls: dict | None = None) -> str:
    clock = pacer.clock if pacer else time.monotonic
    started = clock()
    timings: dict[str, float] = {}
    context = None
    outcome = "retry"
    stage = "读取任务"
    reason = None
    try:
        context = await asyncio.to_thread(read_context, task_id)
        if context is None:
            outcome = "skipped"
            return outcome
        if context.credential_error:
            raise ProviderError(context.credential_error)
        stage = "查询"
        query_started = await pacer.start(context.ref.credential_key) if pacer else clock()
        if query_started is None:
            outcome = "cooldown"
            return outcome
        if metrics:
            metrics.requests += 1
        if enqueued_at is not None:
            timings["queue_wait_ms"] = query_started - enqueued_at
        if last_polls is not None:
            if task_id in last_polls:
                timings["poll_gap_ms"] = query_started - last_polls[task_id]
            last_polls[task_id] = query_started
        try:
            kwargs = {"client": client} if client is not None else {}
            urls = await jobs.poll_async_generation(context.provider, context.ref.provider_task_id, context.api_key, **kwargs)
        finally:
            timings["query_ms"] = clock() - query_started
        if urls is not None:
            stage = "转存"
            persist_started = clock()
            try:
                urls = await jobs.persist_generated_images(urls, context.ref.company_id, task_id)
            finally:
                timings["persist_ms"] = clock() - persist_started
        stage = "结果落库"
        outcome = await asyncio.to_thread(write_result, context, urls=urls)
        return outcome
    except asyncio.CancelledError:
        outcome = "cancelled"
        raise
    except Exception as exc:
        reason = safe_reason(exc, context.api_key if context else None)
        if isinstance(exc, ProviderRateLimitError):
            outcome = "rate_limited"
            if pacer and context:
                key = context.ref.credential_key
                pacer.cool_down(key, exc.retry_after_seconds)
        elif isinstance(exc, ProviderTaskTerminalError):
            outcome = "failed"
        else:
            outcome = "retry"
        if context:
            try:
                written = await asyncio.to_thread(write_result, context, terminal=outcome == "failed",
                    reason=reason if outcome == "failed" else f"{stage}临时失败，下轮继续：{reason}"[:500])
                if written == "skipped":
                    outcome = "skipped"
            except Exception as write_exc:
                # 不把 SQL 参数、供应商响应、签名 URL 或密钥写进日志。
                logger.error("结果状态写入失败 | task_id=%s exception_type=%s", task_id, type(write_exc).__name__)
        return outcome
    finally:
        timings["processing_ms"] = clock() - started
        if metrics:
            metrics.outcomes[outcome] += 1
            for name, duration in timings.items():
                metrics.add(name, duration)
        level = logging.DEBUG if outcome in {"pending", "skipped", "cooldown"} else logging.INFO
        if outcome in {"retry", "rate_limited"}:
            level = logging.WARNING
        elif outcome == "failed":
            level = logging.ERROR
        detail = {"task_id": task_id, "outcome": outcome,
                  **{name: round(duration * 1000, 2) for name, duration in timings.items()}}
        if context:
            detail.update(company_id=context.ref.company_id, created_by=context.ref.created_by,
                          provider=context.provider, model=context.model)
        if reason:
            detail["reason"] = reason
        logger.log(level, "结果处理 | %s", json.dumps(detail, ensure_ascii=False))
        if timings.get("query_ms", 0) > 10:
            logger.warning("结果慢查询 | task_id=%s query_ms=%.2f", task_id, timings["query_ms"] * 1000)


class ResultScheduler:
    """只有此调度器创建处理任务；执行中包含查询、转存和短事务。"""
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.concurrency = 5
        self.pacer = QueryPacer()
        self.metrics = QueryMetrics()
        self.ready: deque[int] = deque()
        self.refs: dict[int, TaskRef] = {}
        self.enqueued: dict[int, float] = {}
        self.active: dict[int, asyncio.Task] = {}
        self.last_polls: dict[int, float] = {}
        self.wake = asyncio.Event()
        self.stopping = False

    async def refresh(self):
        concurrency, interval, refs = await asyncio.to_thread(read_schedule)
        self.concurrency = concurrency
        self.pacer.configure(interval)
        latest = {ref.id: ref for ref in refs}
        self.refs = latest
        self.ready = deque(task_id for task_id in self.ready if task_id in latest)
        known = set(self.ready) | self.active.keys()
        for ref in refs:
            if ref.id not in known:
                self.ready.append(ref.id)
                self.enqueued[ref.id] = time.monotonic()
                known.add(ref.id)
        keep = latest.keys() | self.active.keys()
        for key in list(self.last_polls):
            if key not in keep:
                del self.last_polls[key]
        self.enqueued = {key: value for key, value in self.enqueued.items() if key in keep}
        now = time.monotonic()
        self.pacer.cooldowns = {key: until for key, until in self.pacer.cooldowns.items() if until > now}

    async def handle(self, task_id: int):
        outcome = "retry"
        try:
            outcome = await process_result(task_id, client=self.client, pacer=self.pacer,
                metrics=self.metrics, enqueued_at=self.enqueued[task_id], last_polls=self.last_polls)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("结果任务未预期异常 | task_id=%s exception_type=%s", task_id, type(exc).__name__)
        finally:
            self.active.pop(task_id, None)
            if not self.stopping and outcome in {"pending", "retry", "rate_limited", "cooldown"} and task_id in self.refs:
                self.ready.append(task_id)
                self.enqueued[task_id] = time.monotonic()
            elif outcome not in {"pending", "retry", "rate_limited", "cooldown"}:
                self.last_polls.pop(task_id, None)
                self.enqueued.pop(task_id, None)
            self.wake.set()

    def fill_slots(self):
        # 只遍历一次当前队列；冷却项跳过后，其他凭据仍可获得空位。
        for _ in range(len(self.ready)):
            if len(self.active) >= self.concurrency:
                break
            task_id = self.ready.popleft()
            if not self.pacer.available(self.refs[task_id].credential_key):
                self.ready.append(task_id)
                continue
            self.active[task_id] = asyncio.create_task(self.handle(task_id))

    async def run(self):
        next_refresh = 0.0
        try:
            while True:
                now = time.monotonic()
                if now >= next_refresh:
                    try:
                        await self.refresh()
                    except Exception as exc:
                        logger.error("结果队列刷新失败 | exception_type=%s", type(exc).__name__)
                    next_refresh = time.monotonic() + 1
                self.wake.clear()
                self.fill_slots()
                now = time.monotonic()
                if now - self.metrics.started_at >= 60:
                    logger.info("结果查询统计 | %s", json.dumps(self.metrics.summary(
                        queued=len(self.ready), active=len(self.active), concurrency=self.concurrency,
                        interval=self.pacer.interval), ensure_ascii=False))
                    self.metrics.reset()
                cooldowns = [until for until in self.pacer.cooldowns.values() if until > now]
                deadline = min(next_refresh, self.metrics.started_at + 60, *cooldowns)
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=max(0, deadline - now))
                except TimeoutError:
                    pass
        finally:
            self.stopping = True
            pending = list(self.active.values())
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)


async def run_result_worker():
    async with httpx.AsyncClient(timeout=120, limits=httpx.Limits(
        max_connections=20, max_keepalive_connections=20, keepalive_expiry=60,
    )) as client:
        await ResultScheduler(client).run()
