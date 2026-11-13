"""商家秒杀续期执行器。源码回环调试可显式启用；正式环境须通过已验收签名插件开放。"""
import asyncio
import re
import copy
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qs
from playwright.async_api import TimeoutError as BrowserTimeout
from .tiktok import site_timezone, BUSINESS_QUERY

TASK = 'promotion.flash_sale.renew'
COLLECT_TASK = 'promotion.flash_sale.collect'
URL = 'https://seller.tiktokshopglobalselling.com/promotion/marketing-tools/management?tab=1&shop_region=MY'
TYPE = '商家秒杀活动'
STATES = {'未开始':'scheduled','进行中':'ongoing','已结束':'expired','已终止':'terminated'}
TERMINAL = {'published','failed','skipped','cancelled'}
LIST_PATH = '/api/v1/promotion/list'
DETAIL_PATH = '/api/v1/promotion/flash_sale/get'
PRODUCTS_PATH = '/api/v1/promotion/list_products_by_cursor'
TERMINATE_PATH = '/api/v1/promotion/destroy'
CREATE_PATH = '/api/v1/promotion/flash_sale/create'
API_HOST = 'api16-normal-sg.tiktokshopglobalselling.com'
API_STATUSES = {'all':1,'ongoing':2,'scheduled':3,'terminated':4,'expired':5}
# 列表为 SellerPromotionStatus，详情为 PromotionStatus，不能混用编号。
DETAIL_STATUSES = {1:'scheduled',2:'ongoing',3:'expired',4:'terminated',5:'scheduled'}


def parse_api_activity(value):
    if not isinstance(value,dict):raise PageBlocked('活动接口包含无效记录')
    kind=value.get('promotion_type')
    if not isinstance(kind,int) or isinstance(kind,bool):raise PageBlocked('活动接口缺少活动类型')
    if kind!=5:return None
    if not isinstance(value.get('promotion_type_detail'),int):raise PageBlocked('秒杀活动接口缺少活动子类型')
    if value['promotion_type_detail']!=9:return None
    identity=value.get('id');name=value.get('name');status=value.get('status')
    if not isinstance(identity,str) or not re.fullmatch(r'\d{1,120}',identity) or not isinstance(name,str) or not name.strip():
        raise PageBlocked('活动接口缺少唯一ID或名称')
    if not isinstance(status,int) or isinstance(status,bool) or status not in (2,3,4,5):raise PageBlocked('活动接口状态无法识别')
    def instant(key):
        raw=value.get(key)
        if not isinstance(raw,str) or not re.fullmatch(r'\d{13}',raw):raise PageBlocked('活动接口时间格式无法识别')
        try:return datetime.fromtimestamp(int(raw)/1000,timezone.utc).isoformat()
        except (ValueError,OverflowError,OSError) as exc:raise PageBlocked('活动接口时间无效') from exc
    return {'external_id':identity,'name':name,'activity_type':TYPE,
        'status':{v:k for k,v in API_STATUSES.items()}[status],
        'starts_at':instant('start_time'),'ends_at':instant('end_time'),'product_count':None}


class PageBlocked(RuntimeError):
    """店铺级问题，禁止继续本环境。"""


class PlatformRejected(RuntimeError):
    """平台已明确拒绝请求，区别于响应丢失或超时。"""


def numeric_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,120}',value):raise PageBlocked('缺少有效平台ID')
    return value


