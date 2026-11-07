"""工艺、品牌的人工来源、固定随机选择与历史任务兼容。"""
import copy
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from alembic import command
from fastapi import HTTPException
from sqlalchemy import MetaData, Table, create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.ai_providers import ProviderError
from app.database import Base
from app.schema_version import alembic_config
from app.title_models import TitleAttributeCache, TitleMarket, TitleRecord, TitleTask
from app.title_service import (choose_keywords, create_record, digest, generate_record,
                               identify_facts, match_keywords)
from tests.test_title_length import keyword


class ConfirmedChoicesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.market = TitleMarket(company_id=1, platform='TikTok', site='MY', language='ms')
        self.db.add(self.market)
        self.db.commit()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def snapshot(self, **extra):
        words = [keyword(1, 'sulaman', tag='工艺'), keyword(2, 'renda', tag='工艺'),
                 keyword(3, 'Acme', tag='品牌'), keyword(4, 'BrandB', tag='品牌')]
        return {'template_id': 1, 'category': '连衣裙', 'category_localized_name': 'Gaun',
                'platform': 'TikTok', 'site': 'MY', 'language': 'ms', 'gender': '女', 'age_group': '成人',
                'attributes': {}, 'keywords': words, 'locked_keyword_ids': [], 'forbidden_keyword_ids': [],
                'forbidden_phrases': [], 'confirmed_choices_version': 1,
                'craft_keyword_ids': [1, 2], 'craft_keywords': words[:2],
                'brand_keyword_ids': [3, 4], 'brand_keywords': words[2:], **extra}

    @staticmethod
    async def model(_key, _instructions, data, **_kwargs):
        if 'manual' in data:
            return {'attributes': [{'tag': tag, 'value': value, 'localized_value': 'translated',
                                   'evidence': 'manual', 'source': 'manual'} for tag, value in data['manual'].items()] +
                    [{'tag': '工艺', 'value': 'renda', 'localized_value': 'renda', 'evidence': 'image', 'source': 'image'},
                     {'tag': '品牌', 'value': 'BrandB', 'localized_value': 'BrandB', 'evidence': 'image', 'source': 'image'}]}
        phrases = data['required_phrases']
        return {'title': ' '.join(phrases) + ' Wanita Lengan Panjang Corak Bunga Potongan Longgar'}

    async def test_single_batch_supply_keep_one_choice_per_semantic_across_retries_and_restore(self):
        for mode in ('single', 'batch', 'supply'):
            with self.subTest(mode=mode):
                snapshot = self.snapshot()
                task_id = None
                if mode == 'batch':
                    task = TitleTask(market_id=self.market.id, user_id=1, kind='batch', state='running',
                                     request_key=digest(mode), request_hash=digest(mode), snapshot={'profile': snapshot})
                    self.db.add(task)
                    self.db.flush()
                    task_id = task.id
                with patch('app.title_service.secrets.choice', side_effect=lambda items: items[0]) as random:
                    record = create_record(self.db, self.market, 1, snapshot, 'https://img.example/test.png', mode,
                                           task_id=task_id, supply=mode == 'supply')
                    self.db.commit()
                    self.assertEqual(random.call_count, 2)
                self.assertEqual(record.snapshot['selected_craft_keyword']['id'], 1)
                self.assertEqual(record.snapshot['selected_brand_keyword']['id'], 3)
                if task_id:
                    self.assertNotIn('keywords', record.snapshot)
                    self.assertNotIn('craft_keywords', record.snapshot)
                self.db.expire_all()
                model = AsyncMock(side_effect=self.model)
                with patch('app.title_service.ask_json', new=model), patch('app.title_service.secrets.choice') as random:
                    result = await generate_record(self.db, record.id, 'test-key')
                    repeated = await generate_record(self.db, record.id, 'test-key')
                    random.assert_not_called()
                self.assertEqual(result['title'], repeated['title'])
                self.assertIn('sulaman', result['title'])
                self.assertIn('Acme', result['title'])
                self.assertNotIn('renda', result['title'])
                self.assertNotIn('BrandB', result['title'])
                for call in model.await_args_list:
                    if 'selected' in call.args[2]:
                        self.assertEqual({word['id'] for word in call.args[2]['selected']}, {1, 3})
                self.assertGreater(result['attempts'], 1)

    async def test_no_manual_choice_discards_image_and_forged_manual_facts_and_old_cache(self):
        snapshot = self.snapshot(craft_keyword_ids=[], craft_keywords=[], brand_keyword_ids=[], brand_keywords=[])
        manual = {'品类': '连衣裙', '性别': '女', '年龄': '成人'}
        key = digest(['facts-v4', 'https://img.example/test.png', manual, 'Gaun', 'TikTok', 'MY', 'ms'])
        self.db.add(TitleAttributeCache(market_id=self.market.id, cache_key=key,
            facts={'attributes': [{'tag': '工艺', 'value': 'renda', 'source': 'image'}]}))
        self.db.commit()
        model = AsyncMock(side_effect=self.model)
        with patch('app.title_service.ask_json', new=model):
            facts = await identify_facts(self.db, self.market.id, snapshot, 'https://img.example/test.png', 'key')
            cached = await identify_facts(self.db, self.market.id, snapshot, 'https://img.example/test.png', 'key')
        self.assertEqual(model.await_count, 1)
        self.assertEqual(facts, cached)
        self.assertFalse({'工艺', '品牌'} & {fact['tag'] for fact in facts['attributes']})
        self.assertNotIn('工艺', model.await_args.args[2]['visual_tags'])
        self.assertEqual(match_keywords(snapshot, {'attributes': [
            {'tag': '工艺', 'value': 'renda', 'localized_value': 'renda', 'source': 'manual'},
            {'tag': '品牌', 'value': 'Acme', 'localized_value': 'Acme', 'source': 'manual'}]}), [])

    async def test_indonesian_choices_use_original_brand_and_survive_soft_budget(self):
        snapshot = self.snapshot(site='ID', language='id', category_localized_name='Daster')
        record = create_record(self.db, self.market, 1, snapshot, 'https://img.example/test.png', 'indonesian')
        self.db.commit()
        with patch('app.title_service.ask_json', new=AsyncMock(side_effect=self.model)):
            facts = await identify_facts(self.db, self.market.id, record.snapshot, record.image_url, 'key')
        brand = record.snapshot['selected_brand_keyword']
        self.assertEqual(next(f['localized_value'] for f in facts['attributes'] if f['tag'] == '品牌'), brand['phrase'])
        candidates = match_keywords(record.snapshot, facts)
        chosen = choose_keywords(record.snapshot, candidates, {}, core='a' * 205)
        self.assertEqual({word['tag'] for word in chosen}, {'工艺', '品牌'})

    async def test_generation_does_not_reject_changed_or_omitted_confirmed_phrases(self):
        snapshot = self.snapshot()
        record = create_record(self.db, self.market, 1, snapshot, 'https://img.example/test.png', 'rephrased')
        self.db.commit()
        title = 'Busana wanita acme dengan hiasan cantik ' + 'a' * 145

        async def answer(key, instructions, data, **kwargs):
            if 'manual' in data:
                return await self.model(key, instructions, data, **kwargs)
            return {'title': title}

        with patch('app.title_service.ask_json', new=AsyncMock(side_effect=answer)):
            result = await generate_record(self.db, record.id, 'test-key')
        self.assertEqual(result['title'], title)
        self.assertEqual(result['attempts'], 1)

    async def test_missing_and_invalid_manual_attributes_continue_generation_and_keep_diagnostics(self):
        snapshot = self.snapshot(attributes={'结构设计': '长袖'})
        record = create_record(self.db, self.market, 1, snapshot, 'https://img.example/missing.png', 'missing')
        self.db.commit()
        title = 'Gaun wanita dengan hiasan cantik ' + 'a' * 155

        async def answer(key, instructions, data, **kwargs):
            if 'manual' in data:
                return {'attributes': [{'tag': '性别', 'value': '男', 'localized_value': 'Lelaki',
                    'source': 'manual', 'evidence': 'manual'}]}
            return {'title': title}

        with patch('app.title_service.ask_json', new=AsyncMock(side_effect=answer)):
            result = await generate_record(self.db, record.id, 'test-key')
        self.assertEqual(result['title'], title)
        self.assertEqual(result['source'], 'ai')
        self.assertEqual(result['attempts'], 1)
        self.assertIsNone(record.error)
        facts = record.facts
        missing = {fact['tag']: fact for fact in facts['unretained_confirmed_attributes']}
        self.assertEqual(missing['结构设计']['value'], '长袖')
        self.assertEqual(missing['结构设计']['reason'], '模型未返回该属性')
        self.assertIn('未通过', missing['性别']['reason'])
        self.assertEqual(next(f['localized_value'] for f in facts['attributes'] if f['tag'] == '品类'), 'Gaun')
        self.assertNotIn('性别', {f['tag'] for f in facts['attributes']})
        self.db.expire_all()
        self.assertEqual(self.db.get(TitleRecord, record.id).facts, facts)

    async def test_request_reuse_rejects_changed_choice_configuration_and_keeps_history(self):
        snapshot = self.snapshot()
        record = create_record(self.db, self.market, 1, snapshot, 'https://img.example/test.png', 'reuse')
        self.db.commit()
        original = copy.deepcopy(record.snapshot)
        same = create_record(self.db, self.market, 1, snapshot, record.image_url, 'reuse')
        self.assertEqual(same.id, record.id)
        for field in ('craft_keyword_ids', 'brand_keyword_ids'):
            changed = {**snapshot, field: []}
            with self.assertRaises(HTTPException) as caught:
                create_record(self.db, self.market, 1, changed, record.image_url, 'reuse')
            self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(record.snapshot, original)

    async def test_extra_known_claims_are_preserved_in_single_batch_and_supply_titles(self):
        material = keyword(5, 'kapas', tag='材质')
        other_material = keyword(6, 'linen', tag='材质')
        for mode in ('single', 'batch', 'supply'):
            with self.subTest(mode=mode):
                snapshot = self.snapshot(material_keywords=[material], material_keyword_ids=[5])
                snapshot['keywords'] += [material, other_material]
                task_id = None
                if mode == 'batch':
                    task = TitleTask(market_id=self.market.id, user_id=1, kind='batch', state='running',
                        request_key=digest('cleanup-batch'), request_hash=digest('cleanup-batch'),
                        snapshot={'profile': snapshot})
                    self.db.add(task)
                    self.db.flush()
                    task_id = task.id
                with patch('app.title_service.secrets.choice', side_effect=lambda values: values[0]):
                    record = create_record(self.db, self.market, 1, snapshot, 'https://img.example/cleanup.png',
                        ['cleanup', mode], task_id=task_id, supply=mode == 'supply')
                self.db.commit()

                async def answer(key, instructions, data, **kwargs):
                    result = await self.model(key, instructions, data, **kwargs)
                    if 'title' in result:
                        result['title'] += ' LINEN renda BrandB linen'
                        self.assertIn('Material, craft and brand may use only the exact original phrases', instructions)
                        self.assertEqual({word['phrase'] for word in data['manually_selected']}, {'kapas', 'sulaman', 'Acme'})
                    return result

                with patch('app.title_service.ask_json', new=AsyncMock(side_effect=answer)):
                    result = await generate_record(self.db, record.id, 'key')
                self.assertEqual(result['attempts'], 4)
                for phrase in ('kapas', 'sulaman', 'Acme'):
                    self.assertIn(phrase, result['title'])
                for phrase in ('linen', 'renda', 'BrandB'):
                    self.assertIn(phrase.lower(), result['title'].lower())
                self.assertNotIn('已删除未选定的面料、工艺或品牌词', result['warnings'])


    async def test_recognition_hints_change_cache_and_do_not_become_facts(self):
        snapshot = self.snapshot(recognition_prompt='重点查看领口')
        with patch('app.title_service.ask_json', new=AsyncMock(side_effect=self.model)) as model:
            first = await identify_facts(self.db, self.market.id, snapshot, 'https://img.example/hints.png', 'key')
            self.assertEqual(await identify_facts(self.db, self.market.id, snapshot, 'https://img.example/hints.png', 'key'), first)
            changed = {**snapshot, 'recognition_prompt': '重点查看袖口'}
            await identify_facts(self.db, self.market.id, changed, 'https://img.example/hints.png', 'key')
        self.assertEqual(model.await_count, 2)
        self.assertEqual([call.args[2]['recognition_hints'] for call in model.await_args_list], ['重点查看领口', '重点查看袖口'])
        self.assertNotIn('重点查看领口', str(first))
        self.assertIn('never product evidence', model.await_args.args[1])

    async def test_modern_facts_do_not_reuse_legacy_visual_craft_cache(self):
        legacy = self.snapshot()
        legacy.pop('confirmed_choices_version')
        with patch('app.title_service.ask_json', new=AsyncMock(side_effect=self.model)) as model:
            old = await identify_facts(self.db, self.market.id, legacy, 'https://img.example/shared.png', 'key')
            current = await identify_facts(self.db, self.market.id, self.snapshot(), 'https://img.example/shared.png', 'key')
        self.assertEqual(model.await_count, 2)
        self.assertNotIn('工艺', {fact['tag'] for fact in old['attributes']})
        self.assertNotIn('工艺', {fact['tag'] for fact in current['attributes']})

    async def test_image_failure_does_not_pass_hints_to_manual_fallback(self):
        async def answer(key, instructions, data, **kwargs):
            if kwargs.get('image_url'):
                raise ProviderError('识图失败')
            return await self.model(key, instructions, data, **kwargs)

        with patch('app.title_service.ask_json', new=AsyncMock(side_effect=answer)) as model:
            facts = await identify_facts(self.db, self.market.id,
                self.snapshot(recognition_prompt='重点查看领口'), 'https://img.example/failure.png', 'key')
        self.assertNotIn('recognition_hints', model.await_args.args[2])
        self.assertTrue(all(fact['source'] == 'manual' for fact in facts['attributes']))

    async def test_legacy_snapshot_does_not_allow_visual_craft_or_brand(self):
        snapshot = self.snapshot()
        snapshot.pop('confirmed_choices_version')
        for kind in ('craft', 'brand'):
            snapshot.pop(f'{kind}_keyword_ids')
            snapshot.pop(f'{kind}_keywords')
        with patch('app.title_service.ask_json', new=AsyncMock(side_effect=self.model)) as model:
            facts = await identify_facts(self.db, self.market.id, snapshot, 'https://img.example/test.png', 'key')
        self.assertNotIn('工艺', model.await_args.args[2]['visual_tags'])
        self.assertEqual(match_keywords(snapshot, facts), [])


