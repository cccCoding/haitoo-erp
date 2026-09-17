"""新增 Grsai gpt-image-2 并移除其他图像平台

Revision ID: 20260917_10
Revises: 20260917_09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260917_10"
down_revision: Union[str, None] = "20260917_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_PROVIDERS = ("seedream", "qwen", "gemini")


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("ai_provider_settings")}
    if "credential_provider" not in columns:
        op.add_column("ai_provider_settings", sa.Column("credential_provider", sa.String(40), nullable=True))
    connection.execute(sa.text("UPDATE ai_provider_settings SET credential_provider = 'grsai' WHERE provider = 'grsai'"))

    tasks = sa.table("pod_tasks", sa.column("id", sa.Integer()), sa.column("provider", sa.String()), sa.column("result_urls", sa.JSON()))
    materials = sa.table("material_assets", sa.column("source_task_id", sa.Integer()), sa.column("url", sa.String()))
    drafts = sa.table("product_drafts", sa.column("id", sa.Integer()), sa.column("sku_items", sa.JSON()),
                      sa.column("carousel_items", sa.JSON()), sa.column("image_urls", sa.JSON()))
    task_rows = list(connection.execute(sa.select(tasks.c.id, tasks.c.result_urls).where(tasks.c.provider.in_(OLD_PROVIDERS))).mappings())
    task_ids = [row["id"] for row in task_rows]

    if task_ids:
        # 删除旧平台任务派生素材，并移除草稿中仍指向这些任务或结果图片的项目。
        material_urls = set(connection.execute(sa.select(materials.c.url).where(materials.c.source_task_id.in_(task_ids))).scalars())
        connection.execute(materials.delete().where(materials.c.source_task_id.in_(task_ids)))
        result_urls = {url for row in task_rows for url in (row["result_urls"] or []) if isinstance(url, str)} | material_urls
        for draft in connection.execute(sa.select(drafts)).mappings():
            sku_items = [item for item in (draft["sku_items"] or []) if isinstance(item, dict) and item.get("image_url") not in result_urls]
            items = [item for item in (draft["carousel_items"] or []) if isinstance(item, dict)
                     and item.get("task_id") not in task_ids and item.get("image_url") not in result_urls]
            image_urls = [url for url in (draft["image_urls"] or []) if url not in result_urls]
            if sku_items != (draft["sku_items"] or []) or items != (draft["carousel_items"] or []) or image_urls != (draft["image_urls"] or []):
                connection.execute(drafts.update().where(drafts.c.id == draft["id"]).values(sku_items=sku_items, carousel_items=items, image_urls=image_urls))
        connection.execute(tasks.delete().where(tasks.c.id.in_(task_ids)))

    connection.execute(sa.text("DELETE FROM user_ai_provider_credentials WHERE provider IN ('seedream', 'qwen', 'gemini')"))
    connection.execute(sa.text("DELETE FROM ai_provider_settings WHERE provider IN ('seedream', 'qwen', 'gemini')"))
    connection.execute(sa.text("UPDATE ai_provider_settings SET display_name = 'Grsai · Nano Banana Fast', credential_provider = 'grsai' WHERE provider = 'grsai'"))
    exists = connection.execute(sa.text("SELECT 1 FROM ai_provider_settings WHERE provider = 'grsai-gpt-image-2'")).first()
    if not exists:
        connection.execute(sa.text("""
            INSERT INTO ai_provider_settings (provider, display_name, model, credential_provider, enabled, is_default, images_per_task)
            VALUES ('grsai-gpt-image-2', 'Grsai · GPT Image 2', 'gpt-image-2', 'grsai', 1, 0, 1)
        """))
    with op.batch_alter_table("ai_provider_settings") as batch:
        batch.alter_column("credential_provider", existing_type=sa.String(40), nullable=False)


def downgrade() -> None:
    # 已删除的旧平台任务、密钥及关联素材不恢复。
    op.drop_column("ai_provider_settings", "credential_provider")
