"""马来西亚跨境店只读页面适配。入口按站点与店铺类型定义。"""
import asyncio
import re
from playwright.async_api import TimeoutError as BrowserTimeout, expect
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlsplit, parse_qs, urlencode

# 声明代码实现的能力；公司与成员授权始终由 ERP 后台校验。
# 环境入口、在售总数、商品分页和SKU明细仍须每次核验。
CAPABILITIES={'shop.collect':['MY'],'listing.catalog':['MY']}
# 当前只启用这一组合；未来本土店须提供独立适配，不能回退到跨境入口。
PROFILES={('MY','cross_border'):{
    'url':'https://seller.tiktokshopglobalselling.com/product/manage?shop_region=MY',
    'host':'seller.tiktokshopglobalselling.com','api_host':'api16-normal-sg.tiktokshopglobalselling.com','timezone':'Asia/Kuala_Lumpur',
    'upload_url':'https://seller.tiktokshopglobalselling.com/product/batch/publish?step=2&shop_region=MY'}}


def profile(site,shop_type='cross_border'):
    value=PROFILES.get((site,shop_type))
    if value is None:raise RuntimeError('当前仅支持马来西亚（MY）跨境店，不支持本土店或其他站点')
    return value


def site_timezone(site):
    try:
        return ZoneInfo(profile(site)['timezone'])
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError('连接器缺少站点时区数据，请更新或重新安装新版连接器后重试') from exc


def allowed(url,site):
    p=urlsplit(url)
    config=PROFILES.get((site,'cross_border'))
    regions=parse_qs(p.query,keep_blank_values=True).get('shop_region',[])
    return bool(config and p.scheme=='https' and not p.username and not p.password
                and p.hostname==config['host'] and p.port in (None,443)
                and (not regions or regions==[site]))


def identity_payload(payload,site):
    if not isinstance(payload,dict) or payload.get('code') not in (0,'0',None):return None
    data=payload.get('data',{})
    if not isinstance(data,dict):return None
    # 仅识别明确的当前店铺对象，不遍历商品、订单中的其他seller_id。
    candidates=[data[k] for k in ('shop_info','seller_info','current_shop') if isinstance(data.get(k),dict)]
    for obj in candidates:
        sid=obj.get('shop_id') or obj.get('seller_id')
        name=obj.get('shop_name') or obj.get('seller_name')
        region=obj.get('shop_region') or obj.get('region')
        if sid and isinstance(name,str) and region==site:
            return {'site':site,'external_id':str(sid),'name':name[:255]}
    return None


PRODUCTS_PATH='/api/v1/product/local/products/list'
SKUS_PATH='/api/v1/product/local/product/skus/list'
# 只保留正常页面使用的业务参数；不复制签名、令牌、Cookie或指纹。
BUSINESS_QUERY={'is_need_target_stock','page_number','page_size','product_sort_fields','product_sort_types',
    'same_product_page_size','sku_number','tab_id','locale','language','oec_seller_id','seller_id','aid','app_name','device_platform'}


def product_response(response,site):
    parsed=urlsplit(response.url)
    return parsed.scheme=='https' and parsed.hostname==profile(site)['api_host'] and parsed.path==PRODUCTS_PATH and response.request.method=='GET'


def capture_context(page,site):
    state=getattr(page,'_matrix_product_context',None)
    if state is not None:return state
    state={}
    def remember(response):
        if product_response(response,site):
            parsed=urlsplit(response.url)
            state['params']={k:v[-1] for k,v in parse_qs(parsed.query).items() if k in BUSINESS_QUERY}
    state['listener']=remember
    page.on('response',remember)
    page._matrix_product_context=state
    return state


async def open_environment(page,site,check_stop,progress):
    config=profile(site)
    capture_context(page,site)
    await progress('opening_shop','正在打开所选环境的商品管理页')
    await page.goto(config['url'],wait_until='domcontentloaded',timeout=60000)
    for tick in range(600):
        await check_stop()
        if 'login' not in page.url.lower():
            if not allowed(page.url,site):raise RuntimeError('当前页面不属于马来西亚跨境店入口，请核对环境站点')
            return
        if tick==0:
            await page.bring_to_front()
            await progress('waiting_login','请在当前Hub环境完成登录与验证，最多等待10分钟')
        await asyncio.sleep(1)
    raise RuntimeError('等待登录超时，请在目标环境完成登录后重试')


def number(text):
    text=text.strip().replace(',','')
    if not re.fullmatch(r'\d+',text):raise RuntimeError('商品流量不是明确整数，拒绝推测')
    return int(text)


