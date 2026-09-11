"""数据库迁移入口；部署时必须在 API 和 Worker 启动前单独执行。"""

from __future__ import annotations

import argparse
import logging

from alembic import command
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from .database import Base, SessionLocal, engine
from .logging_config import configure_logging
from .main import initialize_system_defaults
from .schema_version import alembic_config


LOCK_NAME = "haitoro_database_migration"
LOCK_TIMEOUT_SECONDS = 60


def upgrade_database(connection, *, adopt_legacy: bool = False) -> None:
    """升级数据库；无版本记录的既有业务库必须经过显式接管。"""
    existing_tables = set(inspect(connection).get_table_names())
    business_tables = existing_tables.intersection(Base.metadata.tables)
    current_heads = set(MigrationContext.configure(connection).get_current_heads())
    config = alembic_config(connection)

    if business_tables and not current_heads:
        if not adopt_legacy:
            raise RuntimeError(
                "检测到尚未纳入 Alembic 的既有数据库。请先备份，再执行 "
                "python -m app.db_migrate --adopt-legacy"
            )
        # 仅供本次从旧启动期 DDL 流程接管数据库：先补齐旧版本兼容结构，
        # 再标记静态基线；未来结构变化仍逐版本正常 upgrade。
        from .main import ensure_schema

        Base.metadata.create_all(bind=connection)
        ensure_schema(connection=connection)
        command.stamp(config, "20260911_01")

    command.upgrade(config, "head")


def run(*, adopt_legacy: bool = False) -> None:
    configure_logging()
    logger = logging.getLogger(__name__)
    # Alembic 收到外部 Connection 时不会替调用方提交事务；使用 begin() 确保
    # MySQL 上的 alembic_version DML 与迁移一并提交，而非连接关闭时回滚。
    with engine.begin() as connection:
        mysql = connection.dialect.name in {"mysql", "mariadb"}
        if mysql:
            acquired = connection.scalar(
                text("SELECT GET_LOCK(:name, :timeout)"),
                {"name": LOCK_NAME, "timeout": LOCK_TIMEOUT_SECONDS},
            )
            if acquired != 1:
                raise RuntimeError("等待数据库迁移锁超时，请确认没有其他部署正在迁移")
        try:
            logger.info("开始升级数据库")
            upgrade_database(connection, adopt_legacy=adopt_legacy)
        finally:
            if mysql:
                connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": LOCK_NAME})

    with SessionLocal() as db:
        initialize_system_defaults(db)
    logger.info("数据库升级完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="升级 Haitoro 数据库")
    parser.add_argument(
        "--adopt-legacy",
        action="store_true",
        help="备份后接管没有 alembic_version 的旧数据库；只应执行一次",
    )
    run(adopt_legacy=parser.parse_args().adopt_legacy)
