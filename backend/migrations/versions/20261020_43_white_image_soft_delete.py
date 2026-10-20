"""白底图软删除，保留来源记录和图片地址。"""
from alembic import op
import sqlalchemy as sa


revision = "20261020_43"
down_revision = "20261020_42"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_template_white_images", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_user_template_white_images_company_deleted", "user_template_white_images",
                    ["company_id", "deleted_at"])


def downgrade():
    # 仅移除删除标记；保留所有白底图记录、图片地址、风格及素材归属。
    op.drop_index("ix_user_template_white_images_company_deleted", table_name="user_template_white_images")
    with op.batch_alter_table("user_template_white_images") as batch:
        batch.drop_column("deleted_at")
