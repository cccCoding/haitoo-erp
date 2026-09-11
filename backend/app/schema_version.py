"""数据库版本检查；应用进程只读版本，不执行迁移。"""

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection, Engine


ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def schema_heads(connection: Connection) -> tuple[set[str], set[str]]:
    config = alembic_config(connection)
    expected = set(ScriptDirectory.from_config(config).get_heads())
    current = set(MigrationContext.configure(connection).get_current_heads())
    return current, expected


def assert_schema_current(engine: Engine) -> None:
    with engine.connect() as connection:
        current, expected = schema_heads(connection)
    if current != expected:
        current_text = ", ".join(sorted(current)) or "未迁移"
        expected_text = ", ".join(sorted(expected)) or "无迁移版本"
        raise RuntimeError(
            f"数据库版本不匹配：当前 {current_text}，要求 {expected_text}；"
            "请先执行 python -m app.db_migrate"
        )
