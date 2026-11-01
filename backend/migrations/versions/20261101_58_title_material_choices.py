"""模板面料支持多个关键词；保留历史单值属性和任务快照。"""
from alembic import op
import sqlalchemy as sa

revision = '20261101_58'
down_revision = '20261031_57'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('title_template_profiles', sa.Column('material_keyword_ids', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('title_template_profiles', 'material_keyword_ids')
