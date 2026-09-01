import asyncio
from .celery_app import celery
from .main import poll_generation_batch, reconcile_batches, run_generation_batch


@celery.task(name="haitoro.process_batch", bind=True, acks_late=True)
def process_batch(self, batch_id: int) -> None:
    asyncio.run(run_generation_batch(batch_id, self.request.id))


@celery.task(name="haitoro.poll_batch", bind=True, acks_late=True)
def poll_batch(self, batch_id: int) -> None:
    asyncio.run(poll_generation_batch(batch_id, self.request.id))


@celery.task(name="haitoro.reconcile_batches")
def reconcile_persisted_batches() -> None:
    reconcile_batches()
