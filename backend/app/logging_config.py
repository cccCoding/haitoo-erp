"""后端统一日志配置。"""
from __future__ import annotations

import logging
from logging.config import dictConfig
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import get_settings


class Iso8601Formatter(logging.Formatter):
    """输出带毫秒和明确时区偏移的 ISO 8601 时间。"""

    def __init__(self, *args, timezone_name: str = "UTC", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        try:
            self.timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            self.timezone = ZoneInfo("UTC")

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        timestamp = datetime.fromtimestamp(record.created, self.timezone)
        return timestamp.isoformat(timespec="milliseconds")


def configure_logging() -> None:
    """为 API、Uvicorn 和 Worker 安装同一套日志格式。"""
    settings = get_settings()
    level = settings.log_level.upper()
    if level not in logging.getLevelNamesMapping():
        level = "INFO"
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": Iso8601Formatter,
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "timezone_name": settings.log_timezone,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {"handlers": ["default"], "level": level},
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": level, "propagate": False},
            # 请求日志由应用中间件统一输出，避免 Uvicorn 再打印一条缺少耗时和 request_id 的记录。
            "uvicorn.access": {"handlers": [], "level": level, "propagate": False},
            # 第三方 SDK 的 INFO 日志可能包含完整 URL（包括查询参数中的密钥），仅保留告警。
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
            "boto3": {"level": "WARNING"},
            "botocore": {"level": "WARNING"},
            "urllib3": {"level": "WARNING"},
        },
    })