def clone_products(products,dimension):
    """只复制平台活动价格和限购字段，不把实时库存、图片等带入创建请求。"""
    result=[];ids=set();sku_ids=set()
    def limits(source,target):
        for key in ('purchase_limit','total_purchase_limit','user_purchase_limit'):
            if source.get(key) is not None:target[key]=copy.deepcopy(source[key])
    def price(value):
        try:
            if not isinstance(value,str) or not Decimal(value).is_finite() or Decimal(value)<=0:raise ValueError()
        except (InvalidOperation,ValueError,TypeError):raise PageBlocked('原活动秒杀价格无效，保留原活动')
        return format(Decimal(value).normalize(),'f')
    for product in products:
        pid=numeric_id(product.get('product_id'))
        if pid in ids:raise PageBlocked('原活动商品重复')
        ids.add(pid)
        if product.get('product_status',4)!=4:raise PageBlocked('原活动存在非在售商品，保留原活动')
        item={'product_id':pid}
        if dimension in (0,4):item['flash_sale_price']=price(product.get('fixed_price_value'))
        elif dimension==1:
            skus=product.get('skus')
            if not isinstance(skus,list):raise PageBlocked('原活动缺少完整SKU')
            selected=[]
            for sku in skus:
                if not isinstance(sku.get('in_promotion'),bool):raise PageBlocked('原活动SKU参与范围不明确')
                if not sku['in_promotion']:continue
                sid=numeric_id(sku.get('sku_id'))
                if sid in sku_ids or sku.get('product_id')!=pid:raise PageBlocked('原活动SKU重复或归属不一致')
                sku_ids.add(sid)
                value=price(sku.get('fixed_price_value'))
                entry={'product_id':pid,'sku_id':sid,'fixed_price_value':value,'flash_sale_price':value}
                limits(sku,entry);selected.append(entry)
            if not selected:raise PageBlocked('原活动商品没有可核对的参与SKU')
            item['skus']=sorted(selected,key=lambda s:s['sku_id'])
        else:raise PageBlocked('原活动价格维度尚未支持，保留原活动')
        limits(product,item);result.append(item)
    if not result:raise PageBlocked('原活动没有可复制的商品')
    return sorted(result,key=lambda p:p['product_id'])


def prepare_payload(detail,products,renewal_id):
    if detail.get('type_detail')!=9 or detail.get('effective_time_type',1)!=1 or detail.get('display_channels',[1])!=[1]:
        raise PageBlocked('仅支持固定时间的普通商家秒杀活动')
    dimension=detail.get('promotion_limit_dimension')
    if not isinstance(dimension,int) or isinstance(dimension,bool) or dimension not in (0,1,4):raise PageBlocked('原活动价格维度无法识别')
    marker=f'[HT-R{renewal_id}]'
    name=detail.get('promotion_name')
    if not isinstance(name,str) or not name:raise PageBlocked('缺少原活动名称')
    name=re.sub(r'\[HT-R[0-9]+\]','',name)
    body={'promotion_name':name[:50-len(marker)]+marker,'type_detail':9,'promotion_limit_dimension':dimension,
        'effective_time_type':1,'display_channels':[1],'pre_launch_day':detail.get('pre_launch_day',0),
        'flash_sale_products':clone_products(products,dimension)}
    agreement=detail.get('seller_agreement')
    if agreement:
        if not isinstance(agreement.get('content'),str) or agreement.get('status',0) not in (0,1):raise PageBlocked('原活动卖家条款需要人工核对')
        body['seller_agreement']={'content':agreement['content']}
    return body


