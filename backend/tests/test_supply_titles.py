"""货盘站点词库、提交快照、双语言兜底及真实 Excel 输出。"""
import asyncio
import copy
import hashlib
from datetime import datetime, timedelta
from io import BytesIO
import random
import unittest
from unittest.mock import AsyncMock, patch

from openpyxl import load_workbook
from sqlalchemy import select

from app.ai_providers import ProviderError
from app.credentials import encrypt_secret
from app.models import Company, ProductTemplate, SupplyJob, SupplyStrategy
from app.supply_worker import claim_job, request_market_title, run_job, style_sample
from app.supply_common import validate_title_fallback
from app.title_api import router as title_router
from app.title_models import TitleKeyword, TitleRecord, TitleTemplateProfile
from app.title_service import get_market, profile_snapshot
from tests.test_supply_catalog import SupplyFixture


class SupplyTitleTests(SupplyFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.app.include_router(title_router)
        self.configure_supply_titles('MY')
        self.configure_supply_titles('ID')
        self.exports = []

        def upload(company, job, epoch, filename, content):
            self.exports.append(content)
            return {'key': f'supply-exports/company/{company}/jobs/{job}/{epoch}/' + 'a' * 32 + '.xlsx',
                    'sha256': hashlib.sha256(content).hexdigest(), 'size': len(content)}

        self.enterContext(patch('app.supply_worker.upload_supply_export', side_effect=upload))

    def profile(self, db, site='MY'):
        market = get_market(db, 1, site=site, language='id' if site == 'ID' else 'ms')
        return db.scalar(select(TitleTemplateProfile).where(TitleTemplateProfile.market_id == market.id))

    def finish(self, identity):
        claimed = claim_job(self.sessions)
        self.assertEqual(claimed[0], identity)
        asyncio.run(run_job(*claimed, session_factory=self.sessions))
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            self.assertEqual(job.state, 'completed', job.error)
            return copy.deepcopy(job.checkpoint['links'])

    def cancel(self, identity):
        response = self.request('POST', f'/supply/jobs/{identity}/cancel', uid=4)
        self.assertEqual(response.status_code, 200, response.text)

    def test_historical_detail_hides_similarity_but_keeps_fallback_and_failure_reason(self):
        identity = self.submit(self.create_strategy())
        warnings = ['已使用马来语兜底标题；可能与其他链接高度相似',
            'AI 标题生成失败：模型超时', '与并发生成的同批标题高度相似，请核对', '保留其他提示']
        checkpoint = {'links': [{'title': 'Gaun Wanita Lengan Panjang', 'title_warnings': warnings}]}
        with self.sessions() as db:
            db.get(SupplyJob, identity).checkpoint = copy.deepcopy(checkpoint)
            db.commit()
        response = self.request('GET', f'/supply/jobs/{identity}', uid=4)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['drafts'][0]['title_warnings'],
            ['已使用马来语兜底标题', 'AI 标题生成失败：模型超时', '保留其他提示'])
        with self.sessions() as db:
            self.assertEqual(db.get(SupplyJob, identity).checkpoint, checkpoint)

    def test_market_selection_validation_legacy_default_and_omitted_patch_preserves_id(self):
        for site in ('SG', '', 'id'):
            response = self.request('POST', '/supply/strategies', uid=4, json=self.strategy_input(title_site=site))
            self.assertEqual(response.status_code, 422, response.text)
        identity = self.create_strategy(title_site='ID')
        response = self.request('PATCH', f'/supply/strategies/{identity}', uid=4, json=self.strategy_input())
        self.assertEqual(response.json()['title_site'], 'ID')
        job_id = self.submit(identity)
        with self.sessions() as db:
            snap = db.get(SupplyJob, job_id).snapshot
            self.assertEqual((snap['title_profile']['site'], snap['title_profile']['language']), ('ID', 'id'))
        self.cancel(job_id)
        with self.sessions() as db:
            strategy = db.get(SupplyStrategy, identity)
            strategy.parameters = {key: value for key, value in strategy.parameters.items() if key != 'title_site'}
            db.commit()
        self.assertEqual(self.request('GET', '/supply/strategies', uid=4).json()[0]['title_site'], 'MY')
        job_id = self.submit(identity, key='legacy-default-MY')
        with self.sessions() as db:
            snap = db.get(SupplyJob, job_id).snapshot
            self.assertEqual(snap['strategy']['title_site'], 'MY')
            self.assertEqual(snap['title_profile']['site'], 'MY')

    def test_missing_market_profile_and_required_facts_block_submission(self):
        strategy = self.create_strategy(title_site='ID')
        for field in ('gender', 'age_group', 'category'):
            with self.sessions() as db:
                profile = self.profile(db, 'ID')
                original = getattr(profile, field)
                setattr(profile, field, '' if field == 'category' else None)
                db.commit()
            response = self.request('POST', '/supply/jobs', uid=4,
                json={'strategy_id': strategy, 'idempotency_key': f'missing-{field}'})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(response.json()['detail'], '请联系管理员完善印尼站点该模板的词库配置')
            with self.sessions() as db:
                setattr(self.profile(db, 'ID'), field, original)
                db.commit()
        with self.sessions() as db:
            db.delete(self.profile(db, 'ID'))
            db.commit()
        response = self.request('POST', '/supply/jobs', uid=4,
            json={'strategy_id': strategy, 'idempotency_key': 'missing-profile'})
        self.assertEqual(response.status_code, 400, response.text)
        with self.sessions() as db:
            db.delete(get_market(db, 1, site='ID', language='id'))
            db.commit()
        response = self.request('POST', '/supply/jobs', uid=4,
            json={'strategy_id': strategy, 'idempotency_key': 'missing-market'})
        self.assertEqual(response.status_code, 400, response.text)

    def test_unset_localized_fallbacks_export_english(self):
        for site in ('MY', 'ID'):
            with self.subTest(site=site):
                with self.sessions() as db:
                    self.profile(db, site).fallback_title = None
                    self.profile(db, site).fallback_approved = False
                    db.commit()
                identity = self.submit(self.create_strategy(title_site=site), key=f'english-fallback-{site}')
                with patch('app.title_service.ask_json', new=AsyncMock()) as model:
                    links = self.finish(identity)
                    model.assert_not_awaited()  # 未配置公司密钥，直接进入已校验的兜底。
                self.assertTrue(all(link['title_source'] == 'fallback' for link in links))
                self.assertTrue(all(link['title'].startswith('Printed Long Sleeve') for link in links))
                self.assertTrue(all('对应站点兜底标题未设置' in link['title_warnings'][0] for link in links))
                self.assert_exported_titles(links)

    def assert_exported_titles(self, links):
        book = load_workbook(BytesIO(self.exports[-1]), read_only=True)
        sheet = book['Template']
        headers = next(sheet.iter_rows(values_only=True))
        title_column = headers.index('product_name')
        rows = list(sheet.iter_rows(min_row=7, max_row=106, values_only=True))
        book.close()
        self.assertEqual({row[title_column] for row in rows}, {link['title'] for link in links})
        self.assertEqual(len({link['title'] for link in links}), 10)
        self.assertTrue(all(link['title'].endswith(f' - L{index + 1:02d}') for index, link in enumerate(links)))

    def test_unapproved_localized_fallback_is_available_and_configuration_is_frozen_on_submit(self):
        for site, title in (('MY', 'Gaun Wanita Dewasa Lengan Panjang'), ('ID', 'Daster Wanita Dewasa Lengan Panjang')):
            with self.subTest(site=site):
                with self.sessions() as db:
                    profile = self.profile(db, site)
                    profile.fallback_title, profile.fallback_approved = title, False
                    db.commit()
                strategy = self.create_strategy(title_site=site, title_requirements='Keep confirmed facts')
                identity = self.submit(strategy, key=f'localized-fallback-{site}')
                with self.sessions() as db:
                    original = copy.deepcopy(db.get(SupplyJob, identity).snapshot)
                    profile = self.profile(db, site)
                    profile.gender, profile.fallback_title, profile.fallback_approved = '男', None, False
                    db.get(ProductTemplate, 1).title_template = 'Changed after submission'
                    db.get(SupplyStrategy, strategy).parameters = self.strategy_input(title_site='ID' if site == 'MY' else 'MY')
                    db.commit()
                # 相同幂等键在配置变动后仍返回原任务。
                self.assertEqual(self.submit(strategy, key=f'localized-fallback-{site}'), identity)
                links = self.finish(identity)
                self.assertTrue(all(link['title'].startswith(title) for link in links))
                self.assertTrue(all('英文兜底' not in link['title_warnings'][0] for link in links))
                self.assert_exported_titles(links)
                with self.sessions() as db:
                    self.assertEqual(db.get(SupplyJob, identity).snapshot, original)
                    records = db.scalars(select(TitleRecord).where(TitleRecord.snapshot['supply_job_id'].as_integer() == identity)).all()
                    self.assertTrue(all(record.adopted_at and record.source == 'fallback'
                        and record.error == '尚未配置公司货盘 DeepSeek 密钥' for record in records))

    def test_fallback_keeps_provider_and_validation_failures_after_export(self):
        for failure, expected in ((ProviderError('DeepSeek 调用失败：HTTP 429'), 'DeepSeek 调用失败：HTTP 429'),
                                  ({'title': 'Baju Wanita Dewasa Lengan Panjang'}, '标题遗漏核心品类：Gaun')):
            with self.subTest(failure=expected):
                with self.sessions() as db:
                    db.get(Company, 1).supply_ai_secret_encrypted = encrypt_secret('test-supply-key')
                    db.commit()
                identity = self.submit(key=expected)

                async def answer(key, instructions, data, **kwargs):
                    if 'Identify clothing attributes' in instructions:
                        expressions = {'品类': 'Gaun', '性别': 'Wanita', '年龄': 'Dewasa', '结构设计': 'Lengan Panjang'}
                        return {'attributes': [{'tag': tag, 'value': value, 'localized_value': expressions[tag],
                            'evidence': 'confirmed template', 'source': 'manual'} for tag, value in data['manual'].items()]}
                    if isinstance(failure, Exception):
                        raise failure
                    return failure

                with patch('app.title_service.ask_json', side_effect=answer), \
                     self.assertLogs('app.title_service', level='WARNING') as attempts, \
                     self.assertLogs('app.supply_worker', level='WARNING') as fallbacks:
                    links = self.finish(identity)
                self.assertEqual(len(attempts.records), 40)
                self.assertEqual(len(fallbacks.records), 10)
                self.assertTrue(all(expected in row.getMessage() for row in attempts.records + fallbacks.records))
                self.assertTrue(all(f'job={identity}' in row.getMessage() for row in attempts.records + fallbacks.records))
                self.assertTrue(all(link['title_source'] == 'fallback' and
                    any(expected in warning for warning in link['title_warnings']) for link in links))
                with self.sessions() as db:
                    for link in links:
                        record = db.get(TitleRecord, link['generation_id'])
                        self.assertEqual(record.attempts, 4)
                        self.assertIn(expected, record.error)
                        self.assertEqual(record.source, 'fallback')
                        self.assertIsNotNone(record.adopted_at)
                self.assert_exported_titles(links)

    def test_fallback_removes_forbidden_phrases_and_rejects_invalid_result(self):
        with self.sessions() as db:
            market = get_market(db, 1)
            word = TitleKeyword(market_id=market.id, code='FORBIDDEN', identity_hash='a' * 64,
                phrase='Longgar', translation='宽松', tag='版型', categories=['连衣裙'], priority='forbidden')
            db.add(word)
            profile = self.profile(db)
            profile.fallback_title, profile.fallback_approved = 'Gaun Wanita Dewasa Lengan Panjang Longgar', True
            db.commit()
        identity = self.submit()
        with self.sessions() as db:
            self.assertEqual(db.get(SupplyJob, identity).snapshot['title_profile']['fallback_title'], 'Gaun Wanita Dewasa Lengan Panjang')
        self.cancel(identity)
        with self.sessions() as db:
            word = db.scalar(select(TitleKeyword))
            word.phrase = 'Gaun Wanita Dewasa Lengan Panjang'
            db.commit()
        response = self.request('POST', '/supply/jobs', uid=4,
            json={'strategy_id': self.create_strategy(), 'idempotency_key': 'invalid-localized-fallback'})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn('禁用词后无效', response.json()['detail'])
        with self.sessions() as db:
            self.profile(db).fallback_title = None
            db.scalar(select(TitleKeyword)).phrase = 'Printed Long Sleeve Nursing Maxi Dress'
            db.commit()
        response = self.request('POST', '/supply/jobs', uid=4,
            json={'strategy_id': self.create_strategy(), 'idempotency_key': 'invalid-english-fallback'})
        self.assertEqual(response.status_code, 400, response.text)

    def test_both_markets_generate_from_library_and_count_adoption_after_export(self):
        for site, core in (('MY', 'Gaun'), ('ID', 'Daster')):
            with self.subTest(site=site):
                with self.sessions() as db:
                    market = get_market(db, 1, site=site, language='id' if site == 'ID' else 'ms')
                    word = TitleKeyword(market_id=market.id, code='SLEEVE', identity_hash=site * 32,
                        phrase='Lengan Panjang', translation='长袖', tag='结构设计', categories=['连衣裙'])
                    db.add(word)
                    db.get(Company, 1).supply_ai_secret_encrypted = encrypt_secret('test-supply-key')
                    db.get(ProductTemplate, 1).title_template = 'Category first'
                    db.commit()
                    word_id = word.id

                async def answer(key, instructions, data, **kwargs):
                    self.assertEqual(key, 'test-supply-key')
                    if 'Identify clothing attributes' in instructions:
                        expressions = {'品类': core, '性别': 'Wanita', '年龄': 'Dewasa', '结构设计': 'Lengan Panjang'}
                        return {'attributes': [{'tag': tag, 'value': value, 'localized_value': expressions[tag],
                            'evidence': 'confirmed template', 'source': 'manual'} for tag, value in data['manual'].items()], 'conflicts': []}
                    self.assertNotIn('template_requirements', data)
                    self.assertNotIn('style', data)
                    self.assertNotIn('forbidden', data)
                    self.assertIn('Lengan Panjang', [word['phrase'] for word in data['selected']])
                    return {'title': f'{core} Wanita Dewasa Lengan Panjang'}

                identity = self.submit(self.create_strategy(title_site=site, title_requirements='Use confirmed sleeves'), key=f'generate-{site}')
                with self.sessions() as db:
                    word = db.get(TitleKeyword, word_id)
                    word.phrase, word.status = 'Changed after submission', 'disabled'
                    db.get(ProductTemplate, 1).title_template = 'Changed after submission'
                    db.commit()
                with patch('app.title_service.ask_json', side_effect=answer), \
                     patch('app.supply_worker.request_title', new=AsyncMock()) as old_engine:
                    links = self.finish(identity)
                    old_engine.assert_not_awaited()
                self.assertTrue(all(link['title_source'] == 'ai' and link['title'].startswith(core) for link in links))
                self.assert_exported_titles(links)
                with self.sessions() as db:
                    self.assertEqual(db.get(TitleKeyword, word_id).adopted_count, 10)

    def test_profile_fallback_configuration_preserves_admin_and_company_permissions(self):
        payload = {'category': '连衣裙', 'gender': '女', 'age_group': '成人', 'site': 'ID', 'language': 'id',
                   'fallback_title': 'Daster Wanita Dewasa Lengan Panjang'}
        for uid in (2, 3, 4):
            response = self.request('PUT', '/title-profiles/1', uid=uid, json=payload)
            self.assertEqual(response.status_code, 403, response.text)
        response = self.request('PUT', '/title-profiles/1', uid=5, json=payload)
        self.assertEqual(response.status_code, 404, response.text)
        response = self.request('PUT', '/title-profiles/1', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['fallback_title'], payload['fallback_title'])
        self.assertFalse(response.json()['fallback_approved'])
        with self.sessions() as db:
            market = get_market(db, 1, site='ID', language='id')
            self.assertEqual(profile_snapshot(db, market, 1, require_fallback=True)['fallback_title'], payload['fallback_title'])
        # 旧客户端遗留审核值不阻止清空标题；审核字段仅保留接口兼容。
        response = self.request('PUT', '/title-profiles/1', json={**payload, 'fallback_title': None, 'fallback_approved': True})
        self.assertEqual(response.status_code, 200, response.text)

    def test_fallback_api_and_excel_accept_230_but_reject_231(self):
        for length in (230, 231):
            english = 'Printed Dress ' + 'a' * (length - len('Printed Dress '))
            response = self.request('PATCH', '/supply/templates/1', json={'supply_fallback_title': english})
            self.assertEqual(response.status_code, 200 if length == 230 else 422, response.text)
            if length == 230:
                self.assertEqual(response.json()['supply_fallback_title'], english)
            for site, core in (('MY', 'Gaun'), ('ID', 'Daster')):
                title = core + ' ' + 'a' * (length - len(core) - 1)
                payload = {'category': '连衣裙', 'gender': '女', 'age_group': '成人', 'site': site,
                           'language': 'id' if site == 'ID' else 'ms', 'fallback_title': title}
                response = self.request('PUT', '/title-profiles/1', json=payload)
                self.assertEqual(response.status_code, 200 if length == 230 else 422, response.text)
                if length == 230:
                    self.assertEqual(response.json()['fallback_title'], title)
        for site in ('MY', 'ID'):
            identity = self.submit(self.create_strategy(title_site=site), key=f'fallback-230-{site}')
            links = self.finish(identity)
            self.assertTrue(all(len(row['title']) == 236 for row in links))
            self.assert_exported_titles(links)
        with self.sessions() as db:
            self.profile(db).fallback_title = None
            db.commit()
        links = self.finish(self.submit(key='english-fallback-230'))
        self.assertTrue(all(len(row['title']) == 236 for row in links))
        self.assert_exported_titles(links)

    def test_fallback_length_is_checked_after_forbidden_cleanup_in_all_languages(self):
        for language, core, site in (('en', 'Printed Dress', 'MY'), ('ms', 'Gaun', 'MY'), ('id', 'Daster', 'ID')):
            title = core + ' ' + 'a' * (229 - len(core))
            profile = {'fallback_language': language, 'language': language, 'site': site,
                       'fallback_title': title + ' Forbidden', 'forbidden_phrases': ['Forbidden']}
            self.assertEqual(validate_title_fallback(profile), title)
            profile['forbidden_phrases'] = []
            with self.assertRaisesRegex(ProviderError, '25–230'):
                validate_title_fallback(profile)

    def test_ai_230_character_body_survives_export_for_both_markets(self):
        with self.sessions() as db:
            db.get(Company, 1).supply_ai_secret_encrypted = encrypt_secret('test-supply-key')
            db.commit()
        for site, core in (('MY', 'Gaun'), ('ID', 'Daster')):
            title = core + ' ' + 'a' * (229 - len(core))

            async def answer(key, instructions, data, **kwargs):
                if 'Identify clothing attributes' in instructions:
                    expressions = {'品类': core, '性别': 'Wanita', '年龄': 'Dewasa', '结构设计': 'Lengan Panjang'}
                    return {'attributes': [{'tag': tag, 'value': value, 'localized_value': expressions[tag],
                        'evidence': 'confirmed template', 'source': 'manual'} for tag, value in data['manual'].items()]}
                self.assertEqual((data['target_minimum'], data['target_maximum'], data['maximum']), (180, 200, 230))
                return {'title': title}

            identity = self.submit(self.create_strategy(title_site=site), key=f'ai-230-{site}')
            with patch('app.title_service.ask_json', side_effect=answer):
                links = self.finish(identity)
            self.assertTrue(all(row['title_source'] == 'ai' and len(row['title']) == 236 for row in links))
            self.assert_exported_titles(links)

    def test_reclaimed_job_reuses_checkpoint_and_uncheckpointed_title_without_duplicate_records(self):
        identity = self.submit()
        claimed = claim_job(self.sessions)
        with self.sessions() as db:
            snap = db.get(SupplyJob, identity).snapshot
            rng = random.Random(snap['seed'])
            links = [{'index': index, 'materials': style_sample(snap['candidates'], 5, rng),
                      'title': None, 'replaced': False} for index in range(10)]
        generated = []
        for index in (0, 1):
            generated.append(asyncio.run(request_market_title(identity, claimed[1], index,
                links[index]['materials'][0]['url'], self.sessions)))
        # 第一条已写入任务进度；第二条在记录提交后、进度提交前中断。
        result = generated[0]
        links[0].update(title=result['title'] + ' - L01', title_source=result['source'],
                        generation_id=result['generation_id'], title_warnings=result['warnings'])
        with self.sessions() as db:
            job = db.get(SupplyJob, identity)
            job.checkpoint = {'links': links}
            job.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
            self.assertTrue(all(record.adopted_at is None for record in db.scalars(select(TitleRecord))))
            db.commit()
        with patch('app.title_service.ask_json', new=AsyncMock()) as model:
            completed = self.finish(identity)
            model.assert_not_awaited()
        self.assertEqual([link['generation_id'] for link in completed[:2]], [result['generation_id'] for result in generated])
        self.assert_exported_titles(completed)
        with self.sessions() as db:
            records = db.scalars(select(TitleRecord)).all()
            self.assertEqual(len(records), 10)
            self.assertTrue(all(record.adopted_at for record in records))

    def test_cancelled_or_reclaimed_execution_never_uses_fallback(self):
        for action in ('cancel', 'reclaim'):
            identity = self.submit(key=f'execution-{action}')
            claimed = claim_job(self.sessions)

            async def lose_execution(*args, **kwargs):
                with self.sessions() as db:
                    job = db.get(SupplyJob, identity)
                    if action == 'cancel':
                        job.state = 'cancelled'
                    job.lease_epoch += 1
                    db.commit()
                raise ProviderError('模拟请求失败')

            with patch('app.title_service.generate_record', side_effect=lose_execution):
                with self.assertRaisesRegex(ProviderError, '取消|执行权'):
                    asyncio.run(request_market_title(identity, claimed[1], 0, 'https://img.example/1.png', self.sessions))
            with self.sessions() as db:
                records = db.scalars(select(TitleRecord).where(TitleRecord.snapshot['supply_job_id'].as_integer() == identity)).all()
                self.assertTrue(all(record.title is None for record in records))
                db.get(SupplyJob, identity).state = 'cancelled'
                db.commit()
