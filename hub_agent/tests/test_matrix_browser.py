"""MY 商品接口与商品分析页面的隔离回归；不访问真实 TikTok。"""
import json,os,sys,unittest
from unittest.mock import patch,AsyncMock
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from plugins.tiktok import collect,collect_order_count,open_environment,PRODUCTS_PATH,SKUS_PATH,ANALYSIS_API_PATH,parse_analysis_item,analysis_page


@unittest.skipUnless(os.getenv('HAITOO_MATRIX_BROWSER_TESTS')=='1','需启用隔离矩阵浏览器测试')
class MatrixBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright=await async_playwright().start()
        self.browser=await self.playwright.chromium.launch(channel=os.getenv('HAITOO_BROWSER_CHANNEL') or 'chrome')
        self.context=await self.browser.new_context();self.page=await self.context.new_page()
        self.count=3;self.missing=False;self.truncated=False;self.partial=False;self.declared=None
        self.challenge=False;self.mid_challenge=False;self.abbreviated=False;self.triggered=False;self.duplicate=False
        self.analysis_missing=False;self.analysis_abbreviated=False;self.analysis_requests=[];self.analysis_delay=0;self.analysis_page_delay=0;self.analysis_duplicate=False;self.analysis_no_rows=False;self.analysis_api_queries=[]
        self.events=[];self.bulk_queries=[];self.sku_queries=[]
        self.order_count='1,791';self.order_list_count=None;self.order_delay=0;self.order_requests=[]
        await self.context.route('**/*',self.route)

    async def asyncTearDown(self):
        await self.browser.close();await self.playwright.stop()

    def skus(self,pid):
        return [{'id':f'sku-{pid}-{i}','seller_sku':f'S{pid}-{i}','base_price':{'region':'MY','currency':'MYR','sale_price':'109.00','promotion_price':'39.99'},
            'quantities':[{'available_quantity':999}],'properties':[{'value_name':f'Color {pid}'},{'value_name':str(i)}]} for i in (1,2)]

    async def route(self,route):
        parsed=urlsplit(route.request.url);query=parse_qs(parsed.query)
        cors={'Access-Control-Allow-Origin':'https://seller.tiktokshopglobalselling.com','Access-Control-Allow-Credentials':'true',
            'Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'content-type,x-tt-oec-region'}
        if route.request.method=='OPTIONS':await route.fulfill(status=204,headers=cors);return
        if parsed.path==PRODUCTS_PATH:
            page_no=int(query.get('page_number',['1'])[0]);bulk=query.get('sku_number',['1'])[0]=='100'
            if bulk:self.bulk_queries.append(query)
            if bulk and self.mid_challenge and not self.triggered:
                self.triggered=True
                await self.page.evaluate("() => {const e=document.createElement('div');e.id='captcha_container';e.style='position:fixed;inset:0';e.innerText='验证';document.body.append(e);setTimeout(()=>e.remove(),500)}")
                await route.fulfill(json={'code':10000,'data':None},headers=cors);return
            products=[]
            for identity in range((page_no-1)*2+1,min(page_no*2,self.count)+1):
                pid=1 if self.duplicate and page_no>1 else identity
                skus=self.skus(pid)
                if not bulk or self.partial or self.truncated:skus=skus[:1]
                products.append({'product_id':str(pid),'product_name':f'Dress {pid}','is_online_version':True,'total_sku_count':2,'skus':skus,
                    'product_performance':{} if self.missing and pid==1 else {'last_28days_pv':'1.2K' if self.abbreviated and pid==1 else str(pid*10)}})
            await route.fulfill(json={'code':0,'data':{'page_number':page_no,'page_size':2,'total_product_count':self.declared if self.declared is not None else self.count,'products':products}},headers=cors);return
        if parsed.path==SKUS_PATH:
            self.sku_queries.append(query)
            rows=self.skus(query['product_id'][0])
            await route.fulfill(json={'code':0,'data':rows[:1] if self.truncated else rows},headers=cors);return
        if parsed.path==ANALYSIS_API_PATH:
            import asyncio
            body=route.request.post_data_json['request']
            pagination=body['list_control']['pagination'];page_number=pagination['page']
            keyword=body['search'].get('search_keyword')
            ids=[i for i in range(1,self.count+1) if not (self.analysis_missing and i==1)]
            if keyword:ids=[i for i in ids if str(i)==keyword]
            batch=ids[page_number*2:page_number*2+2]
            if self.analysis_duplicate and not keyword and page_number==1:batch=[1]
            if pagination['size']==500:self.analysis_api_queries.append({'body':body,'query':query})
            await asyncio.sleep((self.analysis_page_delay if page_number else self.analysis_delay)/1000)
            rows=[{'meta':{'product_id':str(i)},'stats_v3':{'total':{'product_impression_pv':'1.2K' if self.analysis_abbreviated and i==1 else str(i*100),'product_click_pv':str(i*5),'items_sold':str(i),'gmv':{'amount':f'{i}.23','currency_code':'MYR'}}}} for i in batch]
            await route.fulfill(json={'code':0,'data':{'items':rows,'list_control':{'next_pagination':{'total':len(ids),'has_more':(page_number+1)*2<len(ids),'next_page':page_number+1}}}},headers=cors);return
        if parsed.path=='/order':
            self.order_requests.append(query)
            html='''<!doctype html><meta charset="utf-8"><div role="tab" aria-selected="true">全部</div>
                <div role="tab">待发货 1</div><div role="tab">已发货 16</div><div id="count"></div>
                <script>window.expandCalls=Number(localStorage.getItem('expandCalls')||0);
                setTimeout(()=>document.querySelector('#count').innerHTML='<span>找到 COUNT 个订单</span><label>LIST 个订单</label>',DELAY)</script>'''
            await route.fulfill(body=html.replace('COUNT',self.order_count).replace('LIST',self.order_list_count or self.order_count).replace('DELAY',str(self.order_delay)),content_type='text/html');return
        if parsed.path=='/compass/product-analysis':
            self.analysis_requests.append(query)
            start,end=query['timeRange'][0].split('|')
            from datetime import date,timedelta
            dates=f"{start.replace('-','/')} - {(date.fromisoformat(end)-timedelta(days=1)).strftime('%Y/%m/%d')}"
            values=[{'id':str(i),'impressions':str(i*100),'clicks':str(i*5),'sales':str(i)} for i in range(1,self.count+1)]
            if self.analysis_missing:values=values[1:]
            if self.analysis_abbreviated and values:values[0]['impressions']='1.2K'
            html='''<!doctype html><meta charset="utf-8"><div>DATES</div><div>按商品</div><div>全部</div>
                <button aria-label="自定义指标" onclick="document.querySelector('[role=dialog]').hidden=false">编辑</button>
                <div role="dialog" hidden><h2>自定义指标</h2>
                <label><input type="checkbox" checked>GMV</label><label><input type="checkbox" checked>商品成交件数</label><label><input type="checkbox">商品曝光次数</label><label><input type="checkbox">商品点击量</label>
                <button onclick="selected=true;render();document.querySelector('[role=dialog]').hidden=true">确定</button></div>
                <div id="analysis-loading" class="arco-spin-icon" hidden>加载中</div><table><thead></thead><tbody></tbody></table><span>共 TOTAL 条</span><button aria-label="Next page" onclick="pageNo++;render()">下一页</button><script>
                window.expandCalls=Number(localStorage.getItem('expandCalls')||0);let pageNo=0,selected=false,timer;const data=VALUES;
                function render(){document.querySelector('thead').innerHTML='<tr><th>商品</th><th>GMV</th><th>商品成交件数</th>'+(selected?'<th>商品曝光次数</th><th>商品点击量</th>':'')+'</tr>';
                document.querySelector('[aria-label="Next page"]').disabled=(pageNo+1)*2>=data.length;
                clearTimeout(timer);const delay=pageNo===0?INITIAL_DELAY:PAGE_DELAY;
                const fill=()=>{document.querySelector('tbody').innerHTML=data.slice(pageNo*2,pageNo*2+2).map(p=>`<tr data-product-id="${p.id}"><td>Dress ${p.id}</td><td>${p.sales}</td>${selected?`<td>25%<br>${p.impressions}<br>10%</td><td>${p.clicks}</td>`:''}</tr>`).join('');document.querySelector('#analysis-loading').hidden=true;};
                if(delay){document.querySelector('tbody').innerHTML='<tr><td colspan="4">加载中</td></tr>';document.querySelector('#analysis-loading').hidden=false;timer=setTimeout(fill,delay);}else fill();}render();
                fetch('https://api16-normal-sg.tiktokshopglobalselling.comAPI_PATH?seller_id=fixture&msToken=do-not-copy&fp=do-not-copy',{method:'POST',credentials:'include',headers:{'content-type':'application/json'},body:JSON.stringify({request:{time_descriptor:{start:'START_DATE',end:'END_DATE'},search:{channel_type:0},list_control:{pagination:{page:0,size:10},rules:[{field:'gmv',direction:2}]}}})});</script>'''
            if self.analysis_no_rows:html=html.replace("document.querySelector('tbody').innerHTML=data.slice","document.querySelector('tbody').innerHTML=[].slice")
            html=html.replace('API_PATH',ANALYSIS_API_PATH).replace('START_DATE',start).replace('END_DATE',end)
            await route.fulfill(body=html.replace('DATES',dates).replace('TOTAL',str(len(values))).replace('VALUES',json.dumps(values)).replace('INITIAL_DELAY',str(self.analysis_delay)).replace('PAGE_DELAY',str(self.analysis_page_delay)),content_type='text/html');return
        if '/product/manage' in parsed.path:
            challenge='''<div id="captcha_container" style="position:fixed;inset:0">验证</div><script>setTimeout(()=>document.querySelector('#captcha_container').remove(),300)</script>''' if self.challenge else ''
            html=f'''<!doctype html><meta charset="utf-8"><div role="tab" aria-selected="true">在售 {self.count}</div><button onclick="localStorage.setItem('expandCalls',String(Number(localStorage.getItem('expandCalls')||0)+1))">展开</button>{challenge}<script>window.expandCalls=0;fetch('https://api16-normal-sg.tiktokshopglobalselling.com{PRODUCTS_PATH}?page_number=1&page_size=2&sku_number=1&tab_id=2&seller_id=fixture&msToken=do-not-copy&fp=do-not-copy',{{credentials:'include'}})</script>'''
            await route.fulfill(body=html,content_type='text/html');return
        await route.abort()

    async def check(self):pass
    async def progress(self,stage,message):self.events.append(stage)
    async def package(self):
        await open_environment(self.page,'MY',self.check,self.progress)
        return await collect(self.page,'MY',{'site':'MY','environment_id':7,'name':'所选环境'},self.check,self.progress)

    async def test_full_pagination_and_skus_are_read_without_expanding_any_product(self):
        data=await self.package()
        self.assertEqual([p['external_id'] for p in data['products']],['1','2','3'])
        self.assertEqual(data['header']['on_sale_count'],3)
        self.assertEqual(sum(p['views'] for p in data['products']),60)
        self.assertEqual(sum(p['sku_count'] for p in data['products']),6)
        self.assertEqual(data['products'][0]['skus'][0],{'external_id':'sku-1-1','name':'Color 1 - 1','seller_sku':'S1-1','stock':999,'price':'109.00','sale_price':'39.99','currency':'MYR'})
        self.assertIsNotNone(data['header']['window_start']);self.assertEqual(data['products'][0]['impressions'],100)
        self.assertEqual(data['header']['sections']['traffic'],'completed')
        self.assertEqual(data['products'][0]['gmv'],'1.23')
        self.assertEqual(data['header']['metrics']['gmv'],'6.69')
        self.assertEqual(data['header']['metrics']['orders_total'],1791)
        self.assertNotIn('orders',data['header']['metrics'])
        self.assertEqual(self.order_requests[0]['tab'],['all'])
        self.assertLess(self.events.index('collecting_product_analysis'),self.events.index('opening_orders'))
        self.assertLess(self.events.index('collection_orders'),self.events.index('collection_checked'))
        self.assertEqual(data['products'][0]['clicks'],5);self.assertEqual(data['products'][0]['sales_count'],1)
        self.assertEqual(self.analysis_requests[0]['shortcut'],['last30days'])
        from datetime import datetime,timedelta
        self.assertEqual(datetime.fromisoformat(data['header']['window_end'])-datetime.fromisoformat(data['header']['window_start']),timedelta(days=30))
        self.assertEqual(await self.page.evaluate('window.expandCalls'),0)
        self.assertEqual(len(self.bulk_queries),2);self.assertEqual(self.sku_queries,[])
        self.assertTrue(all('msToken' not in q and 'fp' not in q for q in self.bulk_queries))

    async def test_only_truncated_list_skus_use_direct_sku_endpoint(self):
        self.partial=True
        data=await self.package()
        self.assertEqual(sum(p['sku_count'] for p in data['products']),6)
        self.assertEqual(len(self.sku_queries),3)
        self.assertEqual(await self.page.evaluate('window.expandCalls'),0)

    async def test_zero_orders_remain_explicit_zero(self):
        self.order_count='0'
        data=await self.package()
        self.assertEqual(data['header']['metrics']['orders_total'],0)

    async def test_order_count_waits_for_page_loading(self):
        self.order_delay=800
        data=await self.package()
        self.assertEqual(data['header']['metrics']['orders_total'],1791)

    async def test_abbreviated_order_count_is_not_accepted(self):
        self.order_count='1.7K'
        with patch('plugins.tiktok.asyncio.sleep',new_callable=AsyncMock):
            with self.assertRaisesRegex(RuntimeError,'明确订单数量'):
                await collect_order_count(self.page,'MY',self.check,self.progress,self.check)
        self.assertNotIn('collection_orders',self.events)

    async def test_conflicting_order_counts_are_not_published(self):
        self.order_list_count='16'
        with patch('plugins.tiktok.asyncio.sleep',new_callable=AsyncMock):
            with self.assertRaisesRegex(RuntimeError,'明确订单数量'):
                await collect_order_count(self.page,'MY',self.check,self.progress,self.check)
        self.assertNotIn('collection_orders',self.events)

    async def test_missing_views_remain_unknown(self):
        self.missing=True;data=await self.package()
        self.assertIsNone(data['products'][0]['views']);self.assertIn('--',data['products'][0]['views_reason'])

    async def test_incomplete_skus_are_not_published(self):
        self.truncated=True
        with self.assertRaisesRegex(RuntimeError,'SKU接口条数'):await self.package()

    async def test_declared_total_must_match_all_pages(self):
        self.declared=4
        with self.assertRaisesRegex(RuntimeError,'不完整分页'):await self.package()

    async def test_duplicate_product_ids_are_not_published(self):
        self.duplicate=True
        with self.assertRaisesRegex(RuntimeError,'重复商品ID'):await self.package()

    async def test_security_challenge_waits_before_reading(self):
        self.challenge=True;data=await self.package()
        self.assertEqual(len(data['products']),3);self.assertIn('waiting_verification',self.events)

    async def test_security_challenge_during_request_retries_after_manual_completion(self):
        self.mid_challenge=True;data=await self.package()
        self.assertEqual(len(data['products']),3);self.assertIn('waiting_verification',self.events)

    async def test_abbreviated_views_are_not_truncated_into_fake_integer(self):
        self.abbreviated=True
        with self.assertRaisesRegex(RuntimeError,'明确整数'):await self.package()

    async def test_other_site_is_rejected_before_navigation(self):
        with self.assertRaisesRegex(RuntimeError,'仅支持'):await open_environment(self.page,'ID',self.check,self.progress)
        self.assertEqual(self.page.url,'about:blank')

    async def test_true_empty_on_sale_list_has_explicit_zero(self):
        self.count=0;data=await self.package()
        self.assertEqual(data['header']['on_sale_count'],0);self.assertTrue(data['header']['empty_verified']);self.assertEqual(data['products'],[])

    async def test_analysis_missing_on_sale_product_is_explicitly_unknown(self):
        self.analysis_missing=True
        data=await self.package()
        self.assertIsNone(data['products'][0]['impressions'])
        self.assertIsNone(data['products'][0]['clicks'])
        self.assertEqual(data['products'][0]['traffic_reason'],'商品分析接口按商品ID查询无记录')
        self.assertEqual(data['products'][1]['impressions'],200)

    async def test_analysis_abbreviated_metrics_are_rejected(self):
        self.analysis_abbreviated=True
        with self.assertRaisesRegex(RuntimeError,'明确整数'):await self.package()

    def test_analysis_api_metrics_preserve_zero_and_reject_unknown(self):
        item={'meta':{'product_id':'1'},'stats_v3':{'total':{'product_impression_pv':'0','product_click_pv':'0','items_sold':'0','gmv':{'amount':'0.00','currency_code':'MYR'}}}}
        self.assertEqual(parse_analysis_item(item),('1',{'impressions':0,'clicks':0,'sales_count':0,'gmv':'0.00'}))
        for value in (None,'--','1.2K'):
            item['stats_v3']['total']['product_impression_pv']=value
            with self.assertRaises(RuntimeError):parse_analysis_item(item)

    async def test_analysis_waits_for_initial_interface_response(self):
        self.analysis_delay=800
        data=await self.package()
        self.assertEqual([p['impressions'] for p in data['products']],[100,200,300])
        self.assertEqual(self.events.count('collecting_product_analysis'),2)

    async def test_analysis_waits_for_next_interface_page(self):
        self.analysis_page_delay=800
        data=await self.package()
        self.assertEqual([p['clicks'] for p in data['products']],[5,10,15])
        self.assertEqual(self.events.count('collecting_product_analysis'),2)

    async def test_analysis_api_completes_overlapping_pages_by_product_id(self):
        self.analysis_duplicate=True
        data=await self.package()
        self.assertEqual([p['impressions'] for p in data['products']],[100,200,300])
        self.assertEqual(self.analysis_api_queries[-1]['body']['search']['search_keyword'],'3')
        self.assertNotIn('gmv',data['header']['metrics'])

    async def test_analysis_api_reads_metrics_without_rendered_product_rows(self):
        self.analysis_no_rows=True
        data=await self.package()
        self.assertEqual(sum(p['clicks'] for p in data['products']),30)
        self.assertTrue(all('msToken' not in v['query'] and 'fp' not in v['query'] for v in self.analysis_api_queries))

    def test_analysis_empty_interface_response_requires_explicit_zero_and_end(self):
        self.assertEqual(analysis_page({'list_control':{'next_pagination':{'total':0,'has_more':False}}})[0],[])
        for control in ({'total':1,'has_more':False},{'total':0,'has_more':True}):
            with self.assertRaises(RuntimeError):analysis_page({'list_control':{'next_pagination':control}})

    def test_analysis_gmv_requires_explicit_amount_and_myr_currency(self):
        item={'meta':{'product_id':'1'},'stats_v3':{'total':{'product_impression_pv':'1','product_click_pv':'0','items_sold':'0','gmv':{'amount':'276.61','currency_code':'MYR'}}}}
        self.assertEqual(parse_analysis_item(item)[1]['gmv'],'276.61')
        for gmv in (None,{'amount':'1.00','currency_code':'USD'},{'amount':'--','currency_code':'MYR'},{'amount':'-1.00','currency_code':'MYR'}):
            item['stats_v3']['total']['gmv']=gmv
            with self.assertRaises(RuntimeError):parse_analysis_item(item)
