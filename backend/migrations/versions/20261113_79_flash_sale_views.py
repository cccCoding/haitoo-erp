"""秒杀活动完整快照及行内活动数据。"""
from alembic import op
import sqlalchemy as sa

revision = "20261113_79"
down_revision = "20261113_78"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("matrix_flash_activities",sa.Column("starts_at",sa.DateTime(),nullable=True))
    op.add_column("matrix_flash_activities",sa.Column("present",sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_table("matrix_flash_snapshots",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("company_id",sa.Integer(),nullable=False),
        sa.Column("environment_id",sa.Integer(),nullable=False),
        sa.Column("observed_at",sa.DateTime(),nullable=False),
        sa.Column("source_item_id",sa.Integer(),nullable=False),
        sa.Column("activity_count",sa.Integer(),nullable=False),
        sa.UniqueConstraint("company_id","environment_id",name="uq_matrix_flash_snapshot"))
    for field in ("company_id","environment_id"):
        op.create_index(f"ix_matrix_flash_snapshots_{field}","matrix_flash_snapshots",[field])


def downgrade():
    op.drop_table("matrix_flash_snapshots")
    op.drop_column("matrix_flash_activities","present")
    op.drop_column("matrix_flash_activities","starts_at")
