"""续期执行顺序、保守恢复与时间边界，不连接真实平台。"""
import asyncio
import os
import json
import sys
import unittest
from unittest.mock import patch,AsyncMock
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from plugins.flash_sales import renew_flash_sales,new_window,times,PageBlocked,STATES,normalize_headers,parse_activity_cells,parse_api_activity,parse_detail_activity,MerchantFlashPage,PlatformRejected,prepare_payload,clone_products,LIST_PATH,DETAIL_PATH,PRODUCTS_PATH,TERMINATE_PATH,CREATE_PATH
from plugins.tiktok import site_timezone
TZ=site_timezone('MY')


class FlashExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self,status='ongoing',stage='pending',eligible=True,fail_at=None):
        events=[]
        observation={'external_id':'old','name':'秒杀','activity_type':'商家秒杀活动','status':status,'ends_at':datetime.now(TZ).isoformat(),'product_count':2}
        record={'id':1,'external_id':'old','name':'秒杀','stage':stage,'new_activity_id':'draft' if stage=='draft_confirmed' else None}
        class UI:
            def __init__(self,page,stop):pass
            async def scan(self,status='all'):events.append('scan');return [observation]
            async def lookup(self,external,name=None):events.append('lookup');return observation
            async def prepare(self,activity,rid):events.append('prepare');return {'promotion_name':f'秒杀[HT-R{rid}]','type_detail':9,'promotion_limit_dimension':4,'flash_sale_products':[{'product_id':'1','flash_sale_price':'10'}]}
            async def terminate(self,a):
                self.last_write_sent=True;events.append('terminate')
                if fail_at=='terminate':raise RuntimeError('终止超时')
            async def publish(self,preparation,start,end):
                self.last_write_sent=True;events.append('publish')
                if fail_at=='publish':raise RuntimeError('发布响应超时')
                return 'new'
            async def verify(self,external,start,end,preparation=None):events.append('verify');return '已核对平台活动ID和时间'
        async def rpc(path,body):
            events.append((path,body))
            if path=='scan':return {'renewals':[record]}
            if path.endswith('/recheck'):return {'eligible':eligible,'status':status}
            if path=='complete':return {'complete':fail_at is None and stage!='unknown'}
            return {}
        async def noop(*a):pass
        config={'selected_flash_ids':[1],'flash_sale_targets':[{'external_id':'old','name':'秒杀'}]} if status=='expired' else {}
        try:result=await renew_flash_sales(None,'MY',config,rpc,noop,noop,ui_factory=UI)
        except (PageBlocked,RuntimeError) as exc:result={'error':str(exc),'complete':False}
        return events,result

    async def test_independent_sync_never_calls_renewal_or_platform_write(self):
        from plugins import flash_sales
        rpc=AsyncMock(side_effect=[{'renewals':[]},{'complete':True}])
        async def noop(*args):pass
        adapter=type('ReadOnly',(),{'scan':AsyncMock(return_value=[{'external_id':'1'}])})()
        with patch.object(flash_sales,'MerchantFlashPage',return_value=adapter),patch.object(flash_sales,'renew_flash_sales',new_callable=AsyncMock) as renew:
            result=await flash_sales.collect_flash_sales(None,'MY',{},rpc,noop,noop)
        renew.assert_not_awaited();self.assertTrue(result['complete'])
        self.assertEqual([call.args[0] for call in rpc.await_args_list],['scan','complete'])

    async def test_ongoing_sequence_and_time_window(self):
        events,result=await self.run_case()
        self.assertTrue(result['complete'])
        actions=[e for e in events if isinstance(e,str)]
        self.assertEqual(actions,['scan','lookup','prepare','terminate','publish','verify'])
        self.assertEqual(next(e[1]['scope'] for e in events if isinstance(e,tuple) and e[0]=='scan'),'ongoing')
        checkpoints=[e[1]['stage'] for e in events if isinstance(e,tuple) and e[0].endswith('/step')]
        self.assertEqual(checkpoints,['prepared','terminate_intent','terminated','publish_intent','created','published'])
        planned=next(e[1] for e in events if isinstance(e,tuple) and e[1].get('stage')=='publish_intent')
        self.assertEqual(datetime.fromisoformat(planned['ends_at'])-datetime.fromisoformat(planned['starts_at']),timedelta(hours=72))

    async def test_expired_selection_never_terminates(self):
        events,result=await self.run_case(status='expired')
        self.assertNotIn('terminate',events);self.assertIn('publish',events)
        self.assertNotIn('scan',events)
        self.assertEqual(next(e[1]['scope'] for e in events if isinstance(e,tuple) and e[0]=='scan'),'selected')

    async def test_expired_recheck_skips_without_writing(self):
        events,result=await self.run_case(status='expired',eligible=False)
        self.assertNotIn('publish',events);self.assertNotIn('terminate',events)
        self.assertTrue(any(isinstance(e,tuple) and e[1].get('stage')=='skipped' for e in events))

    async def test_timeout_records_unknown_and_does_not_repeat(self):
        for action in ('terminate','publish'):
            events,result=await self.run_case(fail_at=action)
            self.assertEqual(events.count(action),1)
            self.assertTrue(any(isinstance(e,tuple) and e[1].get('stage')=='unknown' for e in events))

    async def test_unknown_and_existing_draft(self):
        events,result=await self.run_case(stage='unknown')
        self.assertNotIn('copy',events);self.assertNotIn('publish',events)
        events,result=await self.run_case(stage='draft_confirmed',status='terminated')
        self.assertNotIn('terminate',events);self.assertNotIn('publish',events);self.assertIn('待核对',result['error'])

    def test_natural_end_is_distinct_from_manual_termination(self):
        self.assertEqual(set(STATES),{'未开始','进行中','已结束','已终止'})
        self.assertEqual(STATES['已结束'],'expired')
        self.assertEqual(STATES['已终止'],'terminated')

    def test_window_and_local_time_parse(self):
        start,end=new_window(datetime(2026,11,13,23,59,59,tzinfo=TZ))
        self.assertEqual(start,datetime(2026,11,14,0,5,tzinfo=TZ))
        self.assertEqual(end-start,timedelta(hours=72))
        self.assertEqual(times('2026/11/14 00:05:00 — 2026-11-17 00:05:00'),[start,end])


