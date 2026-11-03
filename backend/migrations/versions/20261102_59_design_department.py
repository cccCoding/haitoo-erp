"""美工分组、公司级模板公开、结果审核与永久采用/下载统计。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '20261102_59'
down_revision = '20261101_58'
branch_labels = None
depends_on = None

OLD_ROLES = ('SUPER_ADMIN', 'COMPANY_ADMIN', 'MEMBER', 'TEAM_LEADER', 'SUPPLY_USER')


def upgrade():
    if op.get_bind().dialect.name in ('mysql', 'mariadb'):
        op.alter_column('users', 'role', existing_type=mysql.ENUM(*OLD_ROLES),
                        type_=mysql.ENUM(*OLD_ROLES, 'DESIGNER', 'DESIGN_LEADER'), existing_nullable=False)
    op.add_column('users', sa.Column('design_group_id', sa.Integer(), nullable=True))
    op.create_index('ix_users_design_group_id', 'users', ['design_group_id'])
    op.create_table('design_groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('leader_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id', 'name', name='uq_design_groups_company_name'),
        sa.UniqueConstraint('leader_user_id', name='uq_design_groups_leader'))
    op.create_index('ix_design_groups_company_id', 'design_groups', ['company_id'])
    op.create_table('design_template_visibility',
        sa.Column('company_id', sa.Integer(), primary_key=True),
        sa.Column('template_id', sa.Integer(), primary_key=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.create_table('task_result_reviews',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('result_hash', sa.String(64), nullable=False),
        sa.Column('result_url', sa.String(500), nullable=False),
        sa.Column('rejected', sa.Boolean(), nullable=False),
        sa.Column('marked_by', sa.Integer(), nullable=False),
        sa.Column('marked_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('task_id', 'result_hash', name='uq_task_result_review'))
    for field in ('company_id', 'task_id'):
        op.create_index(f'ix_task_result_reviews_{field}', 'task_result_reviews', [field])
    op.create_table('creative_image_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('user_name', sa.String(80), nullable=False),
        sa.Column('kind', sa.String(12), nullable=False),
        sa.Column('sku', sa.String(24), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('request_key', sa.String(128), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id', 'user_id', 'kind', 'sku', name='uq_creative_image_event'))
    op.create_index('ix_creative_event_company_time', 'creative_image_events', ['company_id', 'occurred_at'])
    op.create_index('ix_creative_event_member_time', 'creative_image_events', ['company_id', 'user_id', 'occurred_at'])
    op.execute("""INSERT INTO creative_image_events
        (company_id, user_id, user_name, kind, sku, task_id, asset_id, occurred_at)
        SELECT a.company_id, t.created_by, u.name, 'adopt', a.sku, t.id, a.id, a.created_at
        FROM material_assets a JOIN pod_tasks t ON t.id = a.source_task_id AND t.company_id = a.company_id
        JOIN users u ON u.id = t.created_by AND u.company_id = a.company_id
        WHERE t.task_type = 'sku_image' AND a.sku IS NOT NULL
        AND (a.source_type = 'ai_created' OR a.source_type IS NULL)""")


def downgrade():
    op.drop_table('creative_image_events')
    op.drop_table('task_result_reviews')
    op.drop_table('design_template_visibility')
    op.drop_table('design_groups')
    op.drop_index('ix_users_design_group_id', table_name='users')
    op.drop_column('users', 'design_group_id')
    op.execute("UPDATE users SET role = 'MEMBER', is_active = 0, token_version = token_version + 1 "
               "WHERE role IN ('DESIGNER', 'DESIGN_LEADER')")
    if op.get_bind().dialect.name in ('mysql', 'mariadb'):
        op.alter_column('users', 'role', existing_type=mysql.ENUM(*OLD_ROLES, 'DESIGNER', 'DESIGN_LEADER'),
                        type_=mysql.ENUM(*OLD_ROLES), existing_nullable=False)
