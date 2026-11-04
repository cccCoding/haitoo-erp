"""为任务中心分页和统计增加覆盖索引。"""
from alembic import op

revision = "20261104_64"
down_revision = "20261104_63"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_pod_tasks_company_type_id_status", ["company_id", "task_type", "id", "status"]),
    ("ix_pod_tasks_company_creator_type_id_status", ["company_id", "created_by", "task_type", "id", "status"]),
)


def upgrade():
    for name, columns in INDEXES:
        op.create_index(name, "pod_tasks", columns)


def downgrade():
    for name, _ in reversed(INDEXES):
        op.drop_index(name, table_name="pod_tasks")
