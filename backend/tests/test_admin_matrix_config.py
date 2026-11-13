"""平台公司矩阵开关、跨公司矩阵管理边界与公司端只读边界。"""
import unittest

from sqlalchemy import select

from app import main
from app.hub_v5.api import router
from app.hub_v5.management import platform_router
from app.hub_v5.models import MatrixCompany, MatrixAudit, MatrixCommand, MatrixMemberPermission
from app.hub_v5 import service
from app.models import HubAgent, User, Role
from app.security import create_access_token
from tests.test_supply_catalog import SupplyFixture, TEST_PASSWORD_HASH


class AdminMatrixConfigTests(SupplyFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.app.include_router(router)
        self.app.include_router(platform_router)
        self.app.add_api_route('/admin/companies', main.list_admin_companies, methods=['GET'])
        self.app.add_api_route('/admin/companies/{company_id}/tk-matrix', main.set_admin_company_matrix, methods=['PUT'])
        with self.sessions() as db:
            user = User(id=8, company_id=None, email='super@example.com', name='平台管理员',
                        role=Role.SUPER_ADMIN, password_hash=TEST_PASSWORD_HASH)
            db.add(user)
            db.commit()
            self.tokens[8] = create_access_token(user)

    def test_platform_switch_controls_company_and_listing(self):
        url = '/admin/companies/1/tk-matrix'
        rows = self.request('GET', '/admin/companies', uid=8).json()
        self.assertFalse(next(row for row in rows if row['id'] == 1)['tk_matrix_enabled'])
        for enabled in (True, False):
            response = self.request('PUT', url, uid=8, json={'enabled': enabled})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {'enabled': enabled})
            config = self.request('GET', '/hub-v5/config').json()
            self.assertEqual(config, {'enabled': enabled, 'listing_enabled': enabled})
            with self.sessions() as db:
                row = db.get(MatrixCompany, 1)
                self.assertEqual((row.enabled, row.listing_enabled), (enabled, enabled))
                self.assertIsNone(db.get(MatrixCompany, 2))
        with self.sessions() as db:
            logs = db.scalars(select(MatrixAudit).where(MatrixAudit.company_id == 1)).all()
            self.assertEqual(len(logs), 2)
            self.assertTrue(all(log.actor_id == 8 for log in logs))

    def test_company_cannot_change_switch_and_invalid_company_rejected(self):
        for uid in (1, 2, 5):
            response = self.request('PUT', '/admin/companies/1/tk-matrix', uid=uid, json={'enabled': True})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.request('PUT', '/hub-v5/config', json={'enabled': True, 'listing_enabled': True}).status_code, 403)
        self.assertEqual(self.request('PUT', '/admin/companies/999/tk-matrix', uid=8, json={'enabled': True}).status_code, 404)
        self.assertEqual(self.request('PUT', '/admin/companies/1/tk-matrix', uid=8, json={'enabled': 'false'}).status_code, 422)

    def test_platform_matrix_reads_and_device_commands_are_company_scoped(self):
        with self.sessions() as db:
            db.add(MatrixCompany(company_id=1, enabled=True, listing_enabled=True))
            db.add(HubAgent(id=20, company_id=1, user_id=1, name='平台管理测试设备', platform='macos',
                            token_hash='d' * 64, is_active=True))
            db.commit()
        members = self.request('GET', '/admin/matrix/companies/1/members', uid=8)
        self.assertEqual(members.status_code, 200, members.text)
        self.assertEqual([item['id'] for item in members.json()['items']], [1, 2, 3, 4, 7])
        company_two = self.request('GET', '/admin/matrix/companies/2/members', uid=8)
        self.assertEqual(company_two.status_code, 200, company_two.text)
        self.assertEqual([item['id'] for item in company_two.json()['items']], [5, 6])
        self.assertEqual(self.request('GET', '/admin/matrix/companies/1/config', uid=8).json(),
                         {'enabled': True, 'listing_enabled': True})
        devices = self.request('GET', '/admin/matrix/companies/1/devices', uid=8).json()['items']
        self.assertEqual([item['id'] for item in devices], [20])
        stats = self.request('GET', '/admin/matrix/companies/1/statistics', uid=8)
        self.assertEqual(stats.status_code, 200, stats.text)
        self.assertEqual(stats.json()['current']['devices'], 1)
        self.assertEqual(stats.json()['current']['authorized_members'], 1)
        self.assertEqual(self.request('GET', '/admin/matrix/companies/1/statistics?user_id=5', uid=8).status_code, 404)
        # 平台管理员可写，但设备必须属于 URL 指定的公司；审计记录平台管理员本人。
        self.assertEqual(self.request('POST', '/admin/matrix/companies/2/agents/20/commands', uid=8,
                                      json={'kind': 'revoke'}).status_code, 404)
        revoked = self.request('POST', '/admin/matrix/companies/1/agents/20/commands', uid=8,
                               json={'kind': 'revoke'})
        self.assertEqual(revoked.status_code, 200, revoked.text)
        with self.sessions() as db:
            self.assertFalse(db.get(HubAgent, 20).is_active)
            self.assertEqual(db.get(MatrixCommand, revoked.json()['command_id']).company_id, 1)
            self.assertEqual(db.scalars(select(MatrixAudit).where(MatrixAudit.action == 'device.revoke')).one().actor_id, 8)

    def test_platform_matrix_endpoints_reject_non_super_admin_and_unknown_company(self):
        for uid in (1, 2, 5):
            self.assertEqual(self.request('GET', '/admin/matrix/companies/1/members', uid=uid).status_code, 403)
            self.assertEqual(self.request('GET', '/admin/matrix/companies/1/devices', uid=uid).status_code, 403)
            self.assertEqual(self.request('GET', '/admin/matrix/companies/1/statistics', uid=uid).status_code, 403)
        self.assertEqual(self.request('GET', '/admin/matrix/companies/999/members', uid=8).status_code, 404)
        self.assertEqual(self.request('GET', '/admin/matrix/companies/999/statistics', uid=8).status_code, 404)

    def test_old_listing_flag_no_longer_blocks_enabled_company(self):
        with self.sessions() as db:
            db.add(MatrixCompany(company_id=1, enabled=True, listing_enabled=False))
            db.commit()
        self.assertEqual(self.request('GET', '/hub-v5/config').json(), {'enabled': True, 'listing_enabled': True})
        with self.sessions() as db:
            self.assertTrue(service.enabled(db, 1, listing=True).enabled)

    def view_token(self, uid=1):
        response = self.request('POST', f'/admin/matrix/companies/1/users/{uid}/view', uid=8)
        self.assertEqual(response.status_code, 200, response.text)
        return {'Authorization': f"Bearer {response.json()['token']}"}

    def test_user_view_issuance_checks_platform_company_and_user(self):
        path = '/admin/matrix/companies/1/users/1/view'
        self.assertEqual(self.request('POST', path, uid=8).status_code, 403)
        with self.sessions() as db:
            db.add(MatrixCompany(company_id=1, enabled=True))
            db.commit()
        for uid in (1, 2, 5):
            self.assertEqual(self.request('POST', path, uid=uid).status_code, 403)
        self.assertEqual(self.request('POST', '/admin/matrix/companies/1/users/5/view', uid=8).status_code, 404)
        self.view_token()
        with self.sessions() as db:
            audit = db.scalars(select(MatrixAudit).where(MatrixAudit.action == 'user.view')).one()
            self.assertEqual(audit.actor_id, 8)
            db.get(User, 1).is_active = False
            db.commit()
        self.assertEqual(self.request('POST', path, uid=8).status_code, 403)

    def test_user_view_is_read_only_scoped_and_revalidates_permissions(self):
        with self.sessions() as db:
            db.add(MatrixCompany(company_id=1, enabled=True))
            db.add(MatrixMemberPermission(user_id=2, company_id=1, enabled=True))
            db.add_all([HubAgent(id=i, company_id=company, user_id=uid, name=f'设备{i}',
                platform='macos', token_hash=str(i)*64) for i, company, uid in ((20,1,1),(21,1,2),(22,2,5))])
            db.commit()
        headers = self.view_token(2)
        response = self.client.get('/hub-v5/agents', headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([row['id'] for row in response.json()], [21])
        for path in ('/hub-v5/access', '/hub-v5/config', '/hub-v5/environments', '/hub-v5/operations',
                     '/hub-v5/plans', '/hub-v5/runs', '/hub-v5/shops/metrics', '/supply/strategies', '/supply/catalogs'):
            response = self.client.get(path, headers=headers)
            self.assertEqual(response.status_code, 200, (path, response.text))
        for method, path, payload in (('POST','/hub-v5/agents/21/commands',{'kind':'refresh'}),
            ('PUT','/hub-v5/config',{'enabled':True,'listing_enabled':True}),
            ('POST','/hub-v5/operations',{'name':'禁止创建','tasks':['shop.collect']}),
            ('POST','/supply/strategies',self.strategy_input()),
            ('GET','/admin/companies',None), ('GET','/supply/users',None)):
            self.assertEqual(self.client.request(method,path,headers=headers,json=payload).status_code,403,path)
        with self.sessions() as db:
            db.get(MatrixMemberPermission, 2).enabled = False
            db.commit()
        self.assertFalse(self.client.get('/hub-v5/access', headers=headers).json()['enabled'])
        self.assertEqual(self.client.get('/hub-v5/environments', headers=headers).status_code, 403)
        with self.sessions() as db:
            db.get(User, 8).token_version += 1
            db.commit()
        self.assertEqual(self.client.get('/hub-v5/access', headers=headers).status_code, 401)

    def test_user_view_rejects_expired_tokens_and_changed_target(self):
        from datetime import datetime, timedelta, timezone
        from jose import jwt
        from app.config import get_settings
        with self.sessions() as db:
            db.add(MatrixCompany(company_id=1, enabled=True))
            db.commit()
        headers = self.view_token()
        payload = jwt.decode(headers['Authorization'][7:], get_settings().secret_key, algorithms=['HS256'])
        payload['exp'] = datetime.now(timezone.utc) - timedelta(seconds=1)
        expired = jwt.encode(payload, get_settings().secret_key, algorithm='HS256')
        self.assertEqual(self.client.get('/hub-v5/access', headers={'Authorization':f'Bearer {expired}'}).status_code,401)
        with self.sessions() as db:
            db.get(User, 1).company_id = 2
            db.commit()
        self.assertEqual(self.client.get('/hub-v5/access', headers=headers).status_code,403)
