"""在最小旧表结构上验证货盘字段扩容；可选专用 MySQL 临时库。"""
import os
import unittest

from alembic import command
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, select
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.schema_version import alembic_config


class SupplyTitleMigrationTests(unittest.TestCase):
    def setUp(self):
        database = os.getenv('SUPPLY_TITLE_MYSQL_DATABASE')
        url = 'sqlite://'
        if database:
            if not database.startswith('haitoo_supply_validation_'):
                raise RuntimeError('只允许专用 MySQL 测试库')
            url = make_url(get_settings().database_url).set(database=database)
            if url.get_backend_name() not in {'mysql', 'mariadb'}:
                raise RuntimeError('指定临时库时必须使用 MySQL 连接')
        self.engine = create_engine(url)
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        self.tables = []
        for name, column in (('product_templates', 'supply_fallback_title'),
                             ('title_template_profiles', 'fallback_title')):
            self.tables.append(Table(name, metadata, Column('id', Integer, primary_key=True),
                                     Column(column, String(220), nullable=True)))
        metadata.create_all(self.engine)
        self.addCleanup(metadata.drop_all, self.engine)
        with self.engine.begin() as connection:
            command.stamp(alembic_config(connection), '20261104_64')
        self.addCleanup(self.clean_version)

    def clean_version(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql('DROP TABLE IF EXISTS alembic_version')

    def assert_lengths(self, connection, expected):
        for table in self.tables:
            column = inspect(connection).get_columns(table.name)[1]
            self.assertEqual(column['type'].length, expected)
            self.assertTrue(column['nullable'])

    def test_expand_preserves_values_and_downgrade_refuses_long_titles(self):
        with self.engine.begin() as connection:
            config = alembic_config(connection)
            for table in self.tables:
                connection.execute(table.insert().values(id=1, **{table.c[1].name: 'Gaun ' + 'a' * 215}))
            command.upgrade(config, '20261104_65')
            self.assert_lengths(connection, 230)
            for table in self.tables:
                self.assertEqual(len(connection.scalar(select(table.c[1]))), 220)
            # 只让第二列超长，验证降级在任何缩列前检查两张表。
            table = self.tables[1]
            connection.execute(table.update().values({table.c[1]: 'Gaun ' + 'a' * 225}))
            with self.assertRaisesRegex(RuntimeError, '拒绝降级'):
                command.downgrade(config, '20261104_64')
            self.assert_lengths(connection, 230)
            self.assertEqual(len(connection.scalar(select(table.c[1]))), 230)
            for table in self.tables:
                # MySQL 必须按字符数而不是 UTF-8 字节数判断。
                connection.execute(table.update().values({table.c[1]: 'é' * 220}))
            command.downgrade(config, '20261104_64')
            self.assert_lengths(connection, 220)
            command.upgrade(config, '20261104_65')
            self.assert_lengths(connection, 230)
            for table in self.tables:
                self.assertEqual(connection.scalar(select(table.c[1])), 'é' * 220)
