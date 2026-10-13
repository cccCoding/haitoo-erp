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
    CrossCompanyCollectionPermissionLog, MaterialAsset, ProductLibraryProduct, ProductLibrarySource,
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

    def test_exact_url_matching_and_delete_recollect(self):
        with self.sessions() as db:
            db.get(MaterialAsset,3).url='https://img.example/A';db.commit()
        first=[r for r in self.listing().json()['items'] if r['id']==1][0]
        self.assertFalse(first['already_collected'])
        result=self.collect().json()
        self.client.delete(f"/material-assets/{result['material_asset_ids'][0]}",headers=self.headers())
        self.assertEqual(self.collect(key='after-delete').status_code,200)

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
