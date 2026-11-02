"""印尼词库的语言、隔离、导入及生成采纳行为。"""
import asyncio
import copy
import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import select

from app import main
from app.ai_providers import ProviderError
from app.credentials import encrypt_secret
from app.models import ProductDraft, User, UserAIProviderCredential
from app.title_import import extract_row, parse_file
from app.title_markets import localized_value
from app.title_models import TitleAttributeCache, TitleMarket, TitleRecord, TitleTask
from app.title_service import (adopt_record, create_record, generate_record, get_market, identify_facts,
    profile_snapshot, validate_localized_title)
from tests import test_title_library as fixtures
from tests.test_supply_catalog import SupplyFixture

ID_MARKET = {'site': 'ID', 'language': 'id'}
ID_TITLE = 'Daster Lengan Panjang Motif Bunga'
ID_KEYWORDS = ('印尼语词语,中文释义,产品分类,标签\n'
               'daster,连衣裙,连衣裙,品类\nlengan panjang,长袖,连衣裙,结构设计\n'
               'motif bunga,花卉,连衣裙,图案\n')
ID_FACTS = {'attributes': [
    {'tag': tag, 'value': value, 'localized_value': expression, 'source': source, 'evidence': 'confirmed fact'}
    for tag, value, expression, source in [
        ('品类', '连衣裙', 'daster', 'manual'), ('结构设计', '长袖', 'lengan panjang', 'manual'),
        ('图案', '花卉', 'motif bunga', 'image'), ('性别', '女', 'wanita', 'manual'),
        ('年龄', '成人', 'dewasa', 'manual')]], 'conflicts': []}


