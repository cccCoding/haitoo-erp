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
from plugins.flash_sales import renew_flash_sales,new_window,times,PageBlocked,STATES,normalize_headers,parse_activity_cells,MerchantFlashPage
from plugins.tiktok import site_timezone
TZ=site_timezone('MY')


class FlashExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self,status='ongoing',stage='pending',eligible=True,fail_at=None):
        events=[]
        observation={'external_id':'old','name':'秒杀','activity_type':'商家秒杀活动','status':status,'ends_at':datetime.now(TZ).isoformat(),'product_count':2}
        record={'id':1,'external_id':'old','stage':stage,'new_activity_id':'draft' if stage=='draft_confirmed' else None}
        class UI:
            def __init__(self,page,stop):pass
            async def scan(self):events.append('scan');return [observation]
            async def preflight(self,a):events.append('preflight')
            async def terminate(self,a):
                events.append('terminate')
                if fail_at=='terminate':raise RuntimeError('终止超时')
            async def copy(self,a):events.append('copy');return 'new'
            async def open_draft(self,a):events.append('open_draft')
            async def configure(self,start,end,count):events.append('configure');self.start,self.end=start,end
            async def publish(self):
                events.append('publish')
                if fail_at=='publish':raise RuntimeError('发布响应超时')
            async def verify(self,external,start,end):events.append('verify');return '已核对平台活动ID和时间'
        async def rpc(path,body):
            events.append((path,body))
            if path=='scan':return {'renewals':[record]}
            if path.endswith('/recheck'):return {'eligible':eligible,'status':status}
            if path=='complete':return {'complete':fail_at is None and stage!='unknown'}
            return {}
        async def noop(*a):pass
        result=await renew_flash_sales(None,'MY',{},rpc,noop,noop,ui_factory=UI)
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
        self.assertEqual(actions,['scan','scan','preflight','terminate','copy','configure','publish','verify'])
        checkpoints=[e[1]['stage'] for e in events if isinstance(e,tuple) and e[0].endswith('/step')]
        self.assertEqual(checkpoints,['terminate_intent','terminated','copy_intent','draft_confirmed','publish_intent','published'])
        planned=next(e[1] for e in events if isinstance(e,tuple) and e[1].get('stage')=='publish_intent')
        self.assertEqual(datetime.fromisoformat(planned['ends_at'])-datetime.fromisoformat(planned['starts_at']),timedelta(hours=72))

    async def test_expired_selection_never_terminates(self):
        events,result=await self.run_case(status='expired')
        self.assertNotIn('terminate',events);self.assertIn('copy',events)

    async def test_expired_recheck_skips_without_writing(self):
        events,result=await self.run_case(status='expired',eligible=False)
        self.assertNotIn('copy',events);self.assertNotIn('terminate',events)
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
        self.assertNotIn('terminate',events);self.assertNotIn('copy',events);self.assertIn('open_draft',events)

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


@unittest.skipUnless(os.getenv('HAITOO_FLASH_BROWSER_TESTS')=='1','需显式启用隔离活动DOM浏览器测试')
class FlashTableBrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.playwright=await async_playwright().start()
        self.browser=await self.playwright.chromium.launch(channel='chrome',headless=True)
        self.context=await self.browser.new_context();self.page=await self.context.new_page()
        self.duplicate=False;self.without_id=False
        await self.context.route('**/*',self.serve)

    async def asyncTearDown(self):
        await self.context.close();await self.browser.close();await self.playwright.stop()

    async def serve(self,route):
        second='1001' if self.duplicate else '1003'
        attr='' if self.without_id else 'data-republish-entry-guide-promotion-id="1001"'
        first=f'<tr><td>秒杀A</td><td>进行中</td><td>2026/11/12&nbsp;11:53</td><td>2026/11/15&nbsp;11:53</td><td>商家秒杀活动</td><td><div {attr}><button>复制</button></div></td></tr>'
        ignored='<tr><td>商品折扣A</td><td>进行中</td><td>2026/11/12 11:53</td><td>2027/05/15 11:53</td><td>商品折扣</td><td>复制</td></tr>'
        last=f'<tr><td>秒杀B</td><td>已结束</td><td>2026/11/09 11:53</td><td>2026/11/12 11:53</td><td>商家秒杀活动</td><td><button data-testid="promotion-action-{second}">复制</button></td></tr>'
        html="""<table style="display:none"><thead><tr><th>隐藏列表</th></tr></thead></table>
        <table><thead><tr><th>活动名称</th><th>状态</th><th>开始时间<br>(GMT+8)</th><th>结束时间<br>(GMT+8)</th><th>类型</th><th>操作</th></tr></thead><tbody id="rows"></tbody></table>
        <div class="p-pagination"><ul><li class="p-pagination-item-active" aria-label="第 1 页">1</li><li class="p-pagination-item-next" aria-label="下一个">&gt;</li></ul></div><script>
        const rows=ROWS;document.querySelector('#rows').innerHTML=rows[0];
        document.querySelector('.p-pagination-item-next').onclick=()=>{document.querySelector('#rows').innerHTML=rows[1];document.querySelector('.p-pagination-item-active').setAttribute('aria-label','第 2 页');document.querySelector('.p-pagination-item-next').classList.add('p-pagination-item-disabled');};
        </script>""".replace('ROWS',json.dumps([first+ignored,last]))
        await route.fulfill(status=200,content_type='text/html; charset=utf-8',body='<meta charset="utf-8">'+html)

    async def adapter(self):
        async def stop():pass
        return MerchantFlashPage(self.page,stop)

    async def test_real_dom_columns_row_ids_and_list_pagination(self):
        rows=await (await self.adapter()).scan()
        self.assertEqual([r['external_id'] for r in rows],['1001','1003'])
        self.assertEqual([r['status'] for r in rows],['ongoing','expired'])

    async def test_duplicate_activity_across_pages_rejects_partial_scan(self):
        self.duplicate=True
        with self.assertRaisesRegex(PageBlocked,'ID重复'):await (await self.adapter()).scan()

    async def test_missing_platform_id_fails_without_copying(self):
        self.without_id=True
        with self.assertRaisesRegex(PageBlocked,'唯一平台活动ID'):await (await self.adapter()).scan()


if __name__=='__main__':unittest.main()
