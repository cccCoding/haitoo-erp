"""美工权限、逐图审核、SKU 下载与统计的业务回归。"""
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import design, image_files, main
from app.database import Base, get_db
from app.models import (AIProviderSetting, Company, CreativeImageEvent, DesignGroup,
    DesignTemplateVisibility, ImageFile, MaterialAsset, PodTask, ProductTemplate, Role,
    TaskResultReview, TaskStatus, User, UserAIProviderCredential, UserTemplatePrompt, UserTemplateWhiteImage)
from app.schema_version import alembic_config
from app.security import create_access_token
from app.storage import StorageError


class DesignDepartmentTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([Company(id=1, name='本公司'), Company(id=2, name='其他公司')])
            for uid, role, company, group in [(1,Role.COMPANY_ADMIN,1,None),(2,Role.DESIGNER,1,1),
                    (3,Role.DESIGN_LEADER,1,1),(4,Role.DESIGNER,1,2),(5,Role.MEMBER,1,None),
                    (6,Role.DESIGN_LEADER,1,2),(7,Role.DESIGNER,2,None),(8,Role.COMPANY_ADMIN,2,None),
                    (9,Role.TEAM_LEADER,1,None),(10,Role.DESIGNER,1,None),(11,Role.SUPPLY_USER,1,None)]:
                db.add(User(id=uid, name=f'成员{uid}', email=f'u{uid}@example.com', user_code=f'{uid:02}',
                    password_hash='x', role=role, company_id=company, design_group_id=group,
                    supply_expires_at=datetime.utcnow()+timedelta(days=30)))
            db.add_all([DesignGroup(id=1,company_id=1,name='美工一组',leader_user_id=3),
                DesignGroup(id=2,company_id=1,name='美工二组',leader_user_id=6),
                ProductTemplate(id=1,company_id=1,name='Y1'), ProductTemplate(id=2,company_id=1,name='Y2'),
                ProductTemplate(id=3,company_id=None,name='Y3',is_platform=True), ProductTemplate(id=4,company_id=2,name='Y4'),
                DesignTemplateVisibility(company_id=1,template_id=1,is_public=True),
                AIProviderSetting(provider='grsai',display_name='Grsai',model='test',enabled=True,is_default=True,credential_provider='grsai')])
            for uid in (2,3,4,5,6,7,9,10):
                db.add(PodTask(id=uid,company_id=2 if uid==7 else 1,template_id=4 if uid==7 else 1,
                    created_by=uid,task_type='sku_image',status=TaskStatus.COMPLETED,
                    parameters={'print_urls':['https://images.example/print.png'],'white_image_url':'https://images.example/private.png',
                        'white_image_id':uid,'creative_requirement':'私有创作要求'},
                    result_urls=[f'https://images.example/{uid}.png',f'https://images.example/{uid}-second.png']))
                db.add(ImageFile(id=uid,company_id=2 if uid==7 else 1,sha256=f'{uid:064}',
                    object_key=f'material/company/{2 if uid==7 else 1}/{uid}.png',url=f'https://images.example/{uid}.png',mime_type='image/png',size_bytes=5))
                db.add(MaterialAsset(id=uid,company_id=2 if uid==7 else 1,template_id=4 if uid==7 else 1,
                    image_file_id=uid,source_task_id=uid,source_type='ai_created',claimed_by=uid,
                    sku=f'SKU{uid}',url=f'https://images.example/{uid}.png',name=f'素材{uid}'))
            db.add(PodTask(id=90,company_id=1,template_id=1,created_by=5,task_type='carousel',parameters={},result_urls=[]))
            db.add_all([UserTemplateWhiteImage(id=1,company_id=1,user_id=2,template_id=1,name='白底',image_url='https://images.example/white.png'),
                UserTemplateWhiteImage(id=2,company_id=1,user_id=2,template_id=2,name='私有模板白底',image_url='https://images.example/hidden.png'),
                UserTemplatePrompt(id=1,company_id=1,user_id=2,template_id=1,name='要求',content='保留印花'),
                UserTemplatePrompt(id=2,company_id=1,user_id=2,template_id=2,name='隐藏要求',content='保留印花')])
            db.commit()
            self.tokens = {u.id:create_access_token(u) for u in db.scalars(select(User))}
        def override():
            with self.sessions() as db:
                yield db
        main.app.dependency_overrides[get_db] = override
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    def request(self, method, path, uid=1, **kwargs):
        return self.client.request(method,path,headers={'Authorization':f'Bearer {self.tokens[uid]}'},**kwargs)

    def ok(self, response):
        self.assertEqual(response.status_code,200,response.text[:1000])
        return response.json()

    def tasks(self, uid, **params):
        return self.ok(self.request('GET','/tasks',uid,params=params))

    def test_default_task_scope_and_sku_search_are_separate_from_mutation(self):
        self.assertEqual([t['id'] for t in self.tasks(2)['items']],[2])
        self.assertEqual({t['id'] for t in self.tasks(3)['items']},{2,3})
        self.assertEqual({m['id'] for m in self.ok(self.request('GET','/design-team-members',3))},{2,3})
        self.assertEqual(self.tasks(3,creator_id=4)['total'],0)
        for uid in (2,3):
            data=self.tasks(uid,sku_query=' SKU5\nSKU4\nSKU7\nSKU5 ')
            self.assertEqual({t['id'] for t in data['items']},{4,5})
            self.assertFalse(any(t['can_manage'] for t in data['items']))
            self.assertEqual(data['task_type_counts']['carousel'],0)
            self.assertEqual(self.request('GET','/tasks/5',uid).status_code,404)
            task=self.ok(self.request('GET','/tasks/5',uid,params={'sku_query':'SKU5'}))
            self.assertNotIn('white_image_url',task['parameters'])
            self.assertIsNone(task['parameters']['creative_requirement'])
            self.assertEqual(self.request('GET','/tasks/4',uid,params={'sku_query':'SKU5'}).status_code,404)
            self.assertEqual(self.request('GET','/tasks/7',uid,params={'sku_query':'SKU7'}).status_code,404)
            self.assertEqual(self.request('POST','/tasks/5/claim-materials',uid,json={'result_urls':[],'request_key':'request-test'}).status_code,404)
            self.assertEqual(self.request('POST','/tasks/5/retry',uid,json={}).status_code,404)
            self.assertEqual(self.request('POST','/tasks/batch-retry',uid,json={'task_ids':[5]}).status_code,404)
        self.assertEqual([t['id'] for t in self.tasks(2,sku_query=' \n  ')['items']],[2])
        self.assertEqual(self.tasks(5,sku_query='SKU4')['total'],0)
        self.assertEqual(self.tasks(9,sku_query='SKU5')['total'],0)
        self.assertEqual(self.tasks(2,sku_query='SKU')['total'],0)
        self.assertEqual(self.tasks(2,sku_query='SKU5',task_type='carousel')['total'],0)

    def test_design_roles_cannot_call_other_business_or_manage_peers_resources(self):
        for uid in (2,3):
            for path in ('/members','/shops','/material-assets','/drafts','/product-library',
                         '/category-catalogs','/operation-statistics','/supply/templates','/hub-upload-tasks'):
                response=self.request('GET',path,uid)
                self.assertIn(response.status_code,(403,404),f'{uid} {path}: {response.text}')
            self.assertEqual(self.request('GET','/user-template-resources',uid,params={'user_id':5}).status_code,403)
            self.assertEqual(self.request('GET','/user-template-resources',uid,params={'scope':'company'}).status_code,403)
            self.assertEqual(self.request('POST','/templates',uid,json={'name':'TEST'}).status_code,403)
            self.assertEqual(self.request('POST','/uploads/presign',uid,json={'category':'template','files':[{'content_type':'image/png','content_length':5,'sha256':'a'*64}]}).status_code,403)
        with patch.object(main,'prepare_upload',return_value={'upload_url':'https://upload.example'}) as upload:
            self.ok(self.request('POST','/uploads/creative-asset/presign',2,json={
                'content_type':'image/png','content_length':5,'sha256':'a'*64}))
            upload.assert_called_once()

    def test_template_publication_is_company_scoped_and_applies_to_resources(self):
        self.assertEqual([t['id'] for t in self.ok(self.request('GET','/templates',2))],[1])
        self.assertEqual({t['id'] for t in self.ok(self.request('GET','/templates',3))},{1,2,3})
        self.assertEqual(self.request('PATCH','/templates/2/design-visibility',2,json={'is_public':True}).status_code,403)
        self.ok(self.request('PATCH','/templates/3/design-visibility',3,json={'is_public':True}))
        self.assertEqual({t['id'] for t in self.ok(self.request('GET','/templates',2))},{1,3})
        with self.sessions() as db:
            self.assertIsNone(db.get(DesignTemplateVisibility,(2,3)))
        self.assertEqual(self.request('PATCH','/templates/4/design-visibility',3,json={'is_public':True}).status_code,404)
        data=self.ok(self.request('GET','/user-template-resources',2))
        self.assertEqual([r['id'] for r in data['white_images']],[1])
        self.assertEqual([r['id'] for r in data['prompts']],[1])
        self.assertEqual(self.request('GET','/user-template-resources',2,params={'template_id':2}).status_code,404)
        self.ok(self.request('PATCH','/templates/1/design-visibility',1,json={'is_public':False}))
        self.assertEqual(self.ok(self.request('GET','/user-template-resources',2))['white_images'],[])
        self.assertEqual(self.request('PUT','/user-template-white-images/1',2,json={'name':'新名字'}).status_code,404)
        self.assertEqual(self.request('PUT','/user-template-prompts/1',2,json={'content':'新要求'}).status_code,404)
        self.assertEqual(self.request('POST','/tasks',2,json={'template_id':1,'white_image_id':1,
            'creative_requirement':'保留印花','print_urls':['https://images.example/print.png']}).status_code,404)
        self.ok(self.request('GET','/tasks/2',2))
        self.assertEqual(self.request('PUT','/templates/1',3,json={'name':'XX'}).status_code,403)

    def test_designer_can_create_with_visible_template_and_own_resources(self):
        from tests.image_file_helpers import index_urls
        from app.credentials import encrypt_secret
        with self.sessions() as db:
            index_urls(db,1,['https://images.example/white.png','https://images.example/print.png'])
            db.add(UserAIProviderCredential(company_id=1,user_id=2,provider='grsai',secret_encrypted=encrypt_secret('test-key')))
            db.commit()
        payload={'template_id':1,'white_image_id':1,'creative_requirement':'保留印花',
                 'print_urls':['https://images.example/print.png']}
        created=self.ok(self.request('POST','/tasks',2,json=payload))
        self.assertEqual(created['items'][0]['created_by'],2)
        self.assertEqual(created['items'][0]['status'],'queued')
        self.assertEqual(self.request('POST','/tasks',3,json=payload).status_code,400)
        self.assertEqual(self.ok(self.request('GET','/ai-providers',2))[0]['credential_configured'],True)

    def test_design_members_group_creation_handover_and_role_transition(self):
        created=self.ok(self.request('POST','/members',json={'name':'新美工','email':'new@example.com',
            'password':'Password123','user_code':'DD','role':'designer'}))
        uid=created['id']
        self.assertEqual(created['role'],'designer')
        group=self.ok(self.request('POST','/design-groups',json={'name':'三组','leader_user_id':uid}))
        self.assertEqual(self.request('POST','/design-groups',json={'name':'重复组长','leader_user_id':uid}).status_code,400)
        self.assertEqual(self.request('POST','/design-groups',json={'name':'跨公司','leader_user_id':7}).status_code,400)
        self.assertEqual(self.request('PUT',f'/members/{uid}',json={'is_active':False}).status_code,400)
        self.assertEqual(self.request('PUT',f'/members/{uid}',json={'role':'member'}).status_code,400)
        self.assertEqual(self.request('PUT','/members/2',json={'group_id':123}).status_code,404)
        self.ok(self.request('PUT','/members/10',json={'role':'design_leader','design_group_id':group['id']}))
        with self.sessions() as db:
            self.assertEqual(db.get(User,uid).role,Role.DESIGNER)
            self.assertEqual(db.get(DesignGroup,group['id']).leader_user_id,10)
        self.ok(self.request('PUT',f'/members/{uid}',json={'role':'member','group_id':None}))
        self.assertEqual(self.request('PATCH',f"/design-groups/{group['id']}",8,json={'name':'跨公司'}).status_code,404)
        self.ok(self.request('DELETE',f"/design-groups/{group['id']}"))
        with self.sessions() as db:
            self.assertEqual(db.get(User,10).role,Role.DESIGNER)
            self.assertIsNone(db.get(User,10).design_group_id)
        self.assertEqual(self.request('POST','/members',json={'name':'无组','email':'invalid@example.com',
            'password':'Password123','user_code':'IV','role':'design_leader'}).status_code,400)
        self.ok(self.request('POST','/members',json={'name':'接任组长','email':'leader@example.com',
            'password':'Password123','user_code':'LD','role':'design_leader','design_group_id':1}))

    def test_quality_marking_single_batch_cancel_and_group_isolation(self):
        first={'task_id':2,'url':'https://images.example/2.png'}
        second={'task_id':2,'url':'https://images.example/2-second.png'}
        self.ok(self.request('POST','/tasks/result-reviews',3,json={'items':[first,second,first],'rejected':True}))
        detail=self.ok(self.request('GET','/tasks/2',3))
        self.assertEqual(detail['rejected_count'],2)
        self.assertEqual(detail['result_reviews'][0]['marked_by_name'],'成员3')
        for uid,task in ((2,2),(6,2),(3,4),(3,5),(8,2)):
            self.assertIn(self.request('POST','/tasks/result-reviews',uid,json={
                'items':[{'task_id':task,'url':f'https://images.example/{task}.png'}],'rejected':True}).status_code,(403,404))
        self.assertEqual(self.request('POST','/tasks/result-reviews',3,json={'items':[
            first,{'task_id':2,'url':'https://images.example/not-result.png'}],'rejected':False}).status_code,400)
        self.ok(self.request('POST','/tasks/result-reviews',1,json={'items':[first],'rejected':False}))
        self.assertEqual(self.ok(self.request('GET','/tasks/2',2))['rejected_count'],1)
        with self.sessions() as db:
            self.assertEqual(db.get(PodTask,2).status,TaskStatus.COMPLETED)
            self.assertIsNotNone(db.get(MaterialAsset,2))

    def download(self, uid=2, ids=None, sku=None, key='download-request'):
        return self.request('POST','/tasks/download',uid,json={'task_ids':ids or [2],
            'sku_query':sku,'request_key':key})

    def test_download_zip_only_adopted_images_and_per_member_permanent_dedup(self):
        with patch.object(design,'read_image_object',return_value=b'image-content'):
            for key in ('first','first','second'):
                response=self.download(key=key)
                self.assertEqual(response.status_code,200,response.text)
                with zipfile.ZipFile(BytesIO(response.content)) as output:
                    self.assertEqual(output.namelist(),['SKU2.png'])
                    self.assertEqual(output.read('SKU2.png'),b'image-content')
            self.assertEqual(self.download(3).status_code,200)
            self.assertEqual(self.download(2,[5]).status_code,404)
            self.assertEqual(self.download(2,[5],sku='SKU5').status_code,200)
            self.assertEqual(self.download(2,[7],sku='SKU7').status_code,404)
            self.assertEqual(self.download(2,[2,7],sku='SKU2\nSKU7').status_code,404)
            self.assertEqual(self.download(2,[2]*1000).status_code,200)
            self.assertEqual(self.download(2,[2]*1001).status_code,422)
        with self.sessions() as db:
            rows=db.scalars(select(CreativeImageEvent).where(CreativeImageEvent.kind=='download')).all()
            self.assertEqual({(r.user_id,r.sku) for r in rows},{(2,'SKU2'),(3,'SKU2'),(2,'SKU5')})
            self.assertEqual(len(rows),3)

    def test_failed_zip_and_empty_selection_never_record_downloads(self):
        with patch.object(design,'read_image_object',side_effect=StorageError('storage offline')):
            self.assertEqual(self.download().status_code,503)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CreativeImageEvent)),0)
            db.delete(db.get(MaterialAsset,2));db.commit()
        self.assertEqual(self.download().status_code,400)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CreativeImageEvent)),0)

    def test_download_preserves_unicode_user_codes_but_rejects_path_components(self):
        with self.sessions() as db:
            db.get(MaterialAsset,2).sku='Y1美工000001';db.commit()
        with patch.object(design,'read_image_object',return_value=b'image-content'):
            response=self.download()
            self.assertEqual(response.status_code,200)
            with zipfile.ZipFile(BytesIO(response.content)) as archive:
                self.assertEqual(archive.namelist(),['Y1美工000001.png'])
        with self.sessions() as db:
            db.get(MaterialAsset,2).sku='../escape';db.commit()
        self.assertEqual(self.download().status_code,400)

    def test_adoption_records_only_created_sku_images_and_survives_material_delete(self):
        with self.sessions() as db:
            file=db.get(ImageFile,2)
            kwargs=dict(image_file=file,template=db.get(ProductTemplate,1),owner=db.get(User,2),
                request_key='claim-once',force_create=True,source_type='ai_created',source_task_id=2)
            first=image_files.create_material(db,**kwargs)
            self.assertTrue(image_files.create_material(db,**kwargs)['replayed'])
            self.assertEqual(db.scalar(select(func.count()).select_from(CreativeImageEvent)),1)
            skipped=image_files.create_material(db,**{**kwargs,'request_key':'skip-duplicate','force_create':False})
            self.assertEqual(skipped['outcome'],'duplicate')
            db.delete(db.get(MaterialAsset,first['asset_id']));db.commit()
            self.assertEqual(db.scalar(select(func.count()).select_from(CreativeImageEvent)),1)
            image_files.create_material(db,**{**kwargs,'request_key':'non-sku','source_task_id':90})
            self.assertEqual(db.scalar(select(func.count()).select_from(CreativeImageEvent)),1)

    def test_statistics_hong_kong_boundaries_zero_days_disabled_members_and_scope(self):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls,tz=None):
                return datetime(2026,11,2,12,tzinfo=design.HK).astimezone(tz) if tz else datetime(2026,11,2,4)
        with self.sessions() as db:
            db.get(User,10).is_active=False
            for index,(uid,kind,at) in enumerate([(2,'adopt',datetime(2026,11,1,16)),
                    (2,'download',datetime(2026,11,1,15,59,59)),(10,'adopt',datetime(2026,11,2,1)),
                    (7,'adopt',datetime(2026,11,2,1)),(5,'adopt',datetime(2026,11,2,16))]):
                db.add(CreativeImageEvent(company_id=2 if uid==7 else 1,user_id=uid,user_name=f'成员{uid}',
                    kind=kind,sku=f'EV{index}',task_id=uid,asset_id=uid,occurred_at=at))
            db.commit()
        with patch.object(design,'datetime',FixedDatetime):
            today=self.ok(self.request('GET','/operation-statistics',params={'period':'today'}))
            self.assertEqual(today['summary'],{'adopted_count':2,'download_count':0})
            self.assertFalse(next(m for m in today['members'] if m['id']==10)['is_active'])
            yesterday=self.ok(self.request('GET','/operation-statistics',params={'period':'yesterday'}))
            self.assertEqual(yesterday['summary'],{'adopted_count':0,'download_count':1})
            for period in ('7','15','30'):
                data=self.ok(self.request('GET','/operation-statistics',params={'period':period,'member_id':2}))
                self.assertEqual(len(data['daily']),int(period))
                self.assertEqual(data['summary'],{'adopted_count':1,'download_count':1})
                self.assertEqual(data['daily'][0]['adopted_count'],0)
            self.assertEqual(self.request('GET','/operation-statistics',params={'member_id':7}).status_code,404)
            self.assertEqual(self.request('GET','/operation-statistics',params={'period':'365'}).status_code,422)
            self.assertEqual(self.request('GET','/operation-statistics',3).status_code,403)


