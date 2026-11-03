"""新增可授予的标题词库管理权限，现有成员默认不授予。"""
from alembic import op
import sqlalchemy as sa

revision = '20261103_60'
down_revision = '20261102_59'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('title_library_admin', sa.Boolean(), nullable=False,
                                   server_default=sa.text('0')))


def downgrade():
    op.drop_column('users', 'title_library_admin')
