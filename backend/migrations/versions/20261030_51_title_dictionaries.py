"""词库产品分类与标签字典，回填既有分类和标签，不改写历史任务。"""
import hashlib
import unicodedata
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = '20261030_51'
down_revision = '20261029_50'
branch_labels = None
depends_on = None

TAGS = ['品类', '性别', '年龄', '人群', '风格', '场景', '季节', '气候', '材质', '面料', '版型', '尺码', '长度',
        '颜色', '图案', '结构设计', '细节元素', '工艺', '功能', '穿着效果', '搭配', '价格定位', '品牌', '流行趋势',
        '地域文化', '搜索意图', '长尾程度', '营销修饰', '时间节点', '目标市场', '搜索语言', '关键词热度', '关键词竞争度', '待分类']


def key(value):
    normalized = ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


def upgrade():
    table = op.create_table('title_dictionary_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('market_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('name_key', sa.String(64), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('semantic_tag', sa.String(40), nullable=True),
        sa.Column('built_in', sa.Boolean(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('market_id', 'kind', 'name_key', name='uq_title_dictionary_name'))
    op.create_index('ix_title_dictionary_entries_market_id', 'title_dictionary_entries', ['market_id'])
    db = op.get_bind()
    markets = sa.table('title_markets', sa.column('id', sa.Integer()))
    words = sa.table('title_keywords', sa.column('market_id', sa.Integer()), sa.column('tag', sa.String()), sa.column('categories', sa.JSON()))
    profiles = sa.table('title_template_profiles', sa.column('market_id', sa.Integer()), sa.column('category', sa.String()))
    now = datetime.utcnow()
    for market_id in db.scalars(sa.select(markets.c.id)):
        values = {}
        def add(kind, name):
            name = str(name or '').strip()
            if not name:
                return
            values.setdefault((kind, key(name)), dict(market_id=market_id, kind=kind, name=name, name_key=key(name),
                description='', semantic_tag=(name if name in TAGS else '待分类') if kind == 'tag' else None,
                built_in=kind == 'tag' and name in TAGS, enabled=True, updated_at=now))
        for tag in TAGS:
            add('tag', tag)
        for word in db.execute(sa.select(words.c.tag, words.c.categories).where(words.c.market_id == market_id)):
            add('tag', word.tag)
            for category in word.categories or []:
                add('category', category)
        for category in db.scalars(sa.select(profiles.c.category).where(profiles.c.market_id == market_id)):
            add('category', category)
        db.execute(table.insert(), list(values.values()))


def downgrade():
    op.drop_index('ix_title_dictionary_entries_market_id', table_name='title_dictionary_entries')
    op.drop_table('title_dictionary_entries')