class DesignMigrationTests(unittest.TestCase):
    def test_migration_backfills_existing_sku_adoptions_and_roundtrip(self):
        engine=create_engine('sqlite://')
        with engine.begin() as connection:
            config=alembic_config(connection)
            command.upgrade(config,'20261101_58')
            connection.execute(text("INSERT INTO companies (id,name,is_active,created_at) VALUES (1,'测试',1,CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO users (id,company_id,name,email,password_hash,role,is_active,created_at,token_version) "
                "VALUES (1,1,'历史用户','legacy@example.com','x','MEMBER',1,CURRENT_TIMESTAMP,0)"))
            for tid,kind in ((1,'sku_image'),(2,'carousel')):
                connection.execute(text("INSERT INTO pod_tasks (id,company_id,created_by,template_id,task_type,status,parameters,result_urls,result_map,submit_attempts,created_at,failure_ignored) "
                    "VALUES (:id,1,1,1,:kind,'COMPLETED','{}','[]','[]',0,CURRENT_TIMESTAMP,0)"),{'id':tid,'kind':kind})
                connection.execute(text("INSERT INTO material_assets (id,company_id,source_task_id,template_id,claimed_by,sku,name,url,created_at,usage_status) "
                    "VALUES (:id,1,:id,1,1,:sku,'历史素材','https://images.example/legacy.png','2026-11-01 16:00:00','unused')"),{'id':tid,'sku':f'LEGACY{tid}'})
            command.upgrade(config,'head')
            rows=connection.execute(text('SELECT sku,user_name,occurred_at FROM creative_image_events')).all()
            self.assertEqual([tuple(row) for row in rows],[('LEGACY1','历史用户','2026-11-01 16:00:00')])
            self.assertEqual(connection.execute(text('SELECT COUNT(*) FROM design_template_visibility')).scalar_one(),0)
            command.downgrade(config,'20261101_58')
            command.upgrade(config,'head')
        engine.dispose()

    def test_mysql_and_mariadb_enum_sql(self):
        for dialect in ('mysql','mariadb'):
            out=StringIO();config=alembic_config();config.output_buffer=out
            with patch('app.config.get_settings',return_value=SimpleNamespace(database_url=f'{dialect}+pymysql://test@localhost/test')):
                command.upgrade(config,'20261101_58:20261102_59',sql=True)
            self.assertIn("'DESIGNER','DESIGN_LEADER'",out.getvalue())
            self.assertIn('design_group_id',out.getvalue())
            self.assertIn('INSERT INTO creative_image_events',out.getvalue())
