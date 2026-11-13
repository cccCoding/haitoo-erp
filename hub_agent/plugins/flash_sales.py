"""商家秒杀续期执行器。源码回环调试可显式启用；正式环境须通过已验收签名插件开放。"""
import asyncio
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit, parse_qs
from playwright.async_api import TimeoutError as BrowserTimeout
from .tiktok import site_timezone

TASK = 'promotion.flash_sale.renew'
COLLECT_TASK = 'promotion.flash_sale.collect'
URL = 'https://seller.tiktokshopglobalselling.com/promotion/marketing-tools/management?tab=1&shop_region=MY'
TYPE = '商家秒杀活动'
STATES = {'未开始':'scheduled','进行中':'ongoing','已结束':'expired','已终止':'terminated'}
TERMINAL = {'published','failed','skipped','cancelled'}


class PageBlocked(RuntimeError):
    """店铺级问题，禁止继续本环境。"""


def times(text):
    values = re.findall(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{1,2}(?::\d{1,2})?', text)
    result=[]
    for value in values:
        normalized=value.replace('/','-')
        result.append(datetime.strptime(normalized,'%Y-%m-%d %H:%M:%S' if normalized.count(':')==2 else '%Y-%m-%d %H:%M').replace(tzinfo=site_timezone('MY')))
    return result


def new_window(now=None):
    # 预留5分钟，避免平台校验时开始时间已过去；向上取整到分钟。
    start=((now or datetime.now(site_timezone('MY')))+timedelta(minutes=6)).replace(second=0,microsecond=0)
    return start,start+timedelta(hours=72)


def activity_id(url):
    values=parse_qs(urlsplit(url).query)
    ids=[values[key][0] for key in ('activity_id','promotion_id') if values.get(key)]
    if len(set(ids))!=1:raise PageBlocked('页面缺少唯一活动ID，不能操作')
    return ids[0]


def normalize_headers(values):
    result=[]
    for value in values:
        text=re.sub(r'\s+','',value)
        for name in ('开始时间','结束时间'):
            if re.fullmatch(re.escape(name)+r'(?:[（(]GMT\+8[）)])?',text):text=name
        result.append(text)
    return result


def parse_activity_cells(headers,cells):
    if len(headers)!=len(cells):raise PageBlocked('活动行结构不完整，未保存残缺扫描')
    value=dict(zip(headers,[v.strip() for v in cells]))
    if value['类型']!=TYPE:return None
    try:start,end=times(value['开始时间']),times(value['结束时间'])
    except ValueError as exc:raise PageBlocked('平台活动时间包含无效日期或时分，未保存残缺扫描') from exc
    if len(start)!=1 or len(end)!=1:raise PageBlocked(f"商家秒杀活动起止时间无法核对：开始 {value['开始时间'][:50]}，结束 {value['结束时间'][:50]}")
    count=value.get('商品数量','')
    return {'name':value['活动名称'],'activity_type':TYPE,'status':STATES.get(value['状态'],'unknown'),
        'starts_at':start[0].isoformat(),'ends_at':end[0].isoformat(),'product_count':int(count) if count.isdigit() else None}


class MerchantFlashPage:
    """严格匹配中文语义和完整分页；页面不符合已支持结构时停止，不猜测控件。"""
    def __init__(self,page,check_stop):self.page,self.check_stop=page,check_stop

    async def ready(self):
        await self.check_stop()
        parsed=urlsplit(self.page.url)
        if parsed.scheme!='https' or parsed.hostname!='seller.tiktokshopglobalselling.com':raise PageBlocked('页面已离开目标跨境店入口')
        regions=parse_qs(parsed.query).get('shop_region',[])
        if regions and regions!=['MY']:raise PageBlocked('页面站点不属于马来西亚')
        if 'login' in parsed.path.lower():raise PageBlocked('登录已失效，请完成登录后重试')
        if await self.page.get_by_text(re.compile('请完成安全验证|拖动滑块|请先登录')).count():raise PageBlocked('需要人工登录或安全验证')
        for loader in await self.page.get_by_role('progressbar').all():
            if await loader.is_visible():raise PageBlocked('活动列表仍在加载，不能确认完整性')

    async def table(self):
        matches=[];observed=[]
        for table in await self.page.locator('table:visible').all():
            headers=normalize_headers(await table.locator('thead th').all_inner_texts())
            observed.append(headers)
            if {'活动名称','状态','开始时间','结束时间','类型','操作'} <= set(headers):matches.append(table)
        if len(matches)!=1:raise PageBlocked(f'未找到唯一活动列表：预期列为活动名称、状态、开始时间、结束时间、类型、操作；实际表头 {observed}')
        return matches[0]

    async def wait_for_rows(self):
        try:
            await self.page.wait_for_function("""()=>{
                const visible=el=>el.getClientRects().length && getComputedStyle(el).visibility!=='hidden';
                const tables=[...document.querySelectorAll('table')].filter(visible);
                return tables.some(table=>{
                    const heads=[...table.querySelectorAll('thead th')].map(h=>h.innerText.trim());
                    if(!heads.includes('活动名称') || !heads.includes('类型'))return false;
                    const rows=[...table.querySelectorAll('tbody tr')];
                    return rows.length>0 && rows.every(row=>{
                        const cells=row.querySelectorAll(':scope > td');
                        return cells.length===heads.length || cells.length===1 && /^(暂无数据|暂无活动|暂无促销活动)$/.test(row.innerText.trim());
                    });
                });
            }""",timeout=30000)
        except BrowserTimeout as exc:
            raise PageBlocked('活动列表数据30秒内未加载完成，未保存残缺扫描；请检查环境网络') from exc

    async def open(self):
        try:
            await self.check_stop()
            await self.page.goto(URL,wait_until='domcontentloaded',timeout=60000)
        except BrowserTimeout as exc:
            raise PageBlocked('打开秒杀活动管理页超时，请检查所选环境的网络与登录状态；尚未操作活动') from exc
        try:
            await self.page.locator('table:visible').first.wait_for(timeout=30000)
        except BrowserTimeout as exc:
            await self.ready()
            raise PageBlocked('活动管理页30秒内未出现列表，请检查页面是否加载失败或需要登录；尚未操作活动') from exc
        await self.ready()
        await self.table()
        await self.wait_for_rows()

    async def next_page(self,table):
        button=self.page.locator('.p-pagination:visible .p-pagination-item-next')
        active=self.page.locator('.p-pagination:visible .p-pagination-item-active')
        if await button.count()!=1 or await button.get_attribute('aria-label')!='下一个' or await active.count()!=1:
            raise PageBlocked('活动列表缺少可核对的分页控件，不能确认扫描完整性')
        if 'p-pagination-item-disabled' in (await button.get_attribute('class') or '').split() or await button.get_attribute('aria-disabled')=='true':return False
        before=await table.locator('tbody').inner_text()
        page_before=await active.get_attribute('aria-label')
        await self.check_stop()
        await button.click()
        try:
            await self.page.wait_for_function('''({before,pageBefore})=>{
                const visible=el=>el.getClientRects().length && getComputedStyle(el).visibility!=='hidden';
                const tables=[...document.querySelectorAll('table')].filter(visible);
                const active=[...document.querySelectorAll('.p-pagination-item-active')].filter(visible);
                return active.length===1 && active[0].getAttribute('aria-label')!==pageBefore &&
                    tables.some(t=>t.querySelector('tbody')?.innerText!==before);
            }''',arg={'before':before,'pageBefore':page_before},timeout=20000)
        except BrowserTimeout as exc:
            raise PageBlocked('活动列表翻页超时，未保存残缺扫描；请检查页面网络后重试') from exc
        await self.wait_for_rows()
        return True

    async def scan(self):
        await self.open()
        result=[];seen=set();pages_seen=set()
        for _ in range(200):
            await self.ready()
            table=await self.table()
            headers=normalize_headers(await table.locator('thead th').all_inner_texts())
            signature=await table.locator('tbody').inner_text()
            if signature in pages_seen:raise PageBlocked('活动分页重复，不能确认完整活动列表')
            pages_seen.add(signature)
            for row in await table.locator('tbody tr').all():
                cells=await row.locator(':scope > td').all_inner_texts()
                # 平台空列表占位行不构成活动，必须有明确的空数据文案。
                if len(cells)==1 and re.fullmatch(r'\s*(暂无数据|暂无活动|暂无促销活动)\s*',cells[0]):continue
                value=parse_activity_cells(headers,cells)
                if value is None:continue
                value['external_id']=await self.row_id(row)
                if value['external_id'] in seen:raise PageBlocked('商家秒杀活动ID重复，不能保存完整扫描')
                seen.add(value['external_id']);result.append(value)
            if not await self.next_page(table):return result
        raise PageBlocked('活动分页超过200页扫描上限，未保存残缺结果')

    async def row_id(self,row):
        values=set(await row.locator('[data-republish-entry-guide-promotion-id]').evaluate_all('(nodes)=>nodes.map(n=>n.getAttribute("data-republish-entry-guide-promotion-id"))'))
        for testid in await row.locator('[data-testid^="promotion-action-"]').evaluate_all('(nodes)=>nodes.map(n=>n.getAttribute("data-testid"))'):
            match=re.fullmatch(r'promotion-action-(\d+)(?:-more)?',testid or '')
            if match:values.add(match.group(1))
        values.discard(None)
        if len(values)!=1 or not re.fullmatch(r'\d{1,120}',next(iter(values),'') or ''):
            raise PageBlocked('商家秒杀活动行缺少唯一平台活动ID')
        return values.pop()

    async def row(self,external):
        table=await self.table();matches=[]
        headers=normalize_headers(await table.locator('thead th').all_inner_texts())
        for row in await table.locator('tbody tr').all():
            values=await row.locator(':scope > td').all_inner_texts()
            if len(values)!=len(headers) or dict(zip(headers,values)).get('类型','').strip()!=TYPE:continue
            if await self.row_id(row)==external:matches.append(row)
        if len(matches)!=1:raise PageBlocked('当前分页没有唯一目标商家秒杀活动')
        return matches[0]

    async def locate(self,external):
        await self.open()
        for _ in range(200):
            await self.ready()
            try:return await self.row(external)
            except PageBlocked:pass
            if not await self.next_page(await self.table()):break
        raise PageBlocked('目标商家秒杀活动不在完整列表中')

    async def preflight(self,activity):
        row=await self.locate(activity['external_id'])
        # 未终止前必须看到允许复制的入口；不依赖禁用按钮尝试副作用。
        button=row.get_by_role('button',name='复制',exact=True)
        if await button.count()!=1 or not await button.is_enabled():raise RuntimeError('平台尚未提供可用复制入口，保留原活动')
        if activity.get('product_count') is None:raise RuntimeError('无法核对原活动商品数量，保留原活动')
        if await row.get_by_text(re.compile('冲突|商品失效|价格失效')).count():raise RuntimeError('活动存在商品或价格限制，请人工处理')

    async def terminate(self,external):
        row=await self.locate(external)
        await row.get_by_role('button',name='终止',exact=True).click()
        dialog=self.page.get_by_role('dialog')
        if await dialog.count()!=1:raise PageBlocked('未出现唯一终止确认框')
        await dialog.get_by_role('button',name=re.compile('^(确定|确认终止)$')).click()
        await row.get_by_text('已终止',exact=True).wait_for(timeout=20000)

    async def copy(self,external):
        row=await self.locate(external)
        await row.get_by_role('button',name='复制',exact=True).click()
        await self.page.get_by_role('button',name='发布',exact=True).wait_for(timeout=20000)
        await self.ready()
        return activity_id(self.page.url)

    async def open_draft(self,external):
        row=await self.locate(external)
        await row.get_by_role('button',name='编辑',exact=True).click()
        await self.page.get_by_role('button',name='发布',exact=True).wait_for(timeout=20000)
        if activity_id(self.page.url)!=external:raise PageBlocked('草稿ID不匹配')

    async def configure(self,start,end,expected_count):
        await self.ready()
        # 保持复制的商品和价格原样，只填写时间并同意平台条款。
        count=self.page.get_by_text(re.compile(r'^已选\s*'+str(expected_count)+r'\s*个商品$'))
        if expected_count is None or await count.count()!=1:raise RuntimeError('复制后的商品数量与原活动无法核对')
        alerts=self.page.get_by_role('alert')
        if any(text.strip() for text in await alerts.all_inner_texts()):raise RuntimeError('平台编辑页存在限制或校验提示，请人工处理')
        for label,value in [('开始时间',start),('结束时间',end)]:
            field=self.page.get_by_role('textbox',name=label,exact=True)
            if await field.count()!=1:raise RuntimeError('时间控件结构未通过验收')
            await field.fill(value.astimezone(site_timezone('MY')).strftime('%Y-%m-%d %H:%M:%S'))
            await field.press('Tab')
        consent=self.page.get_by_role('checkbox',name=re.compile('.*同意.*'))
        if await consent.count()!=1:raise RuntimeError('缺少唯一平台同意项')
        await consent.check()
        button=self.page.get_by_role('button',name='发布',exact=True)
        if not await button.is_enabled():raise RuntimeError('平台不允许发布，请检查商品或活动时间')

    async def publish(self):
        await self.page.get_by_role('button',name='发布',exact=True).click()

    async def verify(self,external,start,end):
        activities=await self.scan()
        matches=[a for a in activities if a['external_id']==external]
        if len(matches)!=1 or matches[0]['status'] not in {'ongoing','scheduled'}:raise RuntimeError('未找到明确发布的新商家秒杀活动')
        row=await self.locate(external)
        values=times(await row.inner_text())
        if len(values)!=2 or values[0]!=start or values[1]!=end:raise RuntimeError('新活动时间与本次发布参数不一致')
        return f'已核对商家秒杀活动 {external}，{start.isoformat()} — {end.isoformat()}'


async def renew_flash_sales(page,site,config,rpc,check_stop,progress,ui_factory=MerchantFlashPage):
    """rpc由宿主绑定租约；插件不会取得ERP令牌。所有未知副作用先交人工核对。"""
    if site!='MY':raise RuntimeError('秒杀续期仅支持MY跨境店')
    ui=ui_factory(page,check_stop)
    await progress('flash_scan','正在完整读取商家秒杀活动，已自然到期活动只生成候选')
    activities=await ui.scan()
    records=(await rpc('scan',{'complete':True,'activities':activities}))['renewals']
    for record in records:
        await check_stop()
        if record['stage'] in TERMINAL:continue
        rid=record['id'];stage=record['stage'];new_id=record.get('new_activity_id')
        async def checkpoint(next_stage,**values):
            nonlocal stage
            await check_stop()
            await rpc(f'{rid}/step',{'stage':next_stage,**values})
            stage=next_stage
        try:
            # 旧意图不能自行假设未提交；已知草稿/已终止阶段可恢复。
            if stage in {'terminate_intent','copy_intent','publish_intent','unknown'}:
                if stage=='publish_intent' and new_id and record.get('starts_at') and record.get('ends_at'):
                    start=datetime.fromisoformat(record['starts_at'].replace('Z','+00:00'))
                    end=datetime.fromisoformat(record['ends_at'].replace('Z','+00:00'))
                    evidence=await ui.verify(new_id,start,end)
                    await checkpoint('published',new_activity_id=new_id,starts_at=start.isoformat(),ends_at=end.isoformat(),evidence=evidence)
                    continue
                raise RuntimeError('上次平台操作结果待核对，禁止重复终止、复制或发布')
            latest=await ui.scan()
            matches=[a for a in latest if a['external_id']==record['external_id']]
            if len(matches)!=1:raise PageBlocked('来源活动不再唯一可见')
            activity=matches[0]
            if stage=='pending':
                checked=await rpc(f'{rid}/recheck',{'activity':activity})
                if not checked['eligible']:
                    await checkpoint('skipped',evidence='活动状态已变化；自然到期活动转用户选择')
                    continue
                await ui.preflight(activity)
                if activity['status']=='ongoing':
                    await checkpoint('terminate_intent')
                    await ui.terminate(record['external_id'])
                    await checkpoint('terminated',evidence='平台列表明确显示已终止')
            if stage in {'pending','terminated'}:
                await checkpoint('copy_intent')
                new_id=await ui.copy(record['external_id'])
                await checkpoint('draft_confirmed',new_activity_id=new_id,evidence='复制后进入具有唯一新活动ID的编辑页')
            elif stage=='draft_confirmed':
                await ui.open_draft(new_id)
            start,end=new_window()
            await ui.configure(start,end,activity.get('product_count'))
            await checkpoint('publish_intent',new_activity_id=new_id,starts_at=start.isoformat(),ends_at=end.isoformat())
            await ui.publish()
            evidence=await ui.verify(new_id,start,end)
            await checkpoint('published',new_activity_id=new_id,starts_at=start.isoformat(),ends_at=end.isoformat(),evidence=evidence)
        except BaseException as exc:
            if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
            # 网络中断可能发生在保存意图的响应返回前；本地不能据stage推断服务端未保存。
            try:
                if stage in {'terminate_intent','copy_intent','publish_intent'}:
                    await rpc(f'{rid}/step',{'stage':'unknown','error':'平台操作结果未知，请核对活动明细'})
                elif stage in {'terminated','draft_confirmed','unknown'}:
                    await rpc(f'{rid}/step',{'stage':stage,'error':str(exc)[:500] or '执行中断，请核对已保存阶段'})
                elif stage=='pending' and not isinstance(exc,asyncio.CancelledError):
                    await rpc(f'{rid}/step',{'stage':'failed','error':str(exc)[:500]})
            except Exception:pass
            if isinstance(exc,(PageBlocked,asyncio.CancelledError)):raise
            await progress('flash_attention',f"活动 {record['external_id']} 未完成，已保存阶段供人工核对")
    return await rpc('complete',{})


async def collect_flash_sales(page,site,config,rpc,check_stop,progress):
    """独立只读同步，不调用续期执行器及任何平台写操作。"""
    if site!='MY':raise RuntimeError('秒杀活动同步仅支持MY跨境店')
    await progress('flash_scan','正在只读同步全部状态的商家秒杀活动')
    activities=await MerchantFlashPage(page,check_stop).scan()
    await check_stop()
    await rpc('scan',{'complete':True,'activities':activities})
    return await rpc('complete',{})
