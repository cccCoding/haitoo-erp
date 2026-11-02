"""连接器只提供健康探测，授权及目录展示统一由 ERP 承担。"""
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connector import ConnectorServer
from matrix_runtime import MatrixRuntime


class ConnectorHealthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connector = ConnectorServer({}, 'https://erp.haitorok.com')
        self.server = TestServer(self.connector.app())
        self.client = TestClient(self.server)
        await self.client.start_server()
        self.connector.port = self.server.port
        self.addAsyncCleanup(self.client.close)

    async def test_health_has_no_credentials_and_no_local_workbench(self):
        response = await self.client.get('/health', headers={'Origin': 'http://localhost:5173'})
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {'application': 'haitoo-hub-agent', 'protocol': 5, 'mode': 'connector', 'status': 'ready'})
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'http://localhost:5173')
        self.assertNotIn('Set-Cookie', response.headers)
        for path in ('/', '/assets/workbench.js', '/api/status', '/api/environments'):
            self.assertEqual((await self.client.get(path)).status, 404)
        self.assertEqual((await self.client.post('/api/login', json={'email': 'unused', 'password': 'unused'})).status, 404)

    async def test_probe_rejects_foreign_origins_hosts_and_credential_preflight(self):
        self.assertEqual((await self.client.get('/health', headers={'Origin': 'https://foreign.example'})).status, 403)
        self.assertEqual((await self.client.get('/health', headers={'Host': 'foreign.example'})).status, 403)
        response = await self.client.options('/health', headers={'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Private-Network': 'true'})
        self.assertEqual(response.status, 204)
        self.assertEqual(response.headers['Access-Control-Allow-Private-Network'], 'true')
        self.assertEqual((await self.client.options('/health', headers={'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Headers': 'authorization'})).status, 403)


class ConnectorSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_connector_registers_and_pulls_identity_from_erp(self):
        with tempfile.TemporaryDirectory() as directory:
            client = SimpleNamespace(post=AsyncMock(return_value={'enabled': True, 'paused': False, 'hub_identity': ''}), request=AsyncMock(return_value=[]))
            host = SimpleNamespace(config={}, state={}, client=client, current_claim=None, synced_monotonic=None, last_sync_attempt=0)
            runtime = MatrixRuntime(host, directory, lambda c: None, AsyncMock())
            with patch('matrix_runtime.load_plugin', return_value=None), patch('matrix_runtime.keys', return_value={}):
                await runtime.heartbeat()
                self.assertFalse(runtime.enabled)
                self.assertNotIn('hub_identity', client.post.call_args_list[0].kwargs['json'])
                client.post.return_value = {'enabled': True, 'paused': False, 'hub_identity': 'erp-team'}
                await runtime.heartbeat()
            self.assertTrue(runtime.enabled)
            self.assertEqual(host.config['matrix_hub_identity'], 'erp-team')
            self.assertIsNone(host.synced_monotonic)



if __name__ == '__main__':
    unittest.main()
