"""Celery 投递层；MySQL 中的批次记录才是任务状态的唯一事实来源。"""
from celery import Celery
from .config import get_settings

celery = Celery("haitoro", broker=get_settings().redis_url)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    beat_schedule={"reconcile-pod-batches": {"task": "haitoro.reconcile_batches", "schedule": 30.0}},
)


def enqueue_batch(batch_id: int, countdown: int = 0, *, poll: bool = False) -> str:
    task_name = "haitoro.poll_batch" if poll else "haitoro.process_batch"
    result = celery.send_task(task_name, args=[batch_id], countdown=countdown)
    return result.id
