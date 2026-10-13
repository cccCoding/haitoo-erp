"""仅显式启用时在本机测试 MySQL 上验证行锁，结束后清理本测试数据。"""
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import delete, select, func
from app import main
from app.database import SessionLocal, engine
from app.cross_company_collection import CollectionInput, PermissionInput, collect, set_permission
from app.models import (Company, MaterialAsset, ProductTemplate, Role, User,
    CrossCompanyCollectionBatch, CrossCompanyCollectionItem, CrossCompanyCollectionPermissionLog)


@unittest.skipUnless(os.environ.get('HAITOO_MYSQL_COLLECTION_TEST') == '1' and engine.dialect.name == 'mysql', '需显式开启本机 MySQL 测试')
class CollectionMySQLTests(unittest.TestCase):
    def setUp(self):
        tag=uuid4().hex
        with SessionLocal() as db:
            target=Company(name=f'采集并发测试目标-{tag}',cross_company_collect_enabled=True)
            source=Company(name=f'采集并发测试来源-{tag}')
            db.add_all([target,source]);db.flush()
            user=User(company_id=target.id,email=f'{tag}@collection-test.invalid',name='并发测试',role=Role.COMPANY_ADMIN,user_code='QA',password_hash='disabled')
            db.add(user);db.flush()
            template=ProductTemplate(company_id=target.id,name='QA1')
            asset=MaterialAsset(company_id=source.id,name='并发来源',url='https://img.example/concurrent',claimed_by=user.id)
            db.add_all([template,asset]);db.flush()
            self.target_id=target.id;self.source_id=source.id;self.user_id=user.id
            self.payload=CollectionInput(source_company_id=source.id,source_library='material',record_ids=[asset.id],template_id=template.id)
            db.commit()

    def tearDown(self):
        with SessionLocal() as db:
            ids=[self.target_id,self.source_id]
            for model in (CrossCompanyCollectionItem,CrossCompanyCollectionBatch,CrossCompanyCollectionPermissionLog,MaterialAsset,ProductTemplate,User):
                db.execute(delete(model).where(model.company_id.in_(ids)))
            db.execute(delete(Company).where(Company.id.in_(ids)));db.commit()

    def run_collect(self,key):
        with SessionLocal() as db:
            try:
                return collect(self.payload,key,user=db.get(User,self.user_id),db=db)
            except HTTPException as exc:
                return exc.status_code

    def test_concurrent_same_key_has_one_batch_and_one_asset(self):
        barrier=threading.Barrier(8)
        def request(_):
            barrier.wait(timeout=10)
            return self.run_collect('same-request')
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(request,range(8)))
        self.assertTrue(all(result==results[0] for result in results),results)
        self.assertEqual(results[0]['collected'],1)
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CrossCompanyCollectionBatch).where(CrossCompanyCollectionBatch.company_id==self.target_id)),1)
            self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset).where(MaterialAsset.company_id==self.target_id)),1)

    def test_concurrent_different_keys_require_explicit_recollection(self):
        barrier=threading.Barrier(2)
        def request(key):
            barrier.wait(timeout=10)
            return self.run_collect(key)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(request,['first','second']))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertIn(409,results)

    def test_revocation_waits_for_collection_and_blocks_next_request(self):
        entered=threading.Event();release=threading.Event();revoke_started=threading.Event()
        original=main.add_material_asset_with_sku
        def held(*args,**kwargs):
            entered.set()
            if not release.wait(timeout=10): raise RuntimeError('测试同步超时')
            return original(*args,**kwargs)
        def revoke():
            revoke_started.set()
            with SessionLocal() as db:
                return set_permission(self.target_id,PermissionInput(enabled=False),user=db.get(User,self.user_id),db=db)
        with patch.object(main,'add_material_asset_with_sku',side_effect=held), ThreadPoolExecutor(max_workers=2) as pool:
            collection=pool.submit(self.run_collect,'in-flight')
            self.assertTrue(entered.wait(timeout=5))
            revocation=pool.submit(revoke)
            self.assertTrue(revoke_started.wait(timeout=5))
            try:
                self.assertFalse(revocation.done())
            finally:
                release.set()
            self.assertEqual(collection.result(timeout=10)['collected'],1)
            self.assertFalse(revocation.result(timeout=10)['enabled'])
        self.assertEqual(self.run_collect('after-revocation'),403)

    def test_request_waiting_before_company_lock_observes_revocation(self):
        from app import cross_company_collection as service
        ready=threading.Event();release=threading.Event()
        original=service.authorized_company
        def paused(user,db,*,lock=False):
            result=original(user,db,lock=lock)
            if not lock:
                ready.set()
                if not release.wait(timeout=10): raise RuntimeError('测试同步超时')
            return result
        with patch.object(service,'authorized_company',side_effect=paused), ThreadPoolExecutor(max_workers=1) as pool:
            request=pool.submit(self.run_collect,'waiting-before-lock')
            self.assertTrue(ready.wait(timeout=5))
            try:
                with SessionLocal() as db:
                    set_permission(self.target_id,PermissionInput(enabled=False),user=db.get(User,self.user_id),db=db)
            finally:
                release.set()
            self.assertEqual(request.result(timeout=10),403)


if __name__ == '__main__':
    unittest.main()
