"""永久风格、入库、权限、批量事务与历史迁移回归。"""
import json
import unittest
from unittest.mock import patch
from alembic import command
from sqlalchemy import create_engine, event, inspect, select, text
from app import main
from app.image_files import file_ticket
from app.models import (AIProviderSetting, MaterialAsset, MaterialStyle, PodTask, ProductTemplate,
    TaskStatus, User, UserAIProviderCredential, UserTemplatePrompt, UserTemplateWhiteImage)
from app.schema_version import alembic_config
from tests.image_file_helpers import index_urls
from tests.test_supply_catalog import SupplyFixture


class MaterialStyleTests(SupplyFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.app.include_router(main.app.router)
        with self.sessions() as db:
            db.get(ProductTemplate, 1).name='Y1'
            db.get(User, 2).user_code='AA'
            self.urls=[f'https://img.example/style-new-{i}.png' for i in range(8)]
            files=index_urls(db,1,self.urls)
            self.file_tokens=[file_ticket(db.get(User,2),image) for image in files]
            db.commit()
        self.white=self.create_white()
        self.style_id=self.white['style_id']

    def create_white(self,name='正面',uid=2):
        response=self.request('POST','/user-template-white-images',uid=uid,
            json={'template_id':1,'name':name,'image_url':self.urls[0]})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def styles(self,uid=2,**params):
        response=self.request('GET','/material-styles',uid=uid,params=params)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['items']

    def upload(self,index=1,key='style-upload-001',style_id=None,force=False):
        response=self.request('POST','/material-assets/commit',uid=2,json={'template_id':1,'items':[
            {'file_token':self.file_tokens[index],'request_key':key,'style_id':style_id,'force_create':force}]})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['items'][0]

    def set_style(self,ids,style_id,uid=2):
        return self.request('PATCH','/material-assets/style',uid=uid,
            json={'material_asset_ids':ids,'style_id':style_id})

    def test_shared_styles_have_stable_identity_and_private_resources_stay_private(self):
        self.assertEqual(self.styles(uid=3)[0]['id'],self.style_id)
        self.assertNotIn('image_url',self.styles()[0])
        self.assertEqual(self.styles(uid=2)[0]['white_image_url'],self.urls[0])
        self.assertEqual(self.styles(uid=1)[0]['white_image_url'],self.urls[0])
        self.assertIsNone(self.styles(uid=3)[0]['white_image_url'])
        self.assertEqual(self.styles(template_id=2),[])
        self.assertEqual(self.styles(search='不存在'),[])
        self.assertEqual(self.styles(uid=5),[])
        self.assertEqual(self.request('GET','/material-styles',uid=4).status_code,403)
        self.assertEqual(self.request('GET','/user-template-resources',uid=3,params={'user_id':2}).status_code,403)
        other_style_id=self.create_white(uid=3)['style_id']
        self.assertNotEqual(other_style_id,self.style_id)
        self.assertEqual(next(style for style in self.styles(uid=3) if style['id']==other_style_id)['white_image_url'],self.urls[0])
        self.assertIsNone(next(style for style in self.styles(uid=2) if style['id']==other_style_id)['white_image_url'])
        response=self.request('PUT',f"/user-template-white-images/{self.white['id']}",uid=2,json={'name':'新风格'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.styles(search='新风格')[0]['id'],self.style_id)
        for method,path in [('DELETE',f'/material-styles/{self.style_id}'),
                            ('PATCH',f'/material-styles/{self.style_id}'),('POST','/material-styles')]:
            self.assertIn(self.request(method,path,uid=1,json={'name':'x'}).status_code,(404,405))
        self.assertEqual(len(self.styles()),2)

    def test_white_update_rejects_image_and_template_changes_and_creation_is_atomic(self):
        for payload in ({'name':'新名','image_url':self.urls[1]},{'name':'新名','template_id':2},
                        {'name':'   '},{'name':None},{}):
            self.assertEqual(self.request('PUT',f"/user-template-white-images/{self.white['id']}",
                uid=2,json=payload).status_code,422)
        self.assertEqual(self.request('PUT',f"/user-template-white-images/{self.white['id']}",
            uid=3,json={'name':'他人修改'}).status_code,404)
        duplicate=self.request('POST','/user-template-white-images',uid=2,
            json={'template_id':1,'name':'正面','image_url':self.urls[1]})
        self.assertEqual(duplicate.status_code,400)
        self.assertEqual(len(self.styles()),1)
        self.assertEqual(self.styles()[0]['name'],'正面')

    def test_company_resource_scope_requires_admin_and_isolates_companies(self):
        admin_white=self.create_white(name='管理员白底图',uid=1)
        other_white=self.create_white(name='成员白底图',uid=3)
        for uid in (1,2,3):
            response=self.request('POST','/user-template-prompts',uid=uid,
                json={'template_id':1,'name':f'要求{uid}','content':f'成员{uid}的内容'})
            self.assertEqual(response.status_code,200,response.text)
        with self.sessions() as db:
            db.add(UserTemplateWhiteImage(company_id=2,user_id=5,template_id=2,name='其他公司图片',
                image_url='https://img.example/foreign-white.png'))
            db.add(UserTemplatePrompt(company_id=2,user_id=5,template_id=2,name='其他公司要求',content='private'))
            db.commit()
        response=self.request('GET','/user-template-resources',uid=1,params={'scope':'company'})
        self.assertEqual(response.status_code,200,response.text)
        data=response.json()
        self.assertIsNone(data['user_id'])
        self.assertEqual(data['scope'],'company')
        self.assertEqual({item['id'] for item in data['white_images']},
            {self.white['id'],admin_white['id'],other_white['id']})
        self.assertEqual({item['user_id'] for item in data['prompts']},{1,2,3})
        self.assertTrue(all(item['company_id']==1 for item in data['white_images']+data['prompts']))
        # AI 创作继续默认读取本人；指定成员仍使用现有的管理员代管理权限。
        for uid in (1,2,3):
            own=self.request('GET','/user-template-resources',uid=uid).json()
            self.assertEqual({item['user_id'] for item in own['white_images']+own['prompts']},{uid})
        selected=self.request('GET','/user-template-resources',uid=1,params={'user_id':3}).json()
        self.assertEqual({item['user_id'] for item in selected['white_images']+selected['prompts']},{3})
        for uid in (2,3):
            self.assertEqual(self.request('GET','/user-template-resources',uid=uid,
                params={'scope':'company'}).status_code,403)
        foreign=self.request('GET','/user-template-resources',uid=5,params={'scope':'company'}).json()
        self.assertEqual({item['company_id'] for item in foreign['white_images']+foreign['prompts']},{2})
        self.assertEqual(self.request('GET','/user-template-resources',uid=1,
            params={'scope':'company','user_id':3}).status_code,400)
        self.assertEqual(self.request('GET','/user-template-resources',uid=1,
            params={'scope':'company','template_id':2}).status_code,404)
        self.assertEqual(self.request('GET','/user-template-resources',uid=1,
            params={'scope':'other'}).status_code,422)

    def test_deleting_white_keeps_assets_pending_claims_and_manual_style_selection(self):
        asset_id=self.upload(style_id=self.style_id)['asset_id']
        with self.sessions() as db:
            db.add(PodTask(id=100,company_id=1,template_id=1,created_by=2,status=TaskStatus.AWAITING_SELECTION,
                parameters={'style_id':self.style_id,'white_image_id':self.white['id']},result_urls=self.urls[2:4]))
            db.commit()
        response=self.request('DELETE',f"/user-template-white-images/{self.white['id']}",uid=2)
        self.assertEqual(response.status_code,200,response.text)
        with self.sessions() as db:
            retained_white=db.get(UserTemplateWhiteImage,self.white['id'])
            self.assertIsNotNone(retained_white)
            self.assertIsNotNone(retained_white.deleted_at)
            self.assertEqual(retained_white.image_url,self.urls[0])
        style=self.styles()[0]
        self.assertFalse(style['source_exists'])
        self.assertIsNone(style['white_image_url'])
        self.assertEqual((style['material_count'],style['name']),(1,'正面'))
        for index in (2,3):
            result=self.request('POST','/tasks/100/claim-materials',uid=2,
                json={'request_key':f'style-claim-{index}','result_urls':[self.urls[index]]})
            self.assertEqual(result.status_code,200,result.text)
            with self.sessions() as db:
                self.assertEqual(db.get(MaterialAsset,result.json()['items'][0]['asset_id']).style_id,self.style_id)
        self.upload(index=4,key='after-white-delete',style_id=self.style_id)
        imported=self.request('POST','/material-assets/import-confirm',uid=2,json={'template_id':1,
            'file_token':self.file_tokens[5],'request_key':'import-after-delete','style_id':self.style_id})
        self.assertEqual(imported.status_code,200,imported.text)
        with self.sessions() as db:
            self.assertEqual(db.get(MaterialAsset,asset_id).style_id,self.style_id)
            self.assertEqual(db.get(MaterialAsset,imported.json()['items'][0]['asset_id']).style_id,self.style_id)
        self.assertEqual(self.set_style([1],self.style_id).status_code,200)
        self.assertIn(self.request('DELETE',f'/material-styles/{self.style_id}').status_code,(404,405))
        replacement=self.create_white(name='新增白底图')
        self.assertNotEqual(replacement['id'],self.white['id'])
        self.assertNotEqual(replacement['style_id'],self.style_id)
        retained=next(style for style in self.styles() if style['id']==self.style_id)
        self.assertFalse(retained['source_exists'])
        self.assertEqual(retained['name'],'正面')

    def test_soft_deleted_white_is_read_only_and_filtered_with_permissions(self):
        from app.schemas import PodTaskCreate
        self.request('POST','/user-template-prompts',uid=2,
            json={'template_id':1,'name':'保留要求','content':'自然光'})
        active=self.create_white(name='有效白底图')
        endpoint=f"/user-template-white-images/{self.white['id']}"
        for uid in (3,5):
            self.assertEqual(self.request('DELETE',endpoint,uid=uid).status_code,404)
        # 管理员可软删除成员资源；重复删除不改变首次删除时间。
        self.assertEqual(self.request('DELETE',endpoint,uid=1).status_code,200)
        deleted=self.request('GET','/user-template-resources',uid=2,
            params={'white_image_status':'deleted'}).json()
        self.assertEqual([item['id'] for item in deleted['white_images']],[self.white['id']])
        self.assertEqual(deleted['prompts'][0]['name'],'保留要求')
        deleted_at=deleted['white_images'][0]['deleted_at']
        self.assertEqual(self.request('DELETE',endpoint,uid=2).status_code,200)
        repeated=self.request('GET','/user-template-resources',uid=2,
            params={'white_image_status':'deleted'}).json()['white_images'][0]
        self.assertEqual(repeated['deleted_at'],deleted_at)
        own=self.request('GET','/user-template-resources',uid=2).json()
        self.assertEqual([item['id'] for item in own['white_images']],[active['id']])
        for uid in (3,5):
            self.assertEqual(self.request('GET','/user-template-resources',uid=uid,
                params={'white_image_status':'deleted'}).json()['white_images'],[])
        admin=self.request('GET','/user-template-resources',uid=1,
            params={'scope':'company','white_image_status':'deleted'}).json()
        self.assertEqual([item['id'] for item in admin['white_images']],[self.white['id']])
        self.assertEqual(self.request('PUT',endpoint,uid=2,json={'name':'不能改名'}).status_code,400)
        self.assertEqual(self.styles(search='正面')[0]['name'],'正面')
        self.assertEqual(self.request('GET','/user-template-resources',uid=2,
            params={'white_image_status':'all'}).status_code,422)
        with self.sessions() as db:
            with self.assertRaisesRegex(Exception,'自己的产品白底图'):
                main.create_task(PodTaskCreate(template_id=1,white_image_id=self.white['id'],
                    creative_requirement='test',print_urls=self.urls[1:2]),user=db.get(User,2),db=db)

    def test_deleted_white_does_not_consume_active_image_limit(self):
        from datetime import datetime
        with self.sessions() as db:
            db.add_all([UserTemplateWhiteImage(company_id=1,user_id=2,template_id=1,
                name=f'已删除{i}',image_url=self.urls[0],deleted_at=datetime.utcnow()) for i in range(50)])
            db.commit()
        self.create_white(name='额度内新增')

    def test_upload_import_replays_duplicates_and_shared_style_validation(self):
        created=self.upload(style_id=self.style_id)
        self.assertTrue(self.upload()['replayed'])
        self.assertEqual(self.upload(key='style-duplicate-001')['outcome'],'duplicate')
        forced=self.upload(key='style-force-001',force=True)
        imported=self.request('POST','/material-assets/import-confirm',uid=2,json={'template_id':1,
            'urls':[self.urls[2]],'style_id':self.style_id,'request_key':'style-import-001'})
        self.assertEqual(imported.status_code,200,imported.text)
        with self.sessions() as db:
            self.assertEqual(db.get(MaterialAsset,created['asset_id']).style_id,self.style_id)
            self.assertIsNone(db.get(MaterialAsset,forced['asset_id']).style_id)
            self.assertEqual(db.get(MaterialAsset,imported.json()['items'][0]['asset_id']).style_id,self.style_id)
            db.add_all([ProductTemplate(id=3,company_id=1,name='Y2'),
                MaterialStyle(company_id=2,template_id=2,name='Foreign',created_by=5,source_white_image_id=999),
                MaterialStyle(company_id=1,template_id=3,name='Other',created_by=2,source_white_image_id=998)])
            db.commit()
            invalid_ids=[9999,*db.scalars(select(MaterialStyle.id).where(MaterialStyle.source_white_image_id.in_([998,999])))]
        for identity in invalid_ids:
            self.assertEqual(self.upload(index=3,key=f'invalid-style-{identity}',style_id=identity)['outcome'],'error')
        shared=self.create_white(name='共享风格',uid=3)
        self.assertEqual(self.upload(index=6,key='shared-style-001',style_id=shared['style_id'])['outcome'],'created')

    def test_batch_permissions_atomicity_mixed_templates_and_filtering(self):
        self.assertEqual(self.set_style([1,2,2],self.style_id).json()['count'],2)
        for uid,ids,status in ((3,[1],404),(5,[1],404),(4,[1],403),(2,[2,99999],404),(2,[2,99],404),(1,[1],200)):
            self.assertEqual(self.set_style(ids,None,uid).status_code,status)
        with self.sessions() as db:
            self.assertEqual(db.get(MaterialAsset,2).style_id,self.style_id)
            db.add(ProductTemplate(id=3,company_id=1,name='Y2'))
            db.get(MaterialAsset,3).template_id=3
            db.get(MaterialAsset,3).style_id=self.style_id
            db.commit()
        self.assertEqual(self.set_style([2,3],self.style_id).status_code,400)
        self.assertEqual(self.set_style([2],99999).status_code,400)
        self.assertEqual(self.set_style([2,3],None).status_code,200)
        self.set_style([1,2],self.style_id)
        response=self.request('GET','/material-assets',uid=2,params={'style_id':self.style_id})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual({row['id'] for row in response.json()['items']},{1,2})
        self.assertEqual(response.json()['items'][0]['style_name'],'正面')
        rows=self.request('GET','/material-assets',uid=2,params={'style_id':0,'page_size':1000}).json()['items']
        self.assertTrue(all(row['style_id'] is None for row in rows))
        for ids in ([],[0],[-1],list(range(1,2002))):
            self.assertEqual(self.set_style(ids,None).status_code,422)
        for identity in (0,-1):
            self.assertEqual(self.set_style([1],identity).status_code,422)
        self.assertEqual(self.request('PATCH','/material-assets/style',uid=2,json={'material_asset_ids':[1]}).status_code,422)

    def test_2000_updates_commit_once_and_preserve_unrelated_fields(self):
        ids=list(range(1000,3000))
        with self.sessions() as db:
            db.add_all(MaterialAsset(id=i,company_id=1,template_id=1,claimed_by=2,name='Batch',url=self.urls[0],
                is_infringing=True,usage_status='used') for i in ids)
            db.commit()
        commits=[]
        def committed(session): commits.append(session)
        event.listen(self.sessions.class_,'after_commit',committed)
        try: response=self.set_style(ids,self.style_id)
        finally: event.remove(self.sessions.class_,'after_commit',committed)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['count'],2000)
        self.assertEqual(len(commits),1)
        listing=self.request('GET','/material-assets',uid=2,
            params={'page_size':2000,'usage_status':'all','style_id':self.style_id})
        self.assertEqual(listing.status_code,200,listing.text)
        self.assertEqual(len(listing.json()['items']),2000)
        with self.sessions() as db:
            for asset in db.scalars(select(MaterialAsset).where(MaterialAsset.id.in_(ids))):
                self.assertEqual(asset.style_id,self.style_id)
                self.assertTrue(asset.is_infringing)
                self.assertEqual(asset.usage_status,'used')

    def test_template_reassignment_clears_only_incompatible_style(self):
        self.set_style([1,2],self.style_id)
        response=self.request('POST','/product-library/templates/batch',json={'material_asset_ids':[1],'template_id':1})
        self.assertEqual(response.status_code,200,response.text)
        with self.sessions() as db:
            self.assertEqual(db.get(MaterialAsset,1).style_id,self.style_id)
            db.add(ProductTemplate(id=3,company_id=1,name='Y2')); db.commit()
        response=self.request('POST','/product-library/templates/batch',json={'material_asset_ids':[1],'template_id':3})
        self.assertEqual(response.status_code,200,response.text)
        with self.sessions() as db:
            self.assertIsNone(db.get(MaterialAsset,1).style_id)
            self.assertEqual(db.get(MaterialAsset,2).style_id,self.style_id)

    def test_ai_submission_snapshots_style_on_every_chunk(self):
        from app.schemas import PodTaskCreate
        with self.sessions() as db:
            db.add(AIProviderSetting(provider='grsai',display_name='Grsai',model='nano',credential_provider='grsai',
                enabled=True,is_default=True,images_per_task=1))
            db.add(UserAIProviderCredential(company_id=1,user_id=2,provider='grsai',secret_encrypted='unused'))
            db.commit()
            with patch.object(main,'registered_image_url',return_value=True):
                result=main.create_task(PodTaskCreate(template_id=1,white_image_id=self.white['id'],
                    creative_requirement='test',print_urls=self.urls[1:3]),user=db.get(User,2),db=db)
            self.assertEqual(len(result['items']),2)
            for item in result['items']:
                self.assertEqual(db.get(PodTask,item['id']).parameters['style_id'],self.style_id)


class MaterialStyleMigrationTests(unittest.TestCase):
    def test_soft_delete_migration_preserves_sources_and_style_assignments(self):
        engine=create_engine('sqlite://'); self.addCleanup(engine.dispose)
        with engine.begin() as db:
            config=alembic_config(db); command.upgrade(config,'20261020_42')
            db.execute(text("""INSERT INTO user_template_white_images
                (id,company_id,user_id,template_id,name,image_url,created_at,updated_at)
                VALUES (1,1,2,1,'Front','https://img.example/white.png',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""))
            db.execute(text("""INSERT INTO material_styles
                (id,company_id,template_id,source_white_image_id,name,created_by,created_at,updated_at)
                VALUES (1,1,1,1,'Front',2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""))
            db.execute(MaterialAsset.__table__.insert().values(id=1,company_id=1,template_id=1,
                claimed_by=2,url='https://img.example/sku.png',name='SKU',style_id=1))
            command.upgrade(config,'head')
            self.assertIsNone(db.scalar(text('SELECT deleted_at FROM user_template_white_images WHERE id=1')))
            db.execute(text('UPDATE user_template_white_images SET deleted_at=CURRENT_TIMESTAMP WHERE id=1'))
            command.downgrade(config,'20261020_42')
            self.assertEqual(db.scalar(text('SELECT image_url FROM user_template_white_images WHERE id=1')),
                'https://img.example/white.png')
            self.assertEqual(db.scalar(text('SELECT style_id FROM material_assets WHERE id=1')),1)
            self.assertEqual(db.scalar(text('SELECT source_white_image_id FROM material_styles WHERE id=1')),1)
            command.upgrade(config,'head')
            self.assertIsNone(db.scalar(text('SELECT deleted_at FROM user_template_white_images WHERE id=1')))

    def test_backfill_and_downgrade_preserve_records_and_skip_unconfirmed_sources(self):
        engine=create_engine('sqlite://'); self.addCleanup(engine.dispose)
        with engine.begin() as db:
            config=alembic_config(db); command.upgrade(config,'20261020_41')
            db.execute(UserTemplateWhiteImage.__table__.insert().values(id=1,company_id=1,user_id=2,
                template_id=1,name='Front',image_url='https://img.example/current.png'))
            params={'white_image_id':1,'white_image_url':'https://img.example/current.png','creative_requirement':'keep'}
            for identity,overrides in ((1,{}),(2,{'white_image_url':'https://img.example/replaced.png'}),
                                      (3,{'white_image_id':999}),(4,{'white_image_id':'1'})):
                db.execute(PodTask.__table__.insert().values(id=identity,company_id=1,template_id=1,created_by=2,
                    parameters={**params,**overrides},task_type='sku_image'))
                db.execute(MaterialAsset.__table__.insert().values(id=identity,company_id=1,template_id=1,claimed_by=2,
                    url='https://img.example/sku.png',name='AI',source_task_id=identity))
            for identity,company,template,creator in ((5,2,1,2),(6,1,2,2),(7,1,1,3)):
                db.execute(PodTask.__table__.insert().values(id=identity,company_id=company,template_id=template,
                    created_by=creator,parameters=params,task_type='sku_image'))
            for identity,company,template,creator in ((8,2,1,2),(9,1,2,2),(10,1,1,3)):
                db.execute(MaterialAsset.__table__.insert().values(id=identity,company_id=company,template_id=template,
                    claimed_by=creator,url='https://img.example/sku.png',name='AI',source_task_id=1))
            for identity in range(20,525):
                db.execute(PodTask.__table__.insert().values(id=identity,company_id=1,template_id=1,created_by=2,
                    parameters=params,task_type='sku_image'))
            command.upgrade(config,'head')
            self.assertIn('AUTOINCREMENT',db.scalar(text(
                "SELECT sql FROM sqlite_master WHERE name='user_template_white_images'")))
            style_id=db.scalar(text('SELECT id FROM material_styles'))
            rows=dict(db.execute(text('SELECT id,style_id FROM material_assets')).all())
            self.assertEqual(rows[1],style_id)
            self.assertTrue(all(style is None for identity,style in rows.items() if identity!=1))
            for identity in (1,524):
                self.assertEqual(json.loads(db.scalar(text('SELECT parameters FROM pod_tasks WHERE id=:id'),
                    {'id':identity}))['style_id'],style_id)
            for identity in range(2,8):
                self.assertNotIn('style_id',json.loads(db.scalar(text('SELECT parameters FROM pod_tasks WHERE id=:id'),{'id':identity})))
            command.downgrade(config,'20261020_41')
            self.assertNotIn('material_styles',inspect(db).get_table_names())
            self.assertNotIn('style_id',{col['name'] for col in inspect(db).get_columns('material_assets')})
            self.assertEqual(db.scalar(text('SELECT count(*) FROM material_assets')),7)
            self.assertEqual(json.loads(db.scalar(text('SELECT parameters FROM pod_tasks WHERE id=524'))),params)
            command.upgrade(config,'head')
            self.assertEqual(db.scalar(text('SELECT count(*) FROM material_styles')),1)
