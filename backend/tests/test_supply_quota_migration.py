"""最小旧表验证 SKU 快照回填、删除素材历史及可重跑迁移。"""
import os
import unittest

from alembic import command
from sqlalchemy import Boolean, Column, Integer, JSON, MetaData, String, Table, create_engine, func, inspect, select
from sqlalchemy.engine import make_url

from app.schema_version import alembic_config


class SupplyQuotaMigrationTests(unittest.TestCase):
    def setUp(self):
        url = make_url(os.getenv('SUPPLY_QUOTA_MIGRATION_DATABASE_URL', 'sqlite://'))
        if url.get_backend_name() != 'sqlite' and (url.get_backend_name() not in {'mysql', 'mariadb'} or
                not (url.database or '').startswith('haitoo_supply_validation_')):
            raise RuntimeError('SKU 回填测试只允许专用临时数据库')
        self.engine = create_engine(url)
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        self.jobs = Table('supply_jobs', metadata, Column('id', Integer, primary_key=True),
            Column('company_id', Integer), Column('snapshot', JSON), Column('checkpoint', JSON))
        self.materials = Table('supply_job_materials', metadata, Column('id', Integer, primary_key=True),
            Column('company_id', Integer), Column('job_id', Integer), Column('material_id', Integer),
            Column('version_hash', String(64)), Column('link_index', Integer), Column('successful', Boolean))
        metadata.create_all(self.engine)
        self.addCleanup(self.clean_tables, metadata)
        with self.engine.begin() as connection:
            command.stamp(alembic_config(connection), '20261105_68')

    def clean_tables(self, metadata):
        metadata.drop_all(self.engine)
        with self.engine.begin() as connection:
            connection.exec_driver_sql('DROP TABLE IF EXISTS alembic_version')

    def seed(self, connection, identity=1, sku='OLD-SKU'):
        connection.execute(self.jobs.insert().values(id=identity, company_id=1,
            snapshot={'candidates': [{'id': 8, 'version_hash': 'original', 'sku': sku}]},
            checkpoint={'links': [{'index': 0, 'materials': [
                {'id': 8, 'version_hash': 'original', 'sku': sku},
                {'id': 9, 'version_hash': 'replacement', 'sku': 'REPLACED-SKU'}]}]}))
        connection.execute(self.materials.insert(), [
            dict(company_id=1, job_id=identity, material_id=8, version_hash='original', link_index=-1, successful=False),
            dict(company_id=1, job_id=identity, material_id=8, version_hash='original', link_index=0, successful=True),
            dict(company_id=1, job_id=identity, material_id=8, version_hash='original', link_index=1, successful=True),
            dict(company_id=1, job_id=identity, material_id=9, version_hash='replacement', link_index=0, successful=True),
        ])

    def test_backfill_uses_final_version_and_candidate_fallback_without_live_materials(self):
        with self.engine.begin() as connection:
            self.seed(connection)
            command.upgrade(alembic_config(connection), '20261105_69')
            table = Table('supply_job_materials', MetaData(), autoload_with=connection)
            self.assertEqual(connection.scalars(select(table.c.sku).order_by(table.c.id)).all(),
                             [None, 'OLD-SKU', 'OLD-SKU', 'REPLACED-SKU'])
            index = next(item for item in inspect(connection).get_indexes(table.name)
                         if item['name'] == 'ix_supply_job_materials_sku_usage')
            self.assertEqual(index['column_names'], ['company_id', 'sku', 'successful', 'job_id', 'link_index'])
            command.downgrade(alembic_config(connection), '20261105_68')
            self.assertNotIn('sku', {item['name'] for item in inspect(connection).get_columns(table.name)})
            self.assertEqual(connection.scalar(select(func.count()).select_from(self.materials)), 4)
            command.upgrade(alembic_config(connection), '20261105_69')
            self.assertEqual(connection.scalars(select(table.c.sku).order_by(table.c.id)).all(),
                             [None, 'OLD-SKU', 'OLD-SKU', 'REPLACED-SKU'])

    def test_missing_snapshot_is_rejected_and_migration_can_resume_after_repair(self):
        with self.engine.begin() as connection:
            self.seed(connection, sku=None)
            with self.assertRaisesRegex(RuntimeError, '缺少有效 SKU 快照'):
                command.upgrade(alembic_config(connection), '20261105_69')
            # 模拟 MySQL 自动提交过加列后，修复快照并重跑，不会重复加列。
            connection.execute(self.jobs.update().values(snapshot={'candidates': [
                {'id': 8, 'version_hash': 'original', 'sku': 'FIXED'}]}))
            command.upgrade(alembic_config(connection), '20261105_69')
            table = Table('supply_job_materials', MetaData(), autoload_with=connection)
            self.assertEqual(connection.scalars(select(table.c.sku).order_by(table.c.id)).all(),
                             [None, 'FIXED', 'FIXED', 'REPLACED-SKU'])

    def test_backfill_paginates_jobs_and_rejects_orphan_successful_records(self):
        with self.engine.begin() as connection:
            for identity in range(1, 102):
                self.seed(connection, identity=identity, sku=f'SKU{identity}')
            connection.execute(self.materials.insert().values(company_id=1, job_id=9999,
                material_id=9, version_hash='missing', link_index=0, successful=True))
            with self.assertRaisesRegex(RuntimeError, '缺少对应任务'):
                command.upgrade(alembic_config(connection), '20261105_69')
            connection.execute(self.materials.delete().where(self.materials.c.job_id == 9999))
            command.upgrade(alembic_config(connection), '20261105_69')
            table = Table('supply_job_materials', MetaData(), autoload_with=connection)
            self.assertEqual(connection.scalars(select(table.c.sku).where(table.c.job_id == 101)
                .order_by(table.c.id)).all(), [None, 'SKU101', 'SKU101', 'REPLACED-SKU'])


if __name__ == '__main__':
    unittest.main()
