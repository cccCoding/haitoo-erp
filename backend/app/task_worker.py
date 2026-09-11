"""提交或结果数据库 Worker 的命令行入口。"""
import argparse
import asyncio
import logging

from .database import engine
from .logging_config import configure_logging
from .schema_version import assert_schema_current
from .task_jobs import queue_interval, run_cycle


async def run_forever(kind: str) -> None:
    while True:
        processed = await run_cycle(kind)
        if processed == 0:
            await asyncio.sleep(queue_interval(kind))


def main() -> None:
    parser = argparse.ArgumentParser(description="Haitoro 印花任务数据库 Worker")
    parser.add_argument("kind", choices=("submit", "result"))
    args = parser.parse_args()
    configure_logging()
    assert_schema_current(engine)
    logging.getLogger(__name__).info("任务 Worker 启动 | kind=%s", args.kind)
    asyncio.run(run_forever(args.kind))


if __name__ == "__main__":
    main()
