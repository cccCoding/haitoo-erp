"""SKU 累计额度、容量匹配与 HTTP 提交规则。"""
import copy
import random
import unittest
from collections import Counter
from functools import lru_cache
from itertools import combinations

from sqlalchemy import select

from app.models import MaterialAsset, SupplyAudit, SupplyJob, SupplyJobMaterial
from app.supply_quota import QUOTA_VERSION, allocate_links, sku_use_counts
from app.supply_worker import style_sample
from tests.test_supply_catalog import SupplyFixture


class SupplyQuotaAllocationTests(unittest.TestCase):
    def candidates(self, count):
        return [{"id": i, "sku": f"SKU{i}", "url": f"https://img/{i}", "style_id": None}
                for i in range(count)]

    def assert_valid(self, links, used, count, length):
        self.assertEqual(len(links), length)
        for link in links:
            for field in ('id', 'sku', 'url'):
                self.assertEqual(len({item[field] for item in link['materials']}), count)
        usages = Counter(item['sku'] for link in links for item in link['materials'])
        self.assertTrue(all(used.get(sku, 0) + value <= 3 for sku, value in usages.items()))

    def test_greedy_dead_end_is_rebalanced_instead_of_rejected(self):
        candidates = self.candidates(4)
        used = {'SKU0': 2, 'SKU1': 2, 'SKU2': 1, 'SKU3': 1}
        # 第一组 0、1、2 会导致第二组无法凑齐，但两组分别用 0/1 + 2 + 3 可行。
        links = allocate_links(candidates, 3, 2, 'seed', used,
                               sample=lambda items, count, rng: copy.deepcopy(items[:count]))
        self.assert_valid(links, used, 3, 2)
        self.assertEqual(Counter(item['sku'] for link in links for item in link['materials']),
                         {'SKU0': 1, 'SKU1': 1, 'SKU2': 2, 'SKU3': 2})

    def test_url_bottleneck_cannot_be_hidden_by_total_sku_budget(self):
        candidates = self.candidates(4)
        for item in candidates[:3]:
            item['url'] = 'https://img/shared'
        # 两种 URL 足以组成一个链接，但独立 URL 的唯一 SKU 只有三次额度。
        with self.assertRaisesRegex(ValueError, '剩余素材额度不足'):
            allocate_links(candidates, 2, 4, 'seed', {}, sample=style_sample)

    def test_style_preference_is_preserved_until_quota_requires_other_styles(self):
        candidates = self.candidates(10)
        for item in candidates:
            item['style_id'] = 1 if item['id'] < 5 else 2
        links = allocate_links(candidates, 5, 6, 'seed', {}, sample=style_sample)
        self.assert_valid(links, {}, 5, 6)
        self.assertTrue(all(len({item['style_id'] for item in link['materials']}) == 1 for link in links))
        self.assertEqual(Counter(item['sku'] for link in links for item in link['materials']),
                         {item['sku']: 3 for item in candidates})

    def test_fifty_links_capacity_match_is_seeded_and_does_not_mutate_candidates(self):
        candidates = self.candidates(150)
        original = copy.deepcopy(candidates)
        # 直接触发全局匹配，验证最大批次 450 个位置。
        links = allocate_links(candidates, 9, 50, 'large', {}, sample=lambda *args: [])
        self.assert_valid(links, {}, 9, 50)
        self.assertEqual(links, allocate_links(candidates, 9, 50, 'large', {}, sample=lambda *args: []))
        self.assertEqual(candidates, original)

    def test_style_quota_is_balanced_before_resorting_to_mixed_groups(self):
        candidates = self.candidates(20)
        for item in candidates:
            item['style_id'] = 1 if item['id'] < 10 else 2
        # 未平衡额度时，这个种子会过早用尽同风格内部分 SKU，最后一组被迫混用。
        links = allocate_links(candidates, 5, 10, 124, {}, sample=style_sample)
        self.assert_valid(links, {}, 5, 10)
        self.assertTrue(all(len({item['style_id'] for item in link['materials']}) == 1 for link in links))

    def test_small_random_cases_agree_with_exhaustive_feasibility_search(self):
        rng = random.Random(19)
        for _ in range(80):
            candidates = self.candidates(6)
            for item in candidates:
                item['url'] = f"https://img/{rng.randrange(4)}"
            used = {item['sku']: rng.randrange(4) for item in candidates}
            count, length = rng.randrange(2, 4), rng.randrange(2, 5)
            choices = [group for group in combinations(range(6), count)
                       if len({candidates[i]['url'] for i in group}) == count]

            @lru_cache(None)
            def feasible(budgets, left):
                if not left:
                    return True
                for group in choices:
                    if all(budgets[i] for i in group):
                        remaining = tuple(value - (i in group) for i, value in enumerate(budgets))
                        if feasible(remaining, left - 1):
                            return True
                return False

            expected = feasible(tuple(3 - used[item['sku']] for item in candidates), length)
            try:
                links = allocate_links(candidates, count, length, 'seed', used, sample=style_sample)
            except ValueError:
                self.assertFalse(expected, (candidates, used, count, length))
            else:
                self.assertTrue(expected)
                self.assert_valid(links, used, count, length)


