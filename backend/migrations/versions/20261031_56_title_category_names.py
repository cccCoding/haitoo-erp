"""分类标准名与别名共用唯一索引，保存合并指向和操作记录。"""
from alembic import op
import sqlalchemy as sa

revision = '20261031_56'
down_revision = '20261030_55'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('title_dictionary_entries', sa.Column('merged_into_id', sa.Integer(), nullable=True))
    names = op.create_table('title_category_names',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('title_dictionary_entries.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('name_key', sa.String(64), nullable=False),
        sa.UniqueConstraint('market_id', 'name_key', name='uq_title_category_name'))
    op.create_index('ix_title_category_names_market_id', 'title_category_names', ['market_id'])
    op.create_index('ix_title_category_names_category_id', 'title_category_names', ['category_id'])
    op.create_table('title_category_merges',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('source_ids', sa.JSON(), nullable=False),
        sa.Column('preview_token', sa.String(64), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('market_id', 'preview_token', name='uq_title_category_merge'))
    op.create_index('ix_title_category_merges_market_id', 'title_category_merges', ['market_id'])
    op.create_index('ix_title_category_merges_user_id', 'title_category_merges', ['user_id'])
    dictionary = sa.table('title_dictionary_entries', sa.column('id', sa.Integer()),
        sa.column('market_id', sa.Integer()), sa.column('kind', sa.String(20)),
        sa.column('name', sa.String(255)), sa.column('name_key', sa.String(64)))
    # 只登记已有标准名称；不推断同义关系，也不改写任何业务引用或快照。
    op.execute(names.insert().from_select(['market_id', 'category_id', 'name', 'name_key'],
        sa.select(dictionary.c.market_id, dictionary.c.id, dictionary.c.name, dictionary.c.name_key)
        .where(dictionary.c.kind == 'category')))


def downgrade():
    op.drop_table('title_category_merges')
    op.drop_table('title_category_names')
    op.drop_column('title_dictionary_entries', 'merged_into_id')
