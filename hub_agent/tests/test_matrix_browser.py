"""真实 MY 商品接口结构的隔离回归；不访问真实 TikTok。"""
import json,os,sys,unittest
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright
from plugins.tiktok import collect,open_environment,PRODUCTS_PATH,SKUS_PATH


@unittest.skipUnless(os.getenv('HAITOO_MATRIX_BROWSER_TESTS')=='1','需启用隔离矩阵浏览器测试')
class MatrixBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright=await async_playwright().start()
        self.browser=await self.playwright.chromium.launch(channel=os.getenv('HAITOO_BROWSER_CHANNEL') or 'chrome')
        self.context=await self.browser.new_context();self.page=await self.context.new_page()
        self.count=3;self.missing=False;self.truncated=False;self.partial=False;self.declared=None
        self.challenge=False;self.mid_challenge=False;self.abbreviated=False;self.triggered=False;self.duplicate=False
        self.events=[];self.bulk_queries=[];self.sku_queries=[]
        await self.context.route('**/*',self.route)

    async def asyncTearDown(self):
        await self.browser.close();await self.playwright.stop()

    def skus(self,pid):
        return [{'id':f'sku-{pid}-{i}','seller_sku':f'S{pid}-{i}','base_price':{'region':'MY','currency':'MYR','sale_price':'109.00','promotion_price':'39.99'},
            'quantities':[{'available_quantity':999}],'properties':[{'value_name':f'Color {pid}'},{'value_name':str(i)}]} for i in (1,2)]

    async def route(self,route):
        parsed=urlsplit(route.request.url);query=parse_qs(parsed.query)
        cors={'Access-Control-Allow-Origin':'https://seller.tiktokshopglobalselling.com','Access-Control-Allow-Credentials':'true',
            'Access-Control-Allow-Methods':'GET,OPTIONS','Access-Control-Allow-Headers':'content-type,x-tt-oec-region'}
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
        if '/product/manage' in parsed.path:
            challenge='''<div id="captcha_container" style="position:fixed;inset:0">验证</div><script>setTimeout(()=>document.querySelector('#captcha_container').remove(),300)</script>''' if self.challenge else ''
            html=f'''<!doctype html><meta charset="utf-8"><div role="tab" aria-selected="true">在售 {self.count}</div><button onclick="window.expandCalls++">展开</button>{challenge}<script>window.expandCalls=0;fetch('https://api16-normal-sg.tiktokshopglobalselling.com{PRODUCTS_PATH}?page_number=1&page_size=2&sku_number=1&tab_id=2&seller_id=fixture&msToken=do-not-copy&fp=do-not-copy',{{credentials:'include'}})</script>'''
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
        self.assertIsNone(data['header']['window_start']);self.assertIsNone(data['products'][0]['impressions'])
        self.assertEqual(data['header']['sections']['traffic'],'unsupported')
        self.assertEqual(await self.page.evaluate('window.expandCalls'),0)
        self.assertEqual(len(self.bulk_queries),2);self.assertEqual(self.sku_queries,[])
        self.assertTrue(all('msToken' not in q and 'fp' not in q for q in self.bulk_queries))

    async def test_only_truncated_list_skus_use_direct_sku_endpoint(self):
        self.partial=True
        data=await self.package()
        self.assertEqual(sum(p['sku_count'] for p in data['products']),6)
        self.assertEqual(len(self.sku_queries),3)
        self.assertEqual(await self.page.evaluate('window.expandCalls'),0)

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
