"""货盘兜底标题扩容至 230 字符。"""
from alembic import op
import sqlalchemy as sa

revision = '20261104_65'
down_revision = '20261104_64'
branch_labels = None
depends_on = None

COLUMNS = (
    ('product_templates', 'supply_fallback_title'),
    ('title_template_profiles', 'fallback_title'),
)


def resize(previous, current):
    for table, column in COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, existing_type=sa.String(previous),
                               type_=sa.String(current), existing_nullable=True)


def upgrade():
    resize(220, 230)


def downgrade():
    connection = op.get_bind()
    # 必须在任何 DDL 前检查两列，避免部分缩列或 MySQL 静默截断。
    for table, column in COLUMNS:
        value = sa.column(column, sa.String())
        length = sa.func.char_length(value) if connection.dialect.name in {'mysql', 'mariadb'} else sa.func.length(value)
        query = sa.select(sa.func.count()).select_from(sa.table(table, value)).where(length > 220)
        if connection.scalar(query):
            raise RuntimeError(f'{table}.{column} 存在超过 220 字符的标题，拒绝降级；请先处理数据')
    resize(230, 220)
