"""协议5本机执行上下文；与旧任务共用Agent主循环的串行槽。"""
import asyncio
import hashlib
import json
import logging
import math
import os
import time
import uuid
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import httpx
from playwright.async_api import async_playwright
from hubstudio import HubstudioClient
from updater import UpdateManager,VERSION,keys,target,atomic
from plugin_manager import load_plugin
from plugins import tiktok

logger=logging.getLogger(__name__)


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class MatrixRuntime:
    def __init__(self,host,root,save_config,upload):
        self.host,self.root,self.save_config,self.upload=host,Path(root),save_config,upload
        self.root.mkdir(parents=True,exist_ok=True)
        self.install_uuid=host.config.setdefault('install_uuid',str(uuid.uuid4()));save_config(host.config)
        host.state['matrix_hub_identity']=host.config.get('matrix_hub_identity')
        self.claim=None;self.stop_requested=False;self.lost_lease=False;self.enabled=False;self.updater=None;self.plugin=None;self.next_heartbeat=0
        self.last_sync_version=int(time.time())

    @property
    def client(self):return self.host.client

    def credentials(self):return {'claim_token':self.claim['claim_token'],'fencing':self.claim['fencing']}

    def path(self,suffix):return f"/hub-v5/agent/items/{self.claim['item']['id']}/{suffix}"

    def journal(self):return self.root/'journal'/f"{self.claim['item']['id']}.json"

    def adapter(self,task=None,site=None):
        if task is not None and site != 'MY':
            raise RuntimeError('当前仅支持马来西亚（MY）跨境店，请更新方案和连接器')
        # 采集固定使用马来西亚跨境店内置适配。
        if task=='shop.collect':return tiktok
        if self.plugin and (task is None or site in self.plugin.CAPABILITIES.get(task,[])):
            return self.plugin
        if task is None or site in tiktok.CAPABILITIES.get(task,[]):return tiktok
        raise RuntimeError('当前连接器不支持此站点的任务，请更新连接器')

    def capabilities(self):
        capabilities={task:list(sites) for task,sites in tiktok.CAPABILITIES.items()}
        if self.plugin:
            for task,sites in self.plugin.CAPABILITIES.items():
                if task=='shop.collect':continue
                capabilities[task]=sorted((set(capabilities.get(task,[])) | set(sites)) & {'MY'})
        return capabilities

    async def heartbeat(self, process_commands=True):
        if not self.client:return
        self.plugin=load_plugin(self.root,keys(),*target())
        result=await self.client.post('/hub-v5/agent/heartbeat',json={'install_uuid':self.install_uuid,'version':VERSION,
            'hub_connected':bool(self.host.state.get('hub_connected')),'capabilities':self.capabilities(),
            'local_paused':bool(self.host.state.get('paused')),
            'update_state':{**(self.updater.state if self.updater else {}),'plugin_version':getattr(self.adapter(),'VERSION','builtin'),
                'plugin_digest':getattr(self.adapter(),'DIGEST','builtin')}})
        identity=result.get('hub_identity', self.host.config.get('matrix_hub_identity'))
        if identity != self.host.config.get('matrix_hub_identity'):
            self.host.config['matrix_hub_identity']=identity
            self.save_config(self.host.config)
            self.host.synced_monotonic=None
            self.host.last_sync_attempt=0
        self.host.state['matrix_hub_identity']=identity
        self.enabled=bool(result['enabled'] and identity)
        self.host.state['matrix_status']='在线；任务权限由 ERP 后台控制' if self.enabled else '请在 ERP 设备管理中配置 Hub 团队身份' if not identity else '公司矩阵尚未启用'
        if self.claim:
            result=await self.client.post(self.path('renew'),json=self.credentials())
            self.stop_requested=result['stop_requested'];self.next_heartbeat=time.monotonic()
        elif not result['paused']:
            self.host.state['matrix_paused']=False
        self.host.state['matrix_paused']=result.get('paused',self.host.state.get('matrix_paused',False))
        if not process_commands:
            return
        for command in await self.client.request('GET','/hub-v5/agent/commands'):
            if command['kind']=='refresh':await self.host.sync()
            elif command['kind']=='stop' and self.claim and command['payload'].get('run_id')==self.claim['item']['run_id']:self.stop_requested=True
            await self.client.post(f"/hub-v5/agent/commands/{command['id']}/ack",json={})

    async def sync(self,items):
        await self.heartbeat(process_commands=False)
        if not self.enabled:return False
        self.last_sync_version=max(self.last_sync_version+1,int(time.time()))
        entries=[]
        for e in items:
            meta=e.get('metadata_fields',{})
            site=meta.get('site') if meta.get('site') in {'MY','ID'} else None
            entries.append({'container_code':e['container_code'],'name':e['name'],'group_name':str(meta.get('group') or ''),
                'serial':str(meta.get('serial_number') or ''),'account_names':e.get('account_names',[]),'site':site})
        count=max(1,math.ceil(len(entries)/200))
        row=await self.client.post('/hub-v5/agent/environment-syncs',json={'snapshot_key':str(uuid.uuid4()),'hub_identity':self.host.config['matrix_hub_identity'],
            'version':self.last_sync_version,'expected_count':len(entries),'part_count':count})
        for n in range(count):await self.client.request('PUT',f"/hub-v5/agent/environment-syncs/{row['id']}/parts/{n}",json={'entries':entries[n*200:(n+1)*200]})
        await self.client.post(f"/hub-v5/agent/environment-syncs/{row['id']}/commit",json={})
        return True

    async def check_stop(self):
        if self.lost_lease:raise RuntimeError('租约已失效，禁止继续操作')
        if self.stop_requested or self.host.state.get('stop'):raise asyncio.CancelledError()
        if time.monotonic()-self.next_heartbeat>=15:
            try:
                result=await self.client.post(self.path('renew'),json=self.credentials());self.stop_requested=result['stop_requested'];self.next_heartbeat=time.monotonic()
            except Exception:self.lost_lease=True;raise
            if self.stop_requested:raise asyncio.CancelledError()

    async def progress(self,stage,message):
        await self.check_stop()
        self.host.state['status']=message
        await self.client.post(self.path('events'),json={**self.credentials(),'source_id':str(uuid.uuid4()),'stage':stage,'message':message})

    async def upload_collection(self,package):
        header=package['header'];products=package['products'];count=max(1,math.ceil(len(products)/200))
        await self.progress('uploading',f'开始同步采集包：{len(products)} 个商品，共 {count} 个分片')
        row=await self.client.post(self.path('collections'),json={**self.credentials(),'content_hash':digest(package),'part_count':count,'header':header})
        for n in range(count):
            await self.check_stop()
            await self.client.request('PUT',self.path(f"collections/{row['id']}/parts/{n}"),json={**self.credentials(),'products':products[n*200:(n+1)*200]})
            await self.progress('uploading',f'采集包分片 {n+1}/{count} 已上传')
        await self.progress('validating_collection','分片上传完成，正在校验商品分页、SKU数量、流量窗口和执行环境' if header.get('collection_kind') in {'product_management','product_analysis'} else '分片上传完成，正在校验完整性、执行环境和数据窗口')
        await self.client.post(self.path(f"collections/{row['id']}/commit"),json=self.credentials())

    async def run_next(self):
        if not self.enabled or self.host.state.get('matrix_paused'):return False
        result=await self.client.request('GET','/hub-v5/agent/queue')
        fresh=self.host.synced_monotonic is not None and time.monotonic()-self.host.synced_monotonic<300
        items=[i for i in result['items'] if fresh or i['result'].get('retransmit_only')]
        if not items:return False
        item=items[0]
        self.claim=await self.client.post(f"/hub-v5/agent/items/{item['id']}/claim",json={})
        self.stop_requested,self.lost_lease=False,False;self.next_heartbeat=time.monotonic()
        self.host.state['matrix_active_item']=item['id']
        try:await self.execute()
        finally:self.claim=None;self.host.state['matrix_active_item']=None
        return True

    async def try_next(self):
        try:
            return await self.run_next()
        except Exception as exc:
            if getattr(exc,'status',None)==401:self.host.state['login_required']=True
            logger.warning('矩阵领取暂不可用 error_type=%s',type(exc).__name__)
            return False

    async def execute(self):
        claim=self.claim;item=claim['item'];tasks=claim['tasks'];submitted=False;listing_confirmed=False;collection_committed=False
        journal_path=self.journal();journal=json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.exists() else {}
        try:
            if item['result'].get('retransmit_only'):
                if not journal.get('collection'):raise RuntimeError('本机没有固定采集包，不能重传；请在原设备核对')
                await self.upload_collection(journal['collection']);collection_committed=True
                status='succeeded' if 'listing.catalog' not in tasks or item['submission']=='confirmed' else 'partial_success'
                await self.client.post(self.path('report'),json={**self.credentials(),'status':status,'message':'仅重传原采集包完成'})
                return
            await self.progress('checking_environment','正在检查目标 HubStudio 环境的访问权限')
            hub=HubstudioClient(self.host.config.get('hubstudio_url','http://127.0.0.1:6873'))
            envs=await hub.environments()
            if sum(e['container_code']==claim['environment']['container_code'] for e in envs)!=1:raise RuntimeError('目标环境不再可访问')
            await self.progress('starting_environment','环境访问检查通过，正在启动浏览器环境')
            port=await hub.start(claim['environment']['container_code'])
            await self.progress('connecting_browser','环境已启动，正在连接浏览器')
            async with async_playwright() as playwright:
                browser=await playwright.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
                page=await browser.contexts[0].new_page();keep=False
                try:
                    site=claim['environment']['site']
                    # 按任务、站点固定适配器；插件未覆盖的采集站点使用内置实现。
                    adapter=self.adapter('listing.catalog' if 'listing.catalog' in tasks else 'shop.collect',site)
                    collector=self.adapter('shop.collect',site) if 'shop.collect' in tasks else None
                    if 'listing.catalog' not in tasks:
                        await tiktok.open_environment(page,site,self.check_stop,self.progress)
                    target=await self.client.post(self.path('environment-target'),json=self.credentials())
                    identity=target['identity']
                    await self.progress('environment_ready',f"目标环境已就绪：{claim['environment']['name']}，按环境归档执行结果")
                    if 'listing.catalog' in tasks:
                        await self.progress('waiting_supply','正在准备本次上品货盘文件')
                        preparation_status=None
                        while True:
                            await self.check_stop()
                            file=await self.client.post(self.path('listing-preparations'),json=self.credentials())
                            if file['status']!=preparation_status:
                                preparation_status=file['status']
                                await self.progress('waiting_supply',f"货盘准备状态：{ {'waiting_supply':'等待货盘','generating_file':'生成文件','ready':'文件就绪'}.get(file['status'],file['status']) }")
                            if file['status']=='ready':break
                            await asyncio.sleep(5)
                        destination=self.root/'files'/file['filename'];destination.parent.mkdir(parents=True,exist_ok=True)
                        await self.progress('downloading_file','货盘文件已生成，正在下载固定文件')
                        await self.client.matrix_download(self.path('file'),self.credentials(),destination,file['size'])
                        if hashlib.sha256(destination.read_bytes()).hexdigest()!=file['sha256']:raise RuntimeError('固定文件摘要不一致')
                        await self.progress('file_verified',f"文件校验通过，预期 {file['expected_count']} 个商品组")
                        async def upload_ready():
                            await self.check_stop()
                            url=urlsplit(page.url)
                            if not tiktok.allowed(page.url,site) or url.path!='/product/batch/publish' or parse_qs(url.query).get('shop_region')!=[site]:
                                raise RuntimeError('未进入目标站点的跨境批量上传页，停止上传')
                        async def before_import():
                            nonlocal submitted
                            await self.check_stop()
                            if not tiktok.allowed(page.url,site):
                                raise RuntimeError('当前页面不属于目标站点入口，尚未导入')
                            if adapter is tiktok:await upload_ready()
                            atomic(journal_path,{**journal,'submission':'intent_recorded','file_sha256':file['sha256']})
                            await self.progress('submission_pending','目标环境已就绪，正在保存提交意图，准备向平台导入商品')
                            await self.client.post(self.path('submission'),json=self.credentials());submitted=True
                        # 只给插件受控页面和提交回调，不分发服务器令牌。
                        if hasattr(adapter,'upload'):
                            result=await adapter.upload(page,site,str(destination),file['expected_count'],before_import,self.check_stop,self.progress)
                        elif adapter is tiktok:
                            result=await self.upload(port,destination,before_import=before_import,on_upload_ready=upload_ready,
                                on_progress=self.progress,expected_count=file['expected_count'],site=site,page=page,
                                upload_url=tiktok.profile(site)['upload_url'],check_stop=self.check_stop)
                        else:
                            account=await hub.bound_account(claim['environment']['container_code'])
                            result=await self.upload(port,destination,before_import=before_import,account=account,on_progress=self.progress,
                                expected_count=file['expected_count'],site=site,page=page)
                        if not result or set(result.get('accepted',[]))|set(result.get('rejected',[]))!=set(range(file['expected_count'])):raise RuntimeError('平台回执无法核对全部商品，提交结果未知')
                        response=await self.client.post(self.path('listing-result'),json={**self.credentials(),**result})
                        listing_confirmed=response['status']=='confirmed'
                        if response.get('partial'):raise RuntimeError('平台部分商品拒绝，请核对明细')
                    if 'shop.collect' in tasks:
                        if 'listing.catalog' in tasks:
                            await tiktok.open_environment(page,site,self.check_stop,self.progress)
                        package=await collector.collect(page,site,identity,self.check_stop,self.progress)
                        journal={**journal,'identity':identity,'collection':package};atomic(journal_path,journal)
                        await self.progress('uploading','采集完成，正在校验并提交固定数据包')
                        await self.upload_collection(package);collection_committed=True
                    await self.client.post(self.path('report'),json={**self.credentials(),'status':'succeeded','message':'全部必需步骤及数据确认完成'})
                except BaseException:
                    keep=True;raise
                finally:
                    if not keep:await page.close()
                    # async_playwright 上下文退出时断开CDP，不调用浏览器关闭接口。
        except BaseException as exc:
            if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
            if not self.lost_lease:
                status='awaiting_attention' if submitted and not listing_confirmed else 'partial_success' if listing_confirmed or collection_committed else 'cancelled' if isinstance(exc,asyncio.CancelledError) else 'failed'
                message=str(exc)[:500] if isinstance(exc,RuntimeError) else '已停止，请查看阶段和平台结果' if isinstance(exc,asyncio.CancelledError) else '执行失败，请查看当前阶段并人工核对'
                with suppress(Exception):await self.client.post(self.path('report'),json={**self.credentials(),'status':status,'message':message})
            logger.warning('矩阵环境项结束 item=%s error_type=%s',item['id'],type(exc).__name__)

    async def check_updates(self):
        if self.claim or self.host.current_claim:return False
        if not self.updater:self.updater=UpdateManager(self.root,self.client)
        return await self.updater.check()
