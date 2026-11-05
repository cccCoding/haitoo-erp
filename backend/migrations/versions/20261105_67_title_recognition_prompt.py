"""模板词库配置增加服装识图补充提示词。"""
from alembic import op
import sqlalchemy as sa

revision = '20261105_67'
down_revision = '20261104_66'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('title_template_profiles', sa.Column('recognition_prompt', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('title_template_profiles', 'recognition_prompt')
