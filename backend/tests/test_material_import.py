import asyncio
from io import BytesIO
import unittest
from unittest.mock import patch
import httpx

from fastapi import HTTPException, UploadFile
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base
from app.material_import import build_import_template, parse_import_workbook, validate_image_link, MAX_IMPORT_BYTES
from app.models import Company, MaterialAsset, ProductTemplate, Role, User
from app.schemas import MaterialImportConfirmInput


def xlsx(rows):
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class MaterialImportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([
                Company(id=1, name='A'), Company(id=2, name='B'),
                User(id=1, company_id=1, email='a@example.com', name='A', password_hash='x', user_code='AA', role=Role.MEMBER),
                ProductTemplate(id=1, company_id=1, name='Y1', cover_url='https://img.example/cover'),
                ProductTemplate(id=2, company_id=2, name='Y2', cover_url='https://img.example/cover'),
                MaterialAsset(company_id=1, template_id=2, claimed_by=99, name='old', url='https://img.example/existing', usage_status='used', sku='OLD'),
                MaterialAsset(company_id=2, claimed_by=99, name='foreign', url='https://img.example/foreign', sku='FOREIGN'),
            ])
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def preview(self, data, name='import.xlsx'):
        with self.sessions() as db:
            return asyncio.run(main.preview_material_import(UploadFile(filename=name, file=BytesIO(data)), user=db.get(User, 1), db=db))

    def test_template_and_parser(self):
        template = main.download_material_import_template().body
        workbook = load_workbook(BytesIO(template))
        self.assertEqual(workbook.active['A1'].value, 'SKU图')
        workbook.close()
        with self.assertRaisesRegex(ValueError, '没有可导入'):
            parse_import_workbook(template)
        data = xlsx([['备注', 'SKU图'], ['a', ' https://img.example/a?q=A '], ['b', None], ['c', 'https://img.example/a?q=A'], ['d', 'https://img.example/a?q=a']])
        self.assertEqual(parse_import_workbook(data), ['https://img.example/a?q=A', 'https://img.example/a?q=a'])

    def test_parser_errors(self):
        cases = [([['图片']], '缺少'), ([['SKU图', 'SKU图']], '只能有一个'), ([['SKU图'], ['ftp://example.com/a']], '第 2 行'), ([['SKU图'], [123]], '第 2 行'), ([['SKU图'], ['=HYPERLINK("https://example.com","a")']], '第 2 行'), ([['SKU图']] + [['https://img.example/a']] * 1001, '超限')]
        for rows, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                parse_import_workbook(xlsx(rows))
        for data, message in [(b'broken', '无法读取'), (b'x' * (MAX_IMPORT_BYTES + 1), '10MB')]:
            with self.assertRaisesRegex(ValueError, message):
                parse_import_workbook(data)
        for url in ['https:///a', 'https://example.com:bad/a', 'https://example.com/a b', 'https://example.com/' + 'a' * 500]:
            with self.assertRaises(ValueError):
                validate_image_link(url, 2)
        with self.assertRaises(HTTPException):
            self.preview(xlsx([['SKU图'], ['https://img.example/a']]), 'a.xls')

    def test_company_wide_preview_is_read_only(self):
        result = self.preview(xlsx([['SKU图'], ['https://img.example/existing'], ['https://img.example/existing'], ['https://img.example/foreign']]))
        self.assertEqual(result['items'], [dict(url='https://img.example/existing', exists=True), dict(url='https://img.example/foreign', exists=False)])
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset)), 2)

    def test_authenticated_http_endpoints(self):
        with self.sessions() as db:
            user = db.get(User, 1)
            main.app.dependency_overrides[main.current_user] = lambda: user
            main.app.dependency_overrides[main.get_db] = lambda: db
            async def requests():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
                    template = await client.get('/material-assets/import-template')
                    self.assertEqual(template.status_code, 200)
                    self.assertIn('spreadsheetml', template.headers['content-type'])
                    self.assertIn('filename*=', template.headers['content-disposition'])
                    preview = await client.post('/material-assets/import-preview', files={'file': ('import.xlsx', xlsx([['SKU图'], ['https://img.example/existing']]))})
                    self.assertEqual(preview.json()['items'], [{'url': 'https://img.example/existing', 'exists': True}])
                    invalid = await client.post('/material-assets/import-confirm', json={'template_id': 1, 'urls': ['https://img.example/valid', 'javascript:bad']})
                    self.assertEqual(invalid.status_code, 400)
                    confirmed = await client.post('/material-assets/import-confirm', json={'template_id': 1, 'urls': ['https://img.example/existing']})
                    self.assertEqual(confirmed.json(), {'imported': 1})
            try:
                asyncio.run(requests())
            finally:
                main.app.dependency_overrides.clear()
            self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset)), 3)

    def test_confirm_existing_link_and_source_compatibility(self):
        urls = ['https://img.example/existing', ' https://img.example/new?q=Original ', 'https://img.example/existing']
        with self.sessions() as db, patch.object(main, 'upload_image_bytes_async') as upload, patch.object(main, 'create_image_upload_url') as presign, patch.object(main.httpx, 'AsyncClient') as client:
            result = main.confirm_material_import(MaterialImportConfirmInput(template_id=1, urls=urls), user=db.get(User, 1), db=db)
            self.assertEqual(result, {'imported': 2})
            assets = db.scalars(select(MaterialAsset).where(MaterialAsset.source_type == 'imported')).all()
            self.assertEqual([asset.url for asset in assets], [urls[0], urls[1].strip()])
            self.assertEqual(len({asset.sku for asset in assets}), 2)
            self.assertTrue(all(asset.sku.startswith('Y1AA') and len(asset.sku) == 10 and asset.template_id == 1 and asset.claimed_by == 1 and asset.company_id == 1 and asset.usage_status == 'unused' for asset in assets))
            upload.assert_not_called(); presign.assert_not_called(); client.assert_not_called()
            unused = main.list_material_assets(page=1, page_size=20, creator_id=None, template_id=None, usage_status='unused', user=db.get(User, 1), db=db)
            self.assertEqual({item['source_type'] for item in unused['items']}, {'imported'})
            admin = db.get(User, 1); admin.role = Role.COMPANY_ADMIN
            old = main.list_material_assets(page=1, page_size=20, creator_id=None, template_id=None, usage_status='used', user=admin, db=db)
            self.assertEqual(old['items'][0]['source_type'], 'local_upload')

    def test_permissions_and_missing_code(self):
        with self.sessions() as db:
            user = db.get(User, 1)
            for template_id in (2, 999):
                with self.assertRaises(HTTPException) as error:
                    main.confirm_material_import(MaterialImportConfirmInput(template_id=template_id, urls=['https://img.example/a']), user=user, db=db)
                self.assertEqual(error.exception.status_code, 404)
            user.user_code = None
            with self.assertRaises(HTTPException) as error:
                main.confirm_material_import(MaterialImportConfirmInput(template_id=1, urls=['https://img.example/a']), user=user, db=db)
            self.assertIn('用户代码', error.exception.detail)

    def test_sku_conflict_retries(self):
        with self.sessions() as db:
            db.add(MaterialAsset(company_id=1, claimed_by=1, name='collision', url='https://img.example/collision', sku='Y1AAAAAAAA'))
            db.commit()
            with patch.object(main.secrets, 'choice', side_effect=list('AAAAAABBBBBB')):
                main.confirm_material_import(MaterialImportConfirmInput(template_id=1, urls=['https://img.example/a']), user=db.get(User, 1), db=db)
            asset = db.scalar(select(MaterialAsset).where(MaterialAsset.source_type == 'imported'))
            self.assertEqual(asset.sku, 'Y1AABBBBBB')

    def test_material_type_filter_includes_legacy_sources_and_scopes(self):
        with self.sessions() as db:
            db.add_all([
                MaterialAsset(company_id=1, claimed_by=1, template_id=1, source_task_id=123, name='AI', url='https://img.example/ai', sku='AI'),
                MaterialAsset(company_id=1, claimed_by=1, template_id=1, name='local', url='https://img.example/local', sku='LOCAL'),
                MaterialAsset(company_id=1, claimed_by=1, template_id=1, source_type='imported', name='imported', url='https://img.example/imported', sku='IMPORTED'),
                MaterialAsset(company_id=2, claimed_by=1, source_type='imported', name='foreign', url='https://img.example/foreign-imported', sku='FOREIGN_IMPORT'),
            ])
            db.commit()
            user = db.get(User, 1)
            for source, expected_sku in [('ai_created', 'AI'), ('local_upload', 'LOCAL'), ('imported', 'IMPORTED')]:
                result = main.list_material_assets(page=1, page_size=20, creator_id=None, template_id=1, usage_status='unused', source_type=source, user=user, db=db)
                self.assertEqual(result['total'], 1)
                self.assertEqual([item['sku'] for item in result['items']], [expected_sku])
                self.assertEqual(result['items'][0]['source_type'], source)
            with self.assertRaises(HTTPException) as error:
                main.list_material_assets(source_type='unsupported', user=user, db=db)
            self.assertEqual(error.exception.status_code, 422)

    def test_batch_rolls_back_when_second_insert_fails(self):
        original = main.add_material_asset_with_sku
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise HTTPException(503, 'SKU 生成失败')
            return original(*args, **kwargs)
        with self.sessions() as db, patch.object(main, 'add_material_asset_with_sku', side_effect=fail_second):
            with self.assertRaises(HTTPException):
                main.confirm_material_import(MaterialImportConfirmInput(template_id=1, urls=['https://img.example/a', 'https://img.example/b']), user=db.get(User, 1), db=db)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset)), 2)


if __name__ == '__main__':
    unittest.main()
