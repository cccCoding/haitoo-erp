"""模板显式设置性别和年龄，统一材质与面料，保留任务快照。"""
import hashlib
import unicodedata
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = '20261030_54'
down_revision = '20261030_53'
branch_labels = None
depends_on = None


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def upgrade():
    op.add_column('title_template_profiles', sa.Column('gender', sa.String(10), nullable=True))
    op.add_column('title_template_profiles', sa.Column('age_group', sa.String(10), nullable=True))
    db = op.get_bind()
    profiles = sa.table('title_template_profiles', sa.column('id', sa.Integer()), sa.column('attributes', sa.JSON()),
        sa.column('gender'), sa.column('age_group'))
    for row in db.execute(sa.select(profiles)).mappings():
        attributes = dict(row['attributes'] or {})
        gender, age = attributes.get('性别'), attributes.get('年龄')
        audience_conflict = gender == '儿童' and age and age != '儿童'
        gender_value = gender if gender in ('男', '女', '中性') else None
        age_value = None if audience_conflict else (age if age in ('成人', '儿童') else ('儿童' if gender == '儿童' and not age else None))
        if gender_value or gender == '儿童' and not audience_conflict:
            attributes.pop('性别', None)
        if age_value and age in ('成人', '儿童'):
            attributes.pop('年龄', None)
        if '面料' in attributes:
            if not attributes.get('材质'):
                attributes['材质'] = attributes.pop('面料')
            elif normalized(attributes['材质']) == normalized(attributes['面料']):
                attributes.pop('面料')
            # 不同值保留两项，由新页面提示人工确认。
        db.execute(profiles.update().where(profiles.c.id == row['id']).values(
            gender=gender_value, age_group=age_value, attributes=attributes))
    dictionary = sa.table('title_dictionary_entries', sa.column('kind'), sa.column('name'),
        sa.column('semantic_tag'), sa.column('built_in', sa.Boolean()))
    db.execute(dictionary.update().where(dictionary.c.kind == 'tag', dictionary.c.semantic_tag == '面料').values(semantic_tag='材质'))
    db.execute(dictionary.delete().where(dictionary.c.kind == 'tag', dictionary.c.built_in.is_(True), dictionary.c.name.in_(('年龄', '面料'))))
    # 分类原有 gender 列保留历史值供回滚核对，但新配置不从分类推断模板性别。


def downgrade():
    db = op.get_bind()
    profiles = sa.table('title_template_profiles', sa.column('id', sa.Integer()), sa.column('attributes', sa.JSON()),
        sa.column('gender'), sa.column('age_group'))
    for row in db.execute(sa.select(profiles)).mappings():
        attributes = dict(row['attributes'] or {})
        if row['gender']:
            attributes.setdefault('性别', row['gender'])
        if row['age_group']:
            attributes.setdefault('年龄', row['age_group'])
        db.execute(profiles.update().where(profiles.c.id == row['id']).values(attributes=attributes))
    table = sa.table('title_dictionary_entries', sa.column('market_id', sa.Integer()), sa.column('kind'), sa.column('name'),
        sa.column('name_key'), sa.column('description'), sa.column('semantic_tag'), sa.column('built_in', sa.Boolean()),
        sa.column('enabled', sa.Boolean()), sa.column('updated_at', sa.DateTime()))
    markets = sa.table('title_markets', sa.column('id', sa.Integer()))
    for market_id in db.scalars(sa.select(markets.c.id)):
        for name in ('年龄', '面料'):
            key = hashlib.sha256(normalized(name).encode()).hexdigest()
            if not db.scalar(sa.select(table.c.name).where(table.c.market_id == market_id, table.c.kind == 'tag', table.c.name_key == key)):
                db.execute(table.insert().values(market_id=market_id, kind='tag', name=name, name_key=key,
                    description='', semantic_tag=name, built_in=True, enabled=True, updated_at=datetime.utcnow()))
    op.drop_column('title_template_profiles', 'age_group')
    op.drop_column('title_template_profiles', 'gender')
