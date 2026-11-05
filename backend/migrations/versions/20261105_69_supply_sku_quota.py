"""保存货盘最终 SKU 快照，从历史选图记录回填账号累计额度。"""
from alembic import op
import sqlalchemy as sa

revision = "20261105_69"
down_revision = "20261105_68"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    # MySQL DDL 自动提交；回填发现异常后允许修复历史数据并重跑同一迁移。
    if "sku" not in {item["name"] for item in sa.inspect(connection).get_columns("supply_job_materials")}:
        op.add_column("supply_job_materials", sa.Column("sku", sa.String(24), nullable=True))
    materials = sa.table("supply_job_materials", sa.column("id", sa.Integer()),
        sa.column("company_id", sa.Integer()), sa.column("job_id", sa.Integer()),
        sa.column("material_id", sa.Integer()), sa.column("version_hash", sa.String(64)),
        sa.column("link_index", sa.Integer()), sa.column("successful", sa.Boolean()),
        sa.column("sku", sa.String(24)))
    jobs = sa.table("supply_jobs", sa.column("id", sa.Integer()), sa.column("company_id", sa.Integer()),
        sa.column("snapshot", sa.JSON()), sa.column("checkpoint", sa.JSON()))
    last_id = 0
    while True:
        ids = connection.scalars(sa.select(materials.c.job_id).where(materials.c.successful.is_(True),
            materials.c.sku.is_(None), materials.c.job_id > last_id).distinct().order_by(
                materials.c.job_id).limit(100)).all()
        if not ids:
            break
        for job in connection.execute(sa.select(jobs).where(jobs.c.id.in_(ids))).mappings():
            # 最终检查点优先，候选快照兼容旧任务；均按当时版本匹配，绝不依赖当前素材。
            final = {(link["index"], item["id"], item["version_hash"]): item.get("sku")
                     for link in (job["checkpoint"] or {}).get("links", []) for item in link["materials"]}
            candidates = {(item["id"], item["version_hash"]): item.get("sku")
                          for item in (job["snapshot"] or {}).get("candidates", [])}
            rows = connection.execute(sa.select(materials).where(materials.c.job_id == job["id"],
                materials.c.company_id == job["company_id"], materials.c.successful.is_(True),
                materials.c.sku.is_(None))).mappings().all()
            updates = []
            for row in rows:
                sku = final.get((row["link_index"], row["material_id"], row["version_hash"])) or candidates.get(
                    (row["material_id"], row["version_hash"]))
                if not isinstance(sku, str) or not sku.strip() or len(sku.strip()) > 24:
                    raise RuntimeError(f"货盘历史任务 #{job['id']} 的素材记录 #{row['id']} 缺少有效 SKU 快照，请修复后重试迁移")
                updates.append({"row_id": row["id"], "snapshot_sku": sku.strip()})
            if updates:
                connection.execute(materials.update().where(materials.c.id == sa.bindparam("row_id")).values(
                    sku=sa.bindparam("snapshot_sku")), updates)
        last_id = ids[-1]
    if connection.scalar(sa.select(materials.c.id).where(
            materials.c.successful.is_(True), materials.c.sku.is_(None)).limit(1)) is not None:
        raise RuntimeError("货盘历史成功素材缺少对应任务，无法回填 SKU，请修复后重试迁移")
    if "ix_supply_job_materials_sku_usage" not in {
            item["name"] for item in sa.inspect(connection).get_indexes("supply_job_materials")}:
        op.create_index("ix_supply_job_materials_sku_usage", "supply_job_materials",
                        ["company_id", "sku", "successful", "job_id", "link_index"])


def downgrade():
    op.drop_index("ix_supply_job_materials_sku_usage", table_name="supply_job_materials")
    op.drop_column("supply_job_materials", "sku")
