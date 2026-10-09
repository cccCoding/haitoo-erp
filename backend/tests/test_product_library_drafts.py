from unittest import TestCase
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.credentials import encrypt_secret, decrypt_secret
from app.database import Base, get_db
from app.models import Company, MaterialAsset, OperatorGroup, ProductDraft, ProductLibraryProduct, ProductLibrarySource, ProductTemplate, Role, User, UserAIProviderCredential
from app.security import create_access_token


class ProductLibraryDraftTests(TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([Company(id=1, name='A'), Company(id=2, name='B'),
                OperatorGroup(id=1, company_id=1, name='Team', leader_user_id=2),
                User(id=1, company_id=1, name='Admin', email='a@example.com', password_hash='x', role=Role.COMPANY_ADMIN),
                User(id=2, company_id=1, name='Leader', email='l@example.com', password_hash='x', role=Role.TEAM_LEADER, group_id=1),
                User(id=3, company_id=1, name='Member', email='m@example.com', password_hash='x', role=Role.MEMBER, group_id=1),
                User(id=4, company_id=1, name='Other', email='o@example.com', password_hash='x', role=Role.MEMBER),
                User(id=5, company_id=2, name='Foreign Admin', email='foreign@example.com', password_hash='x', role=Role.COMPANY_ADMIN),
                ProductTemplate(id=1, company_id=1, name='M01', title_template='title rules', product_description='description', size_chart_url='https://img/size'),
                ProductTemplate(id=2, company_id=1, name='M02'),
                ProductLibrarySource(id=1, company_id=1, platform='TikTok', site='MY', shop_name='Shop', assigned_user_id=3),
                ProductLibrarySource(id=2, company_id=1, platform='TikTok', site='MY', shop_name='Other', assigned_user_id=4),
                ProductLibrarySource(id=3, company_id=2, platform='TikTok', site='MY', shop_name='Foreign'),
            ])
            for i in range(1, 12):
                db.add(MaterialAsset(id=i, company_id=1, template_id=1, claimed_by=3, url=f'https://img/{i}', sku=f'M01AA{i:06d}', name=f'file{i}'))
            for i, source in ((1, 1), (2, 2), (3, 3)):
                db.add(ProductLibraryProduct(id=i, company_id=2 if i == 3 else 1, source_id=source, template_id=1,
                    external_product_id=str(i), sku=f'PRODUCT-{i}', image_url=f'https://product/{i}', title='Original title ' * 3))
            for user_id in (1, 2, 3):
                db.add(UserAIProviderCredential(company_id=1, user_id=user_id, provider='deepseek',
                    secret_encrypted=encrypt_secret(f'title-key-{user_id}')))
            db.commit()
        def override_db():
            with self.sessions() as db:
                yield db
        main.app.dependency_overrides[get_db] = override_db
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def headers(self, user=3):
        with self.sessions() as db:
            return {'Authorization': 'Bearer ' + create_access_token(db.get(User, user))}

    def source(self, i, kind='material'):
        return {'source_type': kind, 'id': i}

    def single(self, sources, user=3, **extra):
        return self.client.post('/drafts/from-product-library', headers=self.headers(user), json={
            'template_id': 1, 'title': 'Draft title ' * 3, 'sources': sources, **extra})

    def batch(self, groups, user=3):
        return self.client.post('/drafts/from-product-library/batch', headers=self.headers(user), json={
            'template_id': 1, 'groups': [{'sources': [self.source(i) for i in ids], 'title': 'Group title ' * 3} for ids in groups]})

    def count(self):
        with self.sessions() as db:
            return db.scalar(select(func.count()).select_from(ProductDraft))

    def test_material_order_usage_description_and_reuse(self):
        result = self.single([self.source(2), self.source(1)], product_description=' edited ')
        self.assertEqual(result.status_code, 200, result.text)
        draft = result.json()
        self.assertEqual(draft['image_urls'], ['https://img/2', 'https://img/1'])
        self.assertEqual(draft['product_description'], 'edited')
        self.assertEqual(draft['created_by'], 3)
        self.assertEqual(draft['workflow_stage'], 'pending')
        self.assertEqual(draft['size_chart_url'], 'https://img/size')
        self.assertIsNone(draft['shop_id'])
        self.assertEqual(self.batch([list(range(1, 6))]).status_code, 200)
        self.assertEqual(self.batch([list(range(1, 6))]).status_code, 200)
        with self.sessions() as db:
            self.assertTrue(all(db.get(MaterialAsset, i).usage_status == 'used' for i in range(1, 6)))
            self.assertEqual(db.get(MaterialAsset, 6).usage_status, 'unused')

    def test_product_permissions_and_no_material_mutation(self):
        self.assertEqual(self.single([self.source(1, 'product')]).status_code, 200)
        self.assertEqual(self.single([self.source(1, 'product')], user=2).status_code, 200)
        for user, i in ((3, 2), (2, 2), (1, 3), (3, 99)):
            self.assertEqual(self.single([self.source(i, 'product')], user=user).status_code, 400)
        with self.sessions() as db:
            self.assertEqual(db.get(MaterialAsset, 1).usage_status, 'unused')

    def test_material_visibility(self):
        self.assertEqual(self.single([self.source(1)], user=2).status_code, 200)
        self.assertEqual(self.single([self.source(2)], user=4).status_code, 400)
        with self.sessions() as db:
            db.get(MaterialAsset, 2).company_id = 2
            db.commit()
        self.assertEqual(self.single([self.source(2)], user=1).status_code, 400)

    def test_batch_validation_is_atomic(self):
        with self.sessions() as db:
            db.get(MaterialAsset, 10).template_id = 2
            db.commit()
        self.assertEqual(self.batch([list(range(1, 6)), list(range(6, 11))]).status_code, 400)
        self.assertEqual(self.count(), 0)
        with self.sessions() as db:
            self.assertTrue(all(db.get(MaterialAsset, i).usage_status == 'unused' for i in range(1, 12)))
        self.assertEqual(self.batch([list(range(1, 6)), list(range(1, 6))]).status_code, 400)
        self.assertEqual(self.count(), 0)

    def test_missing_fields_duplicate_sku_and_title_validation(self):
        for field, value in (('sku', ''), ('url', ''), ('template_id', None)):
            with self.sessions() as db:
                asset = db.get(MaterialAsset, 1)
                old = getattr(asset, field)
                setattr(asset, field, value); db.commit()
            self.assertIn(self.single([self.source(1)]).status_code, (400, 404))
            with self.sessions() as db:
                setattr(db.get(MaterialAsset, 1), field, old); db.commit()
        with self.sessions() as db:
            db.get(ProductLibraryProduct, 1).sku = db.get(MaterialAsset, 1).sku
            db.commit()
        self.assertEqual(self.single([self.source(1), self.source(1, 'product')]).status_code, 400)
        self.assertEqual(self.single([self.source(1), self.source(1)]).status_code, 400)
        for title in ('', 'short', ' ' * 25, 'x' * 256):
            self.assertEqual(self.single([self.source(1)], title=title).status_code, 422)
        self.assertEqual(self.count(), 0)

    def test_ai_reads_authorized_source_image(self):
        with patch.object(main, 'generate_draft_title', new_callable=AsyncMock, return_value='Generated title ' * 3) as generate:
            result = self.client.post('/product-library/generate-draft-title', headers=self.headers(2), json=self.source(1, 'product'))
            self.assertEqual(result.status_code, 200, result.text)
            generate.assert_awaited_once_with('title rules', 'https://product/1', 'title-key-2', additional_requirements='')
            result = self.client.post('/product-library/generate-draft-title', headers=self.headers(3), json=self.source(2, 'product'))
            self.assertEqual(result.status_code, 400)
            self.assertEqual(generate.await_count, 1)

    def test_material_batch_reuses_used_assets_with_existing_permissions(self):
        with self.sessions() as db:
            db.get(MaterialAsset, 1).usage_status = 'used'
            db.commit()
        payload = {'template_id': 1, 'groups': [
            {'material_asset_ids': list(range(1, 6)), 'title': 'Floral Long Sleeve Everyday Dress'}]}
        for user in (4, 5):
            result = self.client.post('/drafts/from-material-assets/batch', headers=self.headers(user), json=payload)
            self.assertIn(result.status_code, (400, 404), result.text)
        self.assertEqual(self.count(), 0)
        for _ in range(2):
            result = self.client.post('/drafts/from-material-assets/batch', headers=self.headers(), json=payload)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['total'], 1)
            self.assertEqual(len(result.json()['drafts'][0]['sku_items']), 5)
        self.assertEqual(self.count(), 2)
        with self.sessions() as db:
            self.assertTrue(all(db.get(MaterialAsset, i).usage_status == 'used' for i in range(1, 6)))
            self.assertEqual(db.get(MaterialAsset, 6).usage_status, 'unused')
        payload['groups'].append(payload['groups'][0])
        result = self.client.post('/drafts/from-material-assets/batch', headers=self.headers(), json=payload)
        self.assertEqual(result.status_code, 400)
        self.assertEqual(self.count(), 2)

    def title_request(self, kind, user=3):
        if kind == 'product':
            return self.client.post('/product-library/generate-draft-title', headers=self.headers(user), json=self.source(1, 'product'))
        return self.client.post('/templates/1/generate-draft-title', headers=self.headers(user), json={'image_url': 'https://img/1'})

    def test_title_requirements_are_optional_for_both_endpoints(self):
        for requirements in (None, '', '   '):
            with self.sessions() as db:
                db.get(ProductTemplate, 1).title_template = requirements
                db.commit()
            with patch.object(main, 'generate_draft_title', new_callable=AsyncMock,
                              return_value='Floral Long Sleeve Everyday Dress') as generate:
                for kind, image in (('product', 'https://product/1'), ('material', 'https://img/1')):
                    result = self.title_request(kind)
                    self.assertEqual(result.status_code, 200, result.text)
                    generate.assert_awaited_with(requirements or '', image, 'title-key-3', additional_requirements='')

    def test_title_endpoints_use_callers_key_and_do_not_fallback(self):
        with patch.object(main, 'generate_draft_title', new_callable=AsyncMock, return_value='Floral Long Sleeve Everyday Dress') as generate:
            for kind, image in (('product', 'https://product/1'), ('material', 'https://img/1')):
                for user in (1, 3):
                    result = self.title_request(kind, user)
                    self.assertEqual(result.status_code, 200, result.text)
                    generate.assert_awaited_with('title rules', image, f'title-key-{user}', additional_requirements='')
            with self.sessions() as db:
                credential = db.scalar(select(UserAIProviderCredential).where(UserAIProviderCredential.user_id == 3))
                # 同 user_id 但公司不匹配的记录不能被采用。
                credential.company_id = 2
                db.commit()
            generate.reset_mock()
            for kind in ('product', 'material'):
                result = self.title_request(kind)
                self.assertEqual(result.status_code, 400)
                self.assertIn('个人 DeepSeek', result.json()['detail'])
            generate.assert_not_awaited()
            for kind in ('product', 'material'):
                self.assertIn(self.title_request(kind, 5).status_code, (400, 404))

    def test_template_and_temporary_requirements_are_separate(self):
        result = self.client.put('/templates/1', headers=self.headers(1), json={
            'title_template': 'Place product category first',
        })
        self.assertEqual(result.status_code, 200, result.text)
        self.assertNotIn('confirmed_product_info', result.json())
        with patch.object(main, 'generate_draft_title', new_callable=AsyncMock, return_value='Floral Nursing Dress With Hidden Zipper') as generate:
            for url, payload in (('/product-library/generate-draft-title', self.source(1, 'product')),
                                 ('/templates/1/generate-draft-title', {'image_url': 'https://img/1'})):
                response = self.client.post(url, headers=self.headers(), json={**payload, 'additional_requirements': 'Emphasize blue flowers'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(generate.call_args.kwargs, {
                    'additional_requirements': 'Emphasize blue flowers',
                })
                self.assertEqual(self.client.post(url, headers=self.headers(), json={**payload, 'additional_requirements': 'x' * 1001}).status_code, 422)
                # 旧客户端不提供补充要求仍可调用，且不会继承上一次请求。
                self.assertEqual(self.client.post(url, headers=self.headers(), json=payload).status_code, 200)
                self.assertEqual(generate.call_args.kwargs['additional_requirements'], '')
        with self.sessions() as db:
            template = db.get(ProductTemplate, 1)
            self.assertEqual(template.title_template, 'Place product category first')

    def test_company_admin_manages_personal_title_keys(self):
        for user_id in (1, 3):
            url = f'/members/{user_id}/ai-provider-credentials/deepseek'
            result = self.client.put(url, headers=self.headers(1), json={'api_key': 'new-personal-title-key'})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertNotIn('new-personal-title-key', result.text)
            with self.sessions() as db:
                credential = db.scalar(select(UserAIProviderCredential).where(UserAIProviderCredential.user_id == user_id))
                self.assertEqual(decrypt_secret(credential.secret_encrypted), 'new-personal-title-key')
                self.assertNotIn('new-personal-title-key', credential.secret_encrypted)
            rows = self.client.get('/members', headers=self.headers(1)).json()
            row = next(row for row in rows if row['id'] == user_id)
            self.assertTrue(row['ai_provider_credentials']['deepseek'])
            self.assertIn('...', row['ai_provider_credential_previews']['deepseek'])
            self.assertNotIn('new-personal-title-key', str(rows))
            self.assertEqual(self.client.put(url, headers=self.headers(3), json={'api_key': 'bad'}).status_code, 403)
            self.assertEqual(self.client.delete(url, headers=self.headers(3)).status_code, 403)
            self.assertEqual(self.client.put(url, headers=self.headers(5), json={'api_key': 'bad'}).status_code, 404)
            self.assertEqual(self.client.delete(url, headers=self.headers(5)).status_code, 404)
            self.assertEqual(self.client.delete(url, headers=self.headers(1)).status_code, 200)
            self.assertEqual(self.title_request('product', user_id).status_code, 400)
        providers = self.client.get('/ai-providers', headers=self.headers(1)).json()
        self.assertTrue(all(row['provider'] != 'deepseek' for row in providers))

    def test_title_provider_errors_are_reported(self):
        with patch.object(main, 'generate_draft_title', new_callable=AsyncMock, side_effect=main.ProviderError('DeepSeek 未完整生成标题')):
            for kind in ('product', 'material'):
                response = self.title_request(kind)
                self.assertEqual(response.status_code, 502)
                self.assertIn('未完整生成', response.json()['detail'])

    def test_product_batch_reuse_and_template_description(self):
        with self.sessions() as db:
            for i in range(4, 8):
                db.add(ProductLibraryProduct(id=i, company_id=1, source_id=1, template_id=1,
                    external_product_id=str(i), sku=f'PRODUCT-{i}', image_url=f'https://product/{i}', title='Original title ' * 3))
            db.commit()
        payload = {'template_id': 1, 'groups': [{'title': 'Batch product title ' * 2,
            'sources': [self.source(i, 'product') for i in (1, 4, 5, 6, 7)]}]}
        for _ in range(2):
            result = self.client.post('/drafts/from-product-library/batch', headers=self.headers(), json=payload)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['drafts'][0]['product_description'], 'description')
        with self.sessions() as db:
            self.assertTrue(all(db.get(MaterialAsset, i).usage_status == 'unused' for i in range(1, 12)))

    def test_commit_failure_rolls_back_draft_and_usage(self):
        with patch('sqlalchemy.orm.Session.commit', side_effect=RuntimeError('database unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
                self.batch([list(range(1, 6))])
        self.assertEqual(self.count(), 0)
        with self.sessions() as db:
            self.assertTrue(all(db.get(MaterialAsset, i).usage_status == 'unused' for i in range(1, 6)))

    def test_list_source_metadata_and_empty_material_title(self):
        result = self.client.get('/product-library/new-images', headers=self.headers()).json()
        self.assertEqual(result['total'], 11)
        self.assertEqual(result['items'][0]['source_type'], 'material')
        self.assertEqual(result['items'][0]['template_id'], 1)
        self.assertEqual(result['items'][0]['title'], '')
        result = self.client.get('/product-library', headers=self.headers()).json()
        self.assertEqual(result['items'][0]['source_type'], 'product')
        self.assertEqual(result['items'][0]['template_id'], 1)


    def set_templates(self, *, user=1, template_id=2, **selection):
        return self.client.post('/product-library/templates/batch', headers=self.headers(user),
            json={'template_id': template_id, **selection})

    def test_material_template_batch_preserves_sku_and_usage(self):
        with self.sessions() as db:
            db.get(MaterialAsset, 1).usage_status = 'used'
            db.commit()
            before = {i: (db.get(MaterialAsset, i).sku, db.get(MaterialAsset, i).usage_status) for i in (1, 2)}
        result = self.set_templates(material_asset_ids=[1, 2])
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['updated'], 2)
        with self.sessions() as db:
            for i in (1, 2):
                asset = db.get(MaterialAsset, i)
                self.assertEqual(asset.template_id, 2)
                self.assertEqual((asset.sku, asset.usage_status), before[i])
            self.assertEqual(db.get(ProductLibraryProduct, 1).template_id, 1)
        items = self.client.get('/product-library/new-images', headers=self.headers()).json()['items']
        changed = [item for item in items if item['id'] in (1, 2)]
        self.assertTrue(all(item['template_id'] == 2 and item['template'] == 'M02' for item in changed))

    def test_template_batch_supports_products_and_mixed_record_ids(self):
        result = self.set_templates(product_ids=[1], material_asset_ids=[1])
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['updated'], 2)
        with self.sessions() as db:
            self.assertEqual(db.get(ProductLibraryProduct, 1).template_id, 2)
            self.assertEqual(db.get(MaterialAsset, 1).template_id, 2)
        result = self.set_templates(product_ids=[1], template_id=1)
        self.assertEqual(result.status_code, 200)
        with self.sessions() as db:
            self.assertEqual(db.get(ProductLibraryProduct, 1).template_id, 1)
            self.assertEqual(db.get(MaterialAsset, 1).template_id, 2)

    def test_template_batch_permissions_and_atomic_validation(self):
        for user in (2, 3, 4):
            self.assertEqual(self.set_templates(user=user, material_asset_ids=[1]).status_code, 403)
            self.assertEqual(self.set_templates(user=user, product_ids=[1]).status_code, 403)
        with self.sessions() as db:
            db.get(MaterialAsset, 2).company_id = 2
            db.add(ProductTemplate(id=3, company_id=2, name='Foreign'))
            db.commit()
        for selection in ({'product_ids':[1], 'material_asset_ids':[2]},
                          {'material_asset_ids':[1,99]}, {'product_ids':[1,3]}):
            self.assertEqual(self.set_templates(**selection).status_code, 404)
        self.assertEqual(self.set_templates(material_asset_ids=[1], template_id=3).status_code, 404)
        with self.sessions() as db:
            self.assertEqual(db.get(ProductLibraryProduct, 1).template_id, 1)
            self.assertEqual(db.get(MaterialAsset, 1).template_id, 1)

    def test_template_batch_selection_validation(self):
        for selection in ({}, {'material_asset_ids':[]}, {'material_asset_ids':[-1]},
                          {'product_ids':list(range(1,1002)), 'material_asset_ids':list(range(1,1002))}):
            self.assertEqual(self.set_templates(**selection).status_code, 422)
        self.assertEqual(self.set_templates(material_asset_ids=[1,1]).status_code, 400)
        self.assertEqual(self.set_templates(product_ids=[1,1]).status_code, 400)
        with self.sessions() as db:
            self.assertEqual(db.get(MaterialAsset, 1).template_id, 1)
