"""采集的真实 HTTP 权限、事务、来源与幂等行为。"""
from datetime import datetime, timedelta, date
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.models import (Company, CrossCompanyCollectionBatch, CrossCompanyCollectionItem,
    CrossCompanyCollectionPermissionLog, MaterialAsset, MaterialStyle, ProductLibraryProduct, ProductLibrarySource,
    ProductLibraryOrder, ProductLibraryOrderProduct, ProductTemplate, Role, User)
from app.security import create_access_token


class CrossCompanyCollectionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([Company(id=1,name='目标公司',cross_company_collect_enabled=True),
                Company(id=2,name='来源公司'),Company(id=3,name='停用公司',is_active=False)])
            for uid, role, company in [(1,Role.COMPANY_ADMIN,1),(2,Role.MEMBER,1),(3,Role.TEAM_LEADER,1),(4,Role.SUPER_ADMIN,None),(5,Role.COMPANY_ADMIN,2)]:
                db.add(User(id=uid,company_id=company,email=f'{uid}@test.example',name=f'用户{uid}',user_code='AA' if uid==1 else f'A{uid}',role=role,password_hash='x'))
            db.add_all([ProductTemplate(id=1,company_id=1,name='Y1'),ProductTemplate(id=2,company_id=2,name='Y2'),
                ProductTemplate(id=3,name='P1',is_platform=True),
                MaterialAsset(id=1,company_id=2,template_id=2,claimed_by=5,url='https://img.example/a',name='原素材',sku='ORIGINAL',usage_status='used'),
                MaterialAsset(id=2,company_id=2,template_id=2,claimed_by=5,url='https://img.example/b',name='新素材',sku='SECOND'),
                MaterialAsset(id=3,company_id=1,template_id=1,claimed_by=1,url='https://img.example/local',name='本公司',sku='LOCAL')])
            for cid, quantity in [(1,99),(2,7)]:
                db.add(ProductLibrarySource(id=cid,company_id=cid,platform='TikTok',site='MY',shop_name=f'私有店铺{cid}'))
                db.add(ProductLibraryProduct(id=cid,company_id=cid,source_id=cid,external_product_id=str(cid),sku='SHARED',title='产品标题',image_url='https://img.example/product',template_id=cid))
                db.add(ProductLibraryOrder(id=cid,company_id=cid,source_id=cid,order_number=f'私有订单{cid}',ordered_at=datetime.utcnow()))
                db.add(ProductLibraryOrderProduct(order_id=cid,product_id=cid,quantity=quantity))
            db.commit()
            self.tokens = {uid:create_access_token(db.get(User,uid)) for uid in range(1,6)}
        def override():
            with self.sessions() as db:
                yield db
        main.app.dependency_overrides[get_db] = override
        self.client = TestClient(main.app)
        from tests.image_file_helpers import index_urls
        def copied(db, target, source, url):
            return index_urls(db,target,[url])[0]
        self.enterContext(patch("app.image_files.ingest_cross_url",side_effect=copied))

    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def headers(self, uid=1, key='request-1'):
        return {'Authorization':f'Bearer {self.tokens[uid]}','Idempotency-Key':key}

    def collect(self, ids=None, uid=1, key='request-1', **extra):
        return self.client.post('/cross-company-collection/collect',headers=self.headers(uid,key),json={
            'source_company_id':2,'source_library':'material','record_ids':ids or [1], 'template_id':1,**extra})

    def listing(self, **params):
        return self.client.get('/cross-company-collection/items',headers=self.headers(),params={'source_company_id':2,**params})

    def test_permissions_and_immediate_revocation(self):
        for uid in (2,3,4,5):
            self.assertEqual(self.collect(uid=uid).status_code,403)
            self.assertEqual(self.client.get('/cross-company-collection/companies',headers=self.headers(uid)).status_code,403)
            self.assertEqual(self.client.get('/cross-company-collection/capability',headers=self.headers(uid)).json(),{'enabled':False})
        self.assertEqual(self.client.get('/cross-company-collection/companies',headers=self.headers()).json(),[{'id':2,'name':'来源公司'}])
        self.assertEqual(self.collect().status_code,200)
        path='/admin/companies/1/cross-company-collection'
        self.assertEqual(self.client.put(path,headers=self.headers(),json={'enabled':False}).status_code,403)
        self.assertEqual(self.client.put(path,headers=self.headers(4),json={'enabled':False}).status_code,200)
        self.assertEqual(self.collect(key='next').status_code,403)
        self.assertEqual(self.listing().status_code,403)
        self.assertEqual(self.client.get('/cross-company-collection/history',headers=self.headers()).json()['total'],1)
        with self.sessions() as db:
            log=db.scalar(select(CrossCompanyCollectionPermissionLog))
            self.assertTrue(log.previous_enabled);self.assertFalse(log.enabled);self.assertEqual(log.changed_by,4)

    def test_scope_and_field_whitelist(self):
        self.assertEqual(self.listing(template_id=1).status_code,404)
        self.assertEqual(self.listing(source_company_id=1).status_code,404)
        self.assertEqual(self.listing(source_company_id=3).status_code,404)
        row=self.listing(source_library='product').json()['items'][0]
        self.assertEqual(row['sales_quantity'],7)
        self.assertEqual(row['id'],2)
        self.assertFalse({'shop_data','order_count','created_by_name','material_created_by_name'} & row.keys())
        material=self.listing().json()['items'][0]
        self.assertNotIn('claimed_by',material);self.assertNotIn('source_task_id',material)
        self.assertEqual(self.collect([3]).status_code,400)
        self.assertEqual(self.collect(template_id=2).status_code,404)
        self.assertEqual(self.collect(template_id=3).status_code,404)
        self.assertEqual(self.collect(company_id=2).status_code,422)
        self.assertEqual(self.collect(urls=['https://evil.example']).status_code,422)
        with self.sessions() as db:
            db.add(Company(id=4,name='新公司'));db.commit()
        self.assertEqual(len(self.client.get('/cross-company-collection/companies',headers=self.headers()).json()),2)

    def test_material_sku_provenance_idempotency_and_duplicates(self):
        with self.sessions() as db:
            style=MaterialStyle(company_id=2,template_id=2,name='来源公司风格',created_by=5,source_white_image_id=100)
            db.add(style);db.flush()
            db.get(MaterialAsset,1).style_id=style.id
            db.commit()
        response=self.collect([1,1,2]);self.assertEqual(response.status_code,200,response.text)
        result=response.json();self.assertEqual(result['collected'],2)
        self.assertEqual(self.collect([2,1]).json(),result)
        self.assertEqual(self.collect([1]).status_code,409)
        self.assertEqual(self.collect(key='new').status_code,409)
        self.assertTrue(all(r['already_collected'] for r in self.listing().json()['items']))
        repeated=self.collect(key='repeat',allow_recollect=True)
        self.assertEqual(repeated.status_code,200)
        with self.sessions() as db:
            assets=list(db.scalars(select(MaterialAsset).where(MaterialAsset.source_type=='cross_company')))
            self.assertEqual(len(assets),3);self.assertEqual(len({a.sku for a in assets}),3)
            for a in assets:
                self.assertTrue(a.sku.startswith('Y1AA'));self.assertEqual(a.template_id,1)
                self.assertEqual(a.company_id,1);self.assertEqual(a.claimed_by,1);self.assertEqual(a.usage_status,'unused')
                self.assertIsNone(a.source_task_id)
                self.assertIsNone(a.style_id)
            self.assertEqual(db.get(MaterialAsset,1).usage_status,'used')
            item=db.scalar(select(CrossCompanyCollectionItem));self.assertEqual(item.source_sku,'ORIGINAL')
        listed=self.client.get('/material-assets',headers=self.headers(),params={'source_type':'cross_company','usage_status':'all'}).json()
        self.assertEqual(listed['total'],3);self.assertEqual(listed['items'][0]['collection_source']['source_company_name'],'来源公司')

    def test_product_collection_and_deleted_source_history(self):
        response=self.collect([2],source_library='product');self.assertEqual(response.status_code,200,response.text)
        asset_id=response.json()['material_asset_ids'][0]
        with self.sessions() as db:
            asset=db.get(MaterialAsset,asset_id);self.assertEqual(asset.url,'https://img.example/product')
            db.delete(db.get(ProductLibraryProduct,2));db.delete(asset);db.commit()
        history=self.client.get('/cross-company-collection/history',headers=self.headers()).json()
        self.assertEqual(history['total'],1);self.assertEqual(history['items'][0]['source_sku'],'SHARED')
        self.assertEqual(self.collect([2],key='missing',source_library='product').status_code,400)

    def test_history_target_template_filter_and_company_scope(self):
        with self.sessions() as db:
            db.add(ProductTemplate(id=4,company_id=1,name='Y3'))
            db.commit()
        self.assertEqual(self.collect().status_code,200)
        self.assertEqual(self.collect([2],key='second-template',template_id=4).status_code,200)
        path='/cross-company-collection/history'
        first=self.client.get(path,headers=self.headers(),params={'template_id':1}).json()
        second=self.client.get(path,headers=self.headers(),params={'template_id':4,'page_size':1}).json()
        self.assertEqual(first['total'],1);self.assertEqual(first['items'][0]['template_id'],1)
        self.assertEqual(second['total'],1);self.assertEqual(second['items'][0]['template_id'],4)
        self.assertEqual(self.client.get(path,headers=self.headers()).json()['total'],2)
        for template_id in (2,3,999):
            self.assertEqual(self.client.get(path,headers=self.headers(),params={'template_id':template_id}).status_code,404)
        self.assertEqual(self.client.get(path,headers=self.headers(),params={'template_id':0}).status_code,422)
        self.assertEqual(self.client.get(path,headers=self.headers(5),params={'template_id':1}).status_code,404)

    def test_rankings_filters_and_material_draft(self):
        from app.product_library_rankings import create_daily_snapshot
        with self.sessions() as db:
            db.get(ProductLibraryOrder,2).ordered_at=datetime.utcnow()-timedelta(days=1)
            db.commit()
            create_daily_snapshot(db,2,date.today())
        result=self.listing(source_library='product',category='top7',sku='SH',template_id=2)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['items'][0]['sales_quantity'],7)
        self.assertIsNotNone(result.json()['snapshot_date'])
        self.assertEqual(self.listing(source_library='product',category='top7',sku='OTHER').json()['total'],0)
        assets=self.collect().json()['material_asset_ids']
        draft=self.client.post('/drafts/from-material-assets',headers=self.headers(),json={
            'template_id':1,'material_asset_ids':assets,'title':'Floral Long Sleeve Everyday Dress'})
        self.assertEqual(draft.status_code,200,draft.text)
        with self.sessions() as db:
            self.assertEqual(db.get(MaterialAsset,assets[0]).usage_status,'used')

    def test_transaction_rollback_and_invalid_urls(self):
        original=main.add_material_asset_with_sku
        counter=[0]
        def fail_second(*args,**kwargs):
            counter[0]+=1
            if counter[0]==2: raise RuntimeError('模拟写入失败')
            return original(*args,**kwargs)
        with patch.object(main,'add_material_asset_with_sku',side_effect=fail_second):
            with self.assertRaises(RuntimeError): self.collect([1,2])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CrossCompanyCollectionBatch)),0)
            self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset)),3)
            db.get(MaterialAsset,2).url='javascript:bad';db.commit()
        response=self.collect([1,2]);self.assertEqual(response.status_code,400)
        self.assertIn('2',response.json()['detail'])
        self.assertEqual(self.collect([1,999]).status_code,400)

    def test_history_matching_ignores_url_and_survives_asset_deletion(self):
        with self.sessions() as db:
            db.get(MaterialAsset,3).url='https://img.example/a';db.commit()
        first=[r for r in self.listing().json()['items'] if r['id']==1][0]
        self.assertFalse(first['already_collected'])
        result=self.collect().json()
        self.client.delete(f"/material-assets/{result['material_asset_ids'][0]}",headers=self.headers())
        with self.sessions() as db:
            db.get(MaterialAsset,1).url='https://img.example/changed';db.commit()
        self.assertTrue(next(r for r in self.listing().json()['items'] if r['id']==1)['already_collected'])
        self.assertEqual(self.collect(key='after-delete').status_code,409)
        self.assertEqual(self.collect(key='after-delete-confirmed',allow_recollect=True).status_code,200)

    def add_history(self, db, *, company_id=1, source_company_id=2, sku='ORIGINAL', source_library='material'):
        batch=CrossCompanyCollectionBatch(company_id=company_id,created_by=1,template_id=1,
            request_key=f'history-{company_id}-{source_company_id}-{sku}',request_hash='historic',result={})
        db.add(batch);db.flush()
        item=CrossCompanyCollectionItem(batch_id=batch.id,company_id=company_id,material_asset_id=9999,
            source_company_id=source_company_id,source_company_name='历史来源',source_library=source_library,
            source_record_id=9999,source_sku=sku,source_url='https://img.example/historic',source_name='历史图片')
        db.add(item);db.flush()
        return item

    def test_collection_status_filters_pagination_and_combined_filters(self):
        self.assertEqual(self.collect().status_code,200)
        self.assertEqual(self.listing().json()['total'],2)
        for status, expected_id in [('collected',1),('uncollected',2)]:
            response=self.listing(collection_status=status,page_size=1,page=8,template_id=2)
            self.assertEqual(response.status_code,200,response.text)
            result=response.json()
            self.assertEqual(result['total'],1);self.assertEqual(result['page'],1)
            self.assertEqual([r['id'] for r in result['items']],[expected_id])
            self.assertEqual(result['items'][0]['already_collected'],status=='collected')
        self.assertEqual(self.listing(collection_status='collected',usage_status='unused').json()['total'],0)
        self.assertEqual(self.listing(collection_status='collected',usage_status='used',
            source_type='local_upload',created_from='2000-01-01T00:00:00Z').json()['total'],1)
        self.assertEqual(self.listing(collection_status='bad').status_code,422)
        self.assertEqual(self.listing(collection_status='collected',source_company_id=1).status_code,404)

    def test_material_status_filters_before_pagination_and_refresh_clamps_page(self):
        with self.sessions() as db:
            db.add_all([MaterialAsset(id=i,company_id=2,template_id=2,claimed_by=5,
                url=f'https://img.example/{i}',name=f'图片{i}',sku=f'NEW{i}') for i in range(4,29)])
            for i in range(4,28): self.add_history(db,sku=f'NEW{i}')
            db.commit()
        result=self.listing(collection_status='uncollected',page_size=1).json()
        self.assertEqual(result['total'],3);self.assertEqual(result['items'][0]['id'],28)
        last=self.listing(collection_status='uncollected',page_size=1,page=3).json()
        self.assertEqual(last['items'][0]['id'],1)
        self.assertEqual(self.collect().status_code,200)
        refreshed=self.listing(collection_status='uncollected',page_size=1,page=3).json()
        self.assertEqual(refreshed['total'],2);self.assertEqual(refreshed['page'],2)
        self.assertEqual(refreshed['items'][0]['id'],2)

    def test_history_identity_is_shared_between_libraries_and_isolated_by_companies(self):
        with self.sessions() as db:
            db.get(MaterialAsset,1).sku='SHARED'
            self.add_history(db,source_company_id=3,sku='SECOND')
            self.add_history(db,company_id=2,sku='SECOND')
            db.commit()
        self.assertEqual(self.collect().status_code,200)
        product=self.listing(source_library='product',collection_status='collected').json()
        self.assertEqual(product['total'],1);self.assertTrue(product['items'][0]['already_collected'])
        self.assertEqual(self.collect([2],key='other-library',source_library='product').status_code,409)
        self.assertEqual(self.collect([2],key='confirmed-library',source_library='product',allow_recollect=True).status_code,200)
        materials=self.listing(collection_status='uncollected').json()
        self.assertEqual([r['id'] for r in materials['items']],[2])
        self.assertEqual(self.collect([2],key='isolated-history').status_code,200)

    def test_sku_matching_is_exact_and_original_value_is_preserved(self):
        self.assertEqual(self.collect().status_code,200)
        for new_sku in ('original','ORIGINAL '):
            with self.sessions() as db:
                db.get(MaterialAsset,1).sku=new_sku;db.commit()
            result=self.listing(collection_status='collected').json()
            self.assertEqual(result['total'],0)
            self.assertEqual(self.collect(key=f'exact-{new_sku}',allow_recollect=True).status_code,200)
            self.assertEqual(self.listing(collection_status='collected').json()['items'][0]['sku'],new_sku)
            with self.sessions() as db:
                self.assertIsNotNone(db.scalar(select(CrossCompanyCollectionItem).where(
                    CrossCompanyCollectionItem.source_sku==new_sku)))

    def test_missing_sku_is_browsable_but_rejected_atomically_and_old_history_is_ignored(self):
        for index, sku in enumerate((None,'',' \t\n\u3000')):
            with self.sessions() as db:
                db.get(MaterialAsset,1).sku=sku
                item=db.scalar(select(CrossCompanyCollectionItem))
                if item: item.source_sku=sku
                else: self.add_history(db,sku=sku)
                db.commit()
            response=self.listing(collection_status='uncollected')
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['total'],2)
            self.assertEqual(self.listing(collection_status='collected').json()['total'],0)
            rejected=self.collect([1,2],key=f'missing-{index}')
            self.assertEqual(rejected.status_code,400);self.assertIn('1',rejected.json()['detail'])
            with self.sessions() as db:
                self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset)),3)
                self.assertEqual(db.scalar(select(func.count()).select_from(CrossCompanyCollectionBatch)),1)
        with self.sessions() as db:
            db.get(ProductLibraryProduct,2).sku='\t';db.commit()
        self.assertEqual(self.collect([2],key='missing-product',source_library='product').status_code,400)

    def test_product_aggregation_and_duplicate_sku_records_in_a_batch(self):
        with self.sessions() as db:
            db.add(ProductLibrarySource(id=4,company_id=2,platform='TikTok',site='MY',shop_name='第二店铺'))
            db.add(ProductLibraryProduct(id=4,company_id=2,source_id=4,external_product_id='4',
                sku='SHARED',title='另一张图片',image_url='https://img.example/other',template_id=2))
            db.add(ProductLibraryOrder(id=4,company_id=2,source_id=4,order_number='extra',ordered_at=datetime.utcnow()))
            db.add(ProductLibraryOrderProduct(order_id=4,product_id=4,quantity=5));db.commit()
        result=self.listing(source_library='product',collection_status='uncollected',sku='SH',template_id=2).json()
        self.assertEqual(result['total'],1);self.assertEqual(result['items'][0]['id'],2)
        self.assertEqual(result['items'][0]['sales_quantity'],12)
        duplicate=self.collect([4,2],key='same-sku',source_library='product')
        self.assertEqual(duplicate.status_code,200,duplicate.text)
        self.assertEqual(duplicate.json()['collected'],1)
        self.assertEqual(self.collect([2,4],key='same-sku',source_library='product').json(),duplicate.json())
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CrossCompanyCollectionBatch)),1)
            self.assertEqual(db.scalar(select(CrossCompanyCollectionItem)).source_record_id,2)
        self.assertEqual(self.collect([4],source_library='product').status_code,409)
        self.assertEqual(self.collect([2,4],key='confirmed-dedup',source_library='product',allow_recollect=True).json()['collected'],1)
        result=self.listing(source_library='product',collection_status='collected',page_size=1,page=9).json()
        self.assertEqual(result['page'],1);self.assertEqual(result['items'][0]['id'],2)
        self.assertEqual(result['items'][0]['sales_quantity'],12)

    def test_filtered_rankings_preserve_top50_and_original_ranks(self):
        from app.product_library_rankings import create_daily_snapshot
        with self.sessions() as db:
            db.get(ProductLibraryOrder,2).ordered_at=datetime.utcnow()-timedelta(days=1)
            for i in range(4,58):
                db.add(ProductLibraryProduct(id=i,company_id=2,source_id=2,external_product_id=str(i),
                    sku=f'RANK{i:03}',title=f'排名图片{i}',image_url=f'https://img.example/rank-{i}',template_id=2))
                db.add(ProductLibraryOrderProduct(order_id=2,product_id=i,quantity=200-i))
            self.add_history(db,sku='RANK004');self.add_history(db,sku='RANK010');db.commit()
            create_daily_snapshot(db,2,date.today())
        for category in ('top7','top15','top30','potential','hot','booming'):
            params={'source_library':'product','category':category,'page_size':100}
            original=self.listing(**params).json()['items']
            for status in ('collected','uncollected'):
                expected=[r for r in original if r['already_collected']==(status=='collected')]
                response=self.listing(**params,collection_status=status)
                self.assertEqual(response.status_code,200,response.text)
                result=response.json()
                self.assertEqual(result['total'],len(expected))
                self.assertEqual(result['items'],expected)
        params={'source_library':'product','category':'top7','collection_status':'uncollected','page_size':1}
        first=self.listing(**params).json();second=self.listing(**params,page=2).json()
        self.assertEqual(first['total'],48);self.assertEqual(first['items'][0]['rank'],2)
        self.assertEqual(second['items'][0]['rank'],3)
        self.assertEqual(self.listing(source_library='product',category='top7',collection_status='collected',sku='OTHER').json()['total'],0)
        with self.sessions() as db:
            from app.models import ProductLibraryDailySnapshot
            db.query(ProductLibraryDailySnapshot).delete();db.commit()
        empty=self.listing(**params,page=8).json()
        self.assertEqual(empty['total'],0);self.assertEqual(empty['page'],1);self.assertIsNone(empty['snapshot_date'])

    def test_product_status_uses_representative_sku_with_case_variants(self):
        with self.sessions() as db:
            db.add(ProductLibraryProduct(id=4,company_id=2,source_id=2,external_product_id='case-variant',
                sku='shared',title='大小写不同的 SKU',image_url='https://img.example/case',template_id=2))
            db.commit()
        self.assertEqual(self.collect([4],source_library='product').status_code,200)
        original=self.listing(source_library='product').json()['items']
        for status in ('collected','uncollected'):
            expected=[row for row in original if row['already_collected']==(status=='collected')]
            result=self.listing(source_library='product',collection_status=status).json()
            self.assertEqual(result['total'],len(expected))
            self.assertEqual(result['items'],expected)

    def test_validation_limits_and_sku_requirements(self):
        self.assertEqual(self.collect(list(range(1,102))).status_code,422)
        self.assertEqual(self.client.post('/cross-company-collection/collect',headers={'Authorization':self.headers()['Authorization']},json={'source_company_id':2,'source_library':'material','record_ids':[1],'template_id':1}).status_code,422)
        with self.sessions() as db:
            db.get(User,1).user_code=None;db.commit()
        self.assertEqual(self.collect().status_code,400)
        with self.sessions() as db:
            db.get(User,1).user_code='AA';db.get(ProductTemplate,1).name='无效模板';db.commit()
        self.assertEqual(self.collect().status_code,400)


if __name__ == '__main__':
    unittest.main()
