"""仅在 haitoo_image_validation_ 前缀的独立 MySQL 数据库执行。"""
from concurrent.futures import ThreadPoolExecutor
import os
import threading
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, delete, func, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db_migrate import upgrade_database
from app.image_files import create_material, register_bytes
from app.models import Company, ImageAddress, ImageFile, MaterialAsset, ProductTemplate, Role, User
from tests.test_image_files import picture


@unittest.skipUnless(os.getenv("IMAGE_FILE_TEST_DATABASE"), "需要独立 MySQL 测试数据库")
class ImageFileMysqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name=os.environ["IMAGE_FILE_TEST_DATABASE"]
        if not name.startswith("haitoo_image_validation_") or not name.replace("_","").isalnum():
            raise RuntimeError("拒绝操作非专用测试数据库")
        url=make_url(get_settings().database_url)
        if url.get_backend_name() not in {"mysql","mariadb"} or url.database==name:
            raise RuntimeError("必须从业务配置派生独立的 MySQL 测试库连接")
        cls.engine=create_engine(url.set(database=name),pool_pre_ping=True)
        cls.sessions=sessionmaker(bind=cls.engine)
        with cls.engine.begin() as connection:
            upgrade_database(connection)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.sessions() as db:
            for model in (MaterialAsset,ImageAddress,ImageFile,User,ProductTemplate,Company):
                db.execute(delete(model))
            db.add_all([Company(id=1,name="Test"),
                User(id=1,company_id=1,email="a@test.example",name="A",user_code="AA",password_hash="x",role=Role.MEMBER),
                ProductTemplate(id=1,company_id=1,name="Y1"),
                ImageFile(id=1,company_id=1,sha256="a"*64,object_key="test/a.png",url="https://images.example/a.png",mime_type="image/png",size_bytes=100)])
            db.commit()

    def compete(self,force,key_factory):
        barrier=threading.Barrier(6)
        def submit(index):
            with self.sessions() as db:
                file=db.get(ImageFile,1); owner=db.get(User,1); template=db.get(ProductTemplate,1)
                barrier.wait(timeout=15)
                return create_material(db,image_file=file,template=template,owner=owner,request_key=key_factory(index),force_create=force)
        with ThreadPoolExecutor(max_workers=6) as executor:
            return list(executor.map(submit,range(6)))

    def test_migration_removes_health_table_and_keeps_unique_indexes(self):
        self.assertNotIn("supply_image_health",inspect(self.engine).get_table_names())
        indexes=inspect(self.engine).get_unique_constraints("image_files")
        self.assertTrue(any(set(row["column_names"])=={"company_id","sha256"} for row in indexes))

    def test_concurrent_default_creates_one_material(self):
        result=self.compete(False,lambda index:f"default-{index}")
        self.assertEqual(sum(row["outcome"]=="created" for row in result),1)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset)),1)

    def test_concurrent_forced_retry_is_idempotent_and_distinct_intents_create(self):
        result=self.compete(True,lambda _:"same-force-key")
        self.assertEqual(len({row["asset_id"] for row in result}),1)
        self.compete(True,lambda index:f"new-force-{index}")
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset)),7)
            self.assertEqual(len(set(db.scalars(select(MaterialAsset.sku)))),7)

    def test_distinct_images_can_create_concurrently_without_gap_lock_deadlock(self):
        with self.sessions() as db:
            for identity in range(2,7):
                db.add(ImageFile(id=identity,company_id=1,sha256=str(identity)*64,object_key=f"test/{identity}.png",
                    url=f"https://images.example/{identity}.png",mime_type="image/png",size_bytes=100))
            db.commit()
        barrier=threading.Barrier(6)
        def submit(identity):
            with self.sessions() as db:
                file=db.get(ImageFile,identity); template=db.get(ProductTemplate,1); owner=db.get(User,1)
                barrier.wait(timeout=15)
                return create_material(db,image_file=file,template=template,owner=owner,request_key=f"different-{identity}")
        with ThreadPoolExecutor(max_workers=6) as executor:
            result=list(executor.map(submit,range(1,7)))
        self.assertTrue(all(row["outcome"]=="created" for row in result))

    def test_existing_transaction_uses_current_read_after_other_creator_commits(self):
        with self.sessions() as stale:
            self.assertEqual(stale.scalar(select(func.count()).select_from(MaterialAsset)),0)
            with self.sessions() as writer:
                create_material(writer,image_file=writer.get(ImageFile,1),template=writer.get(ProductTemplate,1),
                    owner=writer.get(User,1),request_key="winner-request")
            result=create_material(stale,image_file=stale.get(ImageFile,1),template=stale.get(ProductTemplate,1),
                owner=stale.get(User,1),request_key="stale-request",commit=False)
            self.assertEqual(result["outcome"],"duplicate")
            stale.commit()

    def test_concurrent_content_registration_reads_winner_after_unique_conflict(self):
        barrier=threading.Barrier(2)
        def save(content,mime,company,sha):
            barrier.wait(timeout=15)
            return f"images/company/1/{sha}.png",f"https://images.example/{sha}.png"
        def register(_):
            with self.sessions() as db:
                return register_bytes(db,1,picture(),source_url="https://source.example/a").id
        with patch("app.image_files.save_content_image",side_effect=save),ThreadPoolExecutor(max_workers=2) as executor:
            result=list(executor.map(register,range(2)))
        self.assertEqual(len(set(result)),1)
