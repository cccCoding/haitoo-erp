from datetime import datetime, timedelta
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.models import (Company, MaterialAsset, ProductLibraryOrder, ProductLibraryOrderProduct,
                        ProductLibraryProduct, ProductLibrarySource, ProductTemplate, Role, TemplateGroup, User)
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

    def test_access_validation_and_read_only_routes(self):
        for path in ('filters', 'templates', 'materials', 'products', 'shops', 'products/1/orders'):
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
