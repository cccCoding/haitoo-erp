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
                               identify_facts, match_keywords, validate_choice_claims)
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
        with self.assertRaisesRegex(ProviderError, '未选定的工艺'):
            validate_choice_claims('Gaun Wanita Lengan Panjang renda', snapshot)
        with self.assertRaisesRegex(ProviderError, '未选定的品牌'):
            validate_choice_claims('Gaun Wanita Lengan Panjang Acme', snapshot)

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
        with self.assertRaisesRegex(ProviderError, '大小写'):
            validate_choice_claims('Daster Wanita ' + brand['phrase'].lower(), record.snapshot)

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

    async def test_legacy_snapshot_keeps_visual_craft_and_brand_exclusion(self):
        snapshot = self.snapshot()
        snapshot.pop('confirmed_choices_version')
        for kind in ('craft', 'brand'):
            snapshot.pop(f'{kind}_keyword_ids')
            snapshot.pop(f'{kind}_keywords')
        with patch('app.title_service.ask_json', new=AsyncMock(side_effect=self.model)) as model:
            facts = await identify_facts(self.db, self.market.id, snapshot, 'https://img.example/test.png', 'key')
        self.assertIn('工艺', model.await_args.args[2]['visual_tags'])
        self.assertEqual([word['phrase'] for word in match_keywords(snapshot, facts)], ['renda'])


class ConfirmedChoicesMigrationTests(unittest.TestCase):
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