class IndonesiaTitleTests(SupplyFixture, unittest.TestCase):
    confirm_new_categories = fixtures.TitleLibraryTests.confirm_new_categories
    run_worker = fixtures.TitleLibraryTests.run_worker

    def setUp(self):
        super().setUp()
        self.app.include_router(main.app.router)
        with self.sessions() as db:
            for uid in (1, 2):
                db.add(UserAIProviderCredential(company_id=1, user_id=uid, provider='deepseek',
                    secret_encrypted=encrypt_secret('test-key')))
            db.commit()

    def upload(self, content=ID_KEYWORDS, market=None, kind='keywords', filename='words.csv'):
        response = self.request('POST', '/title-imports', files={'file': (filename, content.encode())},
            data={'kind': kind, **(ID_MARKET if market is None else market)})
        self.assertEqual(response.status_code, 200, response.text)
        task = response.json()
        self.confirm_new_categories(task)
        return task

    def import_words(self, **kwargs):
        task = self.upload(**kwargs)
        self.assertEqual(self.request('POST', f"/title-tasks/{task['id']}/start", json={}).status_code, 200)
        self.run_worker()
        detail = self.request('GET', f"/title-tasks/{task['id']}").json()
        self.assertEqual(detail['state'], 'review', detail)
        response = self.request('POST', f"/title-imports/{task['id']}/confirm",
            json={'selections': [word['index'] for word in detail['result']['words']]})
        self.assertEqual(response.status_code, 200, response.text)
        return task['id']

    def configure(self):
        self.import_words()
        response = self.request('PUT', '/title-profiles/1', json={**ID_MARKET,
            'category': '连衣裙', 'gender': '女', 'age_group': '成人', 'attributes': {'结构设计': '长袖'}})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def model(self, title=ID_TITLE, facts=None):
        async def answer(key, instructions, data, **kwargs):
            self.assertIn('Bahasa Indonesia', instructions)
            return copy.deepcopy(facts or ID_FACTS) if 'manual' in data else {'title': title}
        return AsyncMock(side_effect=answer)

    def generate(self, request_key='indonesia-title-001', **kwargs):
        return self.request('POST', '/templates/1/generate-draft-title', uid=2,
            json={**ID_MARKET, 'method': 'library', 'image_url': 'https://img.example/1.png',
                  'request_key': request_key, **kwargs})

    def test_market_pairs_are_validated_on_every_market_query_and_request_body(self):
        endpoints = ['/title-market', '/title-dictionaries', '/title-keywords', '/title-tasks',
            '/title-statistics', '/title-profiles/1', '/title-template-configurations',
            '/title-import-template', '/title-category-merges']
        for endpoint in endpoints:
            for pair in ({'site': 'ID', 'language': 'ms'}, {'site': 'MY', 'language': 'id'},
                         {'site': 'SG', 'language': 'id'}):
                with self.subTest(endpoint=endpoint, pair=pair):
                    self.assertEqual(self.request('GET', endpoint, params=pair).status_code, 400)
            self.assertEqual(self.request('GET', endpoint, params=ID_MARKET).status_code, 200)
        for endpoint, payload in [('/title-market', {'enabled': True}),
            ('/title-profiles/1', {'category': '连衣裙', 'gender': '女', 'age_group': '成人'})]:
            self.assertEqual(self.request('PUT', endpoint, json={**payload, 'site': 'ID', 'language': 'ms'}).status_code, 422)
        for endpoint, payload in [('/templates/1/generate-draft-title', {'image_url': 'https://img.example/1.png'}),
            ('/product-library/generate-draft-title', {'source_type': 'material', 'id': 1}),
            ('/title-generation-jobs', {'template_id': 1, 'request_key': 'invalid-market-pair',
                'groups': [{'key': 'one', 'source': {'source_type': 'material', 'id': 1}}]})]:
            self.assertEqual(self.request('POST', endpoint, json={**payload, 'site': 'ID', 'language': 'ms'}).status_code, 422)

    def test_indonesia_starts_empty_and_profile_metadata_does_not_fall_back_to_my(self):
        self.import_words(content=fixtures.KEYWORDS, market={})
        self.assertEqual(self.request('GET', '/title-profiles/1', params=ID_MARKET).json()['site'], 'ID')
        self.assertEqual(self.request('PUT', '/title-market', json={**ID_MARKET, 'enabled': True}).status_code, 200)
        definitions = self.request('GET', '/title-dictionaries', params=ID_MARKET).json()['items']
        self.assertTrue(definitions)
        self.assertTrue(all(row['built_in'] and row['kind'] == 'tag' for row in definitions))
        self.assertEqual(self.request('GET', '/title-keywords', params=ID_MARKET).json()['total'], 0)
        profile = self.request('GET', '/title-profiles/1', params=ID_MARKET).json()
        self.assertEqual((profile['site'], profile['language'], profile['category']), ('ID', 'id', ''))
        self.assertFalse(profile['ready'])
        self.assertEqual(self.request('GET', '/title-profiles/1').json()['language'], 'ms')

    def test_csv_xlsx_and_download_template_use_indonesian_headers(self):
        csv_rows = parse_file(ID_KEYWORDS.encode(), 'words.csv', 'keywords', **ID_MARKET)
        book = Workbook()
        for line in ID_KEYWORDS.strip().splitlines():
            book.active.append(line.split(','))
        stream = io.BytesIO(); book.save(stream); book.close()
        self.assertEqual(csv_rows, parse_file(stream.getvalue(), 'words.xlsx', 'keywords', **ID_MARKET))
        template = self.request('GET', '/title-import-template', params={**ID_MARKET, 'kind': 'keywords'})
        self.assertIn('印尼语词语', template.content.decode('utf-8-sig'))
        self.assertNotIn('马来语', template.content.decode('utf-8-sig'))
        self.assertIn('马来语词语', self.request('GET', '/title-import-template', params={'kind': 'keywords'}).text)
        with self.assertRaises(HTTPException):
            parse_file(fixtures.KEYWORDS.encode(), 'words.csv', 'keywords', **ID_MARKET)

    def test_original_title_extraction_checks_language_and_original_substrings(self):
        row = {'row': 2, 'values': {'原标题': ID_TITLE, '商品品类': '连衣裙'}}
        keyword = {'phrase': 'Motif Bunga', 'translation': '花卉', 'tag': '图案'}
        model = AsyncMock(return_value={'language': 'id', 'keywords': [keyword]})
        with patch('app.title_import.ask_json', new=model):
            words = asyncio.run(extract_row(row, 'titles', 'key', **ID_MARKET))
        self.assertEqual((words[0]['phrase'], words[0]['position']), ('Motif Bunga', ID_TITLE.index('Motif')))
        self.assertIn('Bahasa Indonesia', model.call_args.args[1])
        for answer in ({'language': 'ms', 'keywords': [keyword]},
                       {'language': 'id', 'keywords': [{**keyword, 'phrase': 'printed flowers'}]}):
            with patch('app.title_import.ask_json', new=AsyncMock(return_value=answer)), self.assertRaises(ValueError):
                asyncio.run(extract_row(row, 'titles', 'key', **ID_MARKET))

    def test_worker_uses_import_language_snapshot_and_duplicate_files_are_market_scoped(self):
        content = '商品标题,商品分类\n' + ID_TITLE + ',连衣裙\n'
        task = self.upload(content=content, kind='titles')
        duplicate = self.upload(content=content, kind='titles')
        self.assertEqual((duplicate['id'], duplicate['duplicate']), (task['id'], True))
        other = self.upload(content=content, kind='titles', market={})
        self.assertNotEqual(other['id'], task['id'])
        with self.sessions() as db:
            self.assertEqual(db.get(TitleTask, task['id']).snapshot['language'], 'id')
        self.request('POST', f"/title-tasks/{task['id']}/start", json={})
        with patch('app.title_import.ask_json', new=AsyncMock(return_value={'language': 'id',
            'keywords': [{'phrase': 'Daster', 'translation': '连衣裙', 'tag': '品类'}]})) as model:
            self.run_worker()
        self.assertIn('Bahasa Indonesia', model.call_args.args[1])
        self.assertEqual(self.request('GET', f"/title-tasks/{task['id']}").json()['state'], 'review')

    def test_market_and_company_isolation_and_cross_market_references(self):
        self.import_words(content=fixtures.KEYWORDS, market={})
        self.configure()
        id_words = self.request('GET', '/title-keywords', params=ID_MARKET).json()['items']
        my_words = self.request('GET', '/title-keywords').json()['items']
        self.assertEqual({word['phrase'] for word in id_words}, {'daster', 'lengan panjang', 'motif bunga'})
        self.assertEqual(self.request('GET', '/title-keywords', params={**ID_MARKET, 'platform': 'Shopee'}).json()['items'], id_words)
        self.assertEqual(self.request('GET', '/title-keywords', uid=5, params=ID_MARKET).json()['total'], 0)
        self.assertEqual(self.request('GET', '/title-tasks', params=ID_MARKET).json()['total'], 1)
        self.assertEqual(self.request('GET', '/title-tasks').json()['total'], 1)
        self.assertFalse(self.request('GET', '/title-profiles/1').json()['ready'])
        self.assertTrue(self.request('GET', '/title-template-configurations', params=ID_MARKET).json()['items'][0]['ready'])
        self.assertFalse(self.request('GET', '/title-template-configurations').json()['items'][0]['ready'])
        response = self.request('PUT', '/title-profiles/1', json={**ID_MARKET, 'category': '连衣裙',
            'gender': '女', 'age_group': '成人', 'forbidden_keyword_ids': [my_words[0]['id']]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.request('POST', f"/title-keywords/{id_words[0]['id']}/merge",
            json={'target_id': my_words[0]['id']}).status_code, 400)

    def test_single_generation_and_adoption_use_record_market_and_indonesian_grammar(self):
        self.configure()
        with patch('app.title_service.ask_json', new=self.model()):
            response = self.generate()
        self.assertEqual(response.status_code, 200, response.text)
        generated = response.json()
        self.assertEqual((generated['site'], generated['language'], generated['title']), ('ID', 'id', ID_TITLE))
        self.assertTrue(all('localized_value' in fact and 'ms' not in fact for fact in generated['facts']['attributes']))
        with self.sessions() as db:
            draft = ProductDraft(company_id=1, created_by=2, template_id=1,
                title='Daster Bermotif Bunga Dengan Lengan Panjang', image_urls=['https://img.example/1.png'])
            db.add(draft); db.flush()
            adopt_record(db, draft, db.get(User, 2), generated['generation_id'])
            db.commit()
        self.assertEqual(self.request('GET', '/title-statistics', uid=2, params=ID_MARKET).json()['manual'], 1)
        self.assertEqual(self.request('GET', '/title-statistics', uid=2).json()['manual'], 0)

    def test_generation_rejects_missing_core_and_unconfirmed_claims_but_removes_forbidden_phrases(self):
        self.configure()
        category = self.request('GET', '/title-dictionaries', params=ID_MARKET).json()['items']
        category = next(row for row in category if row['kind'] == 'category')
        self.assertEqual(self.request('PATCH', f"/title-dictionaries/{category['id']}",
            json={'localized_name': 'Daster'}).status_code, 200)
        for index, title in enumerate(['Lengan Panjang Dengan Motif Bunga', ID_TITLE + ' Katun', ID_TITLE + ' Tahan Air']):
            with self.subTest(title=title), patch('app.title_service.ask_json', new=self.model(title)):
                response = self.generate(request_key=f'indonesia-invalid-{index}')
                self.assertEqual(response.status_code, 502, response.text)
        words = self.request('GET', '/title-keywords', params=ID_MARKET).json()['items']
        forbidden = next(word['id'] for word in words if word['tag'] == '图案')
        self.request('PUT', '/title-profiles/1', json={**ID_MARKET, 'category': '连衣裙', 'gender': '女',
            'age_group': '成人', 'attributes': {'结构设计': '长袖'}, 'forbidden_keyword_ids': [forbidden]})
        with patch('app.title_service.ask_json', new=self.model(ID_TITLE + ' Gaya Santai Kekinian')) as model:
            response = self.generate(request_key='indonesia-forbidden')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['title'], 'Daster Lengan Panjang Gaya Santai Kekinian')
            self.assertEqual(response.json()['attempts'], 1)
            self.assertEqual(model.await_count, 1)  # 复用识图缓存，一次成文；删除禁用词后直接采用。

    def test_batch_cancel_retry_and_snapshot_language_remain_indonesian(self):
        self.configure()
        payload = {**ID_MARKET, 'template_id': 1, 'request_key': 'indonesia-batch-001', 'groups': [
            {'key': 'one', 'source': {'source_type': 'material', 'id': 1}},
            {'key': 'two', 'source': {'source_type': 'material', 'id': 2}}]}
        response = self.request('POST', '/title-generation-jobs', uid=2, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        identity = response.json()['id']
        self.request('POST', f'/title-tasks/{identity}/cancel', uid=2, json={})
        self.assertEqual(self.request('POST', f'/title-tasks/{identity}/retry', uid=2, json={}).status_code, 200)
        with patch('app.title_service.ask_json', new=self.model()):
            self.run_worker()
        task = self.request('GET', f'/title-tasks/{identity}', uid=2).json()
        self.assertEqual(task['state'], 'completed', task)
        self.assertEqual({item['title'] for item in task['result']['items'].values()}, {ID_TITLE})
        with self.sessions() as db:
            self.assertEqual(db.get(TitleTask, identity).snapshot['profile']['language'], 'id')
        self.assertEqual(self.request('GET', '/title-tasks', uid=2, params={**ID_MARKET, 'kind': 'batch'}).json()['total'], 1)
        self.assertEqual(self.request('GET', '/title-tasks', uid=2, params={'kind': 'batch'}).json()['total'], 0)

    def test_confirmed_category_and_cache_are_market_scoped_and_legacy_ms_facts_are_readable(self):
        self.configure()
        with self.sessions() as db, patch('app.title_service.ask_json', new=self.model()) as model:
            market = get_market(db, 1, **ID_MARKET)
            snapshot = profile_snapshot(db, market, 1)
            first = asyncio.run(identify_facts(db, market.id, snapshot, 'https://img.example/1.png', 'key'))
            second = asyncio.run(identify_facts(db, market.id, snapshot, 'https://img.example/1.png', 'key'))
            self.assertEqual(first, second)
            self.assertEqual(model.await_count, 1)
            db.commit()
        self.assertEqual(localized_value({'ms': 'gaun'}), 'gaun')
        self.assertEqual(localized_value({'localized_value': 'daster', 'ms': 'gaun'}), 'daster')
        with self.sessions() as db:
            caches = db.scalars(select(TitleAttributeCache)).all()
            self.assertTrue(all(db.get(TitleMarket, item.market_id).site == 'ID' for item in caches))
        for title in ('Printed Floral Dress For Everyday Wear', '印尼语标题' * 8):
            with self.assertRaises(ProviderError):
                validate_localized_title(title, **ID_MARKET)

    def test_legacy_malay_record_resumes_and_adopts_using_ms_facts(self):
        self.import_words(content=fixtures.KEYWORDS, market={})
        response = self.request('PUT', '/title-profiles/1', json={'category': '连衣裙',
            'gender': '女', 'age_group': '成人', 'attributes': {'结构设计': '长袖'}})
        self.assertEqual(response.status_code, 200, response.text)
        with self.sessions() as db:
            market = get_market(db, 1)
            snapshot = profile_snapshot(db, market, 1)
            record = create_record(db, market, 2, snapshot, 'https://img.example/1.png', ['legacy-ms-record'])
            record.facts = copy.deepcopy(fixtures.FACTS)
            db.commit()
            with patch('app.title_service.ask_json', new=AsyncMock(return_value={'title': fixtures.TITLE})) as model:
                result = asyncio.run(generate_record(db, record.id, 'test-key'))
            self.assertEqual(model.await_count, 4)
            self.assertEqual((result['title'], result['site']), (fixtures.TITLE, 'MY'))
            draft = ProductDraft(company_id=1, created_by=2, template_id=1,
                title='Gaun Dengan Lengan Panjang Corak Bunga', image_urls=['https://img.example/1.png'])
            db.add(draft); db.flush()
            adopt_record(db, draft, db.get(User, 2), record.id)
            db.commit()
            self.assertTrue(all('ms' in fact for fact in db.get(TitleRecord, record.id).facts['attributes']))