def money(text):
    value=text.strip().replace(',','')
    if not re.fullmatch(r"\d+(?:\.\d{1,4})?",value):raise RuntimeError('SKU价格不是明确数值，拒绝推测')
    return value


def parse_sku(sku):
    sid=sku.get('id')
    if not isinstance(sid,str) or not sid:raise RuntimeError('SKU接口缺少明确的字符串SKU ID')
    prices=[v for v in (sku.get('region_prices') or []) if v.get('region')=='MY' and v.get('currency')=='MYR']
    base=sku.get('base_price',{})
    if base.get('region')=='MY' and base.get('currency')=='MYR':price=base
    elif len(prices)==1:price=prices[0]
    else:raise RuntimeError('SKU接口缺少唯一MYR价格')
    quantities=sku.get('quantities')
    if not isinstance(quantities,list) or not quantities:raise RuntimeError('SKU接口未提供库存明细')
    stock=0
    for quantity in quantities:
        value=quantity.get('available_quantity')
        if not isinstance(value,int) or isinstance(value,bool) or value<0:raise RuntimeError('SKU可用库存不是明确的非负整数')
        stock+=value
    properties=sku.get('properties') or []
    names=[v['value_name'] for v in properties if isinstance(v.get('value_name'),str) and v['value_name'].strip()]
    seller=sku.get('seller_sku')
    return {'external_id':sid,'name':' - '.join(names) or None,'seller_sku':seller.strip() if isinstance(seller,str) and seller.strip() else None,
        'stock':stock,'price':money(str(price.get('sale_price',''))),'sale_price':money(str(price['promotion_price'])) if price.get('promotion_price') not in (None,'') else None,'currency':'MYR'}


ANALYSIS_PATH='/compass/product-analysis'
ANALYSIS_COLUMNS={'gmv':'GMV','impressions':'商品曝光次数','clicks':'商品点击量','sales_count':'商品成交件数'}


async def analysis_columns(page):
    """只补选缺少的指标，保留用户已有的其他列。"""
    headers=page.locator('th, [role="columnheader"]')
    names=await headers.all_text_contents()
    if all(any(re.sub(r'\s+','',name)==label for name in names) for label in ANALYSIS_COLUMNS.values()):return
    edit=page.get_by_role('button',name=re.compile(r'自定义指标|Customize metrics|Edit metrics',re.I))
    if await edit.count()==1:
        await edit.click()
    else:
        export=page.get_by_text(re.compile(r'^(导出数据|Export data)$')).last
        # 平台的编辑指标按钮只有图标，位于导出数据控件之前。
        control=export.locator('xpath=ancestor-or-self::*[self::button or @role="button"][1]')
        if not await control.count():control=export.locator('..')
        await control.locator('xpath=preceding-sibling::*[1]').click()
    title=page.get_by_text('自定义指标',exact=True)
    await title.wait_for(state='visible',timeout=15000)
    dialog=title.locator('xpath=ancestor::*[.//button[normalize-space(.)="确定"] or .//*[@role="button" and normalize-space(.)="确定"]][1]')
    for label in ANALYSIS_COLUMNS.values():
        checkbox=dialog.get_by_role('checkbox',name=label,exact=True)
        if await checkbox.count()!=1:
            checkbox=dialog.get_by_text(label,exact=True).first.locator('xpath=ancestor::label[1]').locator('input[type="checkbox"], [role="checkbox"]')
        if await checkbox.count()!=1:raise RuntimeError(f'无法唯一识别自定义指标：{label}')
        if not await checkbox.is_checked():
            await dialog.get_by_text(label,exact=True).first.click()
            await expect(checkbox).to_be_checked()
    await dialog.get_by_role('button',name='确定',exact=True).click()
    await title.wait_for(state='hidden',timeout=15000)
    for label in ANALYSIS_COLUMNS.values():
        await expect(headers.filter(has_text=re.compile(r'^\s*'+re.escape(label)+r'\s*$'))).to_have_count(1)


ANALYSIS_API_PATH='/api/v3/insights/seller/ttp/product/list'
ANALYSIS_PAGE_SIZE=500
ANALYSIS_NO_RECORD='商品分析接口按商品ID查询无记录'
ANALYSIS_FIELDS={'impressions':'product_impression_pv','clicks':'product_click_pv','sales_count':'items_sold'}


