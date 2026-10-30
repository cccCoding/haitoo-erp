"""分类归类、别名与合并的 HTTP 行为、事务及迁移验证。"""
import asyncio
import copy
import io
import unittest
from datetime import datetime
from unittest.mock import patch

from alembic import command
from sqlalchemy import MetaData, Table, create_engine, func, select
from sqlalchemy.exc import IntegrityError

from app import main
from app.schema_version import alembic_config
from app.title_dictionary import name_key
from app.title_models import (TitleCategoryMerge, TitleCategoryName, TitleDictionaryEntry,
    TitleEvidence, TitleImportWord, TitleKeyword, TitleMarket, TitleRecord, TitleTask, TitleTemplateProfile)
from app.title_worker import claim_task, run_task
from tests.test_supply_catalog import SupplyFixture


HEADER = '马来语词语,中文释义,产品分类,标签\n'


class TitleCategoryTests(SupplyFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.sessions.configure(autoflush=False)
        self.app.include_router(main.app.router)

    def category(self, name, *, uid=1, **extra):
        result = self.request('POST', '/title-dictionaries/category', uid=uid, json={'name': name, **extra})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def categories(self, **params):
        return self.request('GET', '/title-dictionaries', params={'kind': 'category', **params}).json()['items']

    def upload(self, rows, *, uid=1):
        result = self.request('POST', '/title-imports', uid=uid,
            files={'file': ('words.csv', (HEADER + rows).encode())}, data={'kind': 'keywords'})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def configure(self, task, mapping, *, save_alias=True):
        resolution = task.get('category_resolution') or self.detail(task)['category_resolution']
        choices = []
        for item in resolution['items']:
            target = mapping.get(item['source'], item['target_id'] or item['new_name'])
            choice = {'source_key': item['source_key'], 'save_alias': save_alias}
            choice['target_id' if isinstance(target, int) else 'new_name'] = target
            choices.append(choice)
        result = self.request('PUT', f"/title-imports/{task['id']}/categories",
            json={'token': resolution['token'], 'choices': choices})
        self.assertEqual(result.status_code, 200, result.text)
        task['category_resolution'] = result.json()
        return result.json()

    def detail(self, task, **params):
        result = self.request('GET', f"/title-tasks/{task['id']}", params=params)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def extract(self, task):
        result = self.request('POST', f"/title-tasks/{task['id']}/start", json={})
        self.assertEqual(result.status_code, 200, result.text)
        claimed = claim_task(self.sessions)
        self.assertIsNotNone(claimed)
        asyncio.run(run_task(*claimed, session_factory=self.sessions))
        return self.detail(task)

    def confirm(self, task, selections=None):
        detail = self.detail(task)
        selections = selections if selections is not None else [word['index'] for word in detail['result']['words']]
        result = self.request('POST', f"/title-imports/{task['id']}/confirm", json={'selections': selections})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def merge(self, sources, target):
        body = {'source_ids': sources, 'target_id': target}
        result = self.request('POST', '/title-category-merges/preview', json=body)
        self.assertEqual(result.status_code, 200, result.text)
        result = self.request('POST', '/title-category-merges', json={**body, 'token': result.json()['token']})
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_unknown_requires_explicit_choice_and_cancel_leaves_no_categories(self):
        task = self.upload('kapas,棉,新上衣,材质\n')
        self.assertFalse(task['category_resolution']['ready'])
        start = self.request('POST', f"/title-tasks/{task['id']}/start", json={})
        self.assertEqual(start.status_code, 409, start.text)
        self.configure(task, {'新上衣': '上衣'})
        self.assertEqual(self.categories(), [])
        self.request('POST', f"/title-tasks/{task['id']}/cancel", json={})
        self.assertEqual(self.categories(), [])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count(TitleCategoryName.id))), 0)

    def test_standard_and_alias_normalization_and_localized_name_is_not_an_alias(self):
        category = self.category('Tops', aliases=['上装'], localized_name='Baju')
        task = self.upload('kapas,棉,ＴＯＰＳ,材质\nlengan panjang,长袖,tops,结构设计\nbunga,花,上装,图案\n')
        items = task['category_resolution']['items']
        self.assertEqual(len(items), 2)
        self.assertEqual([(item['match'], item['row_count']) for item in items], [('standard', 2), ('alias', 1)])
        detail = self.extract(task)
        self.assertTrue(all(word['categories'] == ['Tops'] for word in detail['result']['words']))
        self.assertEqual(self.detail(task, category='Tops')['result']['filtered_total'], 3)
        self.confirm(task)
        self.assertEqual(len(self.categories()), 1)
        unknown = self.upload('kapas,棉,Baju,材质\n')
        self.assertEqual(unknown['category_resolution']['items'][0]['match'], 'unknown')
        self.assertEqual(category['aliases'], ['上装'])

    def test_mapping_and_multivalue_deduplication_only_persists_selected_aliases(self):
        target = self.category('连衣裙')
        task = self.upload('gaun,裙,"连身裙,连衣裙",品类\nkapas,棉,女裙装,材质\n')
        self.configure(task, {'连身裙': target['id'], '女裙装': target['id']})
        self.assertEqual(self.categories()[0]['aliases'], [])
        detail = self.extract(task)
        self.confirm(task, [detail['result']['words'][0]['index']])
        self.assertEqual(self.categories()[0]['aliases'], ['连身裙'])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(TitleKeyword)).categories, ['连衣裙'])
        self.confirm(task)
        self.assertEqual(self.categories()[0]['aliases'], ['女裙装', '连身裙'])
        future = self.upload('lengan panjang,长袖,连身裙,结构设计\n')
        self.assertEqual(future['category_resolution']['items'][0]['match'], 'alias')

    def test_task_only_mapping_does_not_add_an_alias(self):
        target = self.category('上衣')
        task = self.upload('kapas,棉,女装上装,材质\n')
        self.configure(task, {'女装上装': target['id']}, save_alias=False)
        self.extract(task); self.confirm(task)
        self.assertEqual(self.categories()[0]['aliases'], [])
        future = self.upload('bunga,花,女装上装,图案\n')
        self.assertFalse(future['category_resolution']['ready'])

    def test_partial_confirmation_creates_only_selected_categories_and_is_idempotent(self):
        task = self.upload('kapas,棉,上装甲,材质\nbunga,花,上装乙,图案\nlengan panjang,长袖,裙装,结构设计\n')
        self.configure(task, {'上装甲': '上衣', '上装乙': '上衣', '裙装': '连衣裙'})
        detail = self.extract(task)
        self.assertEqual(self.categories(), [])
        first = [detail['result']['words'][0]['index']]
        self.confirm(task, first)
        self.assertEqual([(row['name'], row['aliases']) for row in self.categories()], [('上衣', ['上装甲'])])
        self.confirm(task, [detail['result']['words'][1]['index']])
        self.assertEqual(self.categories()[0]['aliases'], ['上装乙', '上装甲'])
        last = self.confirm(task)
        revision = self.request('GET', '/title-market').json()['revision']
        self.assertEqual(self.confirm(task), last)
        self.assertEqual(self.request('GET', '/title-market').json()['revision'], revision)
        self.assertEqual({row['name'] for row in self.categories()}, {'上衣', '连衣裙'})

    def test_disabled_target_and_conflicting_new_name_rollback_entire_confirmation(self):
        target = self.category('连衣裙')
        task = self.upload('kapas,棉,上装,材质\nbunga,花,裙装,图案\n')
        self.configure(task, {'上装': '上衣', '裙装': target['id']})
        detail = self.extract(task)
        self.request('PATCH', f"/title-dictionaries/{target['id']}", json={'enabled': False})
        result = self.request('POST', f"/title-imports/{task['id']}/confirm",
            json={'selections': [word['index'] for word in detail['result']['words']]})
        self.assertEqual(result.status_code, 400, result.text)
        self.assertEqual([row['name'] for row in self.categories()], ['连衣裙'])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count(TitleKeyword.id))), 0)
            self.assertEqual(db.scalar(select(TitleTask)).result.get('selections', []), [])
        self.request('PATCH', f"/title-dictionaries/{target['id']}", json={'enabled': True})
        self.category('上衣')
        result = self.request('POST', f"/title-imports/{task['id']}/confirm", json={'selections': [detail['result']['words'][0]['index']]})
        self.assertEqual(result.status_code, 409, result.text)
        self.assertIn('已存在', result.json()['detail'])

    def test_late_tag_failure_rolls_back_new_categories_aliases_and_preceding_words(self):
        task = self.upload('kapas,棉,上装,材质\nbunga,花,裙装,图案\n')
        self.configure(task, {'上装': '上衣', '裙装': '连衣裙'})
        detail = self.extract(task)
        tag = next(row for row in self.request('GET', '/title-dictionaries', params={'kind': 'tag'}).json()['items'] if row['name'] == '图案')
        self.request('PATCH', f"/title-dictionaries/{tag['id']}", json={'enabled': False})
        result = self.request('POST', f"/title-imports/{task['id']}/confirm",
            json={'selections': [word['index'] for word in detail['result']['words']]})
        self.assertEqual(result.status_code, 400, result.text)
        self.assertEqual(self.categories(), [])
        with self.sessions() as db:
            for model in (TitleCategoryName, TitleKeyword, TitleEvidence):
                self.assertEqual(db.scalar(select(func.count(model.id))), 0)

    def test_concurrent_name_constraint_returns_conflict_and_rolls_back_flushed_category(self):
        self.category('已有分类')
        before = self.request('GET', '/title-market').json()['revision']
        with patch('app.title_api.sync_names', side_effect=IntegrityError('unique category name', {}, Exception('duplicate'))):
            result = self.request('POST', '/title-dictionaries/category', json={'name': '并发分类'})
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual([row['name'] for row in self.categories()], ['已有分类'])
        self.assertEqual(self.request('GET', '/title-market').json()['revision'], before)

    def test_alias_namespace_conflicts_permissions_and_stale_resolution(self):
        first = self.category('上衣', aliases=['Tops'])
        second = self.category('裙装')
        for body in ({'name': 'ＴＯＰＳ'}, {'name': '新类', 'aliases': ['上衣']}):
            result = self.request('POST', '/title-dictionaries/category', json=body)
            self.assertEqual(result.status_code, 409, result.text)
        result = self.request('PATCH', f"/title-dictionaries/{second['id']}", json={'aliases': ['tops']})
        self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(next(row for row in self.categories() if row['id'] == second['id'])['aliases'], [])
        task = self.upload('kapas,棉,新上装,材质\n')
        old = copy.deepcopy(task['category_resolution'])
        self.configure(task, {'新上装': first['id']})
        stale = self.request('PUT', f"/title-imports/{task['id']}/categories", json={'token': old['token'], 'choices': []})
        self.assertEqual(stale.status_code, 409)
        other = self.category('外部分类', uid=5)
        for uid, status in ((2, 403), (5, 404)):
            result = self.request('PUT', f"/title-imports/{task['id']}/categories", uid=uid,
                json={'token': task['category_resolution']['token'], 'choices': []})
            self.assertEqual(result.status_code, status)
        choice = {'source_key': old['items'][0]['source_key'], 'target_id': other['id']}
        result = self.request('PUT', f"/title-imports/{task['id']}/categories",
            json={'token': task['category_resolution']['token'], 'choices': [choice]})
        self.assertEqual(result.status_code, 404, result.text)

    def test_unused_category_rename_keeps_names_synchronized_without_autoflush(self):
        row = self.category('旧上衣', aliases=['Tops'])
        result = self.request('PATCH', f"/title-dictionaries/{row['id']}", json={'name': '新上衣', 'aliases': ['Tops']})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['name'], '新上衣')
        with self.sessions() as db:
            names = db.scalars(select(TitleCategoryName)).all()
            self.assertEqual({name.name for name in names}, {'新上衣', 'Tops'})

    def test_source_fingerprint_does_not_change_when_categories_are_merged(self):
        source, target = self.category('连身裙'), self.category('连衣裙')
        task = self.upload('gaun,裙,连身裙,品类\n')
        self.extract(task); self.confirm(task)
        with self.sessions() as db:
            fingerprint = db.scalar(select(TitleEvidence)).observation_hash
        self.merge([source['id']], target['id'])
        task = self.upload('gaun,裙,连身裙,品类\n\n')
        self.extract(task); self.confirm(task)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count(TitleEvidence.id))), 1)
            self.assertEqual(db.scalar(select(TitleEvidence)).observation_hash, fingerprint)

    def test_planned_standard_and_alias_conflict_and_disabled_alias_cannot_bypass(self):
        task = self.upload('kapas,棉,甲,材质\nbunga,花,乙,图案\n')
        body = {'token': task['category_resolution']['token'], 'choices': [
            {'source_key': name_key('甲'), 'new_name': '乙'}, {'source_key': name_key('乙'), 'new_name': '丙'}]}
        self.assertEqual(self.request('PUT', f"/title-imports/{task['id']}/categories", json=body).status_code, 409)
        target = self.category('上衣', aliases=['上装'], enabled=False)
        result = self.request('POST', '/title-imports', files={'file': ('words.csv', (HEADER+'kapas,棉,上装,材质\n').encode())}, data={'kind': 'keywords'})
        self.assertEqual(result.status_code, 400, result.text)
        self.assertEqual(len(self.categories()), 1)

    def test_merge_migrates_current_references_preserves_history_and_follows_pending_targets(self):
        source = self.category('连身裙', aliases=['裙装'], localized_name='Gaun', description='源配置')
        target = self.category('连衣裙', localized_name='Dress', description='目标配置')
        task = self.upload('gaun,裙,"裙装,连衣裙",品类\nkapas,棉,连身裙,材质\n')
        detail = self.extract(task)
        first_id = detail['result']['words'][0]['index']
        self.confirm(task, [first_id])
        self.request('PUT', '/title-profiles/1', json={'category': '连身裙', 'gender': '女', 'age_group': '成人'})
        with self.sessions() as db:
            record = TitleRecord(market_id=1, user_id=1, template_id=1, request_key='history', category='连身裙',
                image_url='https://img.example/1.png', snapshot={'category': '连身裙'}, state='pending')
            db.add(record); db.commit()
            snapshot = copy.deepcopy(db.get(TitleTask, task['id']).snapshot['rows'])
            evidence = [(row.id, row.observation_hash, row.original_phrase) for row in db.scalars(select(TitleEvidence))]
        summary = self.merge([source['id']], target['id'])
        self.assertEqual(summary['counts'], {'keywords': 1, 'templates': 1, 'imports': 1})
        live = self.categories()
        self.assertEqual([(row['name'], row['aliases']) for row in live], [('连衣裙', ['裙装', '连身裙'])])
        self.assertEqual((live[0]['localized_name'], live[0]['description']), ('Dress', '目标配置'))
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(TitleKeyword)).categories, ['连衣裙'])
            self.assertEqual(db.scalar(select(TitleTemplateProfile)).category, '连衣裙')
            self.assertEqual(db.scalar(select(TitleRecord)).snapshot, {'category': '连身裙'})
            self.assertEqual(db.get(TitleTask, task['id']).snapshot['rows'], snapshot)
            self.assertEqual([(row.id, row.observation_hash, row.original_phrase) for row in db.scalars(select(TitleEvidence))], evidence)
            self.assertEqual(db.scalar(select(TitleCategoryMerge)).user_id, 1)
        # 已入库结果仍显示当时的归类，未入库结果跟随目标，支持分别筛选。
        detail = self.detail(task)
        self.assertEqual(detail['result']['words'][0]['categories'], ['连身裙', '连衣裙'])
        self.assertEqual(detail['result']['words'][1]['categories'], ['连衣裙'])
        self.assertEqual(self.detail(task, category='连衣裙')['result']['filtered_total'], 2)
        self.confirm(task)
        words = self.request('GET', '/title-keywords').json()['items']
        self.assertTrue(all(word['categories'] == ['连衣裙'] for word in words))
        archive = next(row for row in self.categories(include_merged=True) if row['id'] == source['id'])
        self.assertEqual(archive['merged_into_id'], target['id'])
        self.assertEqual(self.request('DELETE', f"/title-dictionaries/{source['id']}").status_code, 409)

    def test_merge_preview_staleness_replay_flattening_and_scope(self):
        first, second, target = self.category('甲'), self.category('乙'), self.category('丙')
        body = {'source_ids': [first['id']], 'target_id': second['id']}
        preview = self.request('POST', '/title-category-merges/preview', json=body).json()
        self.request('PATCH', f"/title-dictionaries/{first['id']}", json={'description': '变化'})
        stale = self.request('POST', '/title-category-merges', json={**body, 'token': preview['token']})
        self.assertEqual(stale.status_code, 409, stale.text)
        summary = self.merge([first['id']], second['id'])
        repeat = self.request('POST', '/title-category-merges', json={**body, 'token': summary['token']})
        self.assertEqual(repeat.status_code, 200, repeat.text)
        self.assertEqual(repeat.json(), summary)
        self.merge([second['id']], target['id'])
        with self.sessions() as db:
            self.assertEqual(db.get(TitleDictionaryEntry, first['id']).merged_into_id, target['id'])
            self.assertEqual(db.scalar(select(func.count(TitleCategoryMerge.id))), 2)
        self.assertEqual(set(self.categories()[0]['aliases']), {'甲', '乙'})
        locked = self.request('PATCH', f"/title-dictionaries/{target['id']}", json={'name': '丁'})
        self.assertEqual(locked.status_code, 409)
        history = self.request('GET', '/title-category-merges').json()
        self.assertEqual(history['total'], 2)
        self.assertEqual(history['items'][0]['operator'], '用户1')
        self.assertEqual(self.request('GET', '/title-category-merges', uid=5).json()['total'], 0)
        # 合并旧名称受到保护，避免之后重新创建同名分类。
        self.assertEqual(self.request('PATCH', f"/title-dictionaries/{target['id']}", json={'aliases': []}).status_code, 409)
        foreign = self.category('其他公司', uid=5)
        scoped = self.request('POST', '/title-category-merges/preview', json={'source_ids': [foreign['id']], 'target_id': target['id']})
        self.assertEqual(scoped.status_code, 404)
        self.assertEqual(self.request('POST', '/title-category-merges/preview', uid=2, json=body).status_code, 403)
        self.assertEqual(self.request('POST', '/title-category-merges/preview', json={'source_ids': [target['id']], 'target_id': target['id']}).status_code, 400)

    def test_legacy_review_requires_mapping_without_reextraction(self):
        task = self.upload('kapas,棉,旧上装,材质\n')
        with self.sessions() as db:
            row = db.get(TitleTask, task['id'])
            row.state, row.result = 'review', {'word_total': 1}
            db.add(TitleImportWord(task_id=row.id, row_number=2, identity_hash='legacy', word={
                'phrase': 'kapas', 'translation': '棉', 'tag': '材质', 'categories': ['旧上装'],
                'synonyms': [], 'position': 0, 'row': 2, 'is_borrowed': False}))
            db.commit()
        detail = self.detail(task)
        result = self.request('POST', f"/title-imports/{task['id']}/confirm", json={'selections': [detail['result']['words'][0]['index']]})
        self.assertEqual(result.status_code, 409)
        self.configure(task, {'旧上装': '上衣'})
        self.confirm(task)
        self.assertEqual(self.categories()[0]['name'], '上衣')