class FlashTableParsingTests(unittest.TestCase):
    def test_actual_headers_separate_times_and_missing_product_count(self):
        headers=normalize_headers(['活动名称','状态','开始时间\n(GMT+8)','结束时间\n(GMT+8)','类型','操作'])
        value=parse_activity_cells(headers,['秒杀A','已结束','2026/11/9\u00a011:51','2026/11/12\u00a011:51','商家秒杀活动','复制'])
        self.assertEqual(value['status'],'expired')
        self.assertEqual(value['ends_at'],'2026-11-12T11:51:00+08:00')
        self.assertIsNone(value['product_count'])
        value=parse_activity_cells(headers,['秒杀B','已结束','2026/11/1 02:7','2026/11/4 02:7','商家秒杀活动','复制'])
        self.assertEqual(value['ends_at'],'2026-11-04T02:07:00+08:00')

    def test_non_merchant_rows_do_not_enter_flash_data(self):
        headers=['活动名称','状态','开始时间','结束时间','类型','操作']
        self.assertIsNone(parse_activity_cells(headers,['折扣','进行中','--','--','商品折扣','复制']))
        with self.assertRaises(PageBlocked):parse_activity_cells(headers,['不完整'])
        with self.assertRaises(PageBlocked):parse_activity_cells(headers,['秒杀','进行中','--','--','商家秒杀活动','复制'])


