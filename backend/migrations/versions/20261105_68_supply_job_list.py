"""为货盘任务下载状态查询增加覆盖索引。"""
from alembic import op

revision = "20261105_68"
down_revision = "20261105_67"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_supply_audits_download", "supply_audits",
                    ["company_id", "action", "target_type", "target_id"])


def downgrade():
    op.drop_index("ix_supply_audits_download", table_name="supply_audits")