def parse_analysis_item(item):
    if not isinstance(item,dict) or not isinstance(item.get('meta'),dict):raise RuntimeError('商品分析接口商品结构无法识别')
    meta=item['meta']
    pid=meta.get('product_id')
    if not isinstance(pid,str) or not pid:raise RuntimeError('商品分析接口缺少明确商品ID')
    stats_v3=item.get('stats_v3')
    if not isinstance(stats_v3,dict) or not isinstance(stats_v3.get('total'),dict):raise RuntimeError(f'商品 {pid} 的分析指标结构无法识别')
    stats=stats_v3['total']
    values={}
    for key,field in ANALYSIS_FIELDS.items():
        value=stats.get(field)
        if value is None:raise RuntimeError(f'商品 {pid} 的分析指标缺失：{field}')
        values[key]=number(str(value))
    gmv=stats.get('gmv')
    if not isinstance(gmv,dict) or gmv.get('currency_code')!='MYR' or not isinstance(gmv.get('amount'),str):
        raise RuntimeError(f'商品 {pid} 的GMV缺少明确MYR金额')
    values['gmv']=money(gmv['amount'])
    return pid,values


def analysis_page(data):
    if not isinstance(data,dict) or not isinstance(data.get('list_control'),dict):
        raise RuntimeError('商品分析接口结构无法识别')
    control=data['list_control'].get('next_pagination')
    if not isinstance(control,dict):raise RuntimeError('商品分析接口缺少分页信息')
    total=control.get('total')
    if not isinstance(total,int) or isinstance(total,bool) or not 0<=total<=100000:raise RuntimeError('商品分析接口未提供有效总数')
    if not isinstance(control.get('has_more'),bool):raise RuntimeError('商品分析接口缺少分页结束标记')
    items=data.get('items')
    # 平台的零条响应可能省略items字段，须有明确的总数及结束标记。
    if items is None and control.get('total')==0 and control.get('has_more') is False:items=[]
    if not isinstance(items,list):raise RuntimeError('商品分析接口商品列表结构无法识别')
    return items,control