class FlashApiTests(unittest.IsolatedAsyncioTestCase):
    def activity(self,identity='1001',status=2,**values):
        return {'id':identity,'name':'同名活动','status':status,'promotion_type':5,'promotion_type_detail':9,
            'start_time':'1794455596000','end_time':'1794714796000',**values}

    def adapter(self,pages):
        ui=MerchantFlashPage(None,AsyncMock())
        ui.api_request=AsyncMock(side_effect=pages)
        return ui

    async def test_paginates_json_and_counts_all_types_without_page_clicks(self):
        ui=self.adapter([{'total_count':3,'promotions':[self.activity(),self.activity('1002',promotion_type=4)]},
            {'total_count':3,'promotions':[self.activity('1003')]}])
        values=await ui.scan('ongoing')
        self.assertEqual([v['external_id'] for v in values],['1001','1003'])
        self.assertEqual([c.args[0]['index'] for c in ui.api_request.await_args_list],[0,1])
        self.assertTrue(all(c.args[0]['status']==2 for c in ui.api_request.await_args_list))

    async def test_rejects_partial_duplicate_changing_total_and_wrong_state(self):
        for pages in ([{'total_count':1}],
            [{'total_count':2,'promotions':[self.activity()]},{'total_count':2,'promotions':[self.activity()]}],
            [{'total_count':2,'promotions':[self.activity()]},{'total_count':3,'promotions':[self.activity('1002')]}],
            [{'total_count':1,'promotions':[self.activity(status=5)]}]):
            with self.subTest(pages=pages),self.assertRaises(PageBlocked):await self.adapter(pages).scan('ongoing')

    async def test_lookup_uses_name_but_requires_exact_id_among_duplicate_names(self):
        ui=self.adapter([{'total_count':2,'promotions':[self.activity(),self.activity('1002',5)]}])
        value=await ui.lookup('1002','同名活动')
        self.assertEqual(value['external_id'],'1002');self.assertEqual(value['status'],'expired')
        self.assertEqual(ui.api_request.await_args.args[0]['name'],'同名活动')

    async def test_new_id_verification_reads_detail_and_checks_window(self):
        ui=MerchantFlashPage(None,AsyncMock())
        ui.detail=AsyncMock(return_value={'promotion_status':1,'period':{'start_time':'1794455596','end_time':'1794714796'}})
        value=parse_api_activity(self.activity(status=3))
        await ui.verify('1001',datetime.fromisoformat(value['starts_at']),datetime.fromisoformat(value['ends_at']))
        ui.detail.assert_awaited_once_with('1001')

    def test_api_statuses_and_millisecond_times(self):
        for code,status in [(2,'ongoing'),(3,'scheduled'),(4,'terminated'),(5,'expired')]:
            value=parse_api_activity(self.activity(status=code))
            self.assertEqual(value['status'],status)
            self.assertEqual(datetime.fromisoformat(value['ends_at']).timestamp(),1794714796)
        for values in ({'end_time':'--'},{'id':''},{'status':99}):
            with self.assertRaises(PageBlocked):parse_api_activity(self.activity(**values))

    def test_detail_count_requires_matching_activity_and_valid_responses(self):
        detail={'code':0,'data':{'flash_sale':{'promotion_id':'1001','promotion_name':'秒杀','type_detail':9,
            'promotion_status':2,'period':{'start_time':'1794455596','end_time':'1794714796'}}}}
        products={'code':0,'data':{'total_count':50}}
        self.assertEqual(parse_detail_activity('1001',detail,products)['product_count'],50)
        with self.assertRaises(PageBlocked):parse_detail_activity('1002',detail,products)
        for count in (None,True,-1,'50'):
            with self.assertRaises(PageBlocked):parse_detail_activity('1001',detail,{'code':0,'data':{'total_count':count}})
        with self.assertRaises(PageBlocked):parse_detail_activity('1001',detail,{'code':1,'data':{'total_count':50}})

        for code,status in [(1,'scheduled'),(2,'ongoing'),(3,'expired'),(4,'terminated'),(5,'scheduled')]:
            detail['data']['flash_sale']['promotion_status']=code
            self.assertEqual(parse_detail_activity('1001',detail,products)['status'],status)

    async def test_verification_accepts_upcoming_detail_but_rejects_expired_detail(self):
        ui=MerchantFlashPage(None,AsyncMock())
        for code in (1,2,5):
            ui.detail=AsyncMock(return_value={'promotion_status':code,'period':{'start_time':'1794455596','end_time':'1794714796'}})
            await ui.verify('1001',datetime.fromtimestamp(1794455596,TZ),datetime.fromtimestamp(1794714796,TZ))
        for code in (3,4,0):
            ui.detail=AsyncMock(return_value={'promotion_status':code,'period':{'start_time':'1794455596','end_time':'1794714796'}})
            with self.assertRaises(PageBlocked):
                await ui.verify('1001',datetime.fromtimestamp(1794455596,TZ),datetime.fromtimestamp(1794714796,TZ))


