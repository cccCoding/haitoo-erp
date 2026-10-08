"""保存任务模版快照；仅回填可完整确认的历史任务。"""
import json
from alembic import op
import sqlalchemy as sa

revision = "20261008_31"
down_revision = "20261007_30"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("hub_upload_tasks") as batch:
        batch.add_column(sa.Column("template_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("template_name", sa.String(120), nullable=True))
        batch.create_index("ix_hub_upload_tasks_template_id", ["template_id"])
    db = op.get_bind()
    tasks = db.execute(sa.text("SELECT id, company_id, draft_ids FROM hub_upload_tasks")).mappings()
    for task in tasks:
        try:
            ids = json.loads(task["draft_ids"]) if isinstance(task["draft_ids"], str) else task["draft_ids"]
            if not isinstance(ids, list) or not ids or any(type(value) is not int for value in ids):
                continue
            drafts = db.execute(sa.text("SELECT id, company_id, template_id FROM product_drafts WHERE id IN :ids").bindparams(sa.bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
            if len(drafts) != len(set(ids)) or any(row["company_id"] != task["company_id"] for row in drafts):
                continue
            templates = {row["template_id"] for row in drafts}
            if len(templates) != 1 or None in templates:
                continue
            template = db.execute(sa.text("SELECT id, name, company_id, is_platform FROM product_templates WHERE id=:id"), {"id": templates.pop()}).mappings().first()
            if template and (template["is_platform"] or template["company_id"] == task["company_id"]):
                db.execute(sa.text("UPDATE hub_upload_tasks SET template_id=:template_id, template_name=:name WHERE id=:id"), {"template_id": template["id"], "name": template["name"], "id": task["id"]})
        except (ValueError, TypeError):
            continue


def downgrade():
    with op.batch_alter_table("hub_upload_tasks") as batch:
        batch.drop_index("ix_hub_upload_tasks_template_id")
        batch.drop_column("template_name")
        batch.drop_column("template_id")