class CategoryMigrationTests(unittest.TestCase):
    def test_new_migration_generates_mysql_sql_without_reading_live_data(self):
        from unittest.mock import patch
        output = io.StringIO()
        config = alembic_config()
        config.output_buffer = output
        with patch('app.config.get_settings') as settings:
            settings.return_value.database_url = 'mysql+pymysql://unused:unused@localhost/unused'
            command.upgrade(config, '20261030_55:20261031_56', sql=True)
        sql = output.getvalue()
        self.assertIn('uq_title_category_name', sql)
        self.assertIn('title_category_merges', sql)
        self.assertIn('INSERT INTO title_category_names', sql)
        self.assertIn('SELECT title_dictionary_entries.market_id', sql)

    def test_migration_only_registers_standards_and_enforces_shared_namespace(self):
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, '20261030_55')
            dictionary = Table('title_dictionary_entries', MetaData(), autoload_with=connection)
            for identity, name in ((1, '上衣'), (2, 'Tops')):
                connection.execute(dictionary.insert(), {'id': identity, 'market_id': 7, 'kind': 'category',
                    'name': name, 'name_key': name_key(name), 'description': '', 'built_in': False,
                    'enabled': True, 'updated_at': datetime.utcnow()})
            command.upgrade(config, 'head')
            names = Table('title_category_names', MetaData(), autoload_with=connection)
            rows = connection.execute(select(names)).mappings().all()
            self.assertEqual({(row['category_id'], row['name']) for row in rows}, {(1, '上衣'), (2, 'Tops')})
            with connection.begin_nested():
                with self.assertRaises(IntegrityError):
                    connection.execute(names.insert(), {'market_id': 7, 'category_id': 1, 'name': 'ＴＯＰＳ', 'name_key': name_key('ＴＯＰＳ')})
            command.downgrade(config, '20261030_55')
            self.assertEqual(connection.scalar(select(func.count()).select_from(dictionary)), 2)
            command.upgrade(config, 'head')
            self.assertEqual(connection.scalar(select(func.count()).select_from(names)), 2)
        engine.dispose()
