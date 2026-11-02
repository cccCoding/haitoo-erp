"""TK矩阵协议5；新增表与兼容锁，不改变旧任务。"""
from alembic import op
import sqlalchemy as sa

revision = "20261106_70"
down_revision = "20261105_69"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('matrix_access',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('agent_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('environment_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('available', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('seen_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint('agent_id', 'environment_id', name='uq_matrix_access'),
    )
    op.create_index('ix_matrix_access_agent_id', 'matrix_access', ['agent_id'], unique=False)
    op.create_index('ix_matrix_access_environment_id', 'matrix_access', ['environment_id'], unique=False)
    op.create_table('matrix_allocations',
        sa.Column('shop_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('combination_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('item_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('state', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('payload', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('shop_id', 'combination_hash', name='uq_matrix_shop_combination'),
    )
    op.create_index('ix_matrix_allocations_company_id', 'matrix_allocations', ['company_id'], unique=False)
    op.create_index('ix_matrix_allocations_item_id', 'matrix_allocations', ['item_id'], unique=False)
    op.create_table('matrix_attempts',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('item_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('agent_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('number', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('fencing', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('lease_until', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('started_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint('item_id', 'number', name='uq_matrix_attempt'),
    )
    op.create_index('ix_matrix_attempts_item_id', 'matrix_attempts', ['item_id'], unique=False)
    op.create_index('ix_matrix_attempts_lease_until', 'matrix_attempts', ['lease_until'], unique=False)
    op.create_table('matrix_audits',
        sa.Column('actor_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('action', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('subject_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('payload', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
    )
    op.create_index('ix_matrix_audits_company_id', 'matrix_audits', ['company_id'], unique=False)
    op.create_table('matrix_collections',
        sa.Column('item_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('shop_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('part_count', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('header', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('quality', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('committed_at', sa.DateTime(), nullable=True, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('item_id', 'content_hash', name='uq_matrix_collection'),
    )
    op.create_index('ix_matrix_collections_company_id', 'matrix_collections', ['company_id'], unique=False)
    op.create_table('matrix_commands',
        sa.Column('agent_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('payload', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True, primary_key=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
    )
    op.create_index('ix_matrix_commands_agent_id', 'matrix_commands', ['agent_id'], unique=False)
    op.create_index('ix_matrix_commands_company_id', 'matrix_commands', ['company_id'], unique=False)
    op.create_table('matrix_companies',
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('listing_enabled', sa.Boolean(), nullable=False, primary_key=False),
    )
    op.create_table('matrix_devices',
        sa.Column('agent_id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('install_uuid', sa.String(length=36), nullable=False, primary_key=False),
        sa.Column('version', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('capabilities', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('hub_identity', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('hub_connected', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('paused', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('local_paused', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('sync_at', sa.DateTime(), nullable=True, primary_key=False),
        sa.Column('update_state', sa.JSON(), nullable=False, primary_key=False),
        sa.UniqueConstraint('install_uuid', name=None),
    )
    op.create_table('matrix_environments',
        sa.Column('hub_identity', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('container_code', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('group_name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('serial', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('account_names', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('observed_site', sa.String(length=8), nullable=True, primary_key=False),
        sa.Column('override_site', sa.String(length=8), nullable=True, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('shop_id', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('observed_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('company_id', 'hub_identity', 'container_code', name='uq_matrix_env_identity'),
    )
    op.create_index('ix_matrix_environments_company_id', 'matrix_environments', ['company_id'], unique=False)
    op.create_index('ix_matrix_environments_shop_id', 'matrix_environments', ['shop_id'], unique=False)
    op.create_table('matrix_events',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('run_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('attempt_id', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('source_id', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('seq', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('kind', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('payload', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.UniqueConstraint('run_id', 'seq', name='uq_matrix_event_seq'),
        sa.UniqueConstraint('attempt_id', 'source_id', name='uq_matrix_event_source'),
    )
    op.create_index('ix_matrix_events_run_id', 'matrix_events', ['run_id'], unique=False)
    op.create_table('matrix_fires',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('plan_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('fire_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('run_id', sa.Integer(), nullable=True, primary_key=False),
        sa.UniqueConstraint('plan_id', 'revision', 'fire_at', name='uq_matrix_fire'),
    )
    op.create_table('matrix_items',
        sa.Column('run_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('environment_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('agent_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('stage', sa.String(length=80), nullable=False, primary_key=False),
        sa.Column('attempt_id', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('shop_id', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('supply_job_id', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('upload_task_id', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('submission', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('collection_status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('error', sa.String(length=500), nullable=True, primary_key=False),
        sa.Column('result', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('run_id', 'environment_id', name='uq_matrix_run_env'),
    )
    op.create_index('ix_matrix_item_queue', 'matrix_items', ['agent_id', 'status', 'id'], unique=False)
    op.create_index('ix_matrix_items_company_id', 'matrix_items', ['company_id'], unique=False)
    op.create_index('ix_matrix_items_environment_id', 'matrix_items', ['environment_id'], unique=False)
    op.create_index('ix_matrix_items_run_id', 'matrix_items', ['run_id'], unique=False)
    op.create_table('matrix_parts',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('kind', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('parent_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('number', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('digest', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('payload', sa.JSON(), nullable=False, primary_key=False),
        sa.UniqueConstraint('kind', 'parent_id', 'number', name='uq_matrix_part'),
    )
    op.create_table('matrix_plan_versions',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('plan_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('payload', sa.JSON(), nullable=False, primary_key=False),
        sa.UniqueConstraint('plan_id', 'revision', name='uq_matrix_plan_revision'),
    )
    op.create_index('ix_matrix_plan_versions_plan_id', 'matrix_plan_versions', ['plan_id'], unique=False)
    op.create_table('matrix_plans',
        sa.Column('owner_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('agent_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('name', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('config', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('deleted', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
    )
    op.create_index('ix_matrix_plans_agent_id', 'matrix_plans', ['agent_id'], unique=False)
    op.create_index('ix_matrix_plans_company_id', 'matrix_plans', ['company_id'], unique=False)
    op.create_index('ix_matrix_plans_owner_id', 'matrix_plans', ['owner_id'], unique=False)
    op.create_table('matrix_previews',
        sa.Column('token_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('owner_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('plan_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('payload', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('token_hash', name=None),
    )
    op.create_index('ix_matrix_previews_company_id', 'matrix_previews', ['company_id'], unique=False)
    op.create_table('matrix_releases',
        sa.Column('kind', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('version', sa.String(length=40), nullable=False, primary_key=False),
        sa.Column('platform', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('arch', sa.String(length=16), nullable=False, primary_key=False),
        sa.Column('manifest', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('company_id', 'kind', 'version', 'platform', 'arch', name='uq_matrix_release'),
    )
    op.create_index('ix_matrix_releases_company_id', 'matrix_releases', ['company_id'], unique=False)
    op.create_table('matrix_runs',
        sa.Column('owner_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('agent_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('plan_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('plan_revision', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False, primary_key=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('frozen', sa.JSON(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=32), nullable=False, primary_key=False),
        sa.Column('stop_requested', sa.Boolean(), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('company_id', 'owner_id', 'idempotency_key', name='uq_matrix_run_key'),
    )
    op.create_index('ix_matrix_runs_agent_id', 'matrix_runs', ['agent_id'], unique=False)
    op.create_index('ix_matrix_runs_company_id', 'matrix_runs', ['company_id'], unique=False)
    op.create_index('ix_matrix_runs_owner_id', 'matrix_runs', ['owner_id'], unique=False)
    op.create_index('ix_matrix_runs_plan_id', 'matrix_runs', ['plan_id'], unique=False)
    op.create_index('ix_matrix_runs_status', 'matrix_runs', ['status'], unique=False)
    op.create_table('matrix_shops',
        sa.Column('site', sa.String(length=8), nullable=False, primary_key=False),
        sa.Column('external_id', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('name', sa.String(length=255), nullable=False, primary_key=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=True, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('company_id', 'site', 'external_id', name='uq_matrix_shop'),
    )
    op.create_index('ix_matrix_shops_company_id', 'matrix_shops', ['company_id'], unique=False)
    op.create_table('matrix_syncs',
        sa.Column('agent_id', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('snapshot_key', sa.String(length=64), nullable=False, primary_key=False),
        sa.Column('hub_identity', sa.String(length=120), nullable=False, primary_key=False),
        sa.Column('version', sa.BigInteger(), nullable=False, primary_key=False),
        sa.Column('expected_count', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('part_count', sa.Integer(), nullable=False, primary_key=False),
        sa.Column('status', sa.String(length=24), nullable=False, primary_key=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, primary_key=False),
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False, primary_key=False),
        sa.UniqueConstraint('agent_id', 'snapshot_key', name='uq_matrix_sync'),
    )
    op.create_index('ix_matrix_syncs_agent_id', 'matrix_syncs', ['agent_id'], unique=False)
    op.create_index('ix_matrix_syncs_company_id', 'matrix_syncs', ['company_id'], unique=False)
    op.add_column("hub_runtime_locks", sa.Column("matrix_item_id", sa.Integer(), nullable=True))
    op.add_column("hub_runtime_locks", sa.Column("fencing", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("hub_upload_tasks", sa.Column("source_kind", sa.String(24), nullable=False, server_default="draft"))
    op.add_column("hub_upload_tasks", sa.Column("matrix_item_id", sa.Integer(), nullable=True))
    op.add_column("hub_upload_tasks", sa.Column("supply_job_id", sa.Integer(), nullable=True))
    op.create_index("uq_hub_upload_matrix_item", "hub_upload_tasks", ["matrix_item_id"], unique=True)


def downgrade():
    op.drop_index("uq_hub_upload_matrix_item", table_name="hub_upload_tasks")
    for name in ("supply_job_id", "matrix_item_id", "source_kind"):
        op.drop_column("hub_upload_tasks", name)
    op.drop_column("hub_runtime_locks", "fencing")
    op.drop_column("hub_runtime_locks", "matrix_item_id")
    op.drop_table('matrix_syncs')
    op.drop_table('matrix_shops')
    op.drop_table('matrix_runs')
    op.drop_table('matrix_releases')
    op.drop_table('matrix_previews')
    op.drop_table('matrix_plans')
    op.drop_table('matrix_plan_versions')
    op.drop_table('matrix_parts')
    op.drop_table('matrix_items')
    op.drop_table('matrix_fires')
    op.drop_table('matrix_events')
    op.drop_table('matrix_environments')
    op.drop_table('matrix_devices')
    op.drop_table('matrix_companies')
    op.drop_table('matrix_commands')
    op.drop_table('matrix_collections')
    op.drop_table('matrix_audits')
    op.drop_table('matrix_attempts')
    op.drop_table('matrix_allocations')
    op.drop_table('matrix_access')
