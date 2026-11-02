"""首次下载不需要已有Agent，且不开放任意文件或外部用户访问。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tests.test_supply_catalog import SupplyFixture
from app.hub_v5.installers import router


class InstallerTests(SupplyFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.app.include_router(router)
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.settings=patch('app.hub_v5.installers.get_settings',return_value=SimpleNamespace(hub_agent_installer_dir=self.directory.name))
        self.settings.start();self.addCleanup(self.settings.stop)

    def test_only_latest_known_installer_is_downloaded(self):
        for version in ('5.0.0','5.0.2','5.0.10'):
            (self.root/f'HaitooHubAgent-macos-arm64-{version}.zip').write_bytes(version.encode())
        (self.root/'private.txt').write_text('not downloadable')
        response=self.request('GET','/hub-v5/agent-installers')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(response.json()['items']),1)
        self.assertEqual(response.json()['items'][0]['version'],'5.0.10')
        response=self.request('GET','/hub-v5/agent-installers/macos/arm64/file')
        self.assertEqual(response.content,b'5.0.10')
        self.assertIn('no-store',response.headers['cache-control'])
        self.assertEqual(self.request('GET','/hub-v5/agent-installers/windows/x64/file').status_code,404)

    def test_no_token_external_user_and_symlink_are_not_downloadable(self):
        (self.root/'HaitooHubAgent-macos-x64-5.0.0.zip').symlink_to('/etc/hosts')
        self.assertEqual(self.request('GET','/hub-v5/agent-installers').json()['items'],[])
        self.assertEqual(self.request('GET','/hub-v5/agent-installers',uid=4).status_code,403)
        self.assertIn(self.client.get('/hub-v5/agent-installers').status_code,(401,403))
