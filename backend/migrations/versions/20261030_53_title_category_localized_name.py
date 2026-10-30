"""产品分类保存所属站点及语言的名称，保留既有分类标识和引用。"""
from alembic import op
import sqlalchemy as sa

revision = '20261030_53'
down_revision = '20261030_52'
branch_labels = None
depends_on = None


def upgrade():
    # 站点、语言来自分类所属市场；既有分类不由系统自动翻译。
    op.add_column('title_dictionary_entries', sa.Column('localized_name', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('title_dictionary_entries', 'localized_name')
