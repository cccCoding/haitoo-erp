"""平台公司矩阵开关与公司端只读边界。"""
import unittest

from sqlalchemy import select

from app import main
from app.hub_v5.api import router
from app.hub_v5.models import MatrixCompany, MatrixAudit
from app.hub_v5 import service
from app.models import User, Role
from app.security import create_access_token
from tests.test_supply_catalog import SupplyFixture, TEST_PASSWORD_HASH


class AdminMatrixConfigTests(SupplyFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.app.include_router(router)
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

    def test_old_listing_flag_no_longer_blocks_enabled_company(self):
        with self.sessions() as db:
            db.add(MatrixCompany(company_id=1, enabled=True, listing_enabled=False))
            db.commit()
        self.assertEqual(self.request('GET', '/hub-v5/config').json(), {'enabled': True, 'listing_enabled': True})
        with self.sessions() as db:
            self.assertTrue(service.enabled(db, 1, listing=True).enabled)
