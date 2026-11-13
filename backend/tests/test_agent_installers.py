"""首次下载与平台更新统一发布、权限、版本不可变与撤回。"""
import base64
import hashlib
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from app.hub_v5.connector_releases import router as release_router
from app.hub_v5.installers import router
from app.hub_v5.api import agent_auth
from app.models import User, Role, HubAgent
from app.security import create_access_token
from tests.test_supply_catalog import SupplyFixture, TEST_PASSWORD_HASH


class MemoryStorage:
    def __init__(self): self.objects = {}
    def put_object(self, Bucket, Key, Body, **kw):
        self.objects[Key] = Body.read() if hasattr(Body, 'read') else Body
    def get_object(self, Bucket, Key):
        content = self.objects[Key]
        return {'Body': io.BytesIO(content), 'ContentLength': len(content), 'ETag': hashlib.md5(content).hexdigest()}

    def head_object(self, Bucket, Key):
        return {'ContentLength': len(self.objects[Key])}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return 'https://private.example/' + Params['Key']
    def copy_object(self, Bucket, Key, CopySource, CopySourceIfMatch, **kw):
        content = self.objects[CopySource['Key']]
        if hashlib.md5(content).hexdigest() != CopySourceIfMatch:raise ValueError('changed')
        self.objects[Key] = content
    def delete_object(self, Bucket, Key):self.objects.pop(Key, None)


