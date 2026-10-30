"""产品分类新增性别；品类与性别不再作为内置标签。"""
from datetime import datetime
import hashlib

from alembic import op
import sqlalchemy as sa

revision = '20261030_52'
down_revision = '20261030_51'
branch_labels = None
depends_on = None

CATEGORY_FIELDS = ('品类', '性别')


def upgrade():
    # 旧分类保持未设置，不根据名称、模特外观或关键词猜测性别。
    op.add_column('title_dictionary_entries', sa.Column('gender', sa.String(10), nullable=True))
    table = sa.table('title_dictionary_entries', sa.column('kind'), sa.column('name'), sa.column('built_in', sa.Boolean()))
    op.get_bind().execute(table.delete().where(table.c.kind == 'tag', table.c.built_in.is_(True), table.c.name.in_(CATEGORY_FIELDS)))


def downgrade():
    db = op.get_bind()
    table = sa.table('title_dictionary_entries', sa.column('market_id', sa.Integer()), sa.column('kind'),
        sa.column('name'), sa.column('name_key'), sa.column('description'), sa.column('semantic_tag'),
        sa.column('built_in', sa.Boolean()), sa.column('enabled', sa.Boolean()), sa.column('updated_at', sa.DateTime()))
    markets = sa.table('title_markets', sa.column('id', sa.Integer()))
    for market_id in db.scalars(sa.select(markets.c.id)):
        for name in CATEGORY_FIELDS:
            key = hashlib.sha256(name.encode()).hexdigest()
            if not db.scalar(sa.select(table.c.name).where(table.c.market_id == market_id, table.c.kind == 'tag', table.c.name_key == key)):
                db.execute(table.insert().values(market_id=market_id, kind='tag', name=name, name_key=key,
                    description='', semantic_tag=name, built_in=True, enabled=True, updated_at=datetime.utcnow()))
    op.drop_column('title_dictionary_entries', 'gender')
