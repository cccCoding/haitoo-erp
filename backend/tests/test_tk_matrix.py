"""矩阵HTTP闭环：真实数据库状态、固定快照、幂等及提交边界。"""
import copy
import csv
import io
import hashlib
import json
import unittest
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select
from tests.test_supply_catalog import SupplyFixture
from app.models import HubAgent,HubRuntimeLock,HubUploadTask,SupplyJob,SupplyJobMaterial,Role,User,TiktokCategoryCatalog
from app.tiktok_export import TEMPLATE_PATH,parse_listing_options
from app.hub_v5.models import *
from app.hub_v5.api import router
from app.hub_v5.releases import router as release_router
from app.hub_v5 import service as s
from app.hub_v5.listing import combination_hash
from app.supply_common import digest


class MatrixTests(SupplyFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.app.include_router(router);self.app.include_router(release_router)
        from app.hub_v5.management import router as management_router
        self.app.include_router(management_router)
        self.agent_tokens={1:'a'*48,2:'b'*48,3:'c'*48}
        with self.sessions() as db:
            catalog=db.get(TiktokCategoryCatalog,1)
            db.add(TiktokCategoryCatalog(id=3,company_id=1,name='本土类目',source_filename=catalog.source_filename,
                template_type='tiktok_local',template_blob=catalog.template_blob,parsed_options=copy.deepcopy(catalog.parsed_options)))
            catalog.template_type='tiktok_cross_border'
            catalog.template_blob=(TEMPLATE_PATH.parent/'tiktok_seller_cross_border_zh.xlsx').read_bytes()
            catalog.parsed_options=parse_listing_options(catalog.template_blob,'tiktok_cross_border')
            db.add(MatrixCompany(company_id=1,enabled=True,listing_enabled=True))
            for uid in (2,3):db.add(MatrixMemberPermission(user_id=uid,company_id=1,enabled=True,collect_enabled=True,listing_enabled=True,view_scope='own'))
            for identity,uid,company in ((1,1,1),(2,1,1),(3,5,2)):
                db.add(HubAgent(id=identity,company_id=company,user_id=uid,name=f'电脑{identity}',platform='macos',is_active=True,
                    token_hash=hashlib.sha256(self.agent_tokens[identity].encode()).hexdigest(),last_seen_at=datetime.utcnow()))
            db.commit()
        for identity in (1,2,3):self.beat(identity)
        self.env=self.sync(1,[{'container_code':'env-1','name':'测试环境','group_name':'分组A','site':'MY'}])[0]

    def ar(self,method,path,agent=1,json=None,**kwargs):
        return self.client.request(method,'/hub-v5'+path,json=json,headers={'X-Hub-Agent-Token':self.agent_tokens[agent],'X-Hub-Protocol':'5'},**kwargs)

    def beat(self,agent=1,identity='team-1'):
        result=self.ar('POST','/agent/heartbeat',agent,json={'install_uuid':str(__import__('uuid').UUID(int=agent)),'version':'5.0.0','hub_identity':identity,'hub_connected':True,
            'capabilities':{'shop.collect':['MY','ID'],'listing.catalog':['MY','ID']}})
        self.assertEqual(result.status_code,200,result.text)

    def sync(self,agent,entries,version=None):
        version=version or int(datetime.now().timestamp())
        start=self.ar('POST','/agent/environment-syncs',agent,json={'snapshot_key':str(uuid4()),'hub_identity':'team-1','version':version,'expected_count':len(entries),'part_count':1})
        self.assertEqual(start.status_code,200,start.text);identity=start.json()['id']
        r=self.ar('PUT',f'/agent/environment-syncs/{identity}/parts/0',agent,json={'entries':entries});self.assertEqual(r.status_code,200,r.text)
        r=self.ar('POST',f'/agent/environment-syncs/{identity}/commit',agent,json={});self.assertEqual(r.status_code,200,r.text)
        with self.sessions() as db:return list(db.scalars(select(MatrixAccess.environment_id).where(MatrixAccess.agent_id==agent,MatrixAccess.available.is_(True))))

    def strategy_input(self, **extra):
        return super().strategy_input(**{'attributes':{'product_property/100157':'棉','product_property/100198':'花朵'},**extra})

    def operation(self, listing=False, uid=1, **kwargs):
        payload={'name':'采集操作','tasks':['listing.catalog','shop.collect'] if listing else ['shop.collect']}
        if listing: payload['strategies']={'MY':self.create_strategy(uid=uid)}
        result=self.request('POST','/hub-v5/operations',uid=uid,json={**payload,**kwargs})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    def plan(self,listing=False,agent=1,**kwargs):
        operation=self.operation(listing,**{k:kwargs.pop(k) for k in ('tasks','strategies') if k in kwargs})
        payload={'name':'采集方案','agent_id':agent,'operation_id':operation['id'],'environment_ids':[self.env]}
        result=self.request('POST','/hub-v5/plans',json={**payload,**kwargs});self.assertEqual(result.status_code,200,result.text);return result.json()

    def make_run(self,plan=None,ids=None,key=None):
        plan=plan or self.plan(environment_ids=ids or [self.env])
        pv=self.request('POST',f"/hub-v5/plans/{plan['id']}/preview",json={})
        self.assertEqual(pv.status_code,200,pv.text);self.assertEqual(pv.json()['errors'],[])
        data={'preview_token':pv.json()['preview_token'],'expected_revision':plan['revision']}
        result=self.client.post(f"/hub-v5/plans/{plan['id']}/runs",json=data,headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':key or str(uuid4())})
        self.assertEqual(result.status_code,200,result.text);return result.json(),data

    def claim(self,run,agent=1):
        item=run['items'][0]['id'];r=self.ar('POST',f'/agent/items/{item}/claim',agent,json={});self.assertEqual(r.status_code,200,r.text)
        return item,{'claim_token':r.json()['claim_token'],'fencing':r.json()['fencing']}

    def bind(self,item,creds,external='shop-1',agent=1):
        r=self.ar('POST',f'/agent/items/{item}/identity',agent,json={**creds,'identity':{'site':'MY','external_id':external,'name':'测试店铺'}})
        self.assertEqual(r.status_code,200,r.text);return r.json()['shop_id']

    def package(self,count=1,empty_verified=False,total_verified=True):
        now=datetime.now(timezone(timedelta(hours=8)));end=now.replace(hour=0,minute=0,second=0,microsecond=0)
        return {'header':{'identity':{'site':'MY','external_id':'shop-1','name':'测试店铺'},'observed_at':now.isoformat(),
            'window_start':(end-timedelta(days=7)).isoformat(),'window_end':end.isoformat(),'timezone':'Asia/Kuala_Lumpur',
            'expected_count':count,'complete':True,'empty_verified':empty_verified,'total_verified':total_verified,
            'sections':{'identity':'completed','products':'completed','traffic':'completed'},'metrics':{},'reasons':{}},
            'products':[{'external_id':str(i),'name':'商品','impressions':10,'clicks':1,'active':True} for i in range(count)]}

    def upload(self,item,creds,package):
        r=self.ar('POST',f'/agent/items/{item}/collections',json={**creds,'content_hash':digest(package),'part_count':1,'header':package['header']})
        self.assertEqual(r.status_code,200,r.text);cid=r.json()['id']
        r=self.ar('PUT',f'/agent/items/{item}/collections/{cid}/parts/0',json={**creds,'products':package['products']});self.assertEqual(r.status_code,200,r.text)
        return cid,self.ar('POST',f'/agent/items/{item}/collections/{cid}/commit',json=creds)

    def direct_manual_preview(self, **kwargs):
        response=self.request('POST','/hub-v5/manual/preview',json={'tasks':['shop.collect'],'environment_ids':[self.env],**kwargs})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def direct_manual_run(self, pv, key='direct-manual-test'):
        return self.client.post('/hub-v5/manual/runs',json={'previews':[{'preview_token':p['preview_token'],'expected_revision':p['revision']} for p in pv['batches']]},headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':key})

    def test_direct_manual_does_not_require_operation_or_device(self):
        pv=self.direct_manual_preview()
        self.assertEqual(pv['errors'],[])
        self.assertEqual(pv['batches'][0]['agent_id'],1)
        run=self.direct_manual_run(pv)
        self.assertEqual(run.status_code,200,run.text)
        self.assertIsNone(run.json()['items'][0]['plan_id'])
        self.assertEqual(self.request('GET','/hub-v5/operations').json(),[])
        self.assertEqual(self.request('GET','/hub-v5/plans').json(),[])
        self.assertEqual(self.direct_manual_run(pv).json()['items'][0]['id'],run.json()['items'][0]['id'])
        another=self.direct_manual_preview()
        self.assertEqual(self.direct_manual_run(another).status_code,409)
        self.assertEqual(self.request('GET','/hub-v5/runs').json()['total'],1)

    def test_direct_manual_all_filtered_distributes_all_environments(self):
        second=self.sync(2,[{'container_code':'second-device','name':'第二电脑环境','site':'MY'}],version=1999999999)[0]
        pv=self.direct_manual_preview(all_filtered=True,environment_ids=[])
        self.assertEqual(pv['environment_count'],2)
        self.assertEqual({b['agent_id'] for b in pv['batches']},{1,2})
        self.assertEqual({e['id'] for b in pv['batches'] for e in b['environments']},{self.env,second})
        result=self.direct_manual_run(pv)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(len(result.json()['items']),2)
        self.assertEqual({i['environment_id'] for r in result.json()['items'] for i in r['items']},{self.env,second})

    def test_direct_manual_batch_rolls_back_if_one_preview_changes(self):
        second=self.sync(2,[{'container_code':'second-device','name':'第二电脑环境','site':'MY'}],version=1999999999)[0]
        pv=self.direct_manual_preview(environment_ids=[self.env,second])
        with self.sessions() as db:
            db.get(MatrixEnvironment,second).revision+=1;db.commit()
        result=self.direct_manual_run(pv)
        self.assertEqual(result.status_code,409,result.text)
        self.assertEqual(self.request('GET','/hub-v5/runs').json()['total'],0)

    def test_direct_manual_prefers_ready_owned_device(self):
        self.sync(2,[{'container_code':'env-1','name':'测试环境','site':'MY'}],version=1999999999)
        with self.sessions() as db:
            db.get(MatrixDevice,1).paused=True;db.commit()
        pv=self.direct_manual_preview()
        self.assertEqual(pv['errors'],[])
        self.assertEqual(pv['batches'][0]['agent_id'],2)
        with self.sessions() as db:
            db.get(HubAgent,2).user_id=2;db.commit()
        blocked=self.direct_manual_preview()
        self.assertEqual(blocked['batches'][0]['agent_id'],1)
        self.assertTrue(any('暂停' in e for e in blocked['errors']))

    def management_package(self,count=2):
        data=self.package(count=count,empty_verified=count==0)
        data['header'].update(collection_kind='product_management',product_scope='on_sale',on_sale_count=count,window_start=None,window_end=None)
        data['header']['sections']['traffic']='unsupported'
        data['header']['reasons']['traffic']='商品管理页未声明流量日期范围'
        for i,product in enumerate(data['products']):
            product.update(impressions=None,clicks=None,views=10+i,views_reason=None,sku_count=2,
                skus=[{'name':f'Color {i} - {size}','seller_sku':f'S{i}-{size}','stock':999,'price':'109.00','sale_price':'39.99','currency':'MYR'} for size in ('S','M')])
        return data

    def analysis_package(self):
        from zoneinfo import ZoneInfo
        data=self.management_package()
        end=datetime.now(ZoneInfo('Asia/Kuala_Lumpur')).replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
        data['header'].update(collection_kind='product_analysis',window_start=(end-timedelta(days=30)).isoformat(),window_end=end.isoformat())
        data['header']['sections']['traffic']='completed'
        for p in data['products']:p.update(impressions=100,clicks=5,sales_count=1)
        return data

    def test_analysis_snapshot_merges_thirty_day_traffic_and_management_skus(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        data=self.analysis_package()
        _,result=self.upload(item,creds,data)
        self.assertEqual(result.status_code,200,result.text)
        snap=result.json()
        self.assertEqual(snap['collection_kind'],'product_analysis')
        self.assertEqual(snap['impressions'],200);self.assertEqual(snap['clicks'],10)
        self.assertEqual(snap['ctr'],.05);self.assertEqual(snap['sell_through_rate'],1)
        self.assertEqual(snap['sku_count'],4);self.assertEqual(snap['views'],21)
        self.assertEqual(snap['window_start'],data['header']['window_start'])
        self.assertEqual(self.request('GET',f'/hub-v5/shops/{shop}/snapshots').json()['products'][0]['sales_count'],1)
        exported=list(csv.DictReader(io.StringIO(self.request('GET',f'/hub-v5/shops/{shop}/export').text.lstrip('\ufeff'))))
        self.assertEqual(exported[0]['成交件数'],'1');self.assertEqual(exported[0]['曝光'],'100')

    def test_analysis_snapshot_preserves_verified_unavailable_metrics_and_coverage(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        data=self.analysis_package()
        data['products'][0].update(impressions=None,clicks=None,sales_count=None,traffic_reason='商品分析接口按商品ID查询无记录')
        _,result=self.upload(item,creds,data)
        self.assertEqual(result.status_code,200,result.text)
        snap=result.json()
        self.assertEqual(snap['impressions'],100);self.assertEqual(snap['clicks'],5)
        self.assertEqual(snap['ctr'],.05);self.assertEqual(snap['sell_through_rate'],1)
        self.assertEqual(snap['traffic_covered'],1);self.assertEqual(snap['traffic_unknown'],1)
        self.assertEqual(snap['known_impressions'],100);self.assertEqual(snap['known_clicks'],5)
        products=self.request('GET',f'/hub-v5/shops/{shop}/snapshots').json()['products']
        self.assertIsNone(products[0]['impressions']);self.assertIn('无记录',products[0]['traffic_reason'])
        exported=list(csv.DictReader(io.StringIO(self.request('GET',f'/hub-v5/shops/{shop}/export').text.lstrip('\ufeff'))))
        self.assertEqual(exported[0]['曝光'],'');self.assertIn('无记录',exported[0]['分析数据说明'])

    def test_existing_partial_analysis_snapshot_recalculates_summary_and_cards(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        data=self.analysis_package()
        data['products'][0].update(impressions=None,clicks=None,sales_count=None,traffic_reason='商品分析接口按商品ID查询无记录')
        _,result=self.upload(item,creds,data)
        self.assertEqual(result.status_code,200,result.text)
        with self.sessions() as db:
            row=db.get(MatrixCollection,result.json()['id'])
            summary={k:v for k,v in row.quality['summary'].items() if k not in {'analysis_summary_version','sales_covered','known_sell_through_rate'}}
            row.quality={**row.quality,'summary':summary};db.commit()
        snapshot=self.request('GET',f'/hub-v5/shops/{shop}/snapshots').json()['snapshot']
        self.assertEqual(snapshot['impressions'],100);self.assertEqual(snapshot['clicks'],5)
        self.assertEqual(snapshot['ctr'],.05);self.assertEqual(snapshot['sell_through_rate'],1)
        bucket=self.request('GET','/hub-v5/shops/metrics').json()['windows'][0]
        self.assertEqual(bucket['impressions'],100);self.assertEqual(bucket['clicks'],5)
        self.assertEqual(bucket['ctr'],.05);self.assertEqual(bucket['traffic_unknown'],1)

    def test_analysis_card_totals_stay_unknown_when_all_products_have_no_record(self):
        run,_=self.make_run();item,creds=self.claim(run);self.bind(item,creds)
        data=self.analysis_package()
        for product in data['products']:
            product.update(impressions=None,clicks=None,sales_count=None,traffic_reason='商品分析接口按商品ID查询无记录')
        _,result=self.upload(item,creds,data)
        self.assertEqual(result.status_code,200,result.text)
        bucket=self.request('GET','/hub-v5/shops/metrics').json()['windows'][0]
        self.assertIsNone(bucket['impressions']);self.assertIsNone(bucket['clicks']);self.assertIsNone(bucket['ctr'])
        self.assertEqual(bucket['traffic_unknown'],2)

    def test_analysis_gmv_uses_decimal_totals_and_exports_product_amounts(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        data=self.analysis_package()
        data['products'][0]['gmv']='12.34';data['products'][1]['gmv']='0.66'
        _,result=self.upload(item,creds,data)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['gmv'],'13.00');self.assertEqual(result.json()['gmv_covered'],2)
        detail=self.request('GET',f'/hub-v5/shops/{shop}/snapshots').json()
        self.assertEqual(detail['products'][0]['gmv'],'12.34')
        exported=list(csv.DictReader(io.StringIO(self.request('GET',f'/hub-v5/shops/{shop}/export').text.lstrip('\ufeff'))))
        self.assertEqual(exported[0]['GMV'],'12.34');self.assertEqual(exported[0]['GMV币种'],'MYR')

    def test_analysis_shop_gmv_keeps_all_products_total_separate_from_on_sale_subtotal(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        data=self.analysis_package();data['products'][0]['gmv']='12.34';data['products'][1]['gmv']='0.66'
        data['header']['metrics']['gmv']='15.25'
        _,result=self.upload(item,creds,data)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['gmv'],'15.25');self.assertEqual(result.json()['gmv_scope'],'all_products')
        self.assertEqual(result.json()['quality']['summary']['gmv'],'13.00')

    def test_analysis_gmv_preserves_zero_and_legacy_unknown_amounts(self):
        from app.hub_v5.collections import summarize
        self.assertEqual(summarize([{'gmv':'0.00'}])['gmv'],'0.00')
        partial=summarize([{'gmv':'12.34'},{}])
        self.assertEqual(partial['gmv'],'12.34');self.assertEqual(partial['gmv_covered'],1)
        self.assertIsNone(summarize([{}])['gmv'])

    def test_existing_analysis_snapshot_derives_gmv_from_saved_product_amounts(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        data=self.analysis_package();data['products'][0]['gmv']='1.10';data['products'][1]['gmv']='2.20'
        _,result=self.upload(item,creds,data)
        self.assertEqual(result.status_code,200,result.text)
        with self.sessions() as db:
            row=db.get(MatrixCollection,result.json()['id'])
            summary={**row.quality['summary'],'analysis_summary_version':1}
            summary.pop('gmv',None);summary.pop('gmv_covered',None)
            row.quality={**row.quality,'summary':summary};db.commit()
        snapshot=self.request('GET',f'/hub-v5/shops/{shop}/snapshots').json()['snapshot']
        self.assertEqual(snapshot['gmv'],'3.30');self.assertEqual(snapshot['gmv_covered'],2)

    def test_analysis_snapshot_rejects_wrong_window_missing_traffic_or_skus(self):
        for mutation in ('window','clicks','skus','sales','reason'):
            with self.subTest(mutation=mutation):
                run,_=self.make_run();item,creds=self.claim(run);self.bind(item,creds)
                data=self.analysis_package()
                if mutation=='window':data['header']['window_start']=(datetime.fromisoformat(data['header']['window_end'])-timedelta(days=7)).isoformat()
                elif mutation=='clicks':data['products'][0]['clicks']=None
                elif mutation=='sales':data['products'][0]['sales_count']=None
                elif mutation=='reason':data['products'][0]['traffic_reason']='商品分析接口按商品ID查询无记录'
                else:data['products'][0]['skus']=[]
                _,result=self.upload(item,creds,data)
                self.assertEqual(result.status_code,422,result.text)
                self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'failed'})

    def test_management_snapshot_saves_views_and_all_skus_without_traffic_window(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        data=self.management_package()
        _,committed=self.upload(item,creds,data)
        self.assertEqual(committed.status_code,200,committed.text)
        snapshot=committed.json()
        self.assertEqual(snapshot['active'],2)
        self.assertEqual(snapshot['views'],21)
        self.assertEqual(snapshot['sku_count'],4)
        self.assertIsNone(snapshot['impressions']);self.assertIsNone(snapshot['window_start'])
        self.assertIsNone(snapshot['with_impressions'])
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'succeeded'}).status_code,200)
        detail=self.request('GET',f'/hub-v5/shops/{shop}/snapshots').json()
        self.assertEqual(detail['products'][0]['skus'],data['products'][0]['skus'])
        metrics=self.request('GET','/hub-v5/shops/metrics').json()
        self.assertEqual(metrics['active'],2);self.assertEqual(metrics['views'],21);self.assertEqual(metrics['sku_count'],4)
        self.assertEqual(metrics['windows'],[]);self.assertIsNone(metrics['zero_impressions'])
        export=self.request('GET',f'/hub-v5/shops/{shop}/export')
        self.assertEqual(export.status_code,200,export.text)
        self.assertIn('商家SKU',export.text);self.assertIn('S0-S',export.text)
        self.assertEqual(len(export.text.strip().splitlines()),5)

    def test_management_snapshot_accepts_explicit_unknown_views_without_zero_fill(self):
        run,_=self.make_run();item,creds=self.claim(run);self.bind(item,creds)
        data=self.management_package();data['products'][0].update(views=None,views_reason='商品管理页未提供浏览次数（--）')
        _,committed=self.upload(item,creds,data)
        self.assertEqual(committed.status_code,200,committed.text)
        self.assertIsNone(committed.json()['views'])
        self.assertEqual(committed.json()['sku_count'],4)

    def test_product_view_counts_and_sales_rate_preserve_unknowns(self):
        from app.hub_v5.collections import summarize
        products = [{'views': 10, 'sales_count': 2}, {'views': 0, 'sales_count': 0},
                    {'views': 9, 'sales_count': 0, 'active': False}]
        summary = summarize(products)
        self.assertEqual((summary['with_views'], summary['zero_views']), (1, 1))
        self.assertEqual(summary['sell_through_rate'], .5)
        products[0]['views'] = None
        products[1].pop('sales_count')
        summary = summarize(products)
        self.assertIsNone(summary['with_views']);self.assertIsNone(summary['zero_views'])
        self.assertIsNone(summary['sell_through_rate'])
        self.assertEqual(summarize([])['with_views'], 0)
        self.assertIsNone(summarize([])['sell_through_rate'])

    def test_existing_snapshot_derives_view_counts_without_changing_traffic(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        data=self.management_package();data['products'][0]['views']=0
        _,committed=self.upload(item,creds,data)
        self.assertEqual(committed.status_code,200,committed.text)
        with self.sessions() as db:
            row=db.get(MatrixCollection,committed.json()['id'])
            summary={k:v for k,v in row.quality['summary'].items() if k not in {'view_counts_version','with_views','zero_views','sell_through_rate'}}
            row.quality={**row.quality,'summary':summary};db.commit()
        snapshot=self.request('GET',f'/hub-v5/shops/{shop}/snapshots').json()['snapshot']
        self.assertEqual((snapshot['with_views'],snapshot['zero_views']),(1,1))
        self.assertIsNone(snapshot['with_impressions']);self.assertIsNone(snapshot['sell_through_rate'])
        metrics=self.request('GET','/hub-v5/shops/metrics').json()
        self.assertEqual((metrics['with_views'],metrics['zero_views']),(1,1))
        export=self.request('GET','/hub-v5/exports')
        self.assertIn('有浏览,零浏览,动销率',export.text)

    def test_management_dash_views_count_as_zero_for_new_and_saved_snapshots(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        data=self.management_package(count=3)
        data['products'][1]['views']=0
        data['products'][2].update(views=None,views_reason='商品管理页未提供浏览次数（--）')
        _,committed=self.upload(item,creds,data)
        self.assertEqual(committed.status_code,200,committed.text)
        self.assertEqual((committed.json()['with_views'],committed.json()['zero_views']),(1,2))
        with self.sessions() as db:
            row=db.get(MatrixCollection,committed.json()['id'])
            summary={k:v for k,v in row.quality['summary'].items() if k!='view_counts_version'}
            summary.update(with_views=None,zero_views=None)
            row.quality={**row.quality,'summary':summary};db.commit()
        snapshot=self.request('GET',f'/hub-v5/shops/{shop}/snapshots').json()['snapshot']
        self.assertEqual((snapshot['with_views'],snapshot['zero_views']),(1,2))
        self.assertIsNone(snapshot['with_impressions'])
        metrics=self.request('GET','/hub-v5/shops/metrics').json()
        self.assertEqual((metrics['with_views'],metrics['zero_views']),(1,2))
        environment=self.request('GET','/hub-v5/environments').json()['items'][0]
        self.assertEqual((environment['snapshot']['with_views'],environment['snapshot']['zero_views']),(1,2))
        response=self.request('GET','/hub-v5/exports')
        table=list(csv.reader(io.StringIO(response.text.lstrip('\ufeff'))))
        self.assertEqual(table[0],['环境名 / 编号','分组','站点','在售商品','有浏览','零浏览','动销率','曝光','点击','CTR','GMV','7日访客','违规分','采集时间'])
        self.assertEqual(len(table[1]),len(table[0]))
        self.assertEqual(table[1][0],f"{environment['name']}\n{environment['container_code']}")
        self.assertEqual(table[1][3:7],['3','1','2','—'])
        from urllib.parse import unquote
        from zoneinfo import ZoneInfo
        filename=f"店铺数据-{datetime.now(ZoneInfo('Asia/Hong_Kong')):%Y-%m-%d}.csv"
        self.assertIn(filename,unquote(response.headers['content-disposition']))
        # 筛选结果中尚未采集的环境也应保留，与列表一致。
        self.sync(1,[{'container_code':'env-1','name':'测试环境','group_name':'分组A','site':'MY'},
                     {'container_code':'env-2','name':'未采集环境','site':'MY'}],version=int(datetime.now().timestamp())+1)
        response=self.request('GET','/hub-v5/exports?q=未采集环境')
        table=list(csv.reader(io.StringIO(response.text.lstrip('\ufeff'))))
        self.assertEqual(len(table),2)
        self.assertEqual(table[1][3:13],['—']*10)
        self.assertEqual(table[1][-1],'未采集')

    def test_management_snapshot_rejects_incomplete_skus_and_fake_traffic(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        for mutation in ('count','duplicate','traffic','views','scope'):
            with self.subTest(mutation=mutation):
                data=self.management_package()
                if mutation=='count':data['products'][0]['sku_count']=3
                elif mutation=='duplicate':data['products'][0]['skus'][1]=copy.deepcopy(data['products'][0]['skus'][0])
                elif mutation=='traffic':data['products'][0]['impressions']=data['products'][0]['views']
                elif mutation=='views':data['products'][0]['views']=None
                else:data['header']['on_sale_count']=3
                _,committed=self.upload(item,creds,data)
                self.assertEqual(committed.status_code,422,committed.text)
        with self.sessions() as db:self.assertIsNone(db.get(MatrixShop,shop).snapshot_id)

    def test_empty_management_snapshot_keeps_traffic_unknown(self):
        run,_=self.make_run();item,creds=self.claim(run);self.bind(item,creds)
        _,committed=self.upload(item,creds,self.management_package(0))
        self.assertEqual(committed.status_code,200,committed.text)
        self.assertEqual(committed.json()['active'],0)
        self.assertEqual(committed.json()['sku_count'],0)
        self.assertIsNone(committed.json()['impressions'])
        self.assertIsNone(committed.json()['zero_impressions'])

    def test_collection_without_platform_identity_is_archived_by_environment(self):
        run,_=self.make_run();item,creds=self.claim(run)
        response=self.ar('POST',f'/agent/items/{item}/environment-target',json=creds)
        self.assertEqual(response.status_code,200,response.text)
        identity=response.json()['identity']
        self.assertEqual(identity['environment_id'],self.env)
        self.assertNotIn('external_id',identity)
        package=self.package();package['header']['identity']=identity
        _,committed=self.upload(item,creds,package)
        self.assertEqual(committed.status_code,200,committed.text)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'succeeded'}).status_code,200)
        with self.sessions() as db:
            shop=db.get(MatrixShop,response.json()['shop_id'])
            self.assertEqual(shop.environment_id,self.env)
            self.assertIsNone(shop.external_id)
            self.assertIsNotNone(shop.snapshot_id)
        second,_=self.make_run();second_item,second_creds=self.claim(second)
        bound=self.ar('POST',f'/agent/items/{second_item}/environment-target',json=second_creds)
        self.assertEqual(bound.json()['shop_id'],response.json()['shop_id'])

    def test_environment_snapshot_cannot_target_another_environment(self):
        run,_=self.make_run();item,creds=self.claim(run)
        response=self.ar('POST',f'/agent/items/{item}/environment-target',json=creds)
        package=self.package();package['header']['identity']={**response.json()['identity'],'environment_id':self.env+999}
        rejected=self.ar('POST',f'/agent/items/{item}/collections',json={**creds,'content_hash':digest(package),'part_count':1,'header':package['header']})
        self.assertEqual(rejected.status_code,409,rejected.text)
        self.assertIn('执行环境不一致',rejected.json()['detail'])
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/environment-target',agent=2,json=creds).status_code,404)

    def test_environment_target_rechecks_matrix_permission(self):
        run=self.member_run();item,creds=self.claim(run,agent=8)
        with self.sessions() as db:
            db.get(MatrixMemberPermission,2).enabled=False;db.commit()
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/environment-target',agent=8,json=creds).status_code,403)

    def test_listing_can_prepare_using_environment_target(self):
        run,_=self.make_run(self.plan(listing=True));item,creds=self.claim(run)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/environment-target',json=creds).status_code,200)
        response=self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds)
        self.assertEqual(response.status_code,200,response.text)
        with self.sessions() as db:
            self.assertIsNotNone(db.get(MatrixItem,item).shop_id)
            self.assertIsNotNone(db.get(MatrixItem,item).supply_job_id)

    def test_only_my_strategy_is_accepted_in_matrix_operations(self):
        strategy=self.create_strategy(uid=1)
        config={'tasks':['listing.catalog'],'strategies':{'ID':strategy}}
        self.assertEqual(self.request('POST','/hub-v5/operations',json={'name':'印尼策略',**config}).status_code,422)
        operation=self.operation()
        self.assertEqual(self.request('PATCH',f"/hub-v5/operations/{operation['id']}",json={'name':'错误站点','expected_revision':1,**config}).status_code,422)
        self.assertEqual(self.request('POST','/hub-v5/manual/preview',json={'environment_ids':[self.env],**config}).status_code,422)
        with self.sessions() as db:
            with self.assertRaisesRegex(Exception,'马来西亚货盘策略'):
                s.validate_operation(db,db.get(User,1),config)

    def test_listing_rejects_local_catalogs_and_other_market_strategies(self):
        for parameters in ({'category_catalog_id':3},{'title_site':'ID'}):
            with self.subTest(parameters=parameters):
                strategy=self.create_strategy(uid=1,**parameters)
                config={'tasks':['listing.catalog'],'strategies':{'MY':strategy}}
                operation=self.request('POST','/hub-v5/operations',json={'name':'不支持的策略',**config})
                preview=self.request('POST','/hub-v5/manual/preview',json={'environment_ids':[self.env],**config})
                for response in (operation,preview):
                    self.assertEqual(response.status_code,422,response.text)
                    self.assertIn('马来西亚跨境',response.text)
                with self.sessions() as db:
                    with self.assertRaisesRegex(Exception,'马来西亚跨境'):
                        s.freeze_strategy(db,db.get(User,1),strategy)

    def test_listing_rejects_other_catalog_sites_after_site_is_changed(self):
        strategy = self.create_strategy(uid=1)
        with self.sessions() as db:
            db.get(TiktokCategoryCatalog, 1).site = 'ID'
            db.commit()
        config = {'tasks': ['listing.catalog'], 'strategies': {'MY': strategy}}
        for path, payload in (
            ('/hub-v5/operations', {'name': '印尼类目策略', **config}),
            ('/hub-v5/manual/preview', {'environment_ids': [self.env], **config}),
        ):
            response = self.request('POST', path, json=payload)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertIn('马来西亚跨境', response.text)
        with self.sessions() as db:
            with self.assertRaisesRegex(Exception, '马来西亚跨境'):
                s.freeze_strategy(db, db.get(User, 1), strategy)

    def test_direct_manual_checks_tasks_and_freezes_listing_strategy(self):
        self.assertEqual(self.request('POST','/hub-v5/manual/preview',json={'tasks':[],'environment_ids':[self.env]}).status_code,422)
        self.assertEqual(self.request('POST','/hub-v5/manual/preview',json={'tasks':['listing.catalog'],'environment_ids':[self.env]}).status_code,422)
        strategy=self.create_strategy(uid=1)
        pv=self.direct_manual_preview(tasks=['listing.catalog','shop.collect'],strategies={'MY':strategy})
        self.assertEqual(pv['errors'],[])
        result=self.direct_manual_run(pv)
        self.assertEqual(result.status_code,200,result.text)
        with self.sessions() as db:
            run=db.get(MatrixRun,result.json()['items'][0]['id'])
            self.assertEqual(run.frozen['config']['tasks'],['listing.catalog','shop.collect'])
            self.assertEqual(run.frozen['strategies']['MY']['strategy_id'],strategy)
            self.assertEqual(run.frozen['strategies']['MY']['catalog_type'],'tiktok_cross_border')
        self.assertEqual(self.request('POST','/hub-v5/manual/preview',uid=2,json={'tasks':['shop.collect'],'environment_ids':[self.env]}).status_code,422)

    def test_all_filtered_manual_execution_rejects_partial_device_scope(self):
        self.sync(2,[{'container_code':'only-device-2','name':'另一电脑环境','site':'MY'}],version=1999999999)
        operation=self.operation()
        result=self.request('POST',f"/hub-v5/operations/{operation['id']}/preview",json={'agent_id':1,'all_filtered':True})
        self.assertEqual(result.status_code,422,result.text)
        self.assertIn('不全部属于执行设备',result.json()['detail'])
        scoped=self.request('POST',f"/hub-v5/operations/{operation['id']}/preview",json={'agent_id':1,'all_filtered':True,'filters':{'agent_id':1}})
        self.assertEqual(scoped.status_code,200,scoped.text)
        self.assertEqual([e['id'] for e in scoped.json()['environments']],[self.env])

    def test_operation_edit_does_not_repeat_same_schedule_fire(self):
        from app.hub_v5.worker import schedule_plan
        now=datetime.now(timezone.utc).replace(second=10,microsecond=0)
        plan=self.plan(scheduled=True,time=now.astimezone(timezone(timedelta(hours=8))).strftime('%H:%M'))
        with self.sessions() as db:
            db.get(MatrixPlan,plan['id']).updated_at=now.replace(tzinfo=None)-timedelta(minutes=1);db.commit()
        with self.sessions() as db: schedule_plan(db,plan['id'],now)
        self.assertEqual(self.request('PATCH',f"/hub-v5/operations/{plan['operation_id']}",json={'name':'更新方案','tasks':['shop.collect'],'expected_revision':1}).status_code,200)
        with self.sessions() as db: schedule_plan(db,plan['id'],now+timedelta(seconds=5))
        with self.sessions() as db:
            self.assertEqual(len(db.scalars(select(MatrixFire)).all()),1)
            self.assertEqual(len(db.scalars(select(MatrixRun)).all()),1)

    def test_plan_target_cannot_be_overridden_and_manual_run_has_no_plan(self):
        envs=self.sync(1,[{'container_code':'env-1','name':'测试环境','site':'MY'}, {'container_code':'env-2','name':'第二环境','site':'MY'}],version=1999999999)
        other=next(e for e in envs if e!=self.env)
        plan=self.plan()
        rejected=self.request('POST',f"/hub-v5/plans/{plan['id']}/preview",json={'environment_ids':[other]})
        self.assertEqual(rejected.status_code,422)
        fixed=self.request('POST',f"/hub-v5/plans/{plan['id']}/preview",json={}).json()
        self.assertEqual([e['id'] for e in fixed['environments']],[self.env])
        operation_id=plan['operation_id']
        pv=self.request('POST',f'/hub-v5/operations/{operation_id}/preview',json={'agent_id':1,'environment_ids':[other]}).json()
        body={'preview_token':pv['preview_token'],'expected_revision':pv['revision']}
        headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':'manual-test-key'}
        response=self.client.post(f'/hub-v5/operations/{operation_id}/runs',json=body,headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        run=response.json()
        self.assertIsNone(run['plan_id'])
        self.assertEqual([i['environment_id'] for i in run['items']],[other])
        self.assertEqual(run['operation_name'],'采集操作')
        self.assertEqual(self.client.post(f'/hub-v5/operations/{operation_id}/runs',json=body,headers=headers).json()['id'],run['id'])
        self.assertEqual(len(self.request('GET','/hub-v5/plans').json()),1)

    def test_operation_update_invalidates_previews_but_preserves_runs(self):
        plan=self.plan();run,_=self.make_run(plan)
        pv=self.request('POST',f"/hub-v5/plans/{plan['id']}/preview",json={}).json()
        operation_id=plan['operation_id']
        changed=self.request('PATCH',f'/hub-v5/operations/{operation_id}',json={'name':'新采集操作','tasks':['shop.collect'],'expected_revision':1})
        self.assertEqual(changed.status_code,200,changed.text)
        response=self.client.post(f"/hub-v5/plans/{plan['id']}/runs",json={'preview_token':pv['preview_token'],'expected_revision':pv['revision']},headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':'stale-operation'})
        self.assertEqual(response.status_code,409)
        current=self.request('GET','/hub-v5/plans').json()[0]
        self.assertEqual(current['revision'],2)
        self.assertEqual(current['operation_name'],'新采集操作')
        old=self.request('GET',f"/hub-v5/runs/{run['id']}").json()
        self.assertEqual(old['operation_name'],'采集操作')
        self.assertEqual(self.request('DELETE',f'/hub-v5/operations/{operation_id}?expected_revision=2').status_code,409)
        self.assertEqual(self.request('PATCH',f'/hub-v5/operations/{operation_id}',json={'name':'过期','tasks':['shop.collect'],'expected_revision':1}).status_code,409)
        self.assertEqual(self.request('PATCH',f'/hub-v5/operations/{operation_id}',uid=2,json={'name':'越权','tasks':['shop.collect'],'expected_revision':2}).status_code,404)

    def test_manual_preview_checks_operation_revision_and_ownership(self):
        operation=self.operation()
        path=f"/hub-v5/operations/{operation['id']}"
        pv=self.request('POST',path+'/preview',json={'agent_id':1,'environment_ids':[self.env]}).json()
        self.assertEqual(self.request('POST',path+'/preview',uid=2,json={'agent_id':1,'environment_ids':[self.env]}).status_code,404)
        other=self.operation()
        body={'preview_token':pv['preview_token'],'expected_revision':pv['revision']}
        headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':'wrong-operation'}
        self.assertEqual(self.client.post(f"/hub-v5/operations/{other['id']}/runs",json=body,headers=headers).status_code,409)
        self.request('PATCH',path,json={'name':'更新','tasks':['shop.collect'],'expected_revision':1})
        self.assertEqual(self.client.post(path+'/runs',json=body,headers=headers).status_code,409)

    def test_pausing_plan_does_not_stop_existing_run(self):
        plan=self.plan(scheduled=True);run,_=self.make_run(plan)
        response=self.request('PATCH',f"/hub-v5/plans/{plan['id']}",json={'name':plan['name'],'agent_id':1,'operation_id':plan['operation_id'],'environment_ids':[self.env],'scheduled':False,'expected_revision':plan['revision']})
        self.assertEqual(response.status_code,200,response.text)
        current=self.request('GET','/hub-v5/plans').json()[0]
        self.assertIsNone(current['next_fire_at'])
        self.assertFalse(self.request('GET',f"/hub-v5/runs/{run['id']}").json()['stop_requested'])
        self.assertEqual(self.request('DELETE',f"/hub-v5/plans/{plan['id']}?expected_revision={current['revision']}").status_code,200)
        self.assertEqual(self.request('DELETE',f"/hub-v5/operations/{plan['operation_id']}?expected_revision=1").status_code,200)
        self.assertEqual(self.request('GET',f"/hub-v5/runs/{run['id']}").status_code,200)

    def test_run_pagination_keeps_large_frozen_payloads_out_of_sorting(self):
        from sqlalchemy import event
        older,_=self.make_run()
        newer,_=self.make_run()
        with self.sessions() as db:
            for identity,status in ((older['id'],'succeeded'),(newer['id'],'queued')):
                row=db.get(MatrixRun,identity)
                row.status=status
                row.frozen={**row.frozen,'strategies':{'MY':{'catalog':'x'*1000000}}}
            db.commit()
        statements=[]
        def capture(conn,cursor,statement,parameters,context,executemany):
            statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            first=self.request('GET','/hub-v5/runs?page_size=1')
            second=self.request('GET','/hub-v5/runs?page=2&page_size=1')
            empty=self.request('GET','/hub-v5/runs?page=3&page_size=1')
        finally:
            event.remove(self.engine,'before_cursor_execute',capture)
        for response in (first,second,empty):
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['total'],2)
            self.assertEqual(response.json()['summary'],{'succeeded':1,'queued':1})
            self.assertEqual(response.json()['active']['id'],newer['id'])
        self.assertEqual([r['id'] for r in first.json()['items']],[newer['id']])
        self.assertEqual([r['id'] for r in second.json()['items']],[older['id']])
        self.assertEqual(empty.json()['items'],[])
        sorted_runs=[sql for sql in statements if 'matrix_runs' in sql and 'ORDER BY' in sql]
        self.assertTrue(sorted_runs)
        self.assertTrue(all('matrix_runs.frozen' not in sql for sql in sorted_runs))
        self.assertEqual(self.request('GET','/hub-v5/runs',uid=2).json()['total'],0)
        self.assertEqual(self.request('GET','/hub-v5/runs',uid=5).json()['total'],0)

    def test_environment_history_filters_items_before_shop_identification(self):
        envs=self.sync(1,[{'container_code':'env-1','name':'测试环境','group_name':'分组A','site':'MY'},
            {'container_code':'env-2','name':'第二环境','group_name':'分组A','site':'MY'}],version=1999999999)
        other=next(e for e in envs if e!=self.env)
        run,_=self.make_run(ids=envs)
        unrelated,_=self.make_run(ids=[other])
        response=self.request('GET',f'/hub-v5/runs?environment_id={self.env}')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['total'],1)
        record=response.json()['items'][0]
        self.assertEqual(record['id'],run['id'])
        self.assertEqual([i['environment_id'] for i in record['items']],[self.env])
        self.assertIsNone(record['items'][0]['shop'])
        self.assertEqual(record['plan_name'],'采集方案')
        self.assertEqual(record['trigger'],'manual')
        self.assertEqual(self.request('GET','/hub-v5/runs').json()['total'],2)
        with self.sessions() as db:
            db.add(MatrixFire(plan_id=run['plan_id'],revision=1,fire_at=datetime.utcnow(),status='created',run_id=run['id']))
            db.get(MatrixPlan,run['plan_id']).name='已改名方案';db.commit()
        historical=self.request('GET',f"/hub-v5/runs/{run['id']}").json()
        self.assertEqual(historical['trigger'],'scheduled')
        self.assertEqual(historical['plan_name'],'采集方案')
        self.assertEqual(self.request('GET',f'/hub-v5/runs?environment_id={self.env}',uid=5).status_code,404)
        self.assertEqual(self.request('GET',f'/hub-v5/runs?environment_id={other}').json()['total'],2)
        # 环境权限与运行归属分别校验；共享目录不会公开他人运行。
        self.sync(2,[{'container_code':'env-1','name':'测试环境','site':'MY'}],version=1999999999)
        with self.sessions() as db:
            db.get(HubAgent,2).user_id=2;db.commit()
        self.assertEqual(self.request('GET',f'/hub-v5/runs?environment_id={self.env}',uid=2).json()['total'],0)

    def test_shop_history_includes_other_environments_with_same_stable_shop(self):
        envs=self.sync(1,[{'container_code':'env-1','name':'测试环境','group_name':'分组A','site':'MY'},
            {'container_code':'env-2','name':'第二环境','group_name':'分组A','site':'MY'}],version=1999999999)
        other=next(e for e in envs if e!=self.env)
        first,_=self.make_run();second,_=self.make_run(ids=[other])
        with self.sessions() as db:
            shop=MatrixShop(company_id=1,site='MY',external_id='same-shop',name='同一店铺');db.add(shop);db.flush()
            db.get(MatrixEnvironment,self.env).shop_id=shop.id
            db.get(MatrixItem,second['items'][0]['id']).shop_id=shop.id
            db.commit()
        data=self.request('GET',f'/hub-v5/runs?environment_id={self.env}').json()
        self.assertEqual(data['total'],2)
        self.assertEqual(data['items'][0]['items'][0]['shop']['external_id'],'same-shop')
        self.assertEqual(data['items'][1]['items'][0]['environment_id'],self.env)

    def test_item_logs_keep_retries_isolated_and_allow_paging_past_500(self):
        envs=self.sync(1,[{'container_code':'env-1','name':'测试环境','group_name':'分组A','site':'MY'},
            {'container_code':'env-2','name':'第二环境','group_name':'分组A','site':'MY'}],version=1999999999)
        run,_=self.make_run(ids=envs);item=run['items'][0]['id'];other=run['items'][1]['id']
        with self.sessions() as db:
            attempts=[]
            for target,number in ((item,1),(other,1),(item,2)):
                a=MatrixAttempt(item_id=target,number=number,agent_id=1,token_hash='hash',fencing=number,lease_until=datetime.utcnow()+timedelta(minutes=1),status='failed')
                db.add(a);db.flush();attempts.append(a.id)
            for seq in range(1,504):
                # 旧日志没有 payload.item_id，仍能通过历史 attempt 关联。
                db.add(MatrixEvent(run_id=run['id'],attempt_id=attempts[0] if seq<300 else attempts[2],source_id=str(seq),seq=seq,kind='progress',payload={'stage':'collecting','message':str(seq)}))
            db.add(MatrixEvent(run_id=run['id'],attempt_id=attempts[1],source_id='other',seq=504,kind='progress',payload={'message':'其他店铺'}))
            db.add(MatrixEvent(run_id=run['id'],attempt_id=None,source_id='early',seq=505,kind='precheck.failed',payload={'item_id':item,'message':'尚未领取'}))
            db.commit()
        path=f"/hub-v5/runs/{run['id']}/events?item_id={item}"
        first=self.request('GET',path).json();self.assertEqual(len(first),500)
        self.assertEqual(first[0]['attempt_number'],1);self.assertEqual(first[-1]['attempt_number'],2)
        rest=self.request('GET',path+'&after_seq='+str(first[-1]['seq'])).json()
        self.assertEqual([e['seq'] for e in rest],[501,502,503,505])
        self.assertTrue(all(e['item_id']==item for e in first+rest))
        detail=self.request('GET',f"/hub-v5/runs/{run['id']}?item_id={item}").json()
        self.assertEqual(len(detail['items']),1)
        self.assertEqual([a['number'] for a in detail['items'][0]['attempts']],[1,2])
        self.assertEqual(self.request('GET',path,uid=5).status_code,404)
        self.assertEqual(self.request('GET',path,uid=2).status_code,404)
        self.assertEqual(self.request('GET',f"/hub-v5/runs/{run['id']}/events?item_id=999999").status_code,404)
        self.assertEqual(self.request('GET',f"/hub-v5/runs/{run['id']}?item_id=999999").status_code,404)

    def test_progress_idempotency_keeps_server_item_attribution(self):
        run,_=self.make_run();item,creds=self.claim(run)
        payload={**creds,'source_id':'same-event','stage':'collecting','message':'开始采集'}
        for _ in range(2):
            result=self.ar('POST',f'/agent/items/{item}/events',json=payload)
            self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/events',json={**payload,'message':'变更内容'}).status_code,409)
        events=self.request('GET',f"/hub-v5/runs/{run['id']}/events?item_id={item}").json()
        progress=[e for e in events if e['kind']=='progress']
        self.assertEqual(len(progress),1);self.assertEqual(progress[0]['item_id'],item)

    def test_collect_commit_and_run_success(self):
        run,_=self.make_run();item,creds=self.claim(run);self.bind(item,creds)
        denied=self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'succeeded'})
        self.assertEqual(denied.status_code,409)
        _,result=self.upload(item,creds,self.package());self.assertEqual(result.status_code,200,result.text)
        result=self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'succeeded'})
        self.assertEqual(result.status_code,200,result.text)
        view=self.request('GET',f"/hub-v5/runs/{run['id']}").json();self.assertEqual(view['status'],'succeeded')
        self.assertEqual(self.request('GET','/hub-v5/shops/metrics').json()['windows'][0]['ctr'],.1)
        with self.sessions() as db:self.assertIsNone(db.scalar(select(HubRuntimeLock)).matrix_item_id)

    def test_connector_registers_before_team_configuration_and_uses_erp_identity(self):
        with self.sessions() as db:
            db.delete(db.get(MatrixDevice,2));db.commit()
        payload={'install_uuid':str(__import__('uuid').UUID(int=2)),'version':'5.1.0','hub_connected':True}
        response=self.ar('POST','/agent/heartbeat',2,json=payload)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['hub_identity'],'')
        denied=self.request('PUT','/hub-v5/agents/2/connection',uid=5,json={'hub_identity':'foreign'})
        self.assertEqual(denied.status_code,404)
        configured=self.request('PUT','/hub-v5/agents/2/connection',json={'hub_identity':'team-1'})
        self.assertEqual(configured.status_code,200,configured.text)
        response=self.ar('POST','/agent/heartbeat',2,json=payload)
        self.assertEqual(response.json()['hub_identity'],'team-1')
        ids=self.sync(2,[{'container_code':'erp-configured','name':'ERP环境','site':'MY'}])
        self.assertEqual(len(ids),1)
        self.assertEqual(self.request('GET','/hub-v5/environments?q=ERP环境').json()['total'],1)

    def test_team_changes_invalidate_access_and_are_blocked_for_active_runs(self):
        run,_=self.make_run()
        blocked=self.request('PUT','/hub-v5/agents/1/connection',json={'hub_identity':'new-team'})
        self.assertEqual(blocked.status_code,409,blocked.text)
        with self.sessions() as db:
            db.get(MatrixRun,run['id']).status='cancelled';db.commit()
        changed=self.request('PUT','/hub-v5/agents/1/connection',json={'hub_identity':'new-team'})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertIsNone(changed.json()['sync_at'])
        self.assertEqual(self.request('GET','/hub-v5/environments').json()['total'],0)

    def test_reauthorization_preserves_installation_only_after_previous_grant_is_revoked(self):
        self.agent_tokens[4]='d'*48
        with self.sessions() as db:
            db.add(HubAgent(id=4,company_id=1,user_id=1,name='重新授权',platform='macos',is_active=True,
                token_hash=hashlib.sha256(self.agent_tokens[4].encode()).hexdigest(),last_seen_at=datetime.utcnow()))
            db.commit()
        payload={'install_uuid':str(__import__('uuid').UUID(int=1)),'version':'5.1.0','hub_connected':True}
        self.assertEqual(self.ar('POST','/agent/heartbeat',4,json=payload).status_code,409)
        with self.sessions() as db:
            db.get(HubAgent,1).is_active=False;db.commit()
        response=self.ar('POST','/agent/heartbeat',4,json=payload)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['hub_identity'],'')
        with self.sessions() as db:
            self.assertFalse(db.scalar(select(MatrixAccess).where(MatrixAccess.agent_id==1)).available)

    def test_scope_and_directed_claim(self):
        run,_=self.make_run()
        self.assertEqual(self.ar('POST',f"/agent/items/{run['items'][0]['id']}/claim",2,json={}).status_code,404)
        self.assertIn(self.ar('POST',f"/agent/items/{run['items'][0]['id']}/claim",3,json={}).status_code,(403,404))
        self.assertEqual(self.request('GET',f"/hub-v5/runs/{run['id']}",uid=2).status_code,404)
        self.assertEqual(self.request('GET','/hub-v5/environments',uid=5).json()['total'],0)
        self.assertEqual(self.request('GET','/hub-v5/environments',uid=4).status_code,403)

    def test_outdated_connector_capability_error_explains_upgrade(self):
        plan=self.plan()
        with self.sessions() as db:
            db.get(MatrixDevice,1).capabilities={};db.commit()
        result=self.request('POST',f"/hub-v5/plans/{plan['id']}/preview",json={})
        self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(any('马来西亚站店铺采集' in message and '更新或重启连接器' in message for message in result.json()['errors']))

    def test_only_my_cross_border_preview_even_when_device_advertises_id(self):
        plan=self.plan()
        ids=self.sync(1,[{'container_code':'id-env','name':'印尼店','site':'ID'}],version=1999999999)
        result=self.request('POST',f"/hub-v5/operations/{plan['operation_id']}/preview",json={'agent_id':1,'environment_ids':ids})
        self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(any('仅支持马来西亚（MY）跨境店' in message for message in result.json()['errors']))
        self.assertEqual(self.request('GET','/hub-v5/environments?executable=ready').json()['total'],0)

    def test_executability_filter_checks_capability_pause_and_busy(self):
        self.assertEqual(self.request('GET','/hub-v5/environments?executable=ready').json()['total'],1)
        with self.sessions() as db:
            device=db.get(MatrixDevice,1);device.capabilities={};db.commit()
        self.assertEqual(self.request('GET','/hub-v5/environments?executable=ready').json()['total'],0)
        self.assertEqual(self.request('GET','/hub-v5/environments?executable=blocked').json()['total'],1)
        self.beat()
        with self.sessions() as db:
            db.get(MatrixDevice,1).local_paused=True;db.commit()
        self.assertEqual(self.request('GET','/hub-v5/environments?executable=ready').json()['total'],0)
        self.beat()
        run,_=self.make_run();self.claim(run)
        self.assertEqual(self.request('GET','/hub-v5/environments?executable=ready').json()['total'],0)

    def test_shop_export_scope_search_formula_and_window(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        package=self.package();package['products'][0]['name']='=HYPERLINK("bad")'
        self.assertEqual(self.upload(item,creds,package)[1].status_code,200)
        response=self.request('GET',f'/hub-v5/shops/{shop}/export')
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn("'=HYPERLINK",response.text);self.assertIn('MYR',response.text)
        self.assertIn(package['header']['window_start'],response.text)
        self.assertNotIn('HYPERLINK',self.request('GET',f'/hub-v5/shops/{shop}/export?q=absent').text)
        self.assertEqual(self.request('GET',f'/hub-v5/shops/{shop}/export',uid=5).status_code,404)

    def test_unknown_timezone_is_validation_error(self):
        run,_=self.make_run();item,creds=self.claim(run);self.bind(item,creds)
        package=self.package();package['header']['timezone']='Invalid/Zone'
        response=self.ar('POST',f'/agent/items/{item}/collections',json={**creds,'content_hash':digest(package),'part_count':1,'header':package['header']})
        self.assertEqual(response.status_code,422,response.text)

    def test_run_idempotency_and_preview_revision(self):
        plan=self.plan();run,data=self.make_run(plan,key='same-run-key')
        response=self.client.post(f"/hub-v5/plans/{plan['id']}/runs",json=data,headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':'same-run-key'})
        self.assertEqual(response.json()['id'],run['id'])
        response=self.client.post(f"/hub-v5/plans/{plan['id']}/runs",json={**data,'expected_revision':99},headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':'same-run-key'})
        self.assertEqual(response.status_code,409)
        changed=self.request('PATCH',f"/hub-v5/plans/{plan['id']}",json={'name':'改名','agent_id':1,'operation_id':plan['operation_id'],'environment_ids':[self.env],'expected_revision':1})
        self.assertEqual(changed.status_code,200,changed.text)
        response=self.client.post(f"/hub-v5/plans/{plan['id']}/runs",json=data,headers={'Authorization':f'Bearer {self.tokens[1]}','Idempotency-Key':'new-run-key'})
        self.assertEqual(response.status_code,409)

    def test_missing_directory_part_preserves_access(self):
        row=self.ar('POST','/agent/environment-syncs',json={'snapshot_key':str(uuid4()),'hub_identity':'team-1','version':1999999999,'expected_count':0,'part_count':1}).json()
        self.assertEqual(self.ar('POST',f"/agent/environment-syncs/{row['id']}/commit",json={}).status_code,409)
        self.assertEqual(self.request('GET','/hub-v5/environments').json()['total'],1)

    def test_old_fence_cannot_report(self):
        run,_=self.make_run();item,creds=self.claim(run)
        with self.sessions() as db:
            attempt=db.get(MatrixAttempt,db.get(MatrixItem,item).attempt_id);attempt.lease_until=datetime.utcnow()-timedelta(seconds=1);db.commit()
        r=self.ar('POST',f'/agent/items/{item}/renew',json=creds);self.assertEqual(r.status_code,409)
        self.ar('GET','/agent/queue')
        self.assertEqual(self.request('GET',f"/hub-v5/runs/{run['id']}").json()['status'],'awaiting_attention')
        with self.sessions() as db:self.assertEqual(db.scalar(select(HubRuntimeLock)).matrix_item_id,item)

    def test_zero_does_not_overwrite_1038(self):
        run,_=self.make_run();item,creds=self.claim(run);shop=self.bind(item,creds)
        package=self.package()
        cid,result=self.upload(item,creds,package);self.assertEqual(result.status_code,200,result.text)
        with self.sessions() as db:
            old=db.get(MatrixCollection,cid);header=copy.deepcopy(old.header);header['expected_count']=1038;old.header=header;db.commit()
        _,result=self.upload(item,creds,self.package(0,empty_verified=False,total_verified=False))
        self.assertEqual(result.status_code,422)
        with self.sessions() as db:self.assertEqual(db.get(MatrixShop,shop).snapshot_id,cid)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'succeeded'}).status_code,409)

    def test_verified_empty_shop_can_publish(self):
        run,_=self.make_run();item,creds=self.claim(run);self.bind(item,creds)
        _,result=self.upload(item,creds,self.package(0,empty_verified=True));self.assertEqual(result.status_code,200,result.text)
        self.assertIsNone(result.json()['ctr']);self.assertEqual(result.json()['active'],0)

    def test_orders_are_separate_from_pending_shipments_and_preserve_unknown(self):
        run,_=self.make_run();item,creds=self.claim(run);self.bind(item,creds)
        for orders,total in ((None,None),(0,0),(37,1791)):
            with self.subTest(orders=orders,total=total):
                package=self.package()
                package['header']['metrics']={'orders_to_ship':5}
                if orders is not None:package['header']['metrics']['orders']=orders
                if total is not None:package['header']['metrics']['orders_total']=total
                _,result=self.upload(item,creds,package)
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(result.json().get('orders'),orders)
                self.assertEqual(result.json().get('orders_total'),total)
                rows=self.request('GET','/hub-v5/environments').json()['items']
                self.assertEqual(rows[0]['snapshot'].get('orders'),orders)
                self.assertEqual(rows[0]['snapshot'].get('orders_total'),total)
                self.assertEqual(rows[0]['snapshot']['orders_to_ship'],5)

    def test_orders_reject_negative_fractional_and_nonfinite_counts(self):
        run,_=self.make_run();item,creds=self.claim(run);self.bind(item,creds)
        for metric in ('orders','orders_total'):
            for value in (-1,'1.5','NaN','Infinity','unknown'):
                with self.subTest(metric=metric,value=value):
                    package=self.package();package['header']['metrics']={metric:value}
                    response=self.ar('POST',f'/agent/items/{item}/collections',json={**creds,
                        'content_hash':digest(package),'part_count':1,'header':package['header']})
                    self.assertEqual(response.status_code,422,response.text)

    def test_snapshot_digest_and_conflicting_parts(self):
        run,_=self.make_run();item,creds=self.claim(run);self.bind(item,creds)
        p=self.package();row=self.ar('POST',f'/agent/items/{item}/collections',json={**creds,'content_hash':'a'*64,'part_count':1,'header':p['header']}).json()
        path=f"/agent/items/{item}/collections/{row['id']}"
        self.assertEqual(self.ar('PUT',path+'/parts/0',json={**creds,'products':p['products']}).status_code,200)
        self.assertEqual(self.ar('PUT',path+'/parts/0',json={**creds,'products':[]}).status_code,409)
        self.assertEqual(self.ar('POST',path+'/commit',json=creds).status_code,422)

    def test_listing_frozen_combinations_and_unknown_submission(self):
        plan=self.plan(listing=True);run,_=self.make_run(plan);item,creds=self.claim(run);self.bind(item,creds)
        prep=self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds);self.assertEqual(prep.status_code,200,prep.text)
        with self.sessions() as db:
            row=db.get(MatrixItem,item);job=db.get(SupplyJob,row.supply_job_id)
            signatures=[combination_hash(job.template_id,l['materials']) for l in job.checkpoint['links']]
            self.assertEqual(len(set(signatures)),10)
            self.assertEqual(len(db.scalars(select(MatrixAllocation).where(MatrixAllocation.item_id==item)).all()),10)
            job.state='completed';job.output_size=100;job.output_sha256='a'*64;job.output_key='stub';job.output_expires_at=datetime.utcnow()+timedelta(days=7);db.commit()
        prep=self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds);self.assertEqual(prep.status_code,200,prep.text)
        self.assertEqual(prep.json()['expected_count'],10)
        intent=self.ar('POST',f'/agent/items/{item}/submission',json=creds);self.assertEqual(intent.status_code,200,intent.text)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/submission',json=creds).status_code,409)
        result=self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'failed','message':'回执丢失'})
        self.assertEqual(result.json()['status'],'awaiting_attention')
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(HubRuntimeLock)).matrix_item_id,item)
            self.assertFalse(any(a.state=='released' for a in db.scalars(select(MatrixAllocation))))

    def test_retry_reacquires_original_combinations_or_rejects_conflict(self):
        run,_=self.make_run(self.plan(listing=True));item,creds=self.claim(run);self.bind(item,creds)
        self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds)
        with self.sessions() as db:
            row=db.get(MatrixItem,item);job=db.get(SupplyJob,row.supply_job_id)
            job.state='completed';job.output_size=100;job.output_sha256='a'*64;job.output_key='stub';job.output_expires_at=datetime.utcnow()+timedelta(days=7);db.commit()
        self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds)
        self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'failed','message':'尚未提交'})
        with self.sessions() as db:
            allocations=db.scalars(select(MatrixAllocation).where(MatrixAllocation.item_id==item)).all()
            self.assertTrue(all(a.state=='released' for a in allocations))
            allocations[-1].item_id=999;allocations[-1].state='reserved';db.commit()
        response=self.request('POST',f'/hub-v5/run-items/{item}/resolve',json={'action':'retry','evidence':'已核对明确尚未提交'})
        self.assertEqual(response.status_code,409,response.text)
        with self.sessions() as db:
            allocations=db.scalars(select(MatrixAllocation).where(MatrixAllocation.shop_id==1)).all()
            self.assertEqual(sum(a.state=='prepared' for a in allocations),0)
            for a in allocations:
                if a.item_id==999:a.state='released'
            db.commit()
        response=self.request('POST',f'/hub-v5/run-items/{item}/resolve',json={'action':'retry','evidence':'已核对明确尚未提交'})
        self.assertEqual(response.status_code,200,response.text)
        with self.sessions() as db:self.assertTrue(all(a.item_id==item and a.state=='prepared' for a in db.scalars(select(MatrixAllocation))))

    def test_manual_resolution_does_not_require_evidence(self):
        run,_=self.make_run();item,creds=self.claim(run)
        with self.sessions() as db:
            row=db.get(MatrixItem,item);row.status='failed';row.submission='not_started';db.commit()
        response=self.request('POST',f'/hub-v5/run-items/{item}/resolve',json={'action':'cancel'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'cancelled')
        with self.sessions() as db:
            event=db.scalars(select(MatrixEvent).where(MatrixEvent.run_id==run['id'],MatrixEvent.kind=='manual.resolve')).one()
            self.assertEqual(event.payload,{'action':'cancel','evidence':'','item_id':item})

    def test_partial_known_acceptance_cannot_replay_entire_file(self):
        run,_=self.make_run();item,creds=self.claim(run)
        with self.sessions() as db:
            row=db.get(MatrixItem,item);row.status='awaiting_attention';row.submission='unknown';row.result={'listing':{'accepted':[0],'rejected':[]}};db.commit()
        response=self.request('POST',f'/hub-v5/run-items/{item}/resolve',json={'action':'retry','evidence':'尝试重试含已确认商品的文件'})
        self.assertEqual(response.status_code,409,response.text)

    def test_manual_confirmation_preserves_known_rejections_and_their_new_owner(self):
        run,_=self.make_run(self.plan(listing=True,tasks=['listing.catalog']));item,creds=self.claim(run);self.bind(item,creds)
        self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds)
        with self.sessions() as db:
            job=db.get(SupplyJob,db.get(MatrixItem,item).supply_job_id)
            job.state='completed';job.output_size=100;job.output_sha256='a'*64;job.output_key='stub';job.output_expires_at=datetime.utcnow()+timedelta(days=7);db.commit()
        self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds)
        self.ar('POST',f'/agent/items/{item}/submission',json=creds)
        response=self.ar('POST',f'/agent/items/{item}/listing-result',json={**creds,'accepted':[0],'rejected':[1],'receipt':'部分明确受理，其余未知'})
        self.assertEqual(response.status_code,200,response.text)
        self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'failed'})
        with self.sessions() as db:
            rejected=next(a for a in db.scalars(select(MatrixAllocation)) if a.payload['index']==1)
            rid=rejected.id;rejected.item_id=999;rejected.state='reserved';db.commit()
        response=self.request('POST',f'/hub-v5/run-items/{item}/resolve',json={'action':'confirm-submitted'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'partial_success')
        self.assertEqual(response.json()['result']['listing']['rejected'],[1])
        self.assertEqual(response.json()['result']['listing']['receipt'],'人工核对确认提交')
        with self.sessions() as db:
            self.assertEqual((db.get(MatrixAllocation,rid).item_id,db.get(MatrixAllocation,rid).state),(999,'reserved'))
            self.assertEqual(sum(a.state=='confirmed' for a in db.scalars(select(MatrixAllocation))),9)

    def test_admin_cannot_borrow_another_owner_strategy(self):
        strategy=self.create_strategy(uid=2)
        r=self.request('POST','/hub-v5/operations',json={'name':'错误策略','tasks':['listing.catalog'],'strategies':{'MY':strategy}})
        self.assertEqual(r.status_code,404)

    def test_csv_formula_and_unknown_are_preserved(self):
        with self.sessions() as db:db.get(MatrixEnvironment,self.env).name='=HYPERLINK("bad")';db.commit()
        response=self.request('GET','/hub-v5/exports')
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn("'=HYPERLINK",response.text)
        self.assertNotIn('None',response.text)

    def test_stop_does_not_fake_active_cancellation(self):
        run,_=self.make_run();item,creds=self.claim(run)
        self.request('POST',f"/hub-v5/runs/{run['id']}/stop",json={})
        self.assertTrue(self.ar('POST',f'/agent/items/{item}/renew',json=creds).json()['stop_requested'])
        self.assertEqual(self.request('GET',f"/hub-v5/runs/{run['id']}").json()['items'][0]['status'],'running')

    def test_real_supply_workbook_uses_reserved_groups(self):
        import asyncio
        from collections import Counter
        from io import BytesIO
        from openpyxl import load_workbook
        from app.supply_worker import claim_job,run_job
        from app.supply_quota import QUOTA_VERSION, sku_use_counts
        with self.sessions() as db:
            history = SupplyJob(company_id=1, user_id=1, template_id=1, category_catalog_id=1,
                category_blob=b'old', idempotency_key='history', request_hash='x', state='completed')
            db.add(history);db.flush()
            for identity, count in ((1, 3), (2, 2)):
                db.add_all(SupplyJobMaterial(company_id=1, job_id=history.id, material_id=identity,
                    sku=f'SOURCE{identity:03d}', version_hash=f'old-{index}', link_index=index,
                    successful=True) for index in range(count))
            db.commit()
        plan=self.plan(listing=True);run,_=self.make_run(plan);item,creds=self.claim(run);self.bind(item,creds)
        self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds)
        with self.sessions() as db:
            prepared = db.get(SupplyJob, db.get(MatrixItem, item).supply_job_id)
            self.assertEqual(prepared.checkpoint['quota_version'], QUOTA_VERSION)
            planned = copy.deepcopy(prepared.checkpoint['links'])
            counts = Counter(m['sku'] for link in planned for m in link['materials'])
            self.assertEqual(counts['SOURCE001'], 0)
            self.assertLessEqual(counts['SOURCE002'], 1)
            self.assertLessEqual(max(counts.values()), 3)
        claimed=claim_job(self.sessions)
        files={}
        def upload(company,job,epoch,filename,content):
            files['content']=content
            return {'key':'test-fixed-file','sha256':hashlib.sha256(content).hexdigest(),'size':len(content)}
        with patch('app.supply_worker.upload_supply_export',side_effect=upload):asyncio.run(run_job(*claimed,session_factory=self.sessions))
        with self.sessions() as db:
            job=db.get(SupplyJob,claimed[0]);self.assertEqual(job.state,'completed',job.error)
            reserved={a.combination_hash for a in db.scalars(select(MatrixAllocation).where(MatrixAllocation.item_id==item))}
            self.assertEqual(reserved,{combination_hash(job.template_id,l['materials']) for l in job.checkpoint['links']})
            self.assertEqual([link['materials'] for link in planned],
                             [link['materials'] for link in job.checkpoint['links']])
            self.assertLessEqual(max(sku_use_counts(db, 1, 1, counts).values()), 3)
        book=load_workbook(BytesIO(files['content']),read_only=True)
        self.assertGreater(len(book.sheetnames),0)
        ready=self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds)
        self.assertEqual(ready.json()['status'],'ready',ready.text)
        with patch('app.hub_v5.listing.read_supply_export',return_value=files['content']):
            response=self.ar('POST',f'/agent/items/{item}/file',json=creds)
            self.assertEqual(response.content,files['content'])
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/submission',json=creds).status_code,200)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/listing-result',json={**creds,'accepted':list(range(10)),'rejected':[],'receipt':'平台明确受理全部10组'}).status_code,200)
        cid,response=self.upload(item,creds,self.package());self.assertEqual(response.status_code,200,response.text)
        result=self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'succeeded'})
        self.assertEqual(result.status_code,200,result.text)

    def test_listing_rejects_insufficient_quota_without_reserving_combinations(self):
        plan=self.plan(listing=True);run,_=self.make_run(plan);item,creds=self.claim(run);self.bind(item,creds)
        with patch('app.hub_v5.listing.sku_use_counts', return_value={f'SOURCE{i:03d}': 3 for i in range(1, 21)}):
            response=self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds)
        self.assertEqual(response.status_code,422,response.text)
        with self.sessions() as db:
            self.assertIsNone(db.get(MatrixItem,item).supply_job_id)
            self.assertEqual(list(db.scalars(select(MatrixAllocation))), [])

    def test_schedule_single_fire_and_offline_missed(self):
        from app.hub_v5.worker import schedule_plan
        now=datetime.now(timezone.utc).replace(second=30,microsecond=0)
        plan=self.plan(scheduled=True,time=now.astimezone(timezone(timedelta(hours=8))).strftime('%H:%M'),timezone='UTC')
        with self.sessions() as db:
            db.get(MatrixPlan,plan['id']).updated_at=now.replace(tzinfo=None)-timedelta(minutes=1);db.commit()
        for _ in range(2):
            with self.sessions() as db:schedule_plan(db,plan['id'],now)
        with self.sessions() as db:
            fires=db.scalars(select(MatrixFire).where(MatrixFire.plan_id==plan['id'])).all()
            self.assertEqual(len(fires),1);self.assertEqual(fires[0].status,'created')
            self.assertEqual(len(db.scalars(select(MatrixRun)).all()),1)

    def test_scheduled_shop_selection_is_exact_and_uses_beijing_time(self):
        from app.hub_v5.worker import schedule_plan
        ids=self.sync(1,[{'container_code':'env-1','name':'测试环境','group_name':'分组A','site':'MY'},
            {'container_code':'env-2','name':'同组另一店铺','group_name':'分组A','site':'MY'}],version=9999999999)
        now=datetime.now(timezone.utc).replace(second=30,microsecond=0)
        plan=self.plan(scheduled=True,environment_ids=[self.env],time=now.astimezone(timezone(timedelta(hours=8))).strftime('%H:%M'),timezone='UTC')
        self.assertEqual(plan['timezone'],'Asia/Shanghai')
        with self.sessions() as db:
            db.get(MatrixPlan,plan['id']).updated_at=now.replace(tzinfo=None)-timedelta(minutes=1);db.commit()
        with self.sessions() as db:schedule_plan(db,plan['id'],now)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(MatrixFire)).status,'created')
            self.assertEqual(list(db.scalars(select(MatrixItem.environment_id))),[self.env])

    def test_scheduled_selection_checks_device_and_allows_shared_shops(self):
        plan=self.plan(scheduled=True,environment_ids=[self.env])
        for targets,agent in (([],1),([999999],1),([self.env],2)):
            result=self.request('POST','/hub-v5/plans',json={'name':'错误计划','agent_id':agent,'operation_id':plan['operation_id'],'scheduled':True,'environment_ids':targets})
            self.assertEqual(result.status_code,422,result.text)
        self.plan(scheduled=True,environment_ids=[self.env],time='18:00')
        duplicate=self.request('POST','/hub-v5/plans',json={'name':'重复','agent_id':1,'operation_id':plan['operation_id'],'environment_ids':[self.env,self.env]})
        self.assertEqual(duplicate.status_code,422)

    def test_plan_shop_options_are_device_scoped(self):
        result=self.request('GET','/hub-v5/plan-environments?agent_id=1')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual([row['id'] for row in result.json()['items']],[self.env])
        self.assertEqual(self.request('GET','/hub-v5/plan-environments?agent_id=2').json()['items'],[])
        self.assertEqual(self.request('GET','/hub-v5/plan-environments?agent_id=3').status_code,422)
        self.assertEqual(self.request('GET','/hub-v5/plan-environments?agent_id=1',uid=2).status_code,422)

    def test_offline_schedule_is_missed_and_not_replayed(self):
        from app.hub_v5.worker import schedule_plan
        now=datetime.now(timezone.utc).replace(second=30,microsecond=0)
        plan=self.plan(scheduled=True,time=now.astimezone(timezone(timedelta(hours=8))).strftime('%H:%M'),timezone='UTC')
        with self.sessions() as db:
            db.get(MatrixPlan,plan['id']).updated_at=now.replace(tzinfo=None)-timedelta(minutes=1)
            db.get(HubAgent,1).last_seen_at=now.replace(tzinfo=None)-timedelta(hours=1);db.commit()
        with self.sessions() as db:schedule_plan(db,plan['id'],now)
        self.beat()
        with self.sessions() as db:schedule_plan(db,plan['id'],now+timedelta(seconds=15))
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(MatrixFire)).status,'missed')
            self.assertEqual(len(db.scalars(select(MatrixRun)).all()),0)

    def test_signed_release_is_company_scoped_and_immutable(self):
        import base64
        from io import BytesIO
        import zipfile
        from types import SimpleNamespace
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        key=Ed25519PrivateKey.generate();content=BytesIO()
        with zipfile.ZipFile(content,'w') as z:z.writestr('plugin.py','CAPABILITIES={}\n')
        body=content.getvalue()
        manifest={'kind':'plugin','version':'5.0.1','platform':'macos','arch':'arm64','sha256':hashlib.sha256(body).hexdigest(),'size':len(body),
            'key_id':'test','protocol_min':5,'protocol_max':5,'entrypoint':'plugin.py','files':{'plugin.py':hashlib.sha256(b'CAPABILITIES={}\n').hexdigest()}}
        manifest['signature']=base64.b64encode(key.sign(json.dumps(manifest,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())).decode()
        public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()
        storage=__import__('unittest.mock',fromlist=['MagicMock']).MagicMock()
        storage.get_object.side_effect=lambda **kw:{'Body':BytesIO(body)}
        settings=SimpleNamespace(matrix_release_public_keys=json.dumps({'test':public}))
        with patch('app.hub_v5.releases.get_settings',return_value=settings),patch('app.hub_v5.releases.location',return_value=(storage,'private','release-key')):
            response=self.client.post('/hub-v5/releases',headers={'Authorization':f'Bearer {self.tokens[1]}'},data={'manifest_json':json.dumps(manifest),'enabled':'true'},files={'artifact':('plugin.zip',body,'application/zip')})
            self.assertEqual(response.status_code,200,response.text);identity=response.json()['id']
            downloaded=self.ar('GET',f'/agent/releases/{identity}/file');self.assertEqual(downloaded.content,body)
            self.assertEqual(self.ar('GET',f'/agent/releases/{identity}/file',3).status_code,404)
            manifest['version']='5.0.2'
            response=self.client.post('/hub-v5/releases',headers={'Authorization':f'Bearer {self.tokens[1]}'},data={'manifest_json':json.dumps(manifest),'enabled':'true'},files={'artifact':('plugin.zip',body,'application/zip')})
            self.assertEqual(response.status_code,422)

    def test_failed_pre_submission_releases_legacy_running_state(self):
        plan=self.plan(listing=True);run,_=self.make_run(plan);item,creds=self.claim(run);self.bind(item,creds)
        self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds)
        with self.sessions() as db:
            job=db.get(SupplyJob,db.get(MatrixItem,item).supply_job_id)
            job.state='completed';job.output_size=10;job.output_sha256='a'*64;job.output_key='test';job.output_expires_at=datetime.utcnow()+timedelta(days=1);db.commit()
        self.ar('POST',f'/agent/items/{item}/listing-preparations',json=creds)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/report',json={**creds,'status':'failed','message':'尚未导入'}).status_code,200)
        with self.sessions() as db:self.assertEqual(db.get(HubUploadTask,db.get(MatrixItem,item).upload_task_id).status,'failed')

    def test_bulk_preview_uses_lines_and_freezes_executor(self):
        plan=self.plan()
        result=self.request('POST',f"/hub-v5/operations/{plan['operation_id']}/preview",json={'agent_id':1,'all_filtered':True,'filters':{'exact':'env-1\nno-match','agent_id':''}})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual([e['id'] for e in result.json()['environments']],[self.env])
        run,data=self.make_run(plan)
        with self.sessions() as db:db.get(MatrixDevice,1).version='5.0.1';db.commit()
        r=self.ar('POST',f"/agent/items/{run['items'][0]['id']}/claim",json={})
        self.assertEqual(r.status_code,409)
        self.assertEqual(self.request('GET',f"/hub-v5/runs/{run['id']}").json()['status'],'failed')

    def test_batch_activity_preserves_site_and_validates_values(self):
        target = {'environments':[{'id':self.env,'expected_revision':1}]}
        result = self.request('PATCH','/hub-v5/environments/overrides',json={**target,'activity_status':'closed'})
        self.assertEqual(result.status_code,200,result.text)
        row = self.request('GET','/hub-v5/environments').json()['items'][0]
        self.assertEqual(row['site'],'MY')
        self.assertEqual(row['activity_status'],'closed')
        for value in ('normal','unchecked'):
            result = self.request('PATCH','/hub-v5/environments/overrides',json={**target,
                'environments':[{'id':self.env,'expected_revision':row['revision']}], 'activity_status':value})
            self.assertEqual(result.status_code,200,result.text)
            row = self.request('GET','/hub-v5/environments').json()['items'][0]
            self.assertEqual(row['activity_status'],value)
        result = self.request('PATCH','/hub-v5/environments/overrides',json={**target,
            'environments':[{'id':self.env,'expected_revision':row['revision']}], 'site':'ID'})
        self.assertEqual(result.status_code,200,result.text)
        row = self.request('GET','/hub-v5/environments').json()['items'][0]
        self.assertEqual(row['activity_status'],'unchecked')
        for extra in ({},{'activity_status':'invalid'},{'activity_status':None}):
            result = self.request('PATCH','/hub-v5/environments/overrides',json={**target,**extra})
            self.assertEqual(result.status_code,422,result.text)

    def test_group_options_include_all_accessible_groups_and_ungrouped(self):
        self.sync(1,[{'container_code':'env-1','name':'测试环境','group_name':'分组A','site':'MY'},
            {'container_code':'env-2','name':'第二环境','group_name':'分组B','site':'ID'},
            {'container_code':'env-3','name':'第三环境','group_name':'','site':'MY'}],version=1999999999)
        result = self.request('GET','/hub-v5/environments',params={'group':'分组A','page_size':1}).json()
        self.assertEqual(result['total'],1)
        self.assertEqual(result['groups'],['','分组A','分组B'])
        result = self.request('GET','/hub-v5/environments',params={'ungrouped':True}).json()
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['group'],'')
        self.assertEqual(self.request('GET','/hub-v5/environments',uid=2).json()['groups'],[])

    def test_batch_override_is_atomic_on_revision_conflict(self):
        second=self.sync(1,[{'container_code':'env-1','name':'测试环境','group_name':'分组A','site':'MY'},
            {'container_code':'env-2','name':'第二环境','group_name':'分组A','site':'MY'}],version=1999999999)[1]
        result=self.request('PATCH','/hub-v5/environments/overrides',json={'environments':[{'id':self.env,'expected_revision':1},{'id':second,'expected_revision':99}],
            'site':'ID','reason':'批量站点核对'})
        self.assertEqual(result.status_code,409)
        with self.sessions() as db:self.assertIsNone(db.get(MatrixEnvironment,self.env).override_site)


    def member_run(self):
        self.agent_tokens[8]='e'*48
        with self.sessions() as db:
            db.add(HubAgent(id=8,company_id=1,user_id=2,name='成员电脑',platform='macos',is_active=True,token_hash=hashlib.sha256(self.agent_tokens[8].encode()).hexdigest(),last_seen_at=datetime.utcnow()))
            db.commit()
        self.beat(8)
        env=self.sync(8,[{'container_code':'member-env','name':'成员环境','group_name':'分组A','site':'MY'}])[0]
        operation=self.operation(uid=2)
        plan=self.request('POST','/hub-v5/plans',uid=2,json={'name':'成员方案','agent_id':8,'operation_id':operation['id'],'environment_ids':[env]}).json()
        preview=self.request('POST',f"/hub-v5/plans/{plan['id']}/preview",uid=2,json={})
        self.assertEqual(preview.status_code,200,preview.text)
        run=self.client.post(f"/hub-v5/plans/{plan['id']}/runs",json={'preview_token':preview.json()['preview_token'],'expected_revision':plan['revision']},headers={'Authorization':f'Bearer {self.tokens[2]}','Idempotency-Key':str(uuid4())})
        self.assertEqual(run.status_code,200,run.text)
        return run.json()

    def test_member_authorization_is_enforced_and_admin_endpoints_are_isolated(self):
        for path in ('/hub-v5/admin/members','/hub-v5/admin/devices','/hub-v5/admin/statistics'):
            self.assertEqual(self.request('GET',path,uid=2).status_code,403)
        self.assertEqual(self.request('GET','/hub-v5/access',uid=2).json()['enabled'],True)
        with self.sessions() as db:db.delete(db.get(MatrixMemberPermission,2));db.commit()
        self.assertFalse(self.request('GET','/hub-v5/access',uid=2).json()['enabled'])
        self.assertEqual(self.request('GET','/hub-v5/environments',uid=2).status_code,403)
        body={'enabled':True,'collect_enabled':True,'listing_enabled':False,'view_scope':'own','expected_revision':0}
        self.assertEqual(self.request('PUT','/hub-v5/admin/members/2',uid=5,json=body).status_code,404)
        saved=self.request('PUT','/hub-v5/admin/members/2',json=body)
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(self.request('PUT','/hub-v5/admin/members/2',json=body).status_code,409)
        self.assertTrue(saved.json()['collect_enabled'])
        self.assertTrue(saved.json()['listing_enabled'])
        self.operation(listing=True,uid=2)
        self.assertEqual(self.request('PUT','/hub-v5/admin/members/1',json=body).status_code,403)

    def test_unified_grant_ignores_legacy_task_flags_and_supply_defaults_off(self):
        with self.sessions() as db:
            row=db.get(MatrixMemberPermission,2)
            row.collect_enabled=row.listing_enabled=False
            db.commit()
        access=self.request('GET','/hub-v5/access',uid=2).json()
        self.assertTrue(access['enabled'])
        self.assertTrue(access['collect_enabled'])
        self.assertTrue(access['listing_enabled'])
        self.operation(uid=2)
        self.operation(listing=True,uid=2)
        saved=self.request('PUT','/hub-v5/admin/members/2',json={'enabled':True,'view_scope':'own','expected_revision':1})
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertTrue(saved.json()['collect_enabled'])
        self.assertTrue(saved.json()['listing_enabled'])
        self.assertFalse(self.request('GET','/hub-v5/access',uid=4).json()['enabled'])
        self.assertEqual(self.request('PUT','/supply/users/4/matrix',json={'enabled':True,'expected_revision':0}).status_code,200)

    def supply_matrix_run(self, listing=False):
        grant=self.request('PUT','/supply/users/4/matrix',json={'enabled':True,'expected_revision':0})
        self.assertEqual(grant.status_code,200,grant.text)
        self.agent_tokens[8]='e'*48
        with self.sessions() as db:
            db.add(HubAgent(id=8,company_id=1,user_id=4,name='货盘电脑',platform='macos',is_active=True,
                token_hash=hashlib.sha256(self.agent_tokens[8].encode()).hexdigest(),last_seen_at=datetime.utcnow()))
            db.commit()
        self.beat(8)
        env=self.sync(8,[{'container_code':'supply-env','name':'货盘环境','group_name':'货盘','site':'MY'}])[0]
        operation=self.operation(listing=listing,uid=4)
        response=self.request('POST','/hub-v5/plans',uid=4,json={'name':'货盘计划','agent_id':8,'operation_id':operation['id'],'environment_ids':[env]})
        self.assertEqual(response.status_code,200,response.text)
        plan=response.json()
        preview=self.request('POST',f"/hub-v5/plans/{plan['id']}/preview",uid=4,json={})
        self.assertEqual(preview.status_code,200,preview.text)
        self.assertEqual(preview.json()['errors'],[])
        run=self.client.post(f"/hub-v5/plans/{plan['id']}/runs",json={'preview_token':preview.json()['preview_token'],'expected_revision':plan['revision']},headers={'Authorization':f'Bearer {self.tokens[4]}','Idempotency-Key':str(uuid4())})
        self.assertEqual(run.status_code,200,run.text)
        return run.json()

    def test_supply_matrix_full_run_and_own_data_isolation(self):
        foreign_run,_=self.make_run()
        run=self.supply_matrix_run(listing=True)
        members=self.request('GET','/hub-v5/admin/members').json()['items']
        self.assertEqual(next(m for m in members if m['id']==4)['role'],'supply_user')
        self.assertEqual(self.request('GET','/hub-v5/environments',uid=4).json()['total'],1)
        self.assertTrue(all(d['user_id']==4 for d in self.request('GET','/hub-v5/agents',uid=4).json()))
        self.assertEqual(self.request('GET',f"/hub-v5/runs/{foreign_run['id']}",uid=4).status_code,404)
        self.assertEqual(self.request('POST','/hub-v5/agents/1/commands',uid=4,json={'kind':'pause'}).status_code,404)
        self.assertEqual(self.request('GET','/hub-v5/admin/members',uid=4).status_code,403)
        self.assertEqual(self.request('PUT','/supply/users/4/matrix',json={'enabled':True,'view_scope':'company','expected_revision':1}).status_code,422)
        with self.sessions() as db:
            db.get(MatrixMemberPermission,4).view_scope='company';db.commit()
        self.assertEqual(self.request('GET','/hub-v5/access',uid=4).json()['view_scope'],'own')
        self.assertEqual(self.request('GET','/hub-v5/environments',uid=4).json()['total'],1)
        item,creds=self.claim(run,8)
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/environment-target',8,json=creds).status_code,200)
        response=self.ar('POST',f'/agent/items/{item}/listing-preparations',8,json=creds)
        self.assertEqual(response.status_code,200,response.text)
        with self.sessions() as db:
            job=db.get(SupplyJob,db.get(MatrixItem,item).supply_job_id)
            self.assertEqual((job.user_id,job.agent_id,job.agent_name),(4,1,'原代理'))
            self.assertFalse(job.snapshot['internal_usage'])
        revoke=self.request('PUT','/supply/users/4/matrix',json={'enabled':False,'expected_revision':1})
        self.assertEqual(revoke.status_code,200,revoke.text)
        self.assertEqual(self.request('GET','/hub-v5/environments',uid=4).status_code,403)
        self.assertEqual(self.ar('GET','/agent/queue',8).json()['items'],[])
        with self.sessions() as db:self.assertTrue(db.get(MatrixRun,run['id']).stop_requested)

    def test_supply_matrix_permission_has_single_admin_entry_and_revision(self):
        rows=self.request('GET','/supply/users').json()['items']
        account=next(row for row in rows if row['id']==4)
        self.assertFalse(account['matrix_enabled'])
        self.assertEqual(account['matrix_revision'],0)
        self.assertEqual(self.request('PUT','/hub-v5/admin/members/4',json={'enabled':True,'expected_revision':0}).status_code,404)
        for uid in (2,3,4):
            self.assertEqual(self.request('PUT','/supply/users/4/matrix',uid=uid,json={'enabled':True,'expected_revision':0}).status_code,403)
        self.assertEqual(self.request('PUT','/supply/users/4/matrix',uid=5,json={'enabled':True,'expected_revision':0}).status_code,404)
        enabled=self.request('PUT','/supply/users/4/matrix',json={'enabled':True,'expected_revision':0})
        self.assertEqual(enabled.status_code,200,enabled.text)
        self.assertTrue(enabled.json()['matrix_enabled'])
        self.assertEqual(enabled.json()['matrix_revision'],1)
        self.assertEqual(self.request('PUT','/supply/users/4/matrix',json={'enabled':False,'expected_revision':0}).status_code,409)
        self.assertTrue(self.request('GET','/hub-v5/access',uid=4).json()['enabled'])
        with self.sessions() as db:db.get(User,4).is_active=False;db.commit()
        disabled=self.request('PUT','/supply/users/4/matrix',json={'enabled':False,'expected_revision':1})
        self.assertEqual(disabled.status_code,200,disabled.text)
        self.assertFalse(disabled.json()['matrix_enabled'])

    def test_supply_matrix_expiry_blocks_jwt_agent_and_scheduler(self):
        run=self.supply_matrix_run()
        with self.sessions() as db:
            db.get(User,4).supply_expires_at=datetime.utcnow()-timedelta(seconds=1)
            plan=db.get(MatrixPlan,run['plan_id']);plan.config={**plan.config,'scheduled':True,'time':'09:00','timezone':'Asia/Shanghai'}
            db.commit()
        self.assertEqual(self.request('GET','/hub-v5/access',uid=4).status_code,401)
        self.assertEqual(self.ar('GET','/agent/config',8).status_code,401)
        self.assertEqual(self.request('PUT','/supply/users/4/matrix',json={'enabled':True,'expected_revision':1}).status_code,409)
        from app.hub_v5.worker import schedule_plan
        from app.hub_v5 import permissions
        with self.sessions() as db:
            self.assertFalse(permissions.access(db,db.get(User,4))['enabled'])
            schedule_plan(db,run['plan_id'])
            self.assertIsNone(db.scalar(select(MatrixFire)))
            db.get(User,4).supply_expires_at=datetime.utcnow()+timedelta(days=1)
            db.get(User,4).is_active=False;db.commit()
        self.assertEqual(self.request('GET','/hub-v5/access',uid=4).status_code,401)
        self.assertEqual(self.ar('GET','/agent/config',8).status_code,401)

    def test_supply_matrix_pairing_requires_grant_and_does_not_open_internal_routes(self):
        from app import main
        for path,endpoint,method in (
            ('/hub-agent/pairings',main.create_hub_agent_pairing,'POST'),
            ('/hub-agent/pairings/complete',main.complete_hub_agent_pairing,'POST'),
            ('/hub-agents/register',main.register_hub_agent,'POST'),
            ('/hub-agent/templates',main.hub_agent_templates,'GET'),
            ('/templates',main.list_templates,'GET')):
            self.app.add_api_route(path,endpoint,methods=[method])
        code=self.client.post('/hub-agent/pairings',json={'name':'货盘配对电脑','platform':'macos'}).json()['code']
        self.assertEqual(self.request('POST','/hub-agent/pairings/complete',uid=4,json={'code':code}).status_code,403)
        self.assertEqual(self.request('POST','/hub-agents/register',uid=4,json={'name':'货盘注册电脑','platform':'macos'}).status_code,403)
        self.assertEqual(self.request('PUT','/supply/users/4/matrix',json={'enabled':True,'expected_revision':0}).status_code,200)
        paired=self.request('POST','/hub-agent/pairings/complete',uid=4,json={'code':code})
        self.assertEqual(paired.status_code,200,paired.text)
        registered=self.request('POST','/hub-agents/register',uid=4,json={'name':'货盘注册电脑','platform':'macos'})
        self.assertEqual(registered.status_code,200,registered.text)
        self.assertEqual(registered.json()['agent']['user_id'],4)
        legacy=self.client.get('/hub-agent/templates',headers={'X-Hub-Protocol':main.hub.PROTOCOL,'X-Hub-Agent-Token':registered.json()['agent_token']})
        self.assertEqual(legacy.status_code,403,legacy.text)
        self.assertEqual(self.request('GET','/templates',uid=4).status_code,403)
        with self.sessions() as db:db.get(HubAgent,1).is_active=False;db.commit()
        self.assertEqual(self.request('POST','/hub-agents/register',uid=4,json={'name':'电脑1','platform':'macos'}).status_code,403)

    def test_company_view_is_read_only_for_other_members_runs_and_devices(self):
        run,_=self.make_run()
        with self.sessions() as db:db.get(MatrixMemberPermission,2).view_scope='company';db.commit()
        self.assertEqual(self.request('GET','/hub-v5/environments',uid=2).json()['total'],1)
        self.assertEqual(self.request('GET',f"/hub-v5/runs/{run['id']}",uid=2).status_code,200)
        self.assertEqual(self.request('POST',f"/hub-v5/runs/{run['id']}/stop",uid=2,json={}).status_code,404)
        self.assertEqual(self.request('POST','/hub-v5/agents/1/commands',uid=2,json={'kind':'pause'}).status_code,404)
        self.assertEqual(self.request('GET','/hub-v5/agents').json()[0]['user_id'],1)
        self.assertTrue(all(d['user_id']==2 for d in self.request('GET','/hub-v5/agents',uid=2).json()))

    def test_revocation_stops_active_runs_but_allows_final_reports_without_releasing_unknown_locks(self):
        run=self.member_run();item,creds=self.claim(run,8)
        result=self.request('PUT','/hub-v5/admin/members/2',json={'enabled':False,'expected_revision':1})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.ar('GET','/agent/queue',8).json()['items'],[])
        with self.sessions() as db:lease_before=db.get(MatrixAttempt,db.get(MatrixItem,item).attempt_id).lease_until
        renewed=self.ar('POST',f'/agent/items/{item}/renew',8,json=creds)
        self.assertEqual(renewed.status_code,200,renewed.text);self.assertTrue(renewed.json()['stop_requested'])
        with self.sessions() as db:self.assertEqual(db.get(MatrixAttempt,db.get(MatrixItem,item).attempt_id).lease_until,lease_before)
        denied=self.ar('POST',f'/agent/items/{item}/identity',8,json={**creds,'identity':{'site':'MY','external_id':'must-not-bind','name':'禁止新操作'}})
        self.assertEqual(denied.status_code,403)
        report=self.ar('POST',f'/agent/items/{item}/report',8,json={**creds,'status':'awaiting_attention','message':'权限收回，已停止'})
        self.assertEqual(report.status_code,200,report.text)
        with self.sessions() as db:
            self.assertEqual(db.get(MatrixRun,run['id']).status,'awaiting_attention')
            self.assertEqual(db.scalar(select(HubRuntimeLock).where(HubRuntimeLock.matrix_item_id==item)).matrix_item_id,item)

    def test_revoked_unknown_submission_can_be_manually_cancelled_without_retrying_or_losing_the_record(self):
        run=self.member_run();item,creds=self.claim(run,8);shop=self.bind(item,creds,agent=8)
        with self.sessions() as db:
            task=HubUploadTask(company_id=1,created_by=2,agent_id=8,matrix_item_id=item,export_filename='unknown.xlsx',status='awaiting_attention')
            db.add(task);db.flush()
            row=db.get(MatrixItem,item);row.upload_task_id=task.id;row.submission='unknown';row.status='awaiting_attention'
            record=db.get(MatrixRun,run['id']);record.status='awaiting_attention';record.frozen={**record.frozen,'config':{'tasks':['listing.catalog']}}
            db.add(MatrixAllocation(company_id=1,shop_id=shop,combination_hash='f'*64,item_id=item,state='unknown',payload={}))
            db.commit();task_id=task.id
        self.assertEqual(self.request('PUT','/hub-v5/admin/members/2',json={'enabled':False,'expected_revision':1}).status_code,200)
        path=f'/hub-v5/run-items/{item}/resolve'
        self.assertEqual(self.request('POST',path,json={'action':'cancel','evidence':'平台已经核对没有提交'}).status_code,409)
        with self.sessions() as db:
            row=db.get(MatrixItem,item);row.result={'listing':{'accepted':[0]}};db.commit()
        self.assertEqual(self.request('POST',path,json={'action':'confirm-not-submitted','evidence':'平台已经核对没有提交'}).status_code,409)
        with self.sessions() as db:db.get(MatrixItem,item).result={};db.commit()
        result=self.request('POST',path,json={'action':'confirm-not-submitted','evidence':'平台已经核对没有任何商品提交'})
        self.assertEqual(result.status_code,200,result.text)
        with self.sessions() as db:
            self.assertEqual(db.get(HubUploadTask,task_id).status,'cancelled')
            self.assertEqual(db.get(HubUploadTask,task_id).resolved_by,1)
            self.assertEqual(db.get(MatrixItem,item).submission,'not_started')
            self.assertEqual(db.scalar(select(MatrixAllocation.state).where(MatrixAllocation.item_id==item)),'released')
            self.assertIsNone(db.scalar(select(HubRuntimeLock).where(HubRuntimeLock.company_id==1)).matrix_item_id)

    def test_claim_and_scheduler_recheck_matrix_grant(self):
        run=self.member_run();item=run['items'][0]['id']
        with self.sessions() as db:
            db.get(MatrixMemberPermission,2).enabled=False
            plan=db.get(MatrixPlan,run['plan_id']);plan.config={**plan.config,'scheduled':True,'time':'09:00','timezone':'Asia/Shanghai'};db.commit()
        self.assertEqual(self.ar('POST',f'/agent/items/{item}/claim',8,json={}).status_code,403)
        from app.hub_v5.worker import schedule_plan
        with self.sessions() as db:
            schedule_plan(db,run['plan_id']);self.assertEqual(db.scalar(select(__import__('sqlalchemy').func.count()).select_from(MatrixFire)),0)

    def test_admin_statistics_are_tenant_scoped_deduplicated_and_use_hong_kong_dates(self):
        with self.sessions() as db:
            db.add(MatrixShop(id=50,company_id=1,site='MY',external_id='same-shop',name='同店'))
            db.get(MatrixEnvironment,self.env).shop_id=50
            env=MatrixEnvironment(company_id=1,hub_identity='team-1',container_code='second-env',name='同店另一个环境',shop_id=50,observed_site='MY');db.add(env);db.flush()
            db.add(MatrixAccess(agent_id=2,environment_id=env.id,available=True))
            for identity,owner,agent,company,status,task,created in (
                (10,1,1,1,'succeeded','shop.collect',datetime(2026,11,5,16,30)),
                (11,2,2,1,'failed','shop.collect',datetime(2026,11,5,17)),
                (12,2,2,1,'partial_success','listing.catalog',datetime(2026,11,5,18)),
                (13,1,1,1,'cancelled','shop.collect',datetime(2026,11,5,19)),
                (14,5,3,2,'succeeded','shop.collect',datetime(2026,11,5,17)),
                (15,1,1,1,'succeeded','shop.collect',datetime(2026,11,5,15,30))):
                db.add(MatrixRun(id=identity,company_id=company,owner_id=owner,agent_id=agent,plan_id=1,plan_revision=1,idempotency_key=str(identity),request_hash='x'*64,frozen={'config':{'tasks':[task]}},status=status,created_at=created))
                if company==1:db.add(MatrixItem(company_id=1,run_id=identity,agent_id=agent,environment_id=self.env,status=status))
            db.commit()
        endpoint='/hub-v5/admin/statistics?start=2026-11-06&end=2026-11-06'
        response=self.request('GET',endpoint);self.assertEqual(response.status_code,200,response.text)
        data=response.json();self.assertEqual(data['summary']['total'],4);self.assertAlmostEqual(data['summary']['success_rate'],1/3)
        self.assertEqual(data['current']['environments'],2);self.assertEqual(data['current']['shops'],1)
        self.assertEqual(data['daily'][0]['total'],4)
        self.assertEqual(self.request('GET',endpoint+'&user_id=2').json()['summary']['total'],2)
        self.assertEqual(self.request('GET',endpoint+'&task=shop.collect').json()['summary']['total'],3)
        self.assertEqual(self.request('GET',endpoint+'&site=MY').json()['summary']['total'],4)
        self.assertEqual(self.request('GET',endpoint+'&agent_id=3').status_code,404)
        self.assertEqual(self.request('GET','/hub-v5/admin/statistics?start=2025-01-01&end=2026-11-06').status_code,422)


