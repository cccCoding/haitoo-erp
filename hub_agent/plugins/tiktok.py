"""马来西亚跨境店只读页面适配。入口按站点与店铺类型定义。"""
import asyncio
import re
from playwright.async_api import TimeoutError as BrowserTimeout
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit, parse_qs

# 声明代码实现的能力；公司与成员授权始终由 ERP 后台校验。
# 环境入口、在售总数、商品分页和SKU明细仍须每次核验。
CAPABILITIES={'shop.collect':['MY']}
# 当前只启用这一组合；未来本土店须提供独立适配，不能回退到跨境入口。
PROFILES={('MY','cross_border'):{
    'url':'https://seller.tiktokshopglobalselling.com/product/manage?shop_region=MY',
    'host':'seller.tiktokshopglobalselling.com','api_host':'api16-normal-sg.tiktokshopglobalselling.com','timezone':'Asia/Kuala_Lumpur'}}


def profile(site,shop_type='cross_border'):
    value=PROFILES.get((site,shop_type))
    if value is None:raise RuntimeError('当前仅支持马来西亚（MY）跨境店，不支持本土店或其他站点')
    return value


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
    async def request(path,params):
        for attempt in range(2):
            await check_stop();await wait_verification()
            if not allowed(page.url,site):raise RuntimeError('商品管理页入口发生变化，停止读取')
            result=await page.evaluate(r"""async args=>{
                const url=new URL(args.path,args.origin);
                for(const[k,v]of Object.entries(args.params))url.searchParams.set(k,String(v));
                const control=new AbortController();const timer=setTimeout(()=>control.abort(),30000);
                try{const r=await fetch(url.toString(),{method:'GET',credentials:'include',headers:{'content-type':'application/json','x-tt-oec-region':'MY'},signal:control.signal});
                    const text=await r.text();let data=null;try{data=JSON.parse(text)}catch{};return {status:r.status,data};
                }finally{clearTimeout(timer)}
            }""",{'origin':'https://'+config['api_host'],'path':path,'params':params})
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
        observed=datetime.now(ZoneInfo(config['timezone']))
        await progress('collection_checked',f'商品管理页采集完成：{total} 个在售商品、{sum(p["sku_count"] for p in products)} 条SKU，全部分页已核对')
        return {'header':{'identity':identity,'collection_kind':'product_management','product_scope':'on_sale','on_sale_count':total,
            'observed_at':observed.isoformat(),'window_start':None,'window_end':None,'timezone':config['timezone'],
            'expected_count':total,'complete':True,'empty_verified':total==0,'total_verified':True,
            'sections':{'identity':'completed','products':'completed','traffic':'unsupported','metrics':'unsupported','health':'unsupported'},'metrics':{},
            'reasons':{'traffic':'浏览次数取商品管理页product_performance.last_28days_pv原值，不作为曝光或点击；未推断精确时间窗口',
                'metrics':'商品分析与经营指标后续补充','health':'健康指标后续补充'}},'products':products}
    finally:
        listener=state.get('listener')
        if listener:page.remove_listener('response',listener)
        if hasattr(page,'_matrix_product_context'):delattr(page,'_matrix_product_context')