class InstallerTests(SupplyFixture, unittest.TestCase):
    def setUp(self):
        super().setUp(); self.app.include_router(router); self.app.include_router(release_router)
        self.key = Ed25519PrivateKey.generate()
        public = base64.b64encode(self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        self.enterContext(patch('app.hub_v5.releases.get_settings', return_value=SimpleNamespace(matrix_release_public_keys=json.dumps({'test': public}))))
        self.storage = MemoryStorage()
        self.enterContext(patch('app.hub_v5.connector_releases.location', side_effect=lambda m, k: (self.storage, 'private', f'{m["version"]}/{m["platform"]}/{m["arch"]}/{k}')))
        with self.sessions() as db:
            user = User(id=8, company_id=None, email='super@example.com', name='平台', role=Role.SUPER_ADMIN, password_hash=TEST_PASSWORD_HASH)
            db.add(user)
            db.add(HubAgent(id=10, company_id=1, user_id=1, name='test', platform='macos', is_active=True, token_hash='a'*64))
            db.commit(); self.tokens[8] = create_access_token(user)
        self.agent_id = 10
        self.app.dependency_overrides[agent_auth] = lambda: SimpleNamespace(id=self.agent_id)

    def package(self, version='5.2.0', platform='macos', arch='arm64', content=b'update', installer=b'installer', distribution='signed'):
        manifest = {'kind': 'agent', 'version': version, 'platform': platform, 'arch': arch,
                    'sha256': hashlib.sha256(content).hexdigest(), 'size': len(content), 'key_id': 'test',
                    'protocol_min': 5, 'protocol_max': 5, 'entrypoint': 'agent', 'files': {'agent': hashlib.sha256(content).hexdigest()},
                    'min_launcher_version': '5.2.0', 'installer': {'filename': f'HaitooHubAgent-{platform}-{arch}-{version}.{ 'zip' if distribution=='internal' else 'exe' if platform=='windows' else 'dmg'}',
                    'size': len(installer), 'sha256': hashlib.sha256(installer).hexdigest()}}
        if distribution=='internal':manifest['distribution']='internal';manifest['min_launcher_version']='5.3.0'
        manifest['signature'] = base64.b64encode(self.key.sign(json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())).decode()
        return manifest, content, installer

    def upload(self, package=None, uid=8):
        manifest, content, installer = package or self.package()
        return self.request('POST', '/admin/connector-releases', uid=uid,
            data={'manifest_json': json.dumps(manifest)}, files={'artifact': ('update.zip', content), 'installer': ('installer', installer)})

    def stage(self, row, stage, ids=None):
        return self.request('PUT', f'/admin/connector-releases/{row["id"]}/stage', uid=8,
                            json={'revision': row['revision'], 'stage': stage, 'test_agent_ids': ids or []})

    def test_draft_test_stable_withdrawal_and_downloads_share_one_record(self):
        response = self.upload(); self.assertEqual(response.status_code, 200, response.text); row = response.json()
        self.assertEqual(self.request('GET', '/hub-v5/agent-installers').json()['items'], [])
        response = self.stage(row, 'test', [10]); self.assertEqual(response.status_code, 200, response.text); row = response.json()
        url = '/hub-v5/agent/connector-releases?platform=macos&arch=arm64'
        self.assertEqual(self.client.get(url).json()[0]['id'], row['id'])
        self.agent_id = 20; self.assertEqual(self.client.get(url).json(), [])
        self.assertEqual(self.client.get(f'/hub-v5/agent/connector-releases/{row["id"]}/file').status_code, 404)
        self.assertEqual(self.request('GET', '/hub-v5/agent-installers').json()['items'], [])
        response = self.stage(row, 'stable'); self.assertEqual(response.status_code, 200, response.text); row = response.json()
        items = self.request('GET', '/hub-v5/agent-installers').json()['items']; self.assertEqual(items[0]['id'], row['id'])
        response = self.request('GET', f'/hub-v5/agent-installers/macos/arm64/file?release_id={row["id"]}')
        self.assertEqual(response.content, b'installer'); self.assertIn('no-store', response.headers['cache-control'])
        self.assertEqual(self.client.get(f'/hub-v5/agent/connector-releases/{row["id"]}/file').content, b'update')
        response = self.stage(row, 'withdrawn'); self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get(url).json(), [])
        self.assertEqual(self.request('GET', f'/hub-v5/agent-installers/macos/arm64/file?release_id={row["id"]}').status_code, 404)
        self.assertEqual(self.stage(response.json(), 'stable').status_code, 422)

    def test_platform_admin_only_and_download_authentication(self):
        for uid in (1, 2, 5):
            self.assertEqual(self.upload(uid=uid).status_code, 403)
            self.assertEqual(self.request('GET', '/admin/connector-releases', uid=uid).status_code, 403)
        self.assertIn(self.client.get('/hub-v5/agent-installers').status_code, (401, 403))
        self.assertEqual(self.request('GET', '/hub-v5/agent-installers', uid=4).status_code, 403)

    def test_browser_download_link_signs_only_installer_without_reading_file(self):
        row = self.stage(self.upload().json(), 'stable').json()
        url = f"/hub-v5/agent-installers/macos/arm64/download-url?release_id={row['id']}"
        with patch.object(self.storage, 'generate_presigned_url', wraps=self.storage.generate_presigned_url) as sign, \
             patch.object(self.storage, 'get_object', side_effect=AssertionError('must not proxy file')):
            response = self.request('POST', url)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['expires_in'], 300)
        self.assertEqual(response.json()['url'], 'https://private.example/5.2.0/macos/arm64/installer')
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertEqual(sign.call_args.args, ('get_object',))
        self.assertEqual(sign.call_args.kwargs['ExpiresIn'], 300)
        params = sign.call_args.kwargs['Params']
        self.assertEqual(params['Bucket'], 'private')
        self.assertEqual(params['ResponseContentType'], 'application/octet-stream')
        self.assertIn("attachment; filename*=UTF-8''HaitooHubAgent-", params['ResponseContentDisposition'])
        self.assertIn('no-store', params['ResponseCacheControl'])
        self.assertEqual(self.stage(row, 'withdrawn').status_code, 200)
        with patch.object(self.storage, 'generate_presigned_url') as sign:
            self.assertEqual(self.request('POST', url).status_code, 404)
            sign.assert_not_called()

    def test_browser_link_requires_auth_channel_and_visible_test_device(self):
        row = self.stage(self.upload(self.package(distribution='internal')).json(), 'test', [10]).json()
        url = f"/hub-v5/agent-installers/macos/arm64/download-url?release_id={row['id']}&distribution=internal&agent_id=10"
        self.assertEqual(self.request('POST', url).status_code, 200)
        with patch.object(self.storage, 'generate_presigned_url') as sign:
            self.assertIn(self.client.post(url).status_code, (401, 403))
            self.assertEqual(self.request('POST', url, uid=4).status_code, 403)
            self.assertEqual(self.request('POST', url, uid=5).status_code, 404)
            self.assertEqual(self.request('POST', url.replace('&agent_id=10', '')).status_code, 404)
            self.assertEqual(self.request('POST', url.replace('distribution=internal', 'distribution=signed')).status_code, 404)
            sign.assert_not_called()

    def test_platform_browser_link_is_scoped_to_selected_company(self):
        from app.hub_v5.management import platform_router
        self.app.include_router(platform_router)
        row = self.stage(self.upload().json(), 'test', [10]).json()
        url = f"/admin/matrix/companies/1/agent-installers/macos/arm64/download-url?release_id={row['id']}&agent_id=10"
        self.assertEqual(self.request('POST', url, uid=8).status_code, 200)
        self.assertEqual(self.request('POST', url, uid=1).status_code, 403)
        self.assertEqual(self.request('POST', url.replace('/companies/1/', '/companies/2/'), uid=8).status_code, 404)

    def test_browser_link_reports_missing_corrupt_or_unavailable_storage(self):
        self.stage(self.upload().json(), 'stable')
        url = '/hub-v5/agent-installers/macos/arm64/download-url'
        with patch.object(self.storage, 'head_object', side_effect=RuntimeError('missing')):
            self.assertEqual(self.request('POST', url).status_code, 503)
        with patch.object(self.storage, 'head_object', return_value={'ContentLength': 999}):
            self.assertEqual(self.request('POST', url).status_code, 502)
        with patch.object(self.storage, 'generate_presigned_url', side_effect=RuntimeError('unavailable')):
            self.assertEqual(self.request('POST', url).status_code, 503)

    def test_immutable_content_signature_and_missing_installer(self):
        row = self.upload().json(); self.assertEqual(self.upload().json()['id'], row['id'])
        self.assertEqual(self.upload(self.package(content=b'changed')).status_code, 409)
        manifest, content, installer = self.package('5.3.0'); manifest['version'] = '5.4.0'
        self.assertEqual(self.upload((manifest, content, installer)).status_code, 422)
        self.assertEqual(self.upload(self.package('5.3.0')[:2] + (b'wrong',)).status_code, 422)
        self.assertEqual(self.upload(self.package(platform='windows', arch='arm64')).status_code, 422)

    def test_semver_platform_selection_and_stale_revision(self):
        for version in ('5.2.9', '5.2.10'):
            row = self.upload(self.package(version)).json(); response = self.stage(row, 'stable')
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.stage(row, 'withdrawn').status_code, 409)
        items = self.request('GET', '/hub-v5/agent-installers').json()['items']
        self.assertEqual(items[0]['version'], '5.2.10')
        self.assertEqual(self.request('GET', '/hub-v5/agent-installers/windows/x64/file').status_code, 404)
        self.assertEqual(self.request('GET', '/hub-v5/agent-installers/macos/arm64/file?release_id=9999').status_code, 404)


    def test_direct_upload_only_archives_verified_content_and_removes_temporary_files(self):
        package = self.package(); manifest, content, installer = package
        response = self.request('POST','/admin/connector-releases/uploads',uid=8,json=manifest)
        self.assertEqual(response.status_code,200,response.text);pending=response.json()
        self.assertEqual(pending['stage'],'uploading')
        self.assertEqual(self.stage(pending,'stable').status_code,422)
        self.assertEqual(self.request('GET','/hub-v5/agent-installers').json()['items'],[])
        sources = {kind:url.removeprefix('https://private.example/') for kind,url in pending['uploads'].items()}
        self.storage.objects[sources['update']] = content
        self.storage.objects[sources['installer']] = b'wrong'
        response = self.request('POST',f"/admin/connector-releases/{pending['id']}/complete",uid=8,json={})
        self.assertEqual(response.status_code,422,response.text)
        self.storage.objects[sources['installer']] = installer
        response = self.request('POST',f"/admin/connector-releases/{pending['id']}/complete",uid=8,json={})
        self.assertEqual(response.status_code,200,response.text);row=response.json()
        self.assertEqual(row['stage'],'draft')
        self.assertTrue(all(key not in self.storage.objects for key in sources.values()))
        self.assertEqual(self.stage(row,'stable').status_code,200)
        # 未过期临时链接再次写入也无法修改已经归档的安装程序。
        self.storage.objects[sources['installer']] = b'late overwrite'
        self.assertEqual(self.request('GET','/hub-v5/agent-installers/macos/arm64/file').content,installer)
        response = self.request('POST','/admin/connector-releases/uploads',uid=8,json=manifest)
        self.assertNotIn('uploads',response.json())


    def test_internal_zip_releases_are_explicit_and_do_not_replace_signed_channel(self):
        signed=self.stage(self.upload().json(),'stable').json()
        internal=self.upload(self.package('5.3.0',distribution='internal'))
        self.assertEqual(internal.status_code,200,internal.text)
        internal=self.stage(internal.json(),'stable').json()
        normal=self.client.get('/hub-v5/agent/connector-releases?platform=macos&arch=arm64').json()
        self.assertEqual(normal[0]['id'],signed['id'])
        rows=self.client.get('/hub-v5/agent/connector-releases?platform=macos&arch=arm64&distribution=internal').json()
        self.assertEqual(rows[0]['id'],internal['id'])
        items=self.request('GET','/hub-v5/agent-installers?distribution=all').json()['items']
        self.assertEqual({r['distribution'] for r in items},{'internal','signed'})
        response=self.request('GET',f"/hub-v5/agent-installers/macos/arm64/file?release_id={internal['id']}&distribution=internal")
        self.assertEqual(response.content,b'installer')
        self.assertEqual(self.request('GET',f"/hub-v5/agent-installers/macos/arm64/file?release_id={internal['id']}").status_code,404)

    def test_test_device_manual_download_requires_visible_device_and_remains_withdrawable(self):
        row=self.upload(self.package(distribution='internal')).json()
        row=self.stage(row,'test',[10]).json()
        self.assertEqual(self.request('GET','/hub-v5/agent-installers?distribution=internal').json()['items'],[])
        url=f"/hub-v5/agent-installers/macos/arm64/file?distribution=internal&agent_id=10&release_id={row['id']}"
        self.assertEqual(self.request('GET',url).content,b'installer')
        self.assertEqual(self.request('GET',url,uid=5).status_code,404)
        self.assertEqual(self.request('GET',url.replace('agent_id=10','agent_id=999')).status_code,404)
        self.assertEqual(self.stage(row,'withdrawn').status_code,200)
        self.assertEqual(self.request('GET',url).status_code,404)