def parse_detail_activity(external,detail,products):
    for payload in (detail,products):
        if not isinstance(payload,dict) or payload.get('code') not in (0,'0') or not isinstance(payload.get('data'),dict):
            raise PageBlocked('活动详情或商品数量读取失败，保留原活动')
    value=detail['data'].get('flash_sale',{});count=products['data'].get('total_count')
    if not isinstance(value,dict) or value.get('promotion_id')!=external or value.get('type_detail')!=9:
        raise PageBlocked('活动详情ID或类型不匹配，保留原活动')
    if not isinstance(count,int) or isinstance(count,bool) or not 0<=count<=5000:
        raise PageBlocked('无法核对原活动商品数量，保留原活动')
    period=value.get('period',{})
    if not isinstance(period,dict):raise PageBlocked('活动详情时间格式无法识别')
    for key in ('start_time','end_time'):
        if not isinstance(period.get(key),str) or not re.fullmatch(r'\d{10}',period[key]):
            raise PageBlocked('活动详情时间格式无法识别')
    status=value.get('promotion_status')
    if type(status) is not int or status not in DETAIL_STATUSES:raise PageBlocked(f'活动详情状态无法识别：{status}')
    result=parse_api_activity({'id':external,'name':value.get('promotion_name'),'status':API_STATUSES[DETAIL_STATUSES[status]],
        'promotion_type':5,'promotion_type_detail':9,'start_time':period['start_time']+'000','end_time':period['end_time']+'000'})
    result['product_count']=count
    return result


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
    """以正常页面取得接口上下文；活动读写与核验使用明确的接口契约。"""
    def __init__(self,page,check_stop):
        self.page,self.check_stop=page,check_stop
        self.api_params=None
        self.names={}
        self.last_write_sent=False

    async def init_api(self):
        if self.api_params is not None:return
        future=asyncio.get_running_loop().create_future()
        def capture(response):
            parsed=urlsplit(response.url)
            if parsed.scheme=='https' and parsed.hostname==API_HOST and parsed.path==LIST_PATH and response.request.method=='POST' and not future.done():
                # 与商品采集一致：只保留业务参数，令牌、签名、Cookie留在浏览器内。
                future.set_result({k:v[-1] for k,v in parse_qs(parsed.query).items() if k in BUSINESS_QUERY})
        self.page.on('response',capture)
        try:
            await self.open()
            self.api_params=await asyncio.wait_for(future,30)
        except asyncio.TimeoutError as exc:raise PageBlocked('未取得页面正常活动列表请求，不能读取活动接口') from exc
        finally:self.page.remove_listener('response',capture)

    async def api_request(self,body,path=LIST_PATH,method='POST',mutation=False):
        allowed={(LIST_PATH,'POST'),(DETAIL_PATH,'GET'),(PRODUCTS_PATH,'POST'),(TERMINATE_PATH,'POST'),(CREATE_PATH,'POST')}
        if (path,method) not in allowed or mutation != (path in {TERMINATE_PATH,CREATE_PATH}):raise ValueError('接口操作不在白名单')
        if mutation:self.last_write_sent=False
        await self.init_api();await self.ready()
        params=dict(self.api_params)
        if method=='GET':params.update(body)
        if mutation:self.last_write_sent=True
        result=await self.page.evaluate('''async args=>{
            const url=new URL(args.path,args.origin);
            for(const [k,v] of Object.entries(args.params))url.searchParams.set(k,v);
            const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
            try{const r=await fetch(url.toString(),{method:args.method,credentials:'include',cache:'no-store',headers:{'content-type':'application/json','x-tt-oec-region':'MY'},body:args.method==='GET'?undefined:JSON.stringify(args.body),signal:controller.signal});
                const text=await r.text();let data=null;try{data=JSON.parse(text)}catch{};return {status:r.status,data};
            }finally{clearTimeout(timer)}
        }''',{'path':path,'origin':'https://'+API_HOST,'params':params,'body':body,'method':method})
        data=result.get('data')
        if not isinstance(data,dict) or result.get('status')!=200:
            raise PageBlocked('平台接口响应无法确认（HTTP %s），请核对登录与操作结果'%result.get('status'))
        code=data.get('code')
        if isinstance(code,bool) or not isinstance(code,(str,int)) or not re.fullmatch(r'-?\d+',str(code)):
            raise PageBlocked('平台响应缺少明确业务结果码，不能确认操作结果')
        if code not in (0,'0'):
            message=str(data.get('message') or data.get('msg') or '')[:250]
            if mutation:raise PlatformRejected(f'平台明确拒绝请求（code={data.get("code")}）：{message}')
            raise PageBlocked(f'活动接口读取失败（code={data.get("code")}）：{message}')
        payload=data.get('data',{})
        if not isinstance(payload,dict):raise PageBlocked('平台接口数据结构无法确认')
        return payload

    async def detail(self,external):
        external=numeric_id(external)
        data=await self.api_request({'promotion_id':external},DETAIL_PATH,'GET')
        value=data.get('flash_sale')
        if not isinstance(value,dict) or value.get('promotion_id')!=external or value.get('type_detail')!=9:
            raise PageBlocked('详情返回的活动ID或类型不一致')
        return value

    async def products(self,external):
        result=[];seen=set();total=None
        for _ in range(100):
            data=await self.api_request({'promotion_id':numeric_id(external),'cursor':len(result),'limit':50},PRODUCTS_PATH)
            count=data.get('total_count');batch=data.get('item_products',[])
            if not isinstance(count,int) or isinstance(count,bool) or not 0<=count<=5000 or not isinstance(batch,list):raise PageBlocked('活动商品分页结构无效')
            if total is None:total=count
            if count!=total or not batch and len(result)!=total:raise PageBlocked('活动商品分页不完整或总数变化')
            for product in batch:
                pid=numeric_id(product.get('product_id'))
                if pid in seen:raise PageBlocked('活动商品分页重复')
                seen.add(pid);result.append(product)
            if len(result)>total:raise PageBlocked('活动商品条数超过声明总数')
            if len(result)==total:return result
        raise PageBlocked('活动商品分页超过上限')

    async def prepare(self,activity,renewal_id):
        detail=await self.detail(activity['external_id'])
        products=await self.products(activity['external_id'])
        activity.update(parse_detail_activity(activity['external_id'],{'code':0,'data':{'flash_sale':detail}},
            {'code':0,'data':{'total_count':len(products)}}))
        return prepare_payload(detail,products,renewal_id)

    async def scan(self,status='all',name=None):
        if status not in API_STATUSES:raise ValueError('未知活动查询范围')
        result=[];seen=set();total=None;read=0
        for index in range(500):
            body={'index':index,'size':50,'status':API_STATUSES[status],'promotion_type':1}
            if name is not None:body['name']=name
            data=await self.api_request(body)
            count=data.get('total_count');batch=data.get('promotions',[])
            if not isinstance(count,int) or isinstance(count,bool) or not 0<=count<=25000 or not isinstance(batch,list):
                raise PageBlocked('活动接口总数或分页结构无法识别')
            if total is None:total=count
            if count!=total:raise PageBlocked('查询期间活动总数变化，请重试；未保存残缺扫描')
            if not batch and read!=total:raise PageBlocked('活动接口分页不完整')
            for value in batch:
                if not isinstance(value,dict) or not isinstance(value.get('id'),str) or not value['id'] or value['id'] in seen:
                    raise PageBlocked('活动接口ID缺失或重复，不能确认完整分页')
                seen.add(value['id'])
                activity=parse_api_activity(value)
                if activity:
                    if status!='all' and activity['status']!=status:raise PageBlocked('活动接口状态与查询条件不符，请重试')
                    self.names[activity['external_id']]=activity['name'];result.append(activity)
            read+=len(batch)
            if read>total:raise PageBlocked('活动接口条数超过声明总数')
            if read==total:return result
        raise PageBlocked('活动接口分页超过上限，未保存残缺扫描')

    async def lookup(self,external,name=None):
        name=name or self.names.get(external)
        if name:
            values=await self.scan(name=name)
        else:
            values=await self.scan('ongoing')+await self.scan('scheduled')
        matches=[value for value in values if value['external_id']==external]
        if len(matches)!=1:raise PageBlocked('接口未找到唯一目标商家秒杀活动，禁止继续操作')
        return matches[0]

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

    async def terminate(self,external):
        await self.api_request({'promotion_id':numeric_id(external)},TERMINATE_PATH,mutation=True)
        latest=await self.detail(external)
        if latest.get('promotion_status')!=4:raise PageBlocked('终止请求返回后，平台尚未确认旧活动已终止')

    async def publish(self,preparation,start,end):
        if end-start!=timedelta(hours=72) or start<=datetime.now(timezone.utc):raise PageBlocked('新活动必须从未来时间开始并持续72小时')
        body={**copy.deepcopy(preparation),'period':{'start_time':str(int(start.timestamp())),'end_time':str(int(end.timestamp()))}}
        data=await self.api_request(body,CREATE_PATH,mutation=True)
        external=numeric_id(data.get('promotion_id'))
        # 即使平台返回部分商品失败，也先保存已返回的新ID，随后逐项核对，绝不再发一次创建。
        return external

    async def verify(self,external,start,end,preparation=None):
        detail=await self.detail(external)
        status=detail.get('promotion_status')
        if type(status) is not int or DETAIL_STATUSES.get(status) not in {'ongoing','scheduled'}:
            raise PageBlocked(f'新活动尚未确认发布成功（详情状态：{status}）')
        period=detail.get('period',{})
        if period.get('start_time')!=str(int(start.timestamp())) or period.get('end_time')!=str(int(end.timestamp())):
            raise PageBlocked('新活动时间与本次发布参数不一致')
        if preparation is not None:
            if detail.get('promotion_name')!=preparation['promotion_name'] or detail.get('promotion_limit_dimension')!=preparation['promotion_limit_dimension']:
                raise PageBlocked('新活动名称或价格维度与准备数据不一致')
            products=await self.products(external)
            if clone_products(products,preparation['promotion_limit_dimension'])!=preparation['flash_sale_products']:
                raise PageBlocked('新活动商品、SKU、价格或限购与原活动不一致')
        return f'接口已核对新活动 {external}、72小时时间及全部商品价格'