class FlashApiWorkflowTests(unittest.IsolatedAsyncioTestCase):
    """实际适配器 + 隔离的平台接口；任何写请求都只进入本测试的内存模型。"""
    async def run_flow(self,failure=None,partial=False,resume=None):
        import copy
        from datetime import timezone
        from types import SimpleNamespace
        now=datetime.now(timezone.utc)
        detail={'promotion_id':'1001','promotion_name':'原秒杀','promotion_status':2,'type_detail':9,
            'effective_time_type':1,'promotion_limit_dimension':4,
            'period':{'start_time':str(int((now-timedelta(days=1)).timestamp())),'end_time':str(int((now+timedelta(hours=1)).timestamp()))}}
        products=[{'product_id':str(i),'product_status':4,'fixed_price_value':price,'purchase_limit':-1} for i,price in ((101,'23.450'),(102,'28.99'))]
        state={'old':detail,'new':None,'new_products':None};calls=[];events=[]
        async def evaluate(script,args):
            path=args['path'];body=copy.deepcopy(args['body']);calls.append((path,body))
            if path==LIST_PATH:
                rows=[state['old']]+([state['new']] if state['new'] else [])
                rows=[a for a in rows if (body['status']==1 or {1:3,2:2,3:5,4:4,5:3}[a['promotion_status']]==body['status']) and (not body.get('name') or body['name'] in a['promotion_name'])]
                data={'total_count':len(rows),'promotions':[{'id':a['promotion_id'],'name':a['promotion_name'],'status':{1:3,2:2,3:5,4:4,5:3}[a['promotion_status']],
                    'promotion_type':5,'promotion_type_detail':9,'start_time':a['period']['start_time']+'000','end_time':a['period']['end_time']+'000'} for a in rows]}
            elif path==DETAIL_PATH:
                value=state['old'] if args['params']['promotion_id']=='1001' else state['new']
                data={'flash_sale':copy.deepcopy(value)}
            elif path==PRODUCTS_PATH:
                values=products if body['promotion_id']=='1001' else state['new_products']
                # 强制一条一页，验证商品接口游标会继续前进。
                data={'total_count':len(values),'item_products':copy.deepcopy(values[body['cursor']:body['cursor']+1])}
            elif path==TERMINATE_PATH:
                self.assertEqual(body,{'promotion_id':'1001'})
                if failure=='reject_stop':return {'status':200,'data':{'code':123,'message':'测试：平台拒绝终止'}}
                if failure!='stop_unconfirmed':state['old']['promotion_status']=4
                if failure=='stop_timeout':raise RuntimeError('测试：终止响应丢失')
                data={}
            elif path==CREATE_PATH:
                self.assertEqual(state['old']['promotion_status'],4,'旧活动没有确认终止时禁止创建')
                self.assertEqual(body['flash_sale_products'],[{'product_id':'101','flash_sale_price':'23.45','purchase_limit':-1},{'product_id':'102','flash_sale_price':'28.99','purchase_limit':-1}])
                self.assertEqual(int(body['period']['end_time'])-int(body['period']['start_time']),72*3600)
                if failure=='reject_create':return {'status':200,'data':{'code':124,'message':'测试：平台拒绝创建'}}
                state['new']={**copy.deepcopy(body),'promotion_id':'2001','promotion_status':1}
                state['new_products']=copy.deepcopy(products[:1] if partial else products)
                if failure=='create_timeout':raise RuntimeError('测试：创建响应丢失')
                if failure=='missing_code':return {'status':200,'data':{}}
                data={'promotion_id':'2001'}
            else:self.fail('未知平台接口 '+path)
            return {'status':200,'data':{'code':0,'data':data}}
        ui=MerchantFlashPage(SimpleNamespace(evaluate=evaluate),AsyncMock());ui.api_params={}
        ui.init_api=AsyncMock();ui.ready=AsyncMock()
        if failure=='not_sent':
            async def ready():
                if events and events[-1][1].get('stage')=='terminate_intent':raise PageBlocked('测试：尚未发请求就停止')
            ui.ready=ready
        record={'id':7,'external_id':'1001','name':'原秒杀','stage':'pending','terminated':False}
        if resume:
            preparation=prepare_payload(detail,products,7)
            start,end=new_window()
            state['old']['promotion_status']=4
            state['new']={**preparation,'promotion_id':'2001','promotion_status':1,'period':{'start_time':str(int(start.timestamp())),'end_time':str(int(end.timestamp()))}}
            state['new_products']=copy.deepcopy(products)
            record.update(stage=resume,terminated=True,preparation=preparation,starts_at=start.isoformat(),ends_at=end.isoformat())
            if resume=='created':record['new_activity_id']='2001'
        async def rpc(path,body):
            events.append((path,copy.deepcopy(body)))
            if path=='scan':return {'renewals':[record]}
            if path.endswith('/recheck'):return {'eligible':True}
            if path=='complete':return {'complete':True}
            return {}
        try:await renew_flash_sales(None,'MY',{},rpc,AsyncMock(),AsyncMock(),ui_factory=lambda *a:ui)
        except (RuntimeError,PageBlocked):pass
        return state,calls,events

    async def test_real_adapter_stops_then_creates_once_and_verifies_all_products(self):
        state,calls,events=await self.run_flow()
        self.assertEqual([p for p,b in calls if p in (TERMINATE_PATH,CREATE_PATH)],[TERMINATE_PATH,CREATE_PATH])
        self.assertEqual(state['old']['promotion_status'],4)
        steps=[b for p,b in events if p.endswith('/step')]
        self.assertEqual([b['stage'] for b in steps],['prepared','terminate_intent','terminated','publish_intent','created','published'])
        self.assertNotIn('new_activity_id',steps[0]);self.assertNotIn('new_activity_id',steps[3])
        self.assertEqual(steps[4]['new_activity_id'],'2001')

    async def test_unsent_and_explicit_rejection_are_not_unknown(self):
        for failure,outcome in [('not_sent','not_sent'),('reject_stop','rejected'),('reject_create','rejected')]:
            with self.subTest(failure=failure):
                state,calls,events=await self.run_flow(failure=failure)
                failed=[b for p,b in events if b.get('stage')=='failed']
                self.assertEqual(len(failed),1);self.assertEqual(failed[0]['request_outcome'],outcome)
                self.assertIn('测试',failed[0]['error'])
                self.assertFalse(any(b.get('stage')=='unknown' for p,b in events))
                if failure in ('not_sent','reject_stop'):self.assertIsNone(state['new'])

    async def test_timeout_or_unconfirmed_stop_never_repeats_write(self):
        for failure in ('stop_timeout','stop_unconfirmed','create_timeout','missing_code'):
            with self.subTest(failure=failure):
                state,calls,events=await self.run_flow(failure=failure)
                writes=[p for p,b in calls if p in (TERMINATE_PATH,CREATE_PATH)]
                self.assertEqual(writes.count(TERMINATE_PATH),1)
                self.assertEqual(writes.count(CREATE_PATH),1 if failure in ('create_timeout','missing_code') else 0)
                unknown=[b for p,b in events if b.get('stage')=='unknown']
                self.assertEqual(len(unknown),1);self.assertIn('结果待核对',unknown[0]['error'])

    async def test_partial_creation_keeps_returned_id_and_never_reports_success(self):
        state,calls,events=await self.run_flow(partial=True)
        self.assertEqual(sum(p==CREATE_PATH for p,b in calls),1)
        self.assertTrue(any(b.get('stage')=='created' and b.get('new_activity_id')=='2001' for p,b in events))
        self.assertTrue(any(b.get('stage')=='unknown' and b.get('new_activity_id')=='2001' for p,b in events))
        self.assertFalse(any(b.get('stage')=='published' for p,b in events))

    async def test_resume_created_or_lost_create_response_only_reads_platform(self):
        for stage in ('created','publish_intent'):
            state,calls,events=await self.run_flow(resume=stage)
            self.assertFalse(any(p in (TERMINATE_PATH,CREATE_PATH) for p,b in calls))
            self.assertTrue(any(b.get('stage')=='published' and b.get('new_activity_id')=='2001' for p,b in events))

    def test_sku_prices_and_limits_are_preserved_and_missing_prices_block_preparation(self):
        product={'product_id':'101','skus':[{'product_id':'101','sku_id':'10001','in_promotion':True,'fixed_price_value':'12.340','total_purchase_limit':{'limit_dimension':100,'purchase_max_quantity':99}},
            {'product_id':'101','sku_id':'10002','in_promotion':False,'fixed_price_value':'5'}]}
        result=clone_products([product],1)
        self.assertEqual(len(result[0]['skus']),1)
        self.assertEqual(result[0]['skus'][0]['flash_sale_price'],'12.34')
        self.assertEqual(result[0]['skus'][0]['total_purchase_limit']['purchase_max_quantity'],99)
        with self.assertRaises(PageBlocked):clone_products([{'product_id':'101'}],4)
        with self.assertRaises(PageBlocked):clone_products([product,product],1)


