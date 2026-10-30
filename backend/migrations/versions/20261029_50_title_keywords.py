"""马来西亚站点词库与持久化标题任务，历史标题保持原样。"""
from alembic import op
import sqlalchemy as sa

revision = "20261029_50"
down_revision = "20261026_49"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('title_markets',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('platform', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('site', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('language', sa.String(length=10), nullable=False, primary_key=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('next_code', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint('company_id', 'platform', 'site', 'language', name='uq_title_market'))
    op.create_index('ix_title_markets_company_id', 'title_markets', ['company_id'])
    op.create_table('title_template_profiles',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('market_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('template_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('category', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('attributes', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('category_names', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('locked_keyword_ids', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('forbidden_keyword_ids', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('fallback_title', sa.String(length=220), nullable=True, primary_key=False),
        sa.Column('fallback_approved', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint('market_id', 'template_id', name='uq_title_template_profile'))
    op.create_index('ix_title_template_profiles_market_id', 'title_template_profiles', ['market_id'])
    op.create_index('ix_title_template_profiles_template_id', 'title_template_profiles', ['template_id'])
    op.create_table('title_keywords',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('market_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('code', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('phrase', sa.String(length=160), nullable=False, primary_key=False),
        sa.Column('translation', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('identity_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('tag', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('categories', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('synonyms', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('conflicts', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('is_borrowed', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('priority', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('selected_count', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('adopted_count', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True, primary_key=False),
        sa.Column('merged_into_id', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint('market_id', 'code', name='uq_title_keyword_code'),
        sa.UniqueConstraint('market_id', 'identity_hash', name='uq_title_keyword_identity'))
    op.create_index('ix_title_keywords_market_id', 'title_keywords', ['market_id'])
    op.create_table('title_evidence',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('market_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('keyword_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('import_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('observation_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('original_title', sa.Text(), nullable=False, primary_key=False),
        sa.Column('original_phrase', sa.String(length=160), nullable=False, primary_key=False),
        sa.Column('source_name', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('source_product', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('source_url', sa.Text(), nullable=True, primary_key=False),
        sa.Column('period', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('source_kind', sa.String(length=20), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('metrics', sa.JSON(), nullable=False, primary_key=False),
        sa.UniqueConstraint('market_id', 'observation_hash', name='uq_title_evidence_observation'))
    op.create_index('ix_title_evidence_import_id', 'title_evidence', ['import_id'])
    op.create_index('ix_title_evidence_keyword_id', 'title_evidence', ['keyword_id'])
    op.create_index('ix_title_evidence_market_id', 'title_evidence', ['market_id'])
    op.create_table('title_tasks',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('market_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('user_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('request_key', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('state', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('snapshot', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('result', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('progress', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('error', sa.Text(), nullable=True, primary_key=False),
        sa.Column('lease_owner', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('lease_expires_at', sa.DateTime(), nullable=True, primary_key=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint('market_id', 'request_key', name='uq_title_task_request'))
    op.create_index('ix_title_task_queue', 'title_tasks', ['state', 'lease_expires_at', 'id'])
    op.create_index('ix_title_tasks_market_id', 'title_tasks', ['market_id'])
    op.create_index('ix_title_tasks_user_id', 'title_tasks', ['user_id'])
    op.create_table('title_records',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('market_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('user_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('template_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('task_id', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('draft_id', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('request_key', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('category', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('image_url', sa.Text(), nullable=False, primary_key=False),
        sa.Column('snapshot', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('facts', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('selected_keywords', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('title', sa.String(length=255), nullable=True, primary_key=False),
        sa.Column('warnings', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('attempts', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('state', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('source', sa.String(length=20), nullable=False, primary_key=False),
        sa.Column('error', sa.Text(), nullable=True, primary_key=False),
        sa.Column('lease_owner', sa.String(length=64), nullable=True, primary_key=False),
        sa.Column('lease_expires_at', sa.DateTime(), nullable=True, primary_key=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('adopted_at', sa.DateTime(), nullable=True, primary_key=False),
        sa.UniqueConstraint('market_id', 'request_key', name='uq_title_record_request'))
    op.create_index('ix_title_record_history', 'title_records', ['market_id', 'category', 'adopted_at'])
    op.create_index('ix_title_records_draft_id', 'title_records', ['draft_id'])
    op.create_index('ix_title_records_market_id', 'title_records', ['market_id'])
    op.create_index('ix_title_records_task_id', 'title_records', ['task_id'])
    op.create_index('ix_title_records_template_id', 'title_records', ['template_id'])
    op.create_index('ix_title_records_user_id', 'title_records', ['user_id'])
    op.create_table('title_attribute_cache',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('market_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('cache_key', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('facts', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint('market_id', 'cache_key', name='uq_title_attribute_cache'))
    op.create_index('ix_title_attribute_cache_market_id', 'title_attribute_cache', ['market_id'])

    op.create_table('title_import_words',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('identity_hash', sa.String(64), nullable=False),
        sa.Column('word', sa.JSON(), nullable=False),
        sa.UniqueConstraint('task_id', 'row_number', 'identity_hash', name='uq_title_import_word'))
    op.create_index('ix_title_import_words_task_id', 'title_import_words', ['task_id'])


def downgrade():
    op.drop_table('title_import_words')
    op.drop_table('title_attribute_cache')
    op.drop_table('title_records')
    op.drop_table('title_tasks')
    op.drop_table('title_evidence')
    op.drop_table('title_keywords')
    op.drop_table('title_template_profiles')
    op.drop_table('title_markets')
