"""模板工艺、品牌支持人工多选，保留旧属性及历史任务。"""
from alembic import op
import sqlalchemy as sa

revision = '20261104_66'
down_revision = '20261104_65'
branch_labels = None
depends_on = None


def upgrade():
    for field in ('craft_keyword_ids', 'brand_keyword_ids'):
        op.add_column('title_template_profiles', sa.Column(field, sa.JSON(), nullable=True))


def downgrade():
    for field in ('brand_keyword_ids', 'craft_keyword_ids'):
        op.drop_column('title_template_profiles', field)
