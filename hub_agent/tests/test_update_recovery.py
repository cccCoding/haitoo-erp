"""内部更新、系统拒绝、通用启动失败、持久提示和受控人工重试。"""
import base64
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from package_security import canonical, unpack_verified
from updater import UpdateManager, atomic, apply_update, verify_native, UpdateChannelError, NativeSignatureError
from update_recovery import record_failure


class RecoveryFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.key=Ed25519PrivateKey.generate()
        self.keys={'test':base64.b64encode(self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode()}

    def release(self,internal=False):
        import zipfile
        package=self.root/'update.zip'
        with zipfile.ZipFile(package,'w') as archive:archive.writestr('agent.py',b'print("agent")')
        manifest={'kind':'agent','version':'5.4.0','platform':'macos','arch':'arm64','size':package.stat().st_size,
            'sha256':hashlib.sha256(package.read_bytes()).hexdigest(),'key_id':'test','protocol_min':5,'protocol_max':5,
            'entrypoint':'agent.py','files':{'agent.py':hashlib.sha256(b'print("agent")').hexdigest()}}
        if internal:manifest['distribution']='internal'
        manifest['signature']=base64.b64encode(self.key.sign(canonical(manifest))).decode()
        unpack_verified(package,manifest,self.root/'versions'/manifest['sha256'])
        return manifest

    def transaction(self,manifest):
        path=self.root/'pending-agent.json'
        atomic(path,{'manifest':manifest,'release_id':7,'created_at':0,'parent_pid':123456789,'previous_command':['/safe/old-agent','tray']})
        return path


class NativePolicyTests(unittest.TestCase):
    def test_internal_build_accepts_only_company_verified_internal_manifest_without_commercial_certificate(self):
        with patch('updater.DISTRIBUTION','internal'),patch('updater.subprocess.run') as check:
            verify_native(Path('/tmp/Agent.app/Contents/MacOS/Agent'),{'distribution':'internal'})
            check.assert_not_called()
        with patch('updater.DISTRIBUTION','signed'):
            with self.assertRaises(UpdateChannelError):verify_native(Path('/tmp/agent'),{'distribution':'internal'})

    def test_signed_release_keeps_native_verification_in_internal_build(self):
        with patch('updater.DISTRIBUTION','internal'),patch('updater.sys.frozen',True,create=True),patch('updater.platform.system',return_value='Darwin'),patch('updater.subprocess.run',side_effect=OSError('verification unavailable')):
            with self.assertRaises(NativeSignatureError):verify_native(Path('/tmp/Agent.app/Contents/MacOS/Agent'),{})


class RecoveryTests(RecoveryFixture,unittest.TestCase):
    def test_launch_denied_restores_old_command_and_persists_manual_guidance(self):
        manifest=self.release();transaction=self.transaction(manifest)
        def spawn(command,**kwargs):
            if command==['/safe/old-agent','tray']:return MagicMock()
            raise PermissionError('blocked by operating system')
        with patch('updater.keys',return_value=self.keys),patch('updater.target',return_value=('macos','arm64')),patch('updater.subprocess.Popen',side_effect=spawn) as launch:
            apply_update(transaction)
        self.assertFalse(transaction.exists())
        result=json.loads((self.root/'update-result.json').read_text())
        self.assertTrue(result['manual_required']);self.assertEqual(result['error_code'],'LAUNCH_PERMISSION_DENIED')
        self.assertEqual(result['release_id'],'7')
        self.assertEqual(launch.call_args.args[0],['/safe/old-agent','tray'])
        self.assertFalse((self.root/'current-agent.json').exists())

    def test_unexplained_child_exit_is_not_misreported_as_security_block(self):
        manifest=self.release();transaction=self.transaction(manifest);child=MagicMock();child.pid=999999;child.poll.return_value=1
        with patch('updater.keys',return_value=self.keys),patch('updater.target',return_value=('macos','arm64')),patch('updater.subprocess.Popen',return_value=child):apply_update(transaction)
        self.assertEqual(json.loads((self.root/'update-result.json').read_text())['error_code'],'NEW_VERSION_START_FAILED')

    def test_manual_retry_only_clears_exact_verified_failed_release(self):
        manifest=self.release();record_failure(self.root,manifest,'LAUNCH_PERMISSION_DENIED',7)
        atomic(self.root/'blocked-releases.json',[manifest['sha256'],'b'*64])
        manager=UpdateManager(self.root,AsyncMock())
        with patch('updater.keys',return_value=self.keys),patch('updater.target',return_value=('macos','arm64')):
            self.assertFalse(manager.retry_failed_update('c'*64))
            self.assertTrue(manager.retry_failed_update(manifest['sha256']))
        self.assertEqual(json.loads((self.root/'blocked-releases.json').read_text()),['b'*64])
        self.assertFalse(manager.reported_state().get('manual_required',False))

    def test_invalid_or_tampered_package_cannot_be_retried_as_an_os_exception(self):
        manifest=self.release();record_failure(self.root,manifest,'PACKAGE_VALIDATION_FAILED',7)
        atomic(self.root/'blocked-releases.json',[manifest['sha256']])
        manager=UpdateManager(self.root,AsyncMock());self.assertFalse(manager.retry_failed_update())
        record_failure(self.root,manifest,'LAUNCH_PERMISSION_DENIED',7)
        failed=json.loads((self.root/'failed-agent.json').read_text());failed['manifest']['version']='9.9.9';atomic(self.root/'failed-agent.json',failed)
        with patch('updater.keys',return_value=self.keys),patch('updater.target',return_value=('macos','arm64')):
            self.assertFalse(manager.retry_failed_update())
        self.assertIn(manifest['sha256'],json.loads((self.root/'blocked-releases.json').read_text()))

    def test_recovery_notice_survives_routine_version_checks_and_restart(self):
        manifest=self.release();record_failure(self.root,manifest,'NEW_VERSION_START_FAILED',7)
        for status in ('checking','up_to_date','retry'):
            manager=UpdateManager(self.root,AsyncMock());manager.state={'status':status}
            reported=manager.reported_state()
            self.assertEqual(reported['status'],'manual_required');self.assertEqual(reported['target_version'],'5.4.0')
        atomic(self.root/'update-result.json',{'status':'installed','version':'5.5.0'})
        self.assertFalse(manager.reported_state().get('manual_required',False))


class InternalPackageTests(RecoveryFixture,unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        RecoveryFixture.setUp(self)
        # 固定旧版本，确保测试始终执行下载与升级渠道检查。
        installed = patch('updater.VERSION', '5.3.0')
        installed.start(); self.addCleanup(installed.stop)

    async def test_internal_update_still_checks_files_and_prepares_before_restart(self):
        from types import SimpleNamespace
        manifest=self.release(internal=True)
        row={'id':7,'manifest':manifest}
        async def download(identity,path,size,**kwargs):path.write_bytes((self.root/'update.zip').read_bytes())
        client=SimpleNamespace(request=AsyncMock(return_value=[row]),connector_download_release=AsyncMock(side_effect=download))
        manager=UpdateManager(self.root,client)
        with patch('updater.keys',return_value=self.keys),patch('updater.target',return_value=('macos','arm64')),patch('updater.DISTRIBUTION','internal'),patch('updater.subprocess.run') as native,patch('updater.subprocess.Popen') as spawn:
            await manager.check(can_activate=False)
            self.assertEqual(manager.state['status'],'waiting_idle');native.assert_not_called();spawn.assert_not_called()
        self.assertEqual(client.request.await_args.kwargs['params']['distribution'],'internal')

    async def test_offered_internal_package_cannot_disable_signed_build_policy(self):
        from types import SimpleNamespace
        manifest=self.release(internal=True)
        async def download(identity,path,size,**kwargs):path.write_bytes((self.root/'update.zip').read_bytes())
        client=SimpleNamespace(request=AsyncMock(return_value=[{'id':7,'manifest':manifest}]),connector_download_release=AsyncMock(side_effect=download))
        manager=UpdateManager(self.root,client)
        with patch('updater.keys',return_value=self.keys),patch('updater.target',return_value=('macos','arm64')),patch('updater.DISTRIBUTION','signed'):
            await manager.check(can_activate=False)
        self.assertEqual(manager.reported_state()['error_code'],'UPDATE_CHANNEL_MISMATCH')
        self.assertIsNone(manager.prepared)


class InternalSigningTests(RecoveryFixture,unittest.TestCase):
    def test_internal_zip_manifest_requires_matching_build_metadata_and_embedded_public_key(self):
        import sys
        from sign_release import main
        from package_release import package_directory
        from package_security import verify_manifest
        source=self.root/'HaitooHubAgent';source.mkdir()
        (source/'agent.py').write_text('pass')
        (source/'agent-version.json').write_text(json.dumps({'version':'5.4.0','distribution':'internal'}))
        (source/'trusted_keys.json').write_text(json.dumps(self.keys))
        archive=package_directory(source,self.root/'update.zip')
        installer=self.root/'HaitooHubAgent-windows-x64-5.4.0.zip';installer.write_bytes(b'internal installer')
        private=self.root/'private.pem';private.write_bytes(self.key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        output=self.root/'manifest.json'
        args=['sign_release.py','--distribution','internal','--package',str(archive),'--installer',str(installer),'--key',str(private),'--key-id','test','--version','5.4.0','--platform','windows','--arch','x64','--kind','agent','--entrypoint','HaitooHubAgent/agent.py','--output',str(output)]
        with patch.object(sys,'argv',args):main()
        manifest=json.loads(output.read_text());verify_manifest(manifest,self.keys,'windows','x64')
        self.assertEqual(manifest['distribution'],'internal');self.assertEqual(manifest['min_launcher_version'],'5.3.0')
        (source/'agent-version.json').write_text('{"version":"5.4.0"}');package_directory(source,self.root/'update.zip')
        with patch.object(sys,'argv',args):
            with self.assertRaisesRegex(ValueError,'内部渠道元数据'):main()


class ManualInstallTests(RecoveryFixture,unittest.TestCase):
    def test_health_verified_manual_install_clears_old_notice_but_old_version_does_not(self):
        from update_recovery import confirm_manual_install
        manifest=self.release();record_failure(self.root,manifest,'NEW_VERSION_START_FAILED',7)
        with patch('updater.keys',return_value=self.keys),patch('updater.target',return_value=('macos','arm64')):
            with patch('updater.VERSION','5.3.0'):self.assertFalse(confirm_manual_install(self.root))
            with patch('updater.VERSION','5.4.1'):self.assertTrue(confirm_manual_install(self.root))
        result=json.loads((self.root/'update-result.json').read_text());self.assertFalse(result['manual_required'])
        self.assertEqual(result['status'],'manual_installed')


class RestoreFallbackTests(RecoveryFixture,unittest.TestCase):
    def test_baseline_fallback_and_explicit_failure_when_no_old_program_can_start(self):
        manifest=self.release()
        for baseline_available in (True,False):
            with self.subTest(baseline_available=baseline_available):
                transaction=self.transaction(manifest)
                def spawn(command,**kwargs):
                    if command==['/fixed/baseline','tray'] and baseline_available:return MagicMock()
                    raise PermissionError('cannot start executable')
                with patch('updater.keys',return_value=self.keys),patch('updater.target',return_value=('macos','arm64')),patch('updater.subprocess.Popen',side_effect=spawn),patch.dict(os.environ,{'HAITOO_BOOTSTRAP_COMMAND':json.dumps(['/fixed/baseline','tray'])}):
                    apply_update(transaction)
                result=json.loads((self.root/'update-result.json').read_text())
                self.assertEqual(result['error_code'],'LAUNCH_PERMISSION_DENIED' if baseline_available else 'OLD_VERSION_START_FAILED')
                self.assertFalse(transaction.exists())
