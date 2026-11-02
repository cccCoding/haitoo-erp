"""拆分操作方案与运营计划，临时运行不依赖计划。"""
from alembic import op
import sqlalchemy as sa

revision = "20261108_73"
down_revision = "20261108_72"
branch_labels = None
depends_on = None


def upgrade():
    # 未上线的旧调试配置直接归档，不转换成新模型；版本与运行历史保留。
    op.execute(sa.text("UPDATE matrix_plans SET deleted = true"))
    op.create_table("matrix_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False))
    op.create_index("ix_matrix_operations_company_id", "matrix_operations", ["company_id"])
    op.create_index("ix_matrix_operations_owner_id", "matrix_operations", ["owner_id"])
    for table in ("matrix_previews", "matrix_runs"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column("plan_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    # 临时运行的 plan_id 为空，不能静默丢弃其历史。
    bind = op.get_bind()
    for table in ("matrix_previews", "matrix_runs"):
        if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE plan_id IS NULL")).scalar():
            raise RuntimeError("存在临时执行记录，不能回退到要求绑定计划的结构")
    for table in ("matrix_previews", "matrix_runs"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column("plan_id", existing_type=sa.Integer(), nullable=False)
    op.drop_table("matrix_operations")
