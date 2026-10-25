"""以 MySQL 为队列的印花任务处理逻辑。"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import select

from .ai_providers import (
    GenerationRequest,
    ProviderError,
    ProviderTaskTerminalError,
    build_prompt,
    poll_async_generation,
    submit_async_generation,
)
from .database import get_db
from .credentials import decrypt_secret
from .main import map_task_results, persist_generated_images
from .models import AIProviderSetting, PodTask, ProductTemplate, TaskQueueSetting, TaskStatus, UserAIProviderCredential


logger = logging.getLogger(__name__)
SleepCallable = Callable[[float], Awaitable[None]]
MAX_SUBMIT_ATTEMPTS = 3


def queue_interval(kind: str) -> float:
    """读取毫秒配置，转换为 asyncio.sleep 所需的秒数。"""
    db = next(get_db())
    try:
        setting = db.get(TaskQueueSetting, 1)
        if not setting:
            return 1 if kind == "submit" else 5
        return max(1, setting.submit_interval_ms if kind == "submit" else setting.result_interval_ms) / 1000
    finally:
        db.close()


def task_snapshot(status: TaskStatus) -> list[int]:
    """固定本轮任务快照；本轮新增任务留到下一轮，避免队首饥饿。"""
    db = next(get_db())
    try:
        stmt = select(PodTask.id).where(PodTask.status == status)
        if status == TaskStatus.RUNNING:
            stmt = stmt.where(PodTask.provider_task_id.is_not(None))
        return list(db.scalars(stmt.order_by(PodTask.created_at, PodTask.id)).all())
    finally:
        db.close()


def _request_for(task: PodTask, template: ProductTemplate) -> GenerationRequest:
    parameters = (task.parameters or {}) | {"quality": "1K"}
    if task.provider_model == "gpt-image-2":
        parameters["ratio"] = "1:1"
    if task.task_type == "sku_image":
        print_urls = list(parameters.get("print_urls") or ([parameters["print_url"]] if parameters.get("print_url") else []))
        template_url = parameters.get("white_image_url") or template.cover_url or ""
    else:
        references = list(parameters.get("reference_urls") or [])
        template_url = references[0] if references else ""
        print_urls = references[1:]
    return GenerationRequest(
        model=task.provider_model or "",
        prompt=build_prompt(parameters, template.name),
        template_url=template_url,
        print_urls=print_urls,
        ratio=parameters["ratio"],
        quality=parameters["quality"],
        company_id=task.company_id,
        task_id=task.id,
        idempotency_key=f"haitoro-task-{task.id}",
    )


def _task_api_key(db, task: PodTask, setting: AIProviderSetting | None = None) -> str:
    setting = setting or db.get(AIProviderSetting, task.provider)
    if not setting:
        raise ProviderError("任务所选模型不存在")
    credential = db.scalar(select(UserAIProviderCredential).where(
        UserAIProviderCredential.company_id == task.company_id,
        UserAIProviderCredential.user_id == task.created_by,
        UserAIProviderCredential.provider == setting.credential_provider,
    ))
    if not credential:
        raise ProviderError("任务创建人尚未配置该模型平台密钥")
    try:
        return decrypt_secret(credential.secret_encrypted)
    except Exception as exc:
        raise ProviderError("任务创建人的模型平台密钥无法解密，请重新配置") from exc


async def submit_task_once(task_id: int) -> str:
    """提交一次；返回 done、retry 或 skipped。"""
    db = next(get_db())
    try:
        task = db.get(PodTask, task_id)
        if not task or task.status != TaskStatus.QUEUED:
            return "skipped"
        if task.submit_attempts >= MAX_SUBMIT_ATTEMPTS:
            task.status = TaskStatus.FAILED
            task.failure_reason = task.failure_reason or "提交第三方 API 已达到 3 次上限"
            task.completed_at = datetime.utcnow()
            db.commit()
            logger.error("印花任务提交次数已达上限 | task_id=%s attempts=%s", task_id, task.submit_attempts)
            return "done"
        template = db.get(ProductTemplate, task.template_id)
        setting = db.get(AIProviderSetting, task.provider) if task.provider else None
        task.submit_attempts += 1
        db.commit()
        logger.info(
            "印花任务开始提交 | task_id=%s provider=%s model=%s attempt=%s",
            task_id, task.provider, task.provider_model, task.submit_attempts,
        )
        if not template or not ((task.parameters or {}).get("white_image_url") or (task.parameters or {}).get("reference_urls") or template.cover_url):
            raise ProviderError("产品模板不存在或任务缺少产品白底图")
        if not setting or not setting.enabled:
            raise ProviderError("任务所选模型已停用或不存在")
        request = _request_for(task, template)
        api_key = _task_api_key(db, task, setting)
        initial_result, _, _ = await submit_async_generation(task.provider or "", request, api_key)
        provider_task_id = initial_result.get("id")
        if not isinstance(provider_task_id, str) or not provider_task_id:
            raise ProviderError("grsai 异步任务未返回任务 ID")
        task = db.get(PodTask, task_id)
        if not task or task.status != TaskStatus.QUEUED:
            return "skipped"
        task.provider_task_id = provider_task_id
        task.status = TaskStatus.RUNNING
        task.submitted_at = datetime.utcnow()
        task.failure_reason = None
        db.commit()
        logger.info("印花任务已提交第三方 | task_id=%s provider=%s provider_task_id=%s", task_id, task.provider, provider_task_id)
        return "done"
    except Exception as exc:
        db.rollback()
        task = db.get(PodTask, task_id)
        if not task or task.status != TaskStatus.QUEUED:
            logger.warning(
                "印花任务提交异常后状态已变化 | task_id=%s exception_type=%s reason=%s",
                task_id, type(exc).__name__, exc,
            )
            return "skipped"
        task.failure_reason = str(exc)[:500]
        if task.submit_attempts >= MAX_SUBMIT_ATTEMPTS:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.utcnow()
            outcome = "done"
        else:
            outcome = "retry"
        db.commit()
        log_method = logger.error if outcome == "done" else logger.warning
        log_method(
            "印花任务提交失败 | task_id=%s attempt=%s outcome=%s exception_type=%s reason=%s",
            task_id, task.submit_attempts, outcome, type(exc).__name__, exc,
            exc_info=not isinstance(exc, ProviderError),
        )
        return outcome
    finally:
        db.close()


async def process_submission_task(task_id: int, sleep: SleepCallable = asyncio.sleep) -> None:
    while await submit_task_once(task_id) == "retry":
        await sleep(queue_interval("submit"))


async def process_result_task(task_id: int) -> str:
    """兼容单次结果处理入口；生产调度使用 ResultScheduler。"""
    from .result_worker import process_result
    return await process_result(task_id)


async def run_cycle(kind: str, sleep: SleepCallable = asyncio.sleep) -> int:
    status = TaskStatus.QUEUED if kind == "submit" else TaskStatus.RUNNING
    task_ids = task_snapshot(status)
    for task_id in task_ids:
        if kind == "submit":
            await process_submission_task(task_id, sleep=sleep)
        else:
            await process_result_task(task_id)
        await sleep(queue_interval(kind))
    return len(task_ids)