class ConfirmedChoicesMigrationTests(unittest.TestCase):
    def test_recognition_prompt_upgrade_and_downgrade_preserve_other_profile_data(self):
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, '20261104_66')
            profile = Table('title_template_profiles', MetaData(), autoload_with=connection)
            connection.execute(profile.insert(), {'id': 1, 'market_id': 1, 'template_id': 1,
                'category': '连衣裙', 'attributes': {}, 'category_names': [], 'locked_keyword_ids': [],
                'forbidden_keyword_ids': [], 'fallback_approved': False, 'updated_at': datetime.utcnow()})
            command.upgrade(config, 'head')
            current = Table('title_template_profiles', MetaData(), autoload_with=connection)
            self.assertIsNone(connection.scalar(select(current.c.recognition_prompt)))
            connection.execute(current.update().values(recognition_prompt='仔细查看领口'))
            self.assertEqual(connection.scalar(select(current.c.recognition_prompt)), '仔细查看领口')
            command.downgrade(config, '20261104_66')
            self.assertNotIn('recognition_prompt', {col['name'] for col in inspect(connection).get_columns('title_template_profiles')})
            self.assertEqual(connection.scalar(select(profile.c.category)), '连衣裙')
        engine.dispose()

    def test_upgrade_preserves_legacy_attributes_and_task_snapshot(self):
        engine = create_engine('sqlite://')
        with engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, '20261104_65')
            profile = Table('title_template_profiles', MetaData(), autoload_with=connection)
            connection.execute(profile.insert(), {'id': 1, 'market_id': 1, 'template_id': 1,
                'category': '连衣裙', 'attributes': {'品牌': 'Acme', '工艺': '刺绣'}, 'category_names': [],
                'locked_keyword_ids': [], 'forbidden_keyword_ids': [], 'fallback_approved': False, 'updated_at': datetime.utcnow()})
            snapshot = {'profile': {'attributes': {'品牌': 'Acme', '工艺': '刺绣'}}}
            connection.execute(TitleTask.__table__.insert(), {'id': 1, 'market_id': 1, 'user_id': 1,
                'kind': 'batch', 'request_key': 'a' * 64, 'request_hash': 'b' * 64, 'snapshot': snapshot})
            command.upgrade(config, 'head')
            current = Table('title_template_profiles', MetaData(), autoload_with=connection)
            row = connection.execute(select(current)).mappings().one()
            self.assertIsNone(row['craft_keyword_ids'])
            self.assertIsNone(row['brand_keyword_ids'])
            self.assertEqual(row['attributes'], {'品牌': 'Acme', '工艺': '刺绣'})
            self.assertEqual(connection.scalar(select(TitleTask.__table__.c.snapshot)), snapshot)
            command.downgrade(config, '20261104_65')
            self.assertNotIn('craft_keyword_ids', {col['name'] for col in inspect(connection).get_columns('title_template_profiles')})
        engine.dispose()
