"""签名、包完整性、路径约束和插件接口的独立回归。"""
import base64
import hashlib
import io
import json
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch,AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from package_security import canonical,verify_manifest,unpack_verified
from plugin_manager import load_plugin
from updater import atomic,UpdateManager
from matrix_runtime import digest
from plugins.tiktok import identity_payload,number,allowed


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.key=Ed25519PrivateKey.generate()
        self.keys={'test':base64.b64encode(self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()}

    def package(self,files=None):
        files=files or {'plugin.py':b"CAPABILITIES={'shop.collect':['MY']}\nasync def collect(*a): pass\n"}
        archive=self.root/'package.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for name,body in files.items():z.writestr(name,body)
        content=archive.read_bytes()
        m={'kind':'plugin','version':'5.0.1','platform':'macos','arch':'arm64','sha256':hashlib.sha256(content).hexdigest(),'size':len(content),
            'key_id':'test','protocol_min':5,'protocol_max':5,'entrypoint':next(iter(files)),
            'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
        m['signature']=base64.b64encode(self.key.sign(canonical(m))).decode();return archive,m

    def test_valid_signed_plugin_and_modified_install_rejected(self):
        archive,m=self.package();verify_manifest(m,self.keys,'macos','arm64')
        directory=self.root/'plugins'/m['sha256'];unpack_verified(archive,m,directory)
        atomic(self.root/'current-plugin.json',{'manifest':m})
        self.assertEqual(load_plugin(self.root,self.keys,'macos','arm64').CAPABILITIES,{'shop.collect':['MY']})
        (directory/'plugin.py').write_text('CAPABILITIES={}\n')
        with self.assertRaises(ValueError):load_plugin(self.root,self.keys,'macos','arm64')

    def test_bad_signature_unknown_key_target_and_protocol(self):
        _,m=self.package()
        for changed in ({**m,'version':'9.0.0'},{**m,'key_id':'foreign'},{**m,'protocol_min':6}):
            with self.assertRaises(ValueError):verify_manifest(changed,self.keys,'macos','arm64')
        with self.assertRaises(ValueError):verify_manifest(m,self.keys,'windows','x64')

    def test_zip_traversal_and_unlisted_member(self):
        archive,m=self.package({'../escape.py':b'bad'})
        with self.assertRaises(ValueError):unpack_verified(archive,m,self.root/'outside')
        self.assertFalse((self.root.parent/'escape.py').exists())
        archive,m=self.package();m['files']={}
        with self.assertRaises(ValueError):unpack_verified(archive,m,self.root/'missing')

    def test_symlink_and_duplicate_zip_paths_rejected(self):
        archive,m=self.package()
        with zipfile.ZipFile(archive,'w') as z:
            info=zipfile.ZipInfo('plugin.py');info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,b'/etc/passwd')
        content=archive.read_bytes();m['size']=len(content);m['sha256']=hashlib.sha256(content).hexdigest()
        with self.assertRaises(ValueError):unpack_verified(archive,m,self.root/'link')

    def test_identity_is_not_guessed_from_product_seller(self):
        self.assertIsNone(identity_payload({'data':{'products':[{'seller_id':'other'}]}},'MY'))
        self.assertIsNone(identity_payload({'data':{'shop_info':{'shop_id':'1','shop_name':'店','region':'ID'}}},'MY'))
        self.assertEqual(identity_payload({'code':0,'data':{'shop_info':{'shop_id':'1','shop_name':'店','region':'MY'}}},'MY')['external_id'],'1')
        self.assertFalse(allowed('https://seller-id.tokopedia.com/product/manage','ID'))
        self.assertFalse(allowed('https://seller-id.tokopedia.com.evil.test/product/manage','ID'))
        self.assertEqual(number('1,038'),1038)
        for value in ('—','1.2k','unknown'):
            with self.assertRaises(RuntimeError):number(value)

    def test_cross_border_entry_rejects_local_other_region_and_lookalike_domains(self):
        from plugins.tiktok import profile
        self.assertEqual(profile('MY')['url'],'https://seller.tiktokshopglobalselling.com/product/manage?shop_region=MY')
        self.assertTrue(allowed(profile('MY')['url'],'MY'))
        self.assertTrue(allowed('https://seller.tiktokshopglobalselling.com/api/shop/info','MY'))
        for url in ('https://seller-my.tiktok.com/product/manage',
                    'https://seller.tiktokshopglobalselling.com/product/manage?shop_region=ID',
                    'https://seller.tiktokshopglobalselling.com/product/manage?shop_region=MY&shop_region=ID',
                    'https://seller.tiktokshopglobalselling.com.evil.test/product/manage',
                    'https://user:password@seller.tiktokshopglobalselling.com/product/manage',
                    'http://seller.tiktokshopglobalselling.com/product/manage'):
            self.assertFalse(allowed(url,'MY'),url)
        with self.assertRaisesRegex(RuntimeError,'仅支持'):profile('MY','local')

    def test_agent_and_backend_content_digest_contract(self):
        from importlib.util import spec_from_file_location,module_from_spec
        value={'header':{'中文':'值','zero':0,'none':None},'products':[]}
        expected=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest(value),expected)


class UpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_untrusted_key_store_cannot_download_or_execute(self):
        with tempfile.TemporaryDirectory() as root:
            client=AsyncMock();manager=UpdateManager(root,client)
            with patch('updater.keys',return_value={}):self.assertFalse(await manager.check())
            client.request.assert_not_called();self.assertEqual(manager.state['status'],'no_trusted_keys')

class MatrixRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_builtin_collection_needs_no_local_permission_switch(self):
        from types import SimpleNamespace
        from matrix_runtime import MatrixRuntime
        with tempfile.TemporaryDirectory() as temp:
            host=SimpleNamespace(config={},state={},client=None,current_claim=None)
            runtime=MatrixRuntime(host,temp,lambda c:None,AsyncMock())
            self.assertEqual(runtime.capabilities(),{'shop.collect':['MY'],'listing.catalog':['MY']})
            for sites in ([],['MY'],['OTHER']):
                host.config['matrix_collection_validation_sites']=sites
                self.assertEqual(runtime.capabilities(),{'shop.collect':['MY'],'listing.catalog':['MY']})

    async def test_partial_plugin_preserves_builtin_collection_and_routes_by_site(self):
        from types import SimpleNamespace
        from matrix_runtime import MatrixRuntime
        from plugins import tiktok
        with tempfile.TemporaryDirectory() as temp:
            host=SimpleNamespace(config={},state={},client=None,current_claim=None)
            runtime=MatrixRuntime(host,temp,lambda c:None,AsyncMock())
            runtime.plugin=SimpleNamespace(CAPABILITIES={'shop.collect':['MY'],'listing.catalog':['MY']})
            self.assertEqual(runtime.capabilities(),{'shop.collect':['MY'],'listing.catalog':['MY']})
            self.assertIs(runtime.adapter('shop.collect','MY'),tiktok)
            with self.assertRaisesRegex(RuntimeError,'仅支持'):runtime.adapter('shop.collect','ID')
            self.assertIs(runtime.adapter('listing.catalog','MY'),runtime.plugin)
            with self.assertRaisesRegex(RuntimeError,'仅支持'):runtime.adapter('listing.catalog','ID')
            self.assertEqual(tiktok.CAPABILITIES,{'shop.collect':['MY'],'listing.catalog':['MY']})
            runtime.plugin=SimpleNamespace(CAPABILITIES={'listing.catalog':[]})
            self.assertEqual(runtime.capabilities(),{'shop.collect':['MY'],'listing.catalog':['MY']})
            self.assertIs(runtime.adapter('listing.catalog','MY'),tiktok)

    async def test_heartbeat_reports_builtin_capabilities_without_enabling_backend_disabled_company(self):
        from types import SimpleNamespace
        from matrix_runtime import MatrixRuntime
        with tempfile.TemporaryDirectory() as temp:
            client=SimpleNamespace(post=AsyncMock(return_value={'enabled':False,'paused':False}),request=AsyncMock(return_value=[]))
            host=SimpleNamespace(config={'matrix_hub_identity':'team'},state={'hub_connected':True},client=client)
            runtime=MatrixRuntime(host,temp,lambda c:None,AsyncMock())
            with patch('matrix_runtime.load_plugin',return_value=None),patch('matrix_runtime.keys',return_value={}):
                await runtime.heartbeat()
            self.assertEqual(client.post.await_args.kwargs['json']['capabilities'],{'shop.collect':['MY'],'listing.catalog':['MY']})
            self.assertFalse(runtime.enabled)

    async def test_retransmission_never_opens_a_browser(self):
        from types import SimpleNamespace
        from matrix_runtime import MatrixRuntime
        with tempfile.TemporaryDirectory() as temp:
            client=SimpleNamespace(post=AsyncMock(side_effect=lambda path,**kw:{'stop_requested':False} if path.endswith('/renew') else {'id':7}),request=AsyncMock(return_value={}))
            host=SimpleNamespace(config={'matrix_hub_identity':'team'},state={},client=client,synced_monotonic=None,current_claim=None)
            runtime=MatrixRuntime(host,temp,lambda c:None,AsyncMock())
            runtime.claim={'item':{'id':1,'result':{'retransmit_only':True},'submission':'not_started'},'claim_token':'a'*32,'fencing':1,'tasks':['shop.collect']}
            atomic(runtime.journal(),{'collection':{'header':{},'products':[]}})
            with patch('matrix_runtime.async_playwright') as browser:await runtime.execute()
            browser.assert_not_called()
            paths=[call.args[0] for call in client.post.await_args_list]
            self.assertTrue(any(path.endswith('/commit') for path in paths))
            self.assertTrue(paths[-1].endswith('/report'))

    async def test_claim_conflict_does_not_require_reauthorization(self):
        from types import SimpleNamespace
        from matrix_runtime import MatrixRuntime
        from connector import ERPRequestError
        with tempfile.TemporaryDirectory() as temp:
            host=SimpleNamespace(config={},state={},client=None,current_claim=None)
            runtime=MatrixRuntime(host,temp,lambda c:None,AsyncMock())
            runtime.run_next=AsyncMock(side_effect=ERPRequestError(409,'环境被占用'))
            self.assertFalse(await runtime.try_next())
            self.assertNotIn('login_required',host.state)

    async def test_directory_sync_uses_only_whitelisted_fields(self):
        from types import SimpleNamespace
        from matrix_runtime import MatrixRuntime
        with tempfile.TemporaryDirectory() as temp:
            client=SimpleNamespace(post=AsyncMock(return_value={'id':1,'enabled':True,'paused':False}),request=AsyncMock(return_value={}))
            host=SimpleNamespace(config={'matrix_hub_identity':'team'},state={'hub_connected':True},client=client,current_claim=None)
            runtime=MatrixRuntime(host,temp,lambda c:None,AsyncMock())
            with patch('matrix_runtime.load_plugin',return_value=None),patch('matrix_runtime.keys',return_value={}):
                await runtime.sync([{'container_code':'1','name':'店','account_names':['name@example.test'],'accountPassword':'do-not-upload','metadata_fields':{'group':'A','proxyPassword':'do-not-upload'}}])
            self.assertNotIn('do-not-upload',str(client.request.await_args_list))
            client.request.assert_awaited_once()

class EnvironmentExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_builtin_listing_uses_cross_border_page_and_submission_callback(self):
        await self.check_builtin_listing(['listing.catalog'])

    async def test_listing_then_collection_opens_product_page_after_import(self):
        await self.check_builtin_listing(['listing.catalog','shop.collect'])

    async def check_builtin_listing(self,tasks):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from matrix_runtime import MatrixRuntime
        from plugins import tiktok
        identity={'site':'MY','environment_id':7,'name':'测试环境'}
        content=b'fixed workbook'
        async def post(path,**kwargs):
            if path.endswith('/environment-target'):return {'identity':identity}
            if path.endswith('/listing-preparations'):
                return {'status':'ready','filename':'test.xlsx','size':len(content),
                    'sha256':hashlib.sha256(content).hexdigest(),'expected_count':10}
            if path.endswith('/listing-result'):return {'status':'confirmed'}
            return {}
        async def download(path,credentials,destination,size):destination.write_bytes(content)
        client=SimpleNamespace(post=AsyncMock(side_effect=post),matrix_download=AsyncMock(side_effect=download))
        page=SimpleNamespace(url='about:blank',close=AsyncMock())
        async def upload(port,destination,**kwargs):
            open_page.assert_not_awaited()
            self.assertIs(kwargs['page'],page)
            self.assertEqual(kwargs['upload_url'],tiktok.profile('MY')['upload_url'])
            self.assertEqual(kwargs['expected_count'],10)
            self.assertEqual(destination.read_bytes(),content)
            page.url=kwargs['upload_url']
            await kwargs['on_upload_ready']()
            await kwargs['before_import']()
            self.assertTrue(any(c.args[0].endswith('/submission') for c in client.post.await_args_list))
            return {'accepted':list(range(10)),'rejected':[],'receipt':'成功导入10款商品'}
        with tempfile.TemporaryDirectory() as temp:
            host=SimpleNamespace(config={},state={},client=client,current_claim=None)
            runtime=MatrixRuntime(host,temp,lambda c:None,AsyncMock(side_effect=upload))
            runtime.claim={'item':{'id':1,'result':{},'submission':'not_started'},'claim_token':'a'*32,'fencing':1,
                'tasks':tasks,'environment':{'id':7,'site':'MY','name':'测试环境','container_code':'env-7'}}
            runtime.progress=AsyncMock();runtime.check_stop=AsyncMock();runtime.upload_collection=AsyncMock()
            browser=SimpleNamespace(contexts=[SimpleNamespace(new_page=AsyncMock(return_value=page))])
            manager=MagicMock();manager.__aenter__=AsyncMock(return_value=SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=AsyncMock(return_value=browser))));manager.__aexit__=AsyncMock(return_value=False)
            hub=SimpleNamespace(environments=AsyncMock(return_value=[{'container_code':'env-7'}]),start=AsyncMock(return_value=9222),bound_account=AsyncMock())
            with patch('matrix_runtime.HubstudioClient',return_value=hub),patch('matrix_runtime.async_playwright',return_value=manager),patch('matrix_runtime.tiktok.open_environment',new_callable=AsyncMock) as open_page,patch('matrix_runtime.tiktok.collect',new_callable=AsyncMock,return_value={'header':{'identity':identity},'products':[]}) as collect:
                await runtime.execute()
            if 'shop.collect' in tasks:
                open_page.assert_awaited_once();collect.assert_awaited_once();runtime.upload_collection.assert_awaited_once()
            else:
                open_page.assert_not_awaited();collect.assert_not_awaited()
            hub.bound_account.assert_not_awaited()
            runtime.upload.assert_awaited_once();page.close.assert_awaited_once()
            self.assertEqual(client.post.await_args_list[-1].kwargs['json']['status'],'succeeded')

    async def test_collection_does_not_call_platform_identity_methods(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from matrix_runtime import MatrixRuntime
        identity={'site':'MY','environment_id':7,'name':'测试环境'}
        async def post(path,**kwargs):
            return {'identity':identity} if path.endswith('/environment-target') else {}
        client=SimpleNamespace(post=AsyncMock(side_effect=post))
        with tempfile.TemporaryDirectory() as temp:
            host=SimpleNamespace(config={},state={},client=client,current_claim=None)
            runtime=MatrixRuntime(host,temp,lambda c:None,AsyncMock())
            runtime.claim={'item':{'id':1,'result':{},'submission':'not_started'},'claim_token':'a'*32,'fencing':1,'tasks':['shop.collect'],
                'environment':{'id':7,'site':'MY','name':'测试环境','container_code':'env-7'}}
            runtime.progress=AsyncMock();runtime.check_stop=AsyncMock();runtime.upload_collection=AsyncMock()
            package={'header':{'identity':identity},'products':[]}
            adapter=SimpleNamespace(identify=AsyncMock(side_effect=AssertionError('不应识别平台店铺')),verify_identity=AsyncMock(side_effect=AssertionError('不应复核平台店铺')),collect=AsyncMock(return_value=package))
            runtime.adapter=MagicMock(return_value=adapter)
            page=SimpleNamespace(close=AsyncMock())
            browser=SimpleNamespace(contexts=[SimpleNamespace(new_page=AsyncMock(return_value=page))],close=AsyncMock())
            manager=MagicMock();manager.__aenter__=AsyncMock(return_value=SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=AsyncMock(return_value=browser))));manager.__aexit__=AsyncMock(return_value=False)
            hub=SimpleNamespace(environments=AsyncMock(return_value=[{'container_code':'env-7'}]),start=AsyncMock(return_value=9222))
            with patch('matrix_runtime.HubstudioClient',return_value=hub),patch('matrix_runtime.async_playwright',return_value=manager),patch('matrix_runtime.tiktok.open_environment',new_callable=AsyncMock) as open_page:
                await runtime.execute()
            open_page.assert_awaited_once()
            adapter.identify.assert_not_called();adapter.verify_identity.assert_not_called()
            runtime.upload_collection.assert_awaited_once_with(package)
            self.assertEqual(client.post.await_args_list[-1].kwargs['json']['status'],'succeeded')
            self.assertFalse(any(c.args[0].endswith('/identity') for c in client.post.await_args_list))


class IdentityGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_navigation_response_cannot_authorize_new_document(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from browser_identity import IdentityGuard
        page=MagicMock();page.url='https://seller.tiktokshopglobalselling.com/product/manage';guard=IdentityGuard(page,'MY')
        request=object();guard.request(request)
        response=SimpleNamespace(request=request,url='https://seller.tiktokshopglobalselling.com/api/shop/info',headers={},json=AsyncMock(return_value={'data':{'shop_info':{'shop_id':'1','shop_name':'店','region':'MY'}}}))
        guard.navigated(page.main_frame)
        await guard.response(response)
        with self.assertRaises(RuntimeError):guard.verify({'site':'MY','external_id':'1'})
        guard.request(request);await guard.response(response);guard.verify({'site':'MY','external_id':'1'})
        guard.identities.add(('MY','other'))
        with self.assertRaises(RuntimeError):guard.verify({'site':'MY','external_id':'1'})
        guard.close();self.assertEqual(page.remove_listener.call_count,3)

class UpdateLifecycleTests(unittest.TestCase):
    setUp=PackageTests.setUp
    package=PackageTests.package
    def agent_transaction(self):
        archive,m=self.package({'agent.py':b'print("verified")\n'})
        m['kind']='agent';m['signature']=base64.b64encode(self.key.sign(canonical(m))).decode()
        unpack_verified(archive,m,self.root/'versions'/m['sha256'])
        transaction=self.root/'pending-agent.json'
        atomic(transaction,{'manifest':m,'parent_pid':123456,'previous_command':['/safe/old-agent','tray']})
        (self.root/'config.json').write_text('{"preserved":true}')
        return transaction,m

    def test_successful_health_switch_preserves_previous_slot(self):
        from updater import apply_update
        from unittest.mock import MagicMock
        transaction,m=self.agent_transaction();child=MagicMock();child.pid=999999;child.poll.return_value=None
        def spawn(*args,**kwargs):
            Path(kwargs['env']['HAITOO_UPDATE_HEALTH']).write_text(json.dumps({'ready':True,'version':m['version']}))
            return child
        with patch('updater.keys',return_value=self.keys),patch('updater.target',return_value=('macos','arm64')),patch('updater.os.kill',side_effect=ProcessLookupError()),patch('updater.subprocess.Popen',side_effect=spawn):apply_update(transaction)
        self.assertEqual(json.loads((self.root/'current-agent.json').read_text())['manifest']['sha256'],m['sha256'])
        self.assertEqual(json.loads((self.root/'previous-agent.json').read_text())['command'],['/safe/old-agent','tray'])
        self.assertEqual((self.root/'config.json').read_text(),'{"preserved":true}')

    def test_failed_health_restarts_previous_and_quarantines_package(self):
        from updater import apply_update
        from unittest.mock import MagicMock
        transaction,m=self.agent_transaction();child=MagicMock();child.pid=999999;child.poll.return_value=1
        with patch('updater.keys',return_value=self.keys),patch('updater.target',return_value=('macos','arm64')),patch('updater.os.kill',side_effect=ProcessLookupError()),patch('updater.subprocess.Popen',return_value=child) as spawn:apply_update(transaction)
        self.assertFalse((self.root/'current-agent.json').exists())
        self.assertEqual(spawn.call_args_list[-1].args[0],['/safe/old-agent','tray'])
        self.assertIn(m['sha256'],json.loads((self.root/'blocked-releases.json').read_text()))
        self.assertEqual((self.root/'config.json').read_text(),'{"preserved":true}')

class ReleaseArchiveTests(unittest.TestCase):
    def test_internal_links_are_materialized_and_external_links_rejected(self):
        from package_release import package_directory
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'Bundle';source.mkdir()
            (source/'agent.py').write_text('print("agent")')
            (source/'alias.py').symlink_to('agent.py')
            archive=package_directory(source,root/'release.zip')
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(z.read('Bundle/agent.py'),z.read('Bundle/alias.py'))
                self.assertFalse(any(stat.S_ISLNK(i.external_attr>>16) for i in z.infolist()))
            (root/'outside').write_text('private')
            (source/'external').symlink_to(root/'outside')
            with self.assertRaises(ValueError):package_directory(source,root/'unsafe.zip')


class AutomaticUpdateTests(unittest.IsolatedAsyncioTestCase):
    setUp = PackageTests.setUp
    package = PackageTests.package

    def release(self):
        archive, manifest = self.package({'agent.py': b'print("new")'})
        manifest.update(kind='agent', version='5.3.0', min_launcher_version='5.2.0')
        manifest['signature'] = base64.b64encode(self.key.sign(canonical(manifest))).decode()
        return archive, {'id': 12, 'manifest': manifest}

    def client(self, archive, row):
        from types import SimpleNamespace
        async def download(identity, destination, size, **kwargs): destination.write_bytes(archive.read_bytes())
        return SimpleNamespace(request=AsyncMock(side_effect=lambda method, path, **kw: [row] if path.endswith('connector-releases') else []),
                               connector_download_release=AsyncMock(side_effect=download), matrix_download_release=AsyncMock())

    async def test_busy_download_prepares_without_restart_and_idle_activates(self):
        archive, row = self.release(); client = self.client(archive, row); manager = UpdateManager(self.root, client)
        with patch('updater.keys', return_value=self.keys), patch('updater.target', return_value=('macos', 'arm64')), patch('updater.subprocess.Popen') as spawn:
            self.assertFalse(await manager.check(can_activate=False))
            client.connector_download_release.assert_awaited_once(); spawn.assert_not_called()
            self.assertEqual(manager.state['status'], 'waiting_idle')
            self.assertFalse((self.root / 'pending-agent.json').exists())
            self.assertTrue(await manager.activate()); spawn.assert_called_once()
            self.assertEqual(json.loads((self.root / 'pending-agent.json').read_text())['manifest'], row['manifest'])

    async def test_network_failure_retries_without_quarantining_version(self):
        archive, row = self.release(); client = self.client(archive, row)
        client.connector_download_release.side_effect = TimeoutError('offline')
        manager = UpdateManager(self.root, client)
        with patch('updater.keys', return_value=self.keys), patch('updater.target', return_value=('macos', 'arm64')):
            self.assertFalse(await manager.check(can_activate=False))
            self.assertEqual(manager.state['status'], 'retry')
            self.assertFalse((self.root / 'blocked-releases.json').exists())
            self.assertGreater(manager.next_check, 0)
            manager.request_check(); await manager.check(can_activate=False)
            self.assertEqual(client.connector_download_release.await_count, 2)

    async def test_corrupt_package_is_quarantined(self):
        archive, row = self.release(); client = self.client(archive, row)
        archive.write_bytes(b'broken')
        manager = UpdateManager(self.root, client)
        with patch('updater.keys', return_value=self.keys), patch('updater.target', return_value=('macos', 'arm64')):
            await manager.check(can_activate=False)
        self.assertEqual(manager.state['status'], 'rejected')
        self.assertIn(row['manifest']['sha256'], json.loads((self.root / 'blocked-releases.json').read_text()))

    async def test_withdrawn_staged_release_does_not_activate(self):
        archive, row = self.release(); client = self.client(archive, row); manager = UpdateManager(self.root, client)
        with patch('updater.keys', return_value=self.keys), patch('updater.target', return_value=('macos', 'arm64')), patch('updater.subprocess.Popen') as spawn:
            await manager.check(can_activate=False)
            client.request.side_effect = None; client.request.return_value = []
            self.assertFalse(await manager.activate()); spawn.assert_not_called()
        self.assertIsNone(manager.prepared)
        self.assertFalse((self.root / 'staged-agent.json').exists())

    async def test_old_launcher_requires_installer_and_disk_failure_is_retryable(self):
        archive, row = self.release(); client = self.client(archive, row); manager = UpdateManager(self.root, client)
        with patch('updater.keys', return_value=self.keys), patch('updater.target', return_value=('macos', 'arm64')), patch.dict('os.environ', {'HAITOO_LAUNCHER_VERSION': '5.1.0'}):
            await manager.check(can_activate=False)
            self.assertEqual(manager.state['status'], 'installer_required')
            client.connector_download_release.assert_not_awaited()
        from types import SimpleNamespace
        manager.request_check()
        with patch('updater.keys', return_value=self.keys), patch('updater.target', return_value=('macos', 'arm64')), patch('updater.shutil.disk_usage', return_value=SimpleNamespace(free=0)):
            await manager.check(can_activate=False)
            self.assertEqual(manager.state['status'], 'insufficient_space')
            self.assertFalse((self.root / 'blocked-releases.json').exists())


class NativeArchiveTests(unittest.TestCase):
    setUp = PackageTests.setUp

    def test_signed_macos_internal_symlinks_preserve_bundle_structure(self):
        from package_release import package_directory
        from package_security import verify_directory
        source = self.root / 'Agent.app'; (source / 'Contents/Frameworks/Versions/A').mkdir(parents=True)
        (source / 'Contents/Frameworks/Versions/A/binary').write_bytes(b'mach-o')
        (source / 'Contents/Frameworks/Versions/Current').symlink_to('A')
        archive = package_directory(source, self.root / 'update.zip', preserve_links=True)
        with zipfile.ZipFile(archive) as z:
            files = {i.filename: hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist()}
            links = {i.filename: z.read(i).decode() for i in z.infolist() if stat.S_ISLNK(i.external_attr >> 16)}
        manifest = {'kind':'agent', 'version':'5.3.0', 'platform':'macos', 'arch':'arm64', 'key_id':'test',
                    'entrypoint':'Agent.app/Contents/Frameworks/Versions/A/binary', 'files':files, 'symlinks':links,
                    'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(), 'size':archive.stat().st_size, 'protocol_min':5, 'protocol_max':5}
        manifest['signature'] = base64.b64encode(self.key.sign(canonical(manifest))).decode()
        verify_manifest(manifest, self.keys, 'macos', 'arm64')
        directory = unpack_verified(archive, manifest, self.root / 'slot')
        link = directory / 'Agent.app/Contents/Frameworks/Versions/Current'
        self.assertTrue(link.is_symlink()); self.assertEqual((link / 'binary').read_bytes(), b'mach-o')
        verify_directory(directory, manifest)
        link.unlink(); link.symlink_to('/etc')
        with self.assertRaises(ValueError): verify_directory(directory, manifest)


class InterruptedUpdateTests(UpdateLifecycleTests):
    def test_damaged_staged_files_recover_previous_after_interruption(self):
        from updater import apply_update
        transaction, manifest = self.agent_transaction()
        data = json.loads(transaction.read_text()); data['created_at'] = 0; atomic(transaction, data)
        (self.root / 'versions' / manifest['sha256'] / manifest['entrypoint']).write_text('damaged')
        with patch('updater.keys', return_value=self.keys), patch('updater.target', return_value=('macos', 'arm64')), patch('updater.subprocess.Popen') as spawn:
            apply_update(transaction)
        self.assertFalse(transaction.exists())
        spawn.assert_called_once(); self.assertEqual(spawn.call_args.args[0], ['/safe/old-agent', 'tray'])
        self.assertEqual(json.loads((self.root / 'update-result.json').read_text())['status'], 'rolled_back')


class StagedStartupTests(unittest.TestCase):
    def test_new_version_does_not_reactivate_its_own_staged_transaction(self):
        from updater import VERSION
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            atomic(root/'staged-agent.json',{'id':12,'manifest':{'version':VERSION,'sha256':'a'*64}})
            manager=UpdateManager(root,AsyncMock())
            self.assertIsNone(manager.prepared)
            # 原辅助进程仍需要原暂存事务，子进程只忽略，不抢先删除。
            self.assertTrue((root/'staged-agent.json').exists())


class RealChildUpdateTests(unittest.TestCase):
    setUp = PackageTests.setUp
    package = PackageTests.package

    def test_real_child_reports_version_before_pointer_commit(self):
        import subprocess
        from updater import apply_update
        source = b'''import json,os,time
from pathlib import Path
Path(os.environ['HAITOO_UPDATE_HEALTH']).write_text(json.dumps({'ready':True,'version':'5.0.1'}))
time.sleep(30)
'''
        archive, manifest = self.package({'agent.py': source})
        manifest['kind'] = 'agent'; manifest['signature'] = base64.b64encode(self.key.sign(canonical(manifest))).decode()
        unpack_verified(archive, manifest, self.root / 'versions' / manifest['sha256'])
        transaction = self.root / 'pending-agent.json'
        atomic(transaction, {'manifest':manifest, 'parent_pid':123456789, 'created_at':0, 'previous_command':['/safe/old-agent','tray']})
        children = []; original = subprocess.Popen
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs); children.append(child); return child
        try:
            with patch('updater.keys', return_value=self.keys), patch('updater.target', return_value=('macos','arm64')), patch('updater.subprocess.Popen', side_effect=spawn):
                apply_update(transaction)
            self.assertEqual(len(children),1)
            self.assertEqual(json.loads((self.root/'current-agent.json').read_text())['manifest'],manifest)
            self.assertEqual(json.loads((self.root/'update-result.json').read_text())['status'],'installed')
            self.assertFalse(transaction.exists())
        finally:
            for child in children:
                if child.poll() is None:child.terminate()
                child.wait(timeout=5)


class MacReleaseSigningTests(unittest.TestCase):
    setUp = PackageTests.setUp

    def test_formal_manifest_signs_macos_bundle_with_linked_version_and_trust_files(self):
        from package_release import package_directory
        from sign_release import main
        source=self.root/'Agent.app';resources=source/'Contents/Resources';frameworks=source/'Contents/Frameworks'
        resources.mkdir(parents=True);frameworks.mkdir()
        (resources/'agent-version.json').write_text('{"version":"5.3.0"}')
        (resources/'trusted_keys.json').write_text(json.dumps(self.keys))
        for name in ('agent-version.json','trusted_keys.json'):
            (frameworks/name).symlink_to('../Resources/'+name)
        (source/'agent.py').write_text('print("agent")')
        archive=package_directory(source,self.root/'update.zip',preserve_links=True)
        installer=self.root/'HaitooHubAgent-macos-arm64-5.3.0.dmg';installer.write_bytes(b'test installer')
        private=self.root/'private.pem'
        private.write_bytes(self.key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        output=self.root/'manifest.json'
        args=['sign_release.py','--package',str(archive),'--installer',str(installer),'--key',str(private),'--key-id','test',
              '--version','5.3.0','--platform','macos','--arch','arm64','--kind','agent','--entrypoint','Agent.app/agent.py','--output',str(output)]
        with patch.object(sys,'argv',args):main()
        manifest=json.loads(output.read_text())
        verify_manifest(manifest,self.keys,'macos','arm64')
        self.assertEqual(manifest['installer']['sha256'],hashlib.sha256(installer.read_bytes()).hexdigest())
        self.assertEqual(len(manifest['symlinks']),2)