@unittest.skipUnless(os.getenv('HAITOO_FLASH_BROWSER_TESTS')=='1','需显式启用隔离活动接口浏览器测试')
class FlashApiBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright=await async_playwright().start()
        self.browser=await self.playwright.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context(service_workers='block');self.page=await self.context.new_page()
        self.duplicate=False;self.without_id=False;self.requests=[];self.transport_calls=[]
        await self.context.route('**/*',self.serve)

    async def asyncTearDown(self):
        await self.context.close();await self.browser.close();await self.playwright.stop()

    async def serve(self,route):
        from urllib.parse import urlsplit
        parsed=urlsplit(route.request.url)
        headers={'Access-Control-Allow-Origin':'https://seller.tiktokshopglobalselling.com','Access-Control-Allow-Credentials':'true',
            'Access-Control-Allow-Headers':'content-type,x-tt-oec-region','Access-Control-Allow-Methods':'POST,GET,OPTIONS'}
        if route.request.method=='OPTIONS':await route.fulfill(status=204,headers=headers);return
        if parsed.path in (DETAIL_PATH,PRODUCTS_PATH,TERMINATE_PATH,CREATE_PATH):
            self.transport_calls.append((parsed.path,route.request.method))
            await route.fulfill(json={'code':0,'data':{}},headers=headers);return
        if parsed.path==LIST_PATH:
            body=route.request.post_data_json;self.requests.append((route.request.url,body))
            rows=[{'id':str(1001+i),'name':f'秒杀{i}','status':2,'promotion_type':5,'promotion_type_detail':9,
                'start_time':'1794455596000','end_time':'1794714796000'} for i in range(53)]
            if self.duplicate:rows[50]['id']=rows[0]['id']
            if self.without_id:rows[0]['id']=''
            start=body['index']*body['size']
            await route.fulfill(json={'code':0,'data':{'total_count':len(rows),'promotions':rows[start:start+body['size']]}},headers=headers);return
        if parsed.hostname=='seller.tiktokshopglobalselling.com':
            html='''<meta charset="utf-8"><table><thead><tr><th>活动名称</th><th>状态</th><th>开始时间</th><th>结束时间</th><th>类型</th><th>操作</th></tr></thead><tbody><tr><td colspan="6">暂无活动</td></tr></tbody></table><script>
            fetch('https://api16-normal-sg.tiktokshopglobalselling.com/api/v1/promotion/list?oec_seller_id=fixture&msToken=do-not-copy&fp=do-not-copy',{method:'POST',credentials:'include',headers:{'content-type':'application/json'},body:JSON.stringify({index:0,size:10,status:1,promotion_type:1})});</script>'''
            await route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html);return
        await route.abort()

    async def adapter(self):
        async def stop():pass
        return MerchantFlashPage(self.page,stop)

    async def test_real_browser_fetch_paginates_json_without_ui_next_buttons(self):
        from urllib.parse import urlsplit,parse_qs
        ui=await self.adapter();rows=await ui.scan('ongoing')
        self.assertEqual(len(rows),53)
        self.assertEqual(ui.api_params,{'oec_seller_id':'fixture'})
        reads=[(url,body) for url,body in self.requests if body['size']==50]
        self.assertEqual([body['index'] for url,body in reads],[0,1])
        self.assertTrue(all(body['status']==2 for url,body in reads))
        for url,body in reads:
            self.assertNotIn('msToken',parse_qs(urlsplit(url).query));self.assertNotIn('fp',parse_qs(urlsplit(url).query))

    async def test_duplicate_activity_across_api_pages_rejects_partial_scan(self):
        self.duplicate=True
        with self.assertRaisesRegex(PageBlocked,'重复'):await (await self.adapter()).scan('ongoing')

    async def test_loaded_platform_sdk_requires_string_fetch_urls_for_all_methods(self):
        ui=await self.adapter();await ui.init_api()
        await self.page.evaluate('''()=>{const original=window.fetch;window.fetch=(url,options)=>{
            if(typeof url!=='string')throw new TypeError('平台SDK仅支持字符串URL');
            return original.call(window,url,options);
        }}''')
        self.assertEqual(len(await ui.scan('ongoing')),53)
        await ui.api_request({'promotion_id':'1001'},DETAIL_PATH,'GET')
        await ui.api_request({'promotion_id':'1001','cursor':0,'limit':50},PRODUCTS_PATH)
        await ui.api_request({'promotion_id':'1001'},TERMINATE_PATH,mutation=True)
        await ui.api_request({'promotion_name':'隔离测试'},CREATE_PATH,mutation=True)
        self.assertEqual(self.transport_calls,[(DETAIL_PATH,'GET'),(PRODUCTS_PATH,'POST'),(TERMINATE_PATH,'POST'),(CREATE_PATH,'POST')])

    async def test_missing_platform_id_fails_before_any_write(self):
        self.without_id=True
        with self.assertRaisesRegex(PageBlocked,'ID缺失'):await (await self.adapter()).scan('ongoing')


if __name__=='__main__':unittest.main()
