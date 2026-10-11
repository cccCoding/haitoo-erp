from datetime import datetime, timedelta
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.models import (Company, MaterialAsset, ProductLibraryOrder, ProductLibraryOrderProduct,
                        ProductLibraryProduct, ProductLibrarySource, ProductTemplate, Role, TemplateGroup, User,
                        UserTemplatePrompt, UserTemplateWhiteImage)
from app.security import create_access_token


class AdminDataTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([Company(id=1, name='一公司'), Company(id=2, name='二公司')])
            db.add(User(id=1, company_id=None, email='super@example.com', name='Super', password_hash='x', role=Role.SUPER_ADMIN))
            for company_id in (1, 2):
                db.add(User(id=company_id+1, company_id=company_id, email=f'{company_id}@example.com',
                            name=f'管理员{company_id}', password_hash='x', role=Role.COMPANY_ADMIN))
                db.add(ProductTemplate(id=company_id, company_id=company_id, name=f'模板{company_id}'))
                db.add(ProductLibrarySource(id=company_id, company_id=company_id, platform='TikTok', site='MY',
                                            shop_name=f'店铺{company_id}', assigned_user_id=company_id+1))
                db.add(ProductLibraryProduct(id=company_id, company_id=company_id, source_id=company_id,
                                             external_product_id=str(company_id), sku='SHARED', template_id=company_id))
                db.add(ProductLibraryOrder(id=company_id, company_id=company_id, source_id=company_id,
                                           order_number=f'订单{company_id}', ordered_at=datetime.utcnow()))
                db.add(ProductLibraryOrderProduct(order_id=company_id, product_id=company_id, quantity=company_id))
                for offset, usage in enumerate(('unused', 'used')):
                    db.add(MaterialAsset(id=company_id*10+offset, company_id=company_id, claimed_by=company_id+1,
                        template_id=company_id, name=f'素材{company_id}', url='/test.jpg', sku=f'C{company_id}-{usage}',
                        usage_status=usage, created_at=datetime.utcnow()))
            db.add(MaterialAsset(id=30, company_id=1, claimed_by=2, template_id=1, name='滞销素材', url='/old.jpg',
                                 sku='OLD', created_at=datetime.utcnow()-timedelta(days=100)))
            db.commit()
            self.super_token = create_access_token(db.get(User, 1))
            self.company_token = create_access_token(db.get(User, 2))

        def override_get_db():
            with self.sessions() as db:
                yield db
        main.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def get(self, path, token=None, **params):
        return self.client.get('/admin/data/'+path, params={'company_id': 1, **params},
                               headers={'Authorization': f'Bearer {token or self.super_token}'})

    def test_filters_and_materials_are_company_scoped(self):
        filters = self.get('filters').json()
        self.assertEqual(filters['templates'], [{'id': 1, 'name': '模板1'}])
        self.assertEqual([item['id'] for item in filters['members']], [2])
        self.assertEqual([item['id'] for item in filters['shops']], [1])
        result = self.get('materials', page_size=1).json()
        self.assertEqual(result['total'], 2)
        self.assertEqual(len(result['items']), 1)
        used = self.get('materials', usage_status='used', template_id=1, creator_id=2).json()
        self.assertEqual([item['id'] for item in used['items']], [11])
        self.assertEqual(self.get('materials', creator_id=3).json()['total'], 0)
        self.assertEqual(self.get('materials', template_id=2).json()['total'], 0)
        self.assertEqual(self.get('materials', company_id=2, usage_status='used').json()['items'][0]['id'], 21)

    def test_material_source_filter_with_pagination_and_company_scope(self):
        with self.sessions() as db:
            for item_id, company_id, source_type, task_id, usage in (
                (40, 1, 'ai_created', None, 'unused'),
                (41, 1, '', 100, 'unused'),
                (42, 1, 'imported', None, 'unused'),
                (43, 1, 'local_upload', None, 'used'),
                (44, 2, 'imported', None, 'unused'),
            ):
                db.add(MaterialAsset(id=item_id, company_id=company_id, claimed_by=company_id+1,
                    template_id=company_id, name=f'素材{item_id}', url='/test.jpg',
                    source_type=source_type, source_task_id=task_id, usage_status=usage))
            db.commit()
        ai = self.get('materials', source_type='ai_created', page_size=1).json()
        self.assertEqual(ai['total'], 2)
        self.assertEqual([item['id'] for item in ai['items']], [41])
        second = self.get('materials', source_type='ai_created', page_size=1, page=2).json()
        self.assertEqual([item['id'] for item in second['items']], [40])
        imported = self.get('materials', source_type='imported', creator_id=2, template_id=1).json()
        self.assertEqual(imported['total'], 1)
        self.assertEqual([item['id'] for item in imported['items']], [42])
        local = self.get('materials', source_type='local_upload').json()
        self.assertEqual({item['id'] for item in local['items']}, {10, 30})
        used = self.get('materials', source_type='local_upload', usage_status='used').json()
        self.assertEqual({item['id'] for item in used['items']}, {11, 43})
        self.assertEqual(self.get('materials', source_type='imported', creator_id=3).json()['total'], 0)
        self.assertEqual(self.get('materials', source_type='imported', company_id=2).json()['items'][0]['id'], 44)
        self.assertEqual(self.get('materials', source_type='').json()['total'], 5)
        all_statuses = self.get('materials', usage_status='all').json()
        self.assertEqual(all_statuses['total'], 7)
        self.assertEqual({item['usage_status'] for item in all_statuses['items']}, {'unused', 'used'})
        all_local = self.get('materials', usage_status='all', source_type='local_upload',
                             creator_id=2, template_id=1, page_size=2).json()
        self.assertEqual(all_local['total'], 4)
        self.assertEqual(len(all_local['items']), 2)
        self.assertEqual({item['id'] for item in self.get('materials', usage_status='all', company_id=2).json()['items']}, {20, 21, 44})
        self.assertEqual(self.get('materials', source_type='invalid').status_code, 422)

    def test_product_statistics_and_order_details_never_cross_companies(self):
        result = self.get('products', sku='SHA', template_id=1).json()
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['sales_quantity'], 1)
        self.assertEqual(result['items'][0]['shop_data'][0]['shop_name'], '店铺1')
        self.assertEqual(self.get('products', source_ids=[2]).json()['total'], 0)
        self.assertEqual(self.get('products', unmatched=True).json()['total'], 0)
        details = self.get('products/1/orders').json()
        self.assertEqual(details['items'][0]['order_number'], '订单1')
        self.assertEqual(details['items'][0]['quantity'], 1)
        self.assertEqual(self.get('products/2/orders').status_code, 404)
        self.assertEqual(self.get('products', company_id=2).json()['items'][0]['sales_quantity'], 2)
        self.assertEqual(self.get('shops').json()[0]['assigned_user_name'], '管理员1')

    def test_templates_include_details_and_only_selected_company(self):
        with self.sessions() as db:
            db.add_all([TemplateGroup(id=1, company_id=1, name='连衣裙'),
                        TemplateGroup(id=2, company_id=2, name='其他公司分类')])
            template = db.get(ProductTemplate, 1)
            template.group_id = 1
            template.product_description = '商品详情'
            template.sku_specifications = {'size': {'options': ['S', 'M']}}
            template.ai_prompts = [{'name': '提示', 'content': '印花要求'}]
            db.add(ProductTemplate(id=3, name='平台模板', is_platform=True))
            db.commit()
        result = self.get('templates').json()
        self.assertEqual([item['id'] for item in result['items']], [1])
        self.assertEqual(result['groups'], [{'id': 1, 'name': '连衣裙'}])
        self.assertEqual(result['items'][0]['product_description'], '商品详情')
        self.assertEqual(result['items'][0]['sku_specifications']['size']['options'], ['S', 'M'])
        self.assertEqual(result['items'][0]['ai_prompts'][0]['content'], '印花要求')
        self.assertEqual([item['id'] for item in self.get('templates', company_id=2).json()['items']], [2])

    def test_categories_reuse_erp_queries(self):
        self.assertEqual(self.get('products', category='stagnant').json()['items'][0]['sku'], 'OLD')
        self.assertEqual(self.get('products', category='new_images', usage_status='used').json()['total'], 1)
        self.assertEqual(self.get('products', category='new_images', creator_id=3).json()['total'], 0)
        for category in ('top7', 'top15', 'top30', 'potential', 'hot', 'booming'):
            with self.subTest(category=category):
                result = self.get('products', category=category)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()['total'], 0)
                self.assertIsNone(result.json()['snapshot_date'])

    def add_creative_resources(self):
        updated = datetime(2026, 10, 11, 1, 0)
        with self.sessions() as db:
            db.add(ProductTemplate(id=3, name='平台模板', is_platform=True,
                                   ai_prompts=[{'name': '模板内置要求', 'content': '不应合并'}]))
            db.add(User(id=4, company_id=1, email='member@example.com', name='员工',
                        password_hash='x', role=Role.MEMBER))
            for item_id, company_id, user_id, template_id, name, content in (
                (1, 1, 2, 1, '自然贴合', '保持布料光影\n保持花朵清晰'),
                (2, 2, 3, 2, '其他公司要求', '保持花朵清晰'),
                (3, 1, 4, 3, '100%清晰', '平台模板要求'),
                (4, 1, 3, 2, '错误关联', '关联其他公司人员和模板'),
                (5, 1, 99, 99, '历史缺失', '缺失的关联'),
            ):
                db.add(UserTemplatePrompt(id=item_id, company_id=company_id, user_id=user_id,
                    template_id=template_id, name=name, content=content, updated_at=updated))
            for item_id, company_id, url in (
                (1, 1, 'https://cdn.invalid/template-white/company/1/a.png'),
                (2, 2, 'https://cdn.invalid/template-white/company/2/b.png'),
                (3, 1, 'https://foreign.invalid/a.png'),
            ):
                db.add(UserTemplateWhiteImage(id=item_id, company_id=company_id, user_id=company_id+1,
                    template_id=company_id, name=f'白底图{item_id}', image_url=url, updated_at=updated))
            db.commit()

    def test_creative_resources_filters_search_pagination_and_names(self):
        self.add_creative_resources()
        filters = self.get('creative-resources/filters').json()
        self.assertEqual([item['id'] for item in filters['templates']], [1, 3])
        self.assertEqual([item['id'] for item in filters['members']], [2, 4])
        result = self.get('creative-resources', page_size=2).json()
        self.assertEqual(result['total'], 4)
        self.assertEqual([item['id'] for item in result['items']], [5, 4])
        self.assertEqual([item['id'] for item in self.get('creative-resources', page_size=2, page=2).json()['items']], [3, 1])
        self.assertEqual(self.get('creative-resources', page=10).json()['items'], [])
        match = self.get('creative-resources', query=' 花朵 ', creator_id=2, template_id=1).json()['items']
        self.assertEqual([item['id'] for item in match], [1])
        self.assertEqual(match[0]['user_name'], '管理员1')
        self.assertEqual(match[0]['template_name'], '模板1')
        self.assertIsInstance(match[0]['updated_at'], int)
        platform = self.get('creative-resources', creator_id=4, template_id=3).json()['items'][0]
        self.assertEqual(platform['template_name'], '平台模板')
        self.assertEqual(self.get('creative-resources', query='%').json()['total'], 1)
        self.assertEqual(self.get('creative-resources', query='不应合并').json()['total'], 0)
        white = self.get('creative-resources', resource_type='white-images', query='白底图1').json()
        self.assertEqual([item['id'] for item in white['items']], [1])
        self.assertIn('image_url', white['items'][0])
        self.assertEqual(self.get('creative-resources', company_id=2).json()['total'], 1)
        self.assertEqual(self.get('creative-resources', resource_type='invalid').status_code, 422)
        self.assertEqual(self.get('creative-resources', page_size=201).status_code, 422)

    def test_creative_resources_missing_and_foreign_associations_do_not_leak(self):
        self.add_creative_resources()
        result = self.get('creative-resources').json()['items']
        for item in result[:2]:
            self.assertIsNone(item['user_name'])
            self.assertIsNone(item['template_name'])
        self.assertEqual(self.get('creative-resources', creator_id=3, template_id=2).json()['total'], 1)
        self.assertEqual(self.get('creative-resources', creator_id=999).json()['total'], 0)
        with self.sessions() as db:
            item = db.get(UserTemplatePrompt, 1)
            item.updated_at = datetime(2026, 10, 12)
            db.commit()
        self.assertEqual(self.get('creative-resources').json()['items'][0]['id'], 1)

    def test_white_image_sizes_require_owned_ids_and_limit_batches(self):
        self.add_creative_resources()
        path = 'creative-resources/white-image-sizes'
        with patch.object(main, 'read_white_image_sizes', return_value=[
            {'id': 1, 'size_bytes': 2048, 'status': 'available'},
        ]) as read:
            response = self.get(path, image_ids=[1])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['items'][0]['size_bytes'], 2048)
            read.assert_called_once_with(1, [(1, 'https://cdn.invalid/template-white/company/1/a.png')])
            read.reset_mock()
            for ids in ([2], [1, 2], [999]):
                self.assertEqual(self.get(path, image_ids=ids).status_code, 404)
            self.assertEqual(self.get(path, image_ids=[0]).status_code, 422)
            self.assertEqual(self.get(path, image_ids=[1]*21).status_code, 422)
            self.assertEqual(self.get(path).status_code, 422)
            self.assertEqual(self.get(path, token=self.company_token, image_ids=[1]).status_code, 403)
            self.assertEqual(self.get(path, company_id=999, image_ids=[1]).status_code, 404)
            read.assert_not_called()
        for method in ('post', 'put', 'delete'):
            self.assertEqual(getattr(self.client, method)('/admin/data/'+path,
                params={'company_id': 1, 'image_ids': 1},
                headers={'Authorization': f'Bearer {self.super_token}'}).status_code, 405)

    def test_access_validation_and_read_only_routes(self):
        for path in ('filters', 'templates', 'materials', 'products', 'shops', 'products/1/orders',
                     'creative-resources', 'creative-resources/filters'):
            with self.subTest(path=path):
                self.assertEqual(self.get(path, token=self.company_token).status_code, 403)
                self.assertEqual(self.get(path, company_id=999).status_code, 404)
                self.assertEqual(self.client.get('/admin/data/'+path, params={'company_id': 1}).status_code, 403)
                for method in ('post', 'put', 'delete'):
                    response = getattr(self.client, method)('/admin/data/'+path, params={'company_id': 1},
                        headers={'Authorization': f'Bearer {self.super_token}'})
                    self.assertEqual(response.status_code, 405)
        self.assertEqual(self.get('materials', usage_status='invalid').status_code, 422)
        self.assertEqual(self.get('products', category='invalid').status_code, 422)
        self.assertEqual(self.get('products', template_id=1, unmatched=True).status_code, 400)
        self.assertEqual(self.get('materials', page_size=0).status_code, 422)


if __name__ == '__main__':
    unittest.main()
