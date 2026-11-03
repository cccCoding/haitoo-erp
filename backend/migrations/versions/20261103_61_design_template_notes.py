"""按公司保存仅美工角色可见的模板备注，保留原模板公开状态。"""
from alembic import op
import sqlalchemy as sa

revision = '20261103_61'
down_revision = '20261103_60'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('design_template_visibility', sa.Column('note', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('design_template_visibility', 'note')