class MatrixMigrationSQLTests(unittest.TestCase):
    def test_upgrade_from_main_preserves_legacy_locks_and_downgrade(self):
        from alembic import command
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, inspect, text
        from app.schema_version import alembic_config

        engine = create_engine('sqlite://')
        try:
            with engine.begin() as connection:
                config = alembic_config(connection)
                self.assertEqual(ScriptDirectory.from_config(config).get_heads(), ['20261110_76'])
                command.upgrade(config, '20261105_69')
                connection.execute(text("INSERT INTO hub_runtime_locks "
                    "(id, company_id, container_code, task_id) VALUES (1, 1, 'legacy-env', 42)"))
                command.upgrade(config, 'head')
                self.assertEqual(tuple(connection.execute(text("SELECT container_code, task_id, "
                    "matrix_item_id, fencing FROM hub_runtime_locks WHERE id=1")).one()),
                    ('legacy-env', 42, None, 0))
                tables = inspect(connection).get_table_names()
                self.assertIn('design_groups', tables)
                self.assertIn('matrix_allocations', tables)
                command.downgrade(config, '20261105_69')
                self.assertNotIn('matrix_allocations', inspect(connection).get_table_names())
                self.assertEqual(tuple(connection.execute(text("SELECT container_code, task_id "
                    "FROM hub_runtime_locks WHERE id=1")).one()), ('legacy-env', 42))
        finally:
            engine.dispose()

    def test_operation_migration_archives_debug_plans_without_conversion(self):
        from alembic import command
        from sqlalchemy import create_engine, text, inspect
        from app.schema_version import alembic_config
        engine=create_engine('sqlite://')
        try:
            with engine.begin() as connection:
                config=alembic_config(connection);command.upgrade(config,'20261108_72')
                connection.execute(text("INSERT INTO matrix_plans (id,company_id,owner_id,agent_id,name,revision,config,deleted,updated_at) VALUES (1,1,1,1,'调试方案',1,'{}',false,CURRENT_TIMESTAMP)"))
                command.upgrade(config,'head')
                self.assertEqual(connection.execute(text('SELECT deleted FROM matrix_plans WHERE id=1')).scalar(),1)
                self.assertEqual(connection.execute(text('SELECT COUNT(*) FROM matrix_operations')).scalar(),0)
                self.assertIn('matrix_operations',inspect(connection).get_table_names())
        finally: engine.dispose()

    def test_environment_target_migration_supports_mysql_and_mariadb_sql(self):
        from io import StringIO
        from types import SimpleNamespace
        from alembic import command
        from app.schema_version import alembic_config
        for dialect in ('mysql','mariadb'):
            config=alembic_config();output=StringIO();config.output_buffer=output
            with patch('app.config.get_settings',return_value=SimpleNamespace(database_url=f'{dialect}+pymysql://test@localhost/test')):
                command.upgrade(config,'20261108_73:20261108_74',sql=True)
            sql=output.getvalue()
            self.assertIn('environment_id',sql)
            self.assertIn('uq_matrix_shop_environment',sql)

    def test_operation_migration_supports_mysql_and_mariadb_sql(self):
        from io import StringIO
        from types import SimpleNamespace
        from alembic import command
        from app.schema_version import alembic_config
        for dialect in ('mysql','mariadb'):
            config=alembic_config();output=StringIO();config.output_buffer=output
            with patch('app.config.get_settings',return_value=SimpleNamespace(database_url=f'{dialect}+pymysql://test@localhost/test')):
                command.upgrade(config,'20261108_72:20261108_73',sql=True)
            sql=output.getvalue()
            self.assertIn('CREATE TABLE matrix_operations',sql)
            self.assertIn('ALTER TABLE matrix_runs',sql)

    def test_new_migration_supports_mysql_offline_sql(self):
        from io import StringIO
        from types import SimpleNamespace
        from alembic import command
        from app.schema_version import alembic_config
        for dialect in ('mysql','mariadb'):
            config=alembic_config();output=StringIO();config.output_buffer=output
            with patch('app.config.get_settings',return_value=SimpleNamespace(database_url=f'{dialect}+pymysql://test@localhost/test')):
                command.upgrade(config,'20261105_69:20261106_70',sql=True)
            sql=output.getvalue()
            self.assertIn('matrix_allocations',sql);self.assertIn('uq_matrix_shop_combination',sql)
            self.assertIn('fencing INTEGER',sql);self.assertIn('version BIGINT',sql)
            self.assertNotIn('DROP TABLE',sql)


