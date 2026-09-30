"""提交或结果数据库 Worker 的命令行入口。"""
import argparse
import asyncio
import logging
from datetime import datetime, timezone

from .database import engine
from .logging_config import configure_logging
from .schema_version import assert_schema_current
from .task_jobs import queue_interval, run_cycle
from .main import run_miaoshou_collect_box_sync_cycle
from .product_library_rankings import cleanup_expired_snapshots, recover_interrupted_tasks, run_ranking_task_cycle


async def run_forever(kind: str) -> None:
    if kind == "product-library-rankings":
        recover_interrupted_tasks()
        cleanup_expired_snapshots()
        last_cleanup = datetime.now(timezone.utc)
    while True:
        if kind == "product-library-rankings":
            if (datetime.now(timezone.utc) - last_cleanup).total_seconds() >= 3600:
                cleanup_expired_snapshots()
                last_cleanup = datetime.now(timezone.utc)
            if not run_ranking_task_cycle():
                await asyncio.sleep(5)
            continue
        if kind == "miaoshou-collect-box":
            processed = await run_miaoshou_collect_box_sync_cycle()
            logging.getLogger(__name__).info("妙手公共采集箱同步周期完成 | companies=%s", processed)
            await asyncio.sleep(300)
            continue
        processed = await run_cycle(kind)
        if processed == 0:
            await asyncio.sleep(queue_interval(kind))


def main() -> None:
    parser = argparse.ArgumentParser(description="Haitoro 印花任务数据库 Worker")
    parser.add_argument("kind", choices=("submit", "result", "miaoshou-collect-box", "product-library-rankings"))
    args = parser.parse_args()
    configure_logging()
    assert_schema_current(engine)
    logging.getLogger(__name__).info("任务 Worker 启动 | kind=%s", args.kind)
    asyncio.run(run_forever(args.kind))


if __name__ == "__main__":
    main()
