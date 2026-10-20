"""永久素材风格及可确认的白底图、AI 任务和素材历史归属。"""
import json

from alembic import op
import sqlalchemy as sa

revision = "20261020_42"
down_revision = "20261020_41"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    # SQLite 默认会复用已删除的最大主键；永久风格必须始终追溯原白底图。
    if db.dialect.name == "sqlite":
        with op.batch_alter_table("user_template_white_images", recreate="always",
                                 table_kwargs={"sqlite_autoincrement": True}):
            pass
    op.create_table("material_styles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("source_white_image_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_white_image_id", name="uq_material_styles_white_image"))
    op.create_index("ix_material_styles_company_template", "material_styles", ["company_id", "template_id"])
    op.add_column("material_assets", sa.Column("style_id", sa.Integer(), nullable=True))
    op.create_index("ix_material_assets_company_template_style", "material_assets", ["company_id", "template_id", "style_id"])
    # 不依赖运行中的 ORM，保持历史迁移可以独立重放。
    db.execute(sa.text("""INSERT INTO material_styles
        (company_id, template_id, source_white_image_id, name, created_by, created_at, updated_at)
        SELECT company_id, template_id, id, name, user_id, created_at, updated_at
        FROM user_template_white_images ORDER BY id"""))
    sources = {row["source_white_image_id"]: row for row in db.execute(sa.text("""
        SELECT s.id AS style_id, s.source_white_image_id, s.company_id, s.template_id,
               s.created_by, w.image_url
        FROM material_styles s JOIN user_template_white_images w ON w.id=s.source_white_image_id
    """)).mappings()}
    tasks = sa.table("pod_tasks", sa.column("id", sa.Integer()), sa.column("parameters", sa.JSON()))
    last_id = 0
    while True:
        batch = db.execute(sa.text("""SELECT id, company_id, template_id, created_by, parameters
            FROM pod_tasks WHERE id > :last_id AND task_type='sku_image' ORDER BY id LIMIT 500"""),
            {"last_id": last_id}).mappings().all()
        if not batch:
            break
        for task in batch:
            last_id = task["id"]
            try:
                params = json.loads(task["parameters"]) if isinstance(task["parameters"], str) else task["parameters"]
            except (ValueError, TypeError):
                continue
            if not isinstance(params, dict) or type(params.get("white_image_id")) is not int:
                continue
            source = sources.get(params["white_image_id"])
            if not source or (source["company_id"], source["template_id"], source["created_by"], source["image_url"]) != (
                    task["company_id"], task["template_id"], task["created_by"], params.get("white_image_url")):
                continue
            db.execute(tasks.update().where(tasks.c.id == task["id"]).values(
                parameters={**params, "style_id": source["style_id"]}))
            db.execute(sa.text("""UPDATE material_assets SET style_id=:style_id
                WHERE source_task_id=:task_id AND company_id=:company_id AND template_id=:template_id
                  AND claimed_by=:created_by AND (source_type IS NULL OR source_type IN ('', 'ai_created'))"""),
                {**dict(task), "style_id": source["style_id"], "task_id": task["id"]})


def downgrade():
    db = op.get_bind()
    tasks = sa.table("pod_tasks", sa.column("id", sa.Integer()), sa.column("parameters", sa.JSON()))
    last_id = 0
    while True:
        batch = db.execute(sa.text("SELECT id, parameters FROM pod_tasks WHERE id>:last_id ORDER BY id LIMIT 500"),
            {"last_id": last_id}).mappings().all()
        if not batch:
            break
        for row in batch:
            last_id = row["id"]
            try:
                params = json.loads(row["parameters"]) if isinstance(row["parameters"], str) else row["parameters"]
            except (ValueError, TypeError):
                continue
            if isinstance(params, dict) and "style_id" in params:
                db.execute(tasks.update().where(tasks.c.id == row["id"]).values(
                    parameters={key: value for key, value in params.items() if key != "style_id"}))
    op.drop_index("ix_material_assets_company_template_style", table_name="material_assets")
    with op.batch_alter_table("material_assets") as batch:
        batch.drop_column("style_id")
    op.drop_index("ix_material_styles_company_template", table_name="material_styles")
    op.drop_table("material_styles")
    if db.dialect.name == "sqlite":
        with op.batch_alter_table("user_template_white_images", recreate="always",
                                 table_kwargs={"sqlite_autoincrement": False}):
            pass
