"""补齐店铺外部身份约束与 Hub 上传任务索引

Revision ID: 20260924_16
Revises: 20260920_15
Create Date: 2026-09-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260924_16"
down_revision: Union[str, None] = "20260920_15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SHOP_IDENTITY_CONSTRAINT = "uq_shops_company_external_shop_type"
HUB_UPLOAD_TASK_INDEXES = {
    "ix_hub_upload_tasks_status": ["status"],
    "ix_hub_upload_tasks_created_by": ["created_by"],
    "ix_hub_upload_tasks_claim_token": ["claim_token"],
}


def upgrade() -> None:
    connection = op.get_bind()
    duplicate_rows = connection.execute(sa.text("""
        SELECT company_id, external_shop_id, shop_type, COUNT(*) AS duplicate_count
        FROM shops
        WHERE external_shop_id IS NOT NULL
        GROUP BY company_id, external_shop_id, shop_type
        HAVING COUNT(*) > 1
        LIMIT 10
    """)).mappings().all()
    if duplicate_rows:
        examples = ", ".join(
            f"(company_id={row['company_id']}, external_shop_id={row['external_shop_id']}, "
            f"shop_type={row['shop_type']}, count={row['duplicate_count']})"
            for row in duplicate_rows
        )
        raise RuntimeError(
            "无法创建店铺外部身份唯一约束：发现重复跨境店。请先合并重复记录及其关联数据后重试；"
            f"示例：{examples}"
        )

    unique_constraints = {
        item["name"] for item in sa.inspect(connection).get_unique_constraints("shops")
    }
    if SHOP_IDENTITY_CONSTRAINT not in unique_constraints:
        with op.batch_alter_table("shops") as batch:
            batch.create_unique_constraint(
                SHOP_IDENTITY_CONSTRAINT,
                ["company_id", "external_shop_id", "shop_type"],
            )

    existing_indexes = {
        item["name"] for item in sa.inspect(connection).get_indexes("hub_upload_tasks")
    }
    for name, columns in HUB_UPLOAD_TASK_INDEXES.items():
        if name not in existing_indexes:
            op.create_index(name, "hub_upload_tasks", columns, unique=False)


def downgrade() -> None:
    for name in HUB_UPLOAD_TASK_INDEXES:
        op.drop_index(name, table_name="hub_upload_tasks")
    with op.batch_alter_table("shops") as batch:
        batch.drop_constraint(SHOP_IDENTITY_CONSTRAINT, type_="unique")
