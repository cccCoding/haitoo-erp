"""为新 AI 候选分配独立存储身份；已有记录继续使用原路径。"""
from alembic import op
import sqlalchemy as sa

revision = "20261104_63"
down_revision = "20261104_62"
branch_labels = None
depends_on = None


def upgrade():
    # 不回填、不设置数据库默认值：已有对象可能已复制但尚未登记，必须保留旧路径。
    with op.batch_alter_table("ai_image_candidates") as batch:
        batch.add_column(sa.Column("storage_uid", sa.String(32), nullable=True))
        batch.create_unique_constraint("uq_ai_candidate_storage_uid", ["storage_uid"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM ai_image_candidates WHERE storage_uid IS NOT NULL")).scalar():
        raise RuntimeError("存在随机存储标识，不能降级丢弃正式路径身份；请保留当前结构并关闭新任务直存")
    with op.batch_alter_table("ai_image_candidates") as batch:
        batch.drop_constraint("uq_ai_candidate_storage_uid", type_="unique")
        batch.drop_column("storage_uid")
