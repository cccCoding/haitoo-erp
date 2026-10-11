"""删除妙手采集箱同步缓存及公司同步游标。"""

from alembic import op
import sqlalchemy as sa


revision = "20261011_33"
down_revision = "20261010_32"
branch_labels = None
depends_on = None

SYNC_COLUMNS = (
    "miaoshou_collect_box_initial_synced_at",
    "miaoshou_collect_box_last_synced_at",
    "miaoshou_collect_box_last_pruned_at",
)


def upgrade() -> None:
    # 只删除外部采集同步缓存；草稿的发布编号、店铺和妙手凭据继续保留。
    op.drop_table("miaoshou_collect_box_items")
    with op.batch_alter_table("companies") as batch:
        for name in SYNC_COLUMNS:
            batch.drop_column(name)


def downgrade() -> None:
    # 回滚仅恢复空表结构，已删除的同步缓存与时间游标不会恢复。
    for name in SYNC_COLUMNS:
        op.add_column("companies", sa.Column(name, sa.DateTime(), nullable=True))
    op.create_table(
        "miaoshou_collect_box_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("common_collect_box_detail_id", sa.String(120), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("thumbnail", sa.String(500), nullable=True),
        sa.Column("status", sa.String(64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("remote_created_at", sa.DateTime(), nullable=True),
        sa.Column("remote_updated_at", sa.DateTime(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "common_collect_box_detail_id", name="uq_miaoshou_collect_box_company_detail"),
    )
    for name in ("company_id", "common_collect_box_detail_id", "status", "remote_created_at", "remote_updated_at"):
        op.create_index(op.f(f"ix_miaoshou_collect_box_items_{name}"), "miaoshou_collect_box_items", [name])
