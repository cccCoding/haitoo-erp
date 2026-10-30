"""已确认入库的关键词直接启用，保留后续人工停用决定。"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = '20261030_55'
down_revision = '20261030_54'
branch_labels = None
depends_on = None


def upgrade():
    keywords = sa.table('title_keywords', sa.column('id', sa.Integer()), sa.column('market_id', sa.Integer()),
        sa.column('status', sa.String(20)), sa.column('merged_into_id', sa.Integer()), sa.column('updated_at', sa.DateTime()))
    evidence = sa.table('title_evidence', sa.column('keyword_id', sa.Integer()), sa.column('market_id', sa.Integer()),
        sa.column('import_id', sa.Integer()))
    tasks = sa.table('title_tasks', sa.column('id', sa.Integer()), sa.column('market_id', sa.Integer()),
        sa.column('kind', sa.String(20)), sa.column('state', sa.String(24)))
    markets = sa.table('title_markets', sa.column('id', sa.Integer()), sa.column('revision', sa.Integer()),
        sa.column('updated_at', sa.DateTime()))
    confirmed = sa.exists(sa.select(1).select_from(evidence.join(tasks, tasks.c.id == evidence.c.import_id)).where(
        evidence.c.keyword_id == keywords.c.id, evidence.c.market_id == keywords.c.market_id,
        tasks.c.market_id == keywords.c.market_id, tasks.c.kind == 'import', tasks.c.state == 'completed'))
    eligible = sa.and_(keywords.c.status == 'pending', keywords.c.merged_into_id.is_(None), confirmed)
    now = datetime.utcnow()
    db = op.get_bind()
    db.execute(markets.update().where(markets.c.id.in_(sa.select(keywords.c.market_id).where(eligible))).values(
        revision=markets.c.revision + 1, updated_at=now))
    db.execute(keywords.update().where(eligible).values(status='enabled', updated_at=now))


def downgrade():
    # 数据修正无法与后续人工启用区分，降级保留已有启停状态。
    pass