async def collect_analysis(page,site,products,check_stop,progress,wait_verification,request):
    config=profile(site)
    today=datetime.now(site_timezone(site)).replace(hour=0,minute=0,second=0,microsecond=0)
    start=today-timedelta(days=29);end=today+timedelta(days=1)
    dates={'start':start.strftime('%Y-%m-%d'),'end':end.strftime('%Y-%m-%d')}
    query=urlencode({'shop_region':site,'timeRange':f"{dates['start']}|{dates['end']}",'shortcut':'last30days'})
    await check_stop()
    await progress('opening_product_analysis','商品及SKU已读完，正在打开数据分析－商品数据分析，选择最近30天')
    def matches(response):
        parsed=urlsplit(response.url)
        return parsed.scheme=='https' and parsed.hostname==config['api_host'] and parsed.path==ANALYSIS_API_PATH and response.request.method=='POST'
    pending=asyncio.get_running_loop().create_future()
    def remember(response):
        if matches(response) and not pending.done():pending.set_result(response)
    page.on('response',remember)
    try:
        await page.goto(f"https://{config['host']}{ANALYSIS_PATH}?{query}",wait_until='domcontentloaded',timeout=60000)
        await wait_verification()
        response=await asyncio.wait_for(pending,timeout=30)
    except (BrowserTimeout,asyncio.TimeoutError) as exc:
        raise RuntimeError('等待商品分析页正常接口请求超时，请检查登录或安全验证') from exc
    finally:
        page.remove_listener('response',remember)
    if not allowed(page.url,site) or urlsplit(page.url).path!=ANALYSIS_PATH:raise RuntimeError('未进入目标店铺的商品数据分析页')
    try:
        await page.wait_for_function(r"""dates=>{
            const text=document.body.innerText+' '+[...document.querySelectorAll('input')].map(e=>e.value).join(' ');
            return dates.every(date=>text.includes(date)||text.includes(date.replaceAll('/','-')));
        }""",arg=[start.strftime('%Y/%m/%d'),today.strftime('%Y/%m/%d')],timeout=30000)
    except BrowserTimeout as exc:raise RuntimeError('商品分析页未显示最近30天的准确起止日期') from exc
    params={k:v[-1] for k,v in parse_qs(urlsplit(response.url).query).items() if k in BUSINESS_QUERY}
    # 接口提供完整指标；页面缺列时仍补选，便于人工核对。
    await page.locator('th, [role="columnheader"]').first.wait_for(state='visible',timeout=30000)
    await analysis_columns(page)
    body={'request':{'time_descriptor':dates,'search':{'channel_type':0},
        'list_control':{'pagination':{'page':0,'size':ANALYSIS_PAGE_SIZE},'rules':[{'field':'gmv','direction':2}]}}}
    collected={};page_number=0;total=None;read_count=0
    while True:
        body['request']['list_control']['pagination']['page']=page_number
        data=await request(ANALYSIS_API_PATH,params,body)
        batch,control=analysis_page(data)
        count=control.get('total')
        if total is None:total=count
        if count!=total:raise RuntimeError('商品分析分页期间总数发生变化，请重新采集')
        for item in batch:
            pid,values=parse_analysis_item(item)
            collected[pid]=values
        read_count+=len(batch)
        await progress('collecting_product_analysis',f'最近30天商品分析接口第 {page_number+1} 页读取完成：{len(batch)} 条，已核对 {len(collected)} 个商品')
        more=control.get('has_more')
        if not more:
            if read_count!=total:raise RuntimeError('商品分析接口分页条数与声明总数不一致')
            break
        next_page=control.get('next_page')
        if not batch or not isinstance(next_page,int) or isinstance(next_page,bool) or next_page!=page_number+1 or next_page>=500:
            raise RuntimeError('商品分析接口分页未前进或超过安全上限')
        page_number=next_page
    # 只有完整的去重分析列表才可代表店铺全部商品GMV。
    shop_gmv=format(sum((Decimal(values['gmv']) for values in collected.values()),Decimal('0')),'f') if len(collected)==total else None
    # 平台按GMV排序时，同值商品可能跨页重复。按已确认的在售ID精确补查遗漏，不能补零。
    missing=[p['external_id'] for p in products if p['external_id'] not in collected]
    for index,pid in enumerate(missing,1):
        body['request']['search']={'channel_type':0,'search_keyword':pid}
        body['request']['list_control']['pagination']={'page':0,'size':ANALYSIS_PAGE_SIZE}
        data=await request(ANALYSIS_API_PATH,params,body)
        batch,control=analysis_page(data)
        matching=[parse_analysis_item(item) for item in batch if item.get('meta',{}).get('product_id')==pid]
        if not batch and control.get('total')==0 and control.get('has_more') is False:
            collected[pid]={'impressions':None,'clicks':None,'sales_count':None,'gmv':None,'traffic_reason':ANALYSIS_NO_RECORD}
        elif len(matching)==1:
            collected[pid]=matching[0][1]
        else:raise RuntimeError(f'商品分析缺少在售商品 {pid} 的唯一明确数据，请核对平台分析范围')
        await progress('collecting_product_analysis_missing',f'按在售商品ID补查分析数据：{index}/{len(missing)}')
    for product in products:product.update(collected[product['external_id']])
    return start,end,shop_gmv


ORDER_COUNT_PATTERN=re.compile(r'^(?:找到\s*)?([0-9]+(?:,[0-9]{3})*)\s*个订单$|^(?:Found\s+)?([0-9]+(?:,[0-9]{3})*)\s+orders?$',re.I)


async def collect_order_count(page,site,check_stop,progress,wait_verification):
    config=profile(site)
    await check_stop()
    await progress('opening_orders','商品数据已采集完毕，正在打开管理订单－全部，读取订单总数')
    query=urlencode({'shop_region':site,'selected_sort':6,'tab':'all'})
    await page.goto(f"https://{config['host']}/order?{query}",wait_until='domcontentloaded',timeout=60000)
    await wait_verification()
    if not allowed(page.url,site) or urlsplit(page.url).path!='/order' or parse_qs(urlsplit(page.url).query).get('tab')!=['all']:
        raise RuntimeError('未进入管理订单的全部标签页')
    tab=page.get_by_role('tab',name=re.compile(r'^(?:全部|All)(?:\s*[\d,]+)?$',re.I))
    if not await tab.count():tab=page.get_by_text(re.compile(r'^(?:全部|All)$',re.I))
    await tab.wait_for(state='visible',timeout=30000)
    if await tab.count()!=1:raise RuntimeError('无法唯一识别全部订单标签')
    if await tab.get_attribute('aria-selected')!='true':await tab.click()
    if await tab.get_attribute('role')=='tab':await expect(tab).to_have_attribute('aria-selected','true')
    # 同时兼容筛选栏“找到 N 个订单”和列表上方“N 个订单”，两处有值时必须一致。
    labels=page.get_by_text(ORDER_COUNT_PATTERN)
    previous=None
    for _ in range(60):
        await check_stop()
        await wait_verification()
        if not allowed(page.url,site) or urlsplit(page.url).path!='/order' or parse_qs(urlsplit(page.url).query).get('tab')!=['all']:
            raise RuntimeError('读取订单数量时离开了管理订单的全部标签页')
        counts=set()
        for label in await labels.all():
            if await label.is_visible():
                match=ORDER_COUNT_PATTERN.fullmatch((await label.inner_text()).strip())
                if match:counts.add(number(match.group(1) or match.group(2)))
        if len(counts)==1:
            count=counts.pop()
            if count==previous:
                await progress('collection_orders',f'管理订单－全部：{count} 个订单')
                return count
            previous=count
        else:previous=None
        await asyncio.sleep(.5)
    raise RuntimeError('全部订单页未显示唯一且稳定的明确订单数量，请核对登录、筛选条件或页面加载状态')


