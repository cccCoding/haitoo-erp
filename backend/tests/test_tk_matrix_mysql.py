"""仅专用临时MySQL库：新旧领取竞争、唯一约束及迁移兼容。"""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
from threading import Barrier
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import create_engine,select,text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from app.models import Company,User,Role,HubAgent,HubUploadTask,HubRuntimeLock
from app.hub_v5.models import *
from app.hub_v5 import service as s
from app.hub import claim as legacy_claim
from app.schemas import HubTaskClaimInput
from app.db_migrate import upgrade_database


def test_url():
    name=os.getenv('MATRIX_VALIDATION_DATABASE','')
    if not name.startswith('haitoo_matrix_validation_'):raise RuntimeError('仅允许专用矩阵验证数据库')
    url=make_url(os.environ['DATABASE_URL'])
    if url.get_backend_name() not in {'mysql','mariadb'}:raise RuntimeError('必须使用MySQL')
    return url.set(database=name)


@unittest.skipUnless(os.getenv('MATRIX_VALIDATION_DATABASE'),'需要专用MySQL验证库')
class MatrixMySQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=create_engine(test_url(),pool_pre_ping=True)
        cls.sessions=sessionmaker(bind=cls.engine)
        with cls.engine.begin() as connection:upgrade_database(connection)

    @classmethod
    def tearDownClass(cls):cls.engine.dispose()

    def setUp(self):
        with self.sessions() as db:
            company=Company(name='matrix-'+uuid4().hex);db.add(company);db.flush();self.cid=company.id
            owner=User(company_id=self.cid,name='owner',email=uuid4().hex+'@example.test',role=Role.COMPANY_ADMIN,password_hash='test')
            db.add(owner);db.flush();self.uid=owner.id
            agents=[]
            for _ in range(2):
                a=HubAgent(company_id=self.cid,user_id=owner.id,name=uuid4().hex,platform='macos',token_hash=uuid4().hex*2,last_seen_at=datetime.utcnow())
                db.add(a);db.flush();agents.append(a.id)
                db.add(MatrixDevice(agent_id=a.id,install_uuid=str(uuid4()),version='5.0.0',hub_identity='team',hub_connected=True,capabilities={'shop.collect':['MY']}))
            self.agents=agents
            db.add(MatrixCompany(company_id=self.cid,enabled=True,listing_enabled=True))
            env=MatrixEnvironment(company_id=self.cid,hub_identity='team',container_code='same-env',name='店铺',observed_site='MY')
            db.add(env);db.flush();self.env=env.id
            self.items=[]
            for aid in agents:
                db.add(MatrixAccess(agent_id=aid,environment_id=env.id,available=True,seen_at=datetime.utcnow()))
                run=MatrixRun(company_id=self.cid,owner_id=owner.id,agent_id=aid,plan_id=1,plan_revision=1,idempotency_key=uuid4().hex,request_hash='a'*64,
                    frozen={'config':{'tasks':['shop.collect']},'environments':[{'id':env.id,'name':env.name,'site':'MY','revision':1,'hub_identity':'team','container_code':'same-env'}]})
                db.add(run);db.flush();item=MatrixItem(company_id=self.cid,run_id=run.id,agent_id=aid,environment_id=env.id);db.add(item);db.flush();self.items.append(item.id)
            task=HubUploadTask(company_id=self.cid,created_by=owner.id,template_id=1,template_name='模板',draft_ids=[],export_filename='fixed.xlsx',export_blob=b'fixed',export_expires_at=datetime.utcnow()+timedelta(days=1))
            db.add(task);db.flush();self.legacy=task.id;db.commit()

    def compete(self,left,right):
        barrier=Barrier(2)
        def call(callback):
            with self.sessions() as db:
                barrier.wait()
                try:return callback(db)
                except HTTPException as e:db.rollback();return e.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(call,(left,right)))

    def test_two_devices_only_one_matrix_claim(self):
        def contender(index):
            def callback(db):
                s.claim(db,db.get(HubAgent,self.agents[index]),self.items[index]);return 'claimed'
            return callback
        result=self.compete(contender(0),contender(1))
        self.assertEqual(result.count('claimed'),1,result)
        with self.sessions() as db:self.assertEqual(len(db.scalars(select(MatrixItem).where(MatrixItem.company_id==self.cid,MatrixItem.status=='running')).all()),1)

    def test_legacy_and_matrix_share_guard(self):
        def legacy(db):
            r=legacy_claim(db,db.get(HubAgent,self.agents[1]),HubTaskClaimInput(task_id=self.legacy,container_code='same-env',environment_name='店铺',confirmed_local=True))
            return 'claimed' if r['task'] else 'blocked'
        def matrix(db):s.claim(db,db.get(HubAgent,self.agents[0]),self.items[0]);return 'claimed'
        result=self.compete(legacy,matrix)
        self.assertEqual(result.count('claimed'),1,result)
        with self.sessions() as db:
            row=db.scalar(select(HubRuntimeLock).where(HubRuntimeLock.company_id==self.cid))
            self.assertFalse(row.task_id and row.matrix_item_id)

    def test_combination_unique_even_without_coordinator(self):
        def insert(db):
            db.add(MatrixAllocation(company_id=self.cid,shop_id=self.env,combination_hash='a'*64,item_id=self.items[0],payload={}))
            try:db.commit();return 'inserted'
            except IntegrityError:db.rollback();return 'duplicate'
        self.assertCountEqual(self.compete(insert,insert),['inserted','duplicate'])

    def test_ready_filter_json_capability(self):
        with self.sessions() as db:
            actor=db.get(User,self.uid)
            self.assertEqual([e.id for e in db.scalars(s.environment_query(db,actor,{'executable':'ready'}))],[self.env])
            for aid in self.agents:db.get(MatrixDevice,aid).capabilities={}
            db.commit()
            self.assertEqual(list(db.scalars(s.environment_query(db,actor,{'executable':'ready'}))),[])
            self.assertEqual([e.id for e in db.scalars(s.environment_query(db,actor,{'executable':'blocked'}))],[self.env])