class MatrixMemberMigrationTests(unittest.TestCase):
    def test_existing_connector_users_are_preserved_and_new_members_remain_ungranted(self):
        from alembic import command
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session
        from app.models import Company
        from app.schema_version import alembic_config
        engine=create_engine('sqlite://')
        try:
            with engine.begin() as connection:
                config=alembic_config(connection);command.upgrade(config,'20261106_70')
                with Session(bind=connection) as db:
                    db.add(Company(id=1,name='迁移公司'))
                    for uid,role in ((1,Role.COMPANY_ADMIN),(2,Role.MEMBER),(3,Role.MEMBER),(4,Role.DESIGNER)):
                        db.add(User(id=uid,company_id=1,name=f'成员{uid}',email=f'migration{uid}@test.invalid',password_hash='unused',role=role))
                    for uid in (2,4):db.add(HubAgent(id=uid,company_id=1,user_id=uid,name=f'旧电脑{uid}',platform='macos',is_active=True,token_hash=str(uid)*64))
                    db.commit()
                command.upgrade(config,'head')
                rows=connection.execute(text('SELECT user_id,enabled,collect_enabled,listing_enabled,view_scope FROM matrix_member_permissions')).all()
                self.assertEqual([tuple(row) for row in rows],[(2,1,1,1,'own')])
        finally:engine.dispose()

    def test_permission_migration_has_portable_mysql_and_mariadb_sql(self):
        from io import StringIO
        from types import SimpleNamespace
        from alembic import command
        from app.schema_version import alembic_config
        for dialect in ('mysql','mariadb'):
            config=alembic_config();output=StringIO();config.output_buffer=output
            with patch('app.config.get_settings',return_value=SimpleNamespace(database_url=f'{dialect}+pymysql://test@localhost/test')):
                command.upgrade(config,'20261106_70:20261106_71',sql=True)
            self.assertIn('matrix_member_permissions',output.getvalue())
            self.assertIn('INSERT INTO matrix_member_permissions',output.getvalue())