async def renew_flash_sales(page,site,config,rpc,check_stop,progress,ui_factory=MerchantFlashPage):
    """rpc由宿主绑定租约；插件不会取得ERP令牌。所有未知副作用先交人工核对。"""
    if site!='MY':raise RuntimeError('秒杀续期仅支持MY跨境店')
    ui=ui_factory(page,check_stop)
    selected=config.get('selected_flash_ids') is not None
    scope='selected' if selected else 'ongoing'
    await progress('flash_scan','正在查询所选已结束活动' if selected else '正在通过接口读取进行中的商家秒杀活动')
    if selected:
        if 'flash_sale_targets' not in config:raise RuntimeError('服务器未提供已选择活动，请先更新服务器后重新创建运行')
        activities=[await ui.lookup(t['external_id'],t['name']) for t in config['flash_sale_targets']]
    else:activities=await ui.scan('ongoing')
    records=(await rpc('scan',{'complete':True,'scope':scope,'activities':activities}))['renewals']
    for record in records:
        await check_stop()
        if record['stage'] in TERMINAL:continue
        rid=record['id'];stage=record['stage'];new_id=record.get('new_activity_id')
        preparation=record.get('preparation');terminated=record.get('terminated',False)
        ui.last_write_sent=False
        async def checkpoint(next_stage,**values):
            nonlocal stage
            await check_stop()
            await rpc(f'{rid}/step',{'stage':next_stage,**values})
            stage=next_stage
        try:
            if stage in {'publish_intent','created'}:
                if not record.get('starts_at') or not record.get('ends_at'):raise PageBlocked('上次创建缺少已保存的时间，禁止重复发布')
                start=datetime.fromisoformat(record['starts_at'].replace('Z','+00:00'))
                end=datetime.fromisoformat(record['ends_at'].replace('Z','+00:00'))
                if not new_id and preparation:
                    matches=[a for a in await ui.scan(name=preparation['promotion_name']) if a['name']==preparation['promotion_name'] and a['external_id']!=record['external_id']]
                    if len(matches)!=1:raise PageBlocked('上次创建结果尚未唯一确认，禁止重发创建请求')
                    new_id=matches[0]['external_id']
                if not new_id:raise PageBlocked('上次创建缺少新活动ID，禁止重复发布')
                evidence=await ui.verify(new_id,start,end,preparation)
                await checkpoint('published',new_activity_id=new_id,starts_at=start.isoformat(),ends_at=end.isoformat(),evidence=evidence)
                continue
            if stage in {'terminate_intent','copy_intent','draft_confirmed','unknown'}:
                raise PageBlocked('上次平台操作结果待核对，禁止重复终止或创建；请在活动明细核对后恢复')
            activity=await ui.lookup(record['external_id'],record['name'])
            if terminated and activity['status']!='terminated':raise PageBlocked('台账记录旧活动已终止，但平台状态不一致')
            if not preparation:
                preparation=await ui.prepare(activity,rid)
            if not terminated:
                checked=await rpc(f'{rid}/recheck',{'activity':activity})
                if not checked['eligible']:
                    await checkpoint('skipped',evidence='活动状态已变化，尚未提交终止或创建')
                    continue
            if stage!='prepared':
                await checkpoint('prepared',preparation=preparation,evidence='原活动全部商品、SKU、价格及限购已准备并保存')
            if not terminated and activity['status']=='ongoing':
                ui.last_write_sent=False
                await checkpoint('terminate_intent')
                await ui.terminate(record['external_id'])
                await checkpoint('terminated',evidence='终止接口成功，且详情接口确认旧活动状态为已终止')
                terminated=True
            if not terminated and activity['status']!='expired':raise PageBlocked('原活动仍未终止，禁止创建替代活动')
            start,end=new_window()
            ui.last_write_sent=False
            await checkpoint('publish_intent',starts_at=start.isoformat(),ends_at=end.isoformat(),evidence='已保存创建准备数据与72小时窗口，尚未取得平台新ID')
            new_id=await ui.publish(preparation,start,end)
            await checkpoint('created',new_activity_id=new_id,evidence='创建接口已返回新活动ID，正在核对商品与时间')
            evidence=await ui.verify(new_id,start,end,preparation)
            await checkpoint('published',new_activity_id=new_id,starts_at=start.isoformat(),ends_at=end.isoformat(),evidence=evidence)
        except BaseException as exc:
            if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
            detail=f'{type(exc).__name__}: {str(exc)}'[:440] or '执行中断'
            try:
                if stage in {'terminate_intent','publish_intent'}:
                    if isinstance(exc,PlatformRejected) or not ui.last_write_sent:
                        await rpc(f'{rid}/step',{'stage':'failed','request_outcome':'rejected' if isinstance(exc,PlatformRejected) else 'not_sent','error':detail})
                    else:
                        await rpc(f'{rid}/step',{'stage':'unknown',**({'new_activity_id':new_id} if new_id else {}),'error':'请求已发出，结果待核对；'+detail})
                elif stage=='created':
                    await rpc(f'{rid}/step',{'stage':'unknown','new_activity_id':new_id,'error':'新活动ID已返回，但核对未通过；'+detail})
                elif stage in {'pending','prepared','terminated'} and not isinstance(exc,asyncio.CancelledError):
                    await rpc(f'{rid}/step',{'stage':'failed','error':detail})
                elif stage in {'unknown','draft_confirmed','copy_intent'}:
                    await rpc(f'{rid}/step',{'stage':stage,'error':detail})
            except Exception:pass
            await progress('flash_attention',f"活动 {record['external_id']} 未完成：{detail}")
            if isinstance(exc,(PageBlocked,asyncio.CancelledError)) or stage in {'created','terminate_intent','publish_intent'} and not isinstance(exc,PlatformRejected):raise
    return await rpc('complete',{})


async def collect_flash_sales(page,site,config,rpc,check_stop,progress):
    """独立只读同步，不调用续期执行器及任何平台写操作。"""
    if site!='MY':raise RuntimeError('秒杀活动同步仅支持MY跨境店')
    await progress('flash_scan','正在只读同步全部状态的商家秒杀活动')
    activities=await MerchantFlashPage(page,check_stop).scan()
    await check_stop()
    await rpc('scan',{'complete':True,'activities':activities})
    return await rpc('complete',{})
