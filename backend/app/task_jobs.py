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
    generate,
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


def queue_interval(kind: str) -> int:
    db = next(get_db())
    try:
        setting = db.get(TaskQueueSetting, 1)
        if not setting:
            return 1 if kind == "submit" else 5
        return max(1, setting.submit_interval_seconds if kind == "submit" else setting.result_interval_seconds)
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
    parameters = task.parameters or {}
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


def _task_api_key(db, task: PodTask) -> str:
    credential = db.scalar(select(UserAIProviderCredential).where(
        UserAIProviderCredential.company_id == task.company_id,
        UserAIProviderCredential.user_id == task.created_by,
        UserAIProviderCredential.provider == task.provider,
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
        api_key = _task_api_key(db, task)
        if task.provider == "grsai":
            initial_result, _, _ = await submit_async_generation(task.provider, request, api_key)
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
            logger.info(
                "印花任务已提交第三方 | task_id=%s provider=%s provider_task_id=%s",
                task_id, task.provider, provider_task_id,
            )
            return "done"

        urls = await generate(task.provider or "", request, api_key)
        urls = await persist_generated_images(urls, task.company_id, task.id)
        task = db.get(PodTask, task_id)
        if not task or task.status != TaskStatus.QUEUED:
            return "skipped"
        task.result_map = map_task_results(task, urls)
        task.result_urls = urls
        task.status = TaskStatus.AWAITING_SELECTION
        task.submitted_at = datetime.utcnow()
        task.completed_at = datetime.utcnow()
        task.failure_reason = None
        db.commit()
        logger.info("印花任务同步生成完成 | task_id=%s image_count=%s", task_id, len(urls))
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


async def process_result_task(task_id: int) -> None:
    """只查询一次外部结果；未完成或临时异常时保留运行状态。"""
    db = next(get_db())
    try:
        task = db.get(PodTask, task_id)
        if not task or task.status != TaskStatus.RUNNING or not task.provider_task_id:
            return
        provider, provider_task_id = task.provider or "", task.provider_task_id
        company_id = task.company_id
        try:
            api_key = _task_api_key(db, task)
            urls = await poll_async_generation(provider, provider_task_id, api_key)
        except ProviderTaskTerminalError as exc:
            task = db.get(PodTask, task_id)
            if task and task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.FAILED
                task.failure_reason = str(exc)[:500]
                task.completed_at = datetime.utcnow()
                db.commit()
                logger.error("印花任务第三方处理失败 | task_id=%s reason=%s", task_id, exc)
            return
        except Exception as exc:
            logger.warning("印花任务 #%s 查询临时失败：%s", task_id, exc)
            task = db.get(PodTask, task_id)
            if task and task.status == TaskStatus.RUNNING:
                task.failure_reason = f"查询临时失败，下轮继续：{exc}"[:500]
                db.commit()
            return
        if urls is None:
            task = db.get(PodTask, task_id)
            if task and task.status == TaskStatus.RUNNING:
                task.failure_reason = None
                db.commit()
            return
        urls = await persist_generated_images(urls, company_id, task_id)
        task = db.get(PodTask, task_id)
        if not task or task.status != TaskStatus.RUNNING:
            return
        try:
            result_map = map_task_results(task, urls)
        except ProviderError as exc:
            task.status = TaskStatus.FAILED
            task.failure_reason = str(exc)[:500]
            task.completed_at = datetime.utcnow()
            db.commit()
            return
        task.result_map = result_map
        task.result_urls = urls
        task.status = TaskStatus.AWAITING_SELECTION
        task.failure_reason = None
        task.completed_at = datetime.utcnow()
        db.commit()
        logger.info("印花任务异步生成完成 | task_id=%s image_count=%s", task_id, len(urls))
    except Exception as exc:
        db.rollback()
        logger.exception("印花任务 #%s 结果处理异常", task_id)
        task = db.get(PodTask, task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.failure_reason = f"结果处理临时失败，下轮继续：{exc}"[:500]
            db.commit()
    finally:
        db.close()


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