async def collect(page,site,identity,check_stop,progress):
    config=profile(site)
    if not allowed(page.url,site):raise RuntimeError('当前页面不属于马来西亚跨境店入口，拒绝采集')
    state=capture_context(page,site)
    async def wait_verification():
        challenge=page.locator('#captcha_container')
        if not await challenge.is_visible():return False
        await page.bring_to_front()
        await progress('waiting_verification','TikTok要求安全验证，请在当前环境手动完成；最多等待10分钟，完成后自动继续')
        for _ in range(600):
            await check_stop()
            if not await challenge.is_visible():
                await progress('collecting','安全验证已完成，继续读取商品接口')
                return True
            await asyncio.sleep(1)
        raise RuntimeError('等待TikTok安全验证超时，请完成验证后重试')
    async def request(path,params,body=None):
        for attempt in range(2):
            await check_stop();await wait_verification()
            if not allowed(page.url,site):raise RuntimeError('商品管理页入口发生变化，停止读取')
            result=await page.evaluate(r"""async args=>{
                const url=new URL(args.path,args.origin);
                for(const[k,v]of Object.entries(args.params))url.searchParams.set(k,String(v));
                const control=new AbortController();const timer=setTimeout(()=>control.abort(),30000);
                try{const r=await fetch(url.toString(),{method:args.body===null?'GET':'POST',credentials:'include',headers:{'content-type':'application/json','x-tt-oec-region':'MY'},body:args.body===null?undefined:JSON.stringify(args.body),signal:control.signal});
                    const text=await r.text();let data=null;try{data=JSON.parse(text)}catch{};return {status:r.status,data};
                }finally{clearTimeout(timer)}
            }""",{'origin':'https://'+config['api_host'],'path':path,'params':params,'body':body})
            payload=result.get('data')
            if result.get('status')==200 and isinstance(payload,dict) and payload.get('code') in (0,'0'):return payload.get('data')
            if attempt==0 and await wait_verification():continue
            code=payload.get('code') if isinstance(payload,dict) else '非JSON响应'
            raise RuntimeError(f'TikTok商品接口读取失败（HTTP {result.get("status")}，code {code}），请检查当前环境的登录或安全验证')
    try:
        await wait_verification()
        tab=page.get_by_role('tab',name=re.compile(r'^(?:在售|Live|On sale)\s*[\d,]+$',re.I))
        await tab.wait_for(state='visible',timeout=30000)
        if await tab.count()!=1:raise RuntimeError('无法唯一识别在售商品标签')
        if await tab.get_attribute('aria-selected')!='true':
            async with page.expect_response(lambda r:product_response(r,site),timeout=30000):await tab.click()
        if 'params' not in state:
            # 明确触发一次正常页面读取，不等待一个可能不再发生的历史响应。
            async with page.expect_response(lambda r:product_response(r,site),timeout=30000):await page.reload(wait_until='domcontentloaded')
        params=dict(state.get('params',{}))
        if params.get('tab_id')!='2':raise RuntimeError('未取得当前在售列表的接口参数，请重新打开商品管理页')
        params.update(page_size='50',sku_number='100',is_need_target_stock='true')
        await progress('collecting','按商品列表接口逐页读取在售商品及完整SKU，不逐项展开页面')
        products=[];seen=set();total=None;page_number=1
        while True:
            params['page_number']=str(page_number)
            data=await request(PRODUCTS_PATH,params)
            if not isinstance(data,dict) or not isinstance(data.get('products'),list):raise RuntimeError('商品列表接口结构无法识别')
            count=data.get('total_product_count')
            if not isinstance(count,int) or isinstance(count,bool) or not 0<=count<=100000:raise RuntimeError('商品接口未返回有效在售总数')
            if total is None:
                total=count;await progress('collection_count',f'平台在售商品总数：{total}')
            if count!=total or data.get('page_number')!=page_number:raise RuntimeError('商品接口分页或在售数量发生变化，请重新采集')
            batch=data['products']
            if not batch and len(products)!=total:raise RuntimeError('在售商品接口返回了不完整分页')
            for product in batch:
                await check_stop()
                pid=product.get('product_id');expected=product.get('total_sku_count')
                if not isinstance(pid,str) or not pid or pid in seen:raise RuntimeError('商品接口包含空ID或重复商品ID')
                if not isinstance(expected,int) or isinstance(expected,bool) or not 1<=expected<=5000:raise RuntimeError(f'商品 {pid} 的SKU数量无效')
                raw=product.get('skus',[])
                if not isinstance(raw,list):raise RuntimeError('商品接口SKU结构无效')
                if len(raw)<expected:
                    # 只有超过列表接口返回上限时，才直接读取该商品的SKU明细接口。
                    extra={k:v for k,v in params.items() if k not in {'page_number','page_size','sku_number','product_sort_fields','product_sort_types','same_product_page_size'}}
                    extra.update(product_id=pid,is_online_version=str(bool(product.get('is_online_version',True))).lower())
                    raw=await request(SKUS_PATH,extra)
                if not isinstance(raw,list) or len(raw)!=expected:raise RuntimeError(f'商品 {pid} 的SKU接口条数与声明数量不一致')
                skus=[parse_sku(v) for v in raw]
                if len({s['external_id'] for s in skus})!=expected:raise RuntimeError(f'商品 {pid} 的SKU ID重复')
                performance=product.get('product_performance') or {}
                pv=performance.get('last_28days_pv')
                views=number(str(pv)) if pv not in (None,'','--','—','-') else None
                products.append({'external_id':pid,'name':str(product.get('product_name',''))[:500],
                    'views':views,'views_reason':'商品管理页未提供浏览次数（--）' if views is None else None,
                    'sku_count':expected,'skus':skus,'impressions':None,'clicks':None,'active':True})
                seen.add(pid)
            await progress('collecting_products',f'第 {page_number} 页读取完成：{len(batch)} 个商品，累计 {len(products)}/{total}；已读取 {sum(p["sku_count"] for p in products)} 条SKU')
            if len(products)==total:break
            if len(products)>total or page_number>=500:raise RuntimeError('商品接口分页超过声明总数或安全上限')
            page_number+=1;await asyncio.sleep(.2)
        start,end,shop_gmv=await collect_analysis(page,site,products,check_stop,progress,wait_verification,request)
        orders_total=await collect_order_count(page,site,check_stop,progress,wait_verification)
        observed=datetime.now(site_timezone(site))
        covered=sum(p.get('impressions') is not None for p in products)
        await progress('collection_checked',f'商品管理及最近30天商品分析采集完成：{total} 个在售商品、{sum(p["sku_count"] for p in products)} 条SKU；{covered} 个商品有分析数据，{total-covered} 个商品经ID查询确认无记录，已标记未知；全部订单 {orders_total} 个')
        return {'header':{'identity':identity,'collection_kind':'product_analysis','product_scope':'on_sale','on_sale_count':total,
            'observed_at':observed.isoformat(),'window_start':start.isoformat(),'window_end':end.isoformat(),'timezone':config['timezone'],
            'expected_count':total,'complete':True,'empty_verified':total==0,'total_verified':True,
            'sections':{'identity':'completed','products':'completed','traffic':'completed','metrics':'completed','health':'unsupported'},'metrics':{'orders_total':orders_total,**({'gmv':shop_gmv} if shop_gmv is not None else {})},
            'reasons':{'traffic':'GMV、曝光、点击及成交件数来自商品数据分析－按商品－全部，最近30天（含今天）；浏览次数独立取商品管理页近28天字段',
                'metrics':'全部订单数取管理订单－全部标签页当前显示数量；GMV在分析列表完整去重核对后汇总全部商品金额，完整性不足时展示在售商品已知小计及覆盖数','health':'健康指标后续补充'}},'products':products}
    finally:
        listener=state.get('listener')
        if listener:page.remove_listener('response',listener)
        if hasattr(page,'_matrix_product_context'):delattr(page,'_matrix_product_context')