class SupplyQuotaApiTests(SupplyFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.configure_supply_titles()

    def history(self, *, uid=4, sku='SOURCE001', count=3, state='completed', successful=True,
                company_id=1, material_id=1, link_index=0):
        with self.sessions() as db:
            job = SupplyJob(company_id=company_id, user_id=uid, template_id=1, category_catalog_id=1,
                category_blob=b'old', idempotency_key=f'history-{random.random()}', request_hash='x', state=state)
            db.add(job); db.flush()
            db.add_all(SupplyJobMaterial(company_id=company_id, job_id=job.id, material_id=material_id,
                sku=sku, version_hash=f'v{index}', link_index=link_index + index, successful=successful)
                for index in range(count))
            db.commit()
            return job.id

    def test_third_use_is_available_and_fourth_is_excluded_for_all_roles(self):
        for uid in (1, 2, 3, 4):
            with self.subTest(uid=uid):
                self.history(uid=uid, count=2)
                identity = self.submit(uid=uid)
                with self.sessions() as db:
                    checkpoint = db.get(SupplyJob, identity).checkpoint
                    self.assertEqual(checkpoint['quota_version'], QUOTA_VERSION)
                    uses = sum(item['sku'] == 'SOURCE001' for link in checkpoint['links']
                               for item in link['materials'])
                    self.assertLessEqual(uses, 1)
                self.request('POST', f'/supply/jobs/{identity}/cancel', uid=uid)
                self.history(uid=uid, count=1)
                identity = self.submit(uid=uid, key=f'after-third-{uid}')
                with self.sessions() as db:
                    links = db.get(SupplyJob, identity).checkpoint['links']
                    self.assertNotIn('SOURCE001', [item['sku'] for link in links for item in link['materials']])
                self.request('POST', f'/supply/jobs/{identity}/cancel', uid=uid)

    def test_insufficient_total_quota_rejects_without_creating_job_or_audit(self):
        # 20 个 SKU 原有 60 次容量，耗掉 12 次后不足一批 50 次。
        for index in range(1, 5):
            self.history(sku=f'SOURCE{index:03d}', material_id=index)
        strategy = self.create_strategy()
        with self.sessions() as db:
            before_jobs, before_audits = db.query(SupplyJob).count(), db.query(SupplyAudit).count()
        response = self.request('POST', '/supply/jobs', uid=4,
            json={'strategy_id': strategy, 'idempotency_key': 'insufficient-quota'})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn('减少链接数量或补充素材', response.json()['detail'])
        with self.sessions() as db:
            self.assertEqual(db.query(SupplyJob).count(), before_jobs)
            self.assertEqual(db.query(SupplyAudit).count(), before_audits)
        self.assertIsInstance(self.submit(uid=7), int)

    def test_sku_counts_survive_material_deletion_reimport_template_and_file_changes(self):
        self.history(uid=2, count=4)
        with self.sessions() as db:
            db.delete(db.get(MaterialAsset, 1)); db.flush()
            db.add(MaterialAsset(id=100, company_id=1, template_id=1, claimed_by=2, name='重新导入',
                sku='SOURCE001', url='https://img.example/reimport.png', supply_listed=True))
            jobs = db.scalars(select(SupplyJob)).all()
            for job in jobs:
                job.template_id, job.output_deleted_at = 999, job.created_at
            db.commit()
        response = self.request('GET', '/supply/materials', uid=2)
        row = next(row for row in response.json()['items'] if row['sku'] == 'SOURCE001')
        self.assertEqual((row['id'], row['my_sku_use_count'], row['my_sku_remaining'], row['sku_use_limit']),
                         (100, 4, 0, 3))
        for uid in (1, 3):
            row = next(row for row in self.request('GET', '/supply/materials', uid=uid).json()['items']
                       if row['sku'] == 'SOURCE001')
            self.assertEqual((row['my_sku_use_count'], row['my_sku_remaining']), (0, 3))

    def test_only_successful_final_links_of_completed_own_company_jobs_count(self):
        for state in ('failed', 'cancelled'):
            self.history(uid=2, state=state)
        self.history(uid=2, successful=False)
        self.history(uid=7)
        self.history(uid=2, company_id=2)
        self.history(uid=2, link_index=-1, count=1)
        history = self.history(uid=2, count=2)
        # 相同链接内历史重复关联只按一个商品链接计次。
        with self.sessions() as db:
            db.add(SupplyJobMaterial(company_id=1, job_id=history, material_id=100, sku='SOURCE001',
                version_hash='duplicate', link_index=0, successful=True))
            db.commit()
            self.assertEqual(sku_use_counts(db, 1, 2, ['SOURCE001']), {'SOURCE001': 2})
            self.assertEqual(sku_use_counts(db, 1, 2, []), {})
        row = next(row for row in self.request('GET', '/supply/materials', uid=2).json()['items'] if row['id'] == 1)
        self.assertEqual((row['my_sku_use_count'], row['my_sku_remaining']), (2, 1))


if __name__ == '__main__':
    unittest.main()
