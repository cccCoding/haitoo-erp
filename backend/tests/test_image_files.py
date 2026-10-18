from io import BytesIO
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import image_files, main
from app.database import Base
from app.models import Company, ImageFile, MaterialAsset, ProductLibraryProduct, ProductLibrarySource, ProductTemplate, Role, User
from app.schemas import ImageUploadCompleteInput, MaterialImportConfirmInput, MaterialUploadCommitInput, MaterialUploadPresignInput, UploadPresignInput


def picture(color="red"):
    stream = BytesIO()
    Image.new("RGB", (4, 4), color).save(stream, format="PNG")
    return stream.getvalue()


class ImageFileTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add_all([Company(id=1,name="One"),Company(id=2,name="Two"),
                User(id=1,company_id=1,email="a@a.com",name="A",user_code="AA",password_hash="x",role=Role.MEMBER),
                User(id=2,company_id=2,email="b@a.com",name="B",user_code="BB",password_hash="x",role=Role.MEMBER),
                ProductTemplate(id=1,company_id=1,name="Y1"),ProductTemplate(id=2,company_id=1,name="Y2")])
            db.commit()
        def save(content,mime,company,sha):
            key=f"images/company/{company}/{sha}.png"
            return key,f"https://images.example/{key}"
        self.save=self.enterContext(patch.object(image_files,"save_content_image",side_effect=save))
        self.download=self.enterContext(patch.object(image_files,"download_image",AsyncMock(return_value=picture())))

    def tearDown(self):
        self.engine.dispose()

    def create(self,db,file,key,force=False,template=1):
        return image_files.create_material(db,image_file=file,template=db.get(ProductTemplate,template),
            owner=db.get(User,1),request_key=key,force_create=force)

    def test_same_bytes_different_sources_skip_force_and_replay(self):
        with self.sessions() as db:
            a=image_files.ingest_url(db,1,"https://source.example/a")
            self.assertEqual(self.create(db,a,"first-request")["outcome"],"created")
            b=image_files.ingest_url(db,1,"https://source.example/b")
            self.assertEqual(a.id,b.id)
            self.assertEqual(self.create(db,b,"second-request",template=2)["outcome"],"duplicate")
            forced=self.create(db,b,"force-request",True,2)
            replay=self.create(db,b,"force-request",True,2)
            self.assertEqual(forced["asset_id"],replay["asset_id"])
            assets=db.scalars(select(MaterialAsset)).all()
            self.assertEqual(len(assets),2)
            self.assertEqual(len({a.sku for a in assets}),2)
            self.assertEqual({a.url for a in assets},{b.url})
            self.assertEqual({a.template_id for a in assets},{1,2})
        self.assertEqual(self.save.call_count,1)

    def test_mapped_source_reused_and_company_isolation(self):
        with self.sessions() as db:
            a=image_files.ingest_url(db,1,"https://source.example/a")
            self.download.side_effect=AssertionError("不应下载")
            self.assertEqual(image_files.ingest_url(db,1,"https://source.example/a").id,a.id)
            self.download.side_effect=None
            b=image_files.ingest_url(db,2,"https://source.example/a")
            self.assertNotEqual(a.id,b.id)
            self.assertNotEqual(a.url,b.url)
        self.assertEqual(self.save.call_count,2)

    def test_different_bytes_and_corrupt_files(self):
        with self.sessions() as db:
            image_files.register_bytes(db,1,picture())
            image_files.register_bytes(db,1,picture("blue"))
            with self.assertRaises(HTTPException): image_files.register_bytes(db,1,b"not an image")
            self.assertEqual(db.scalar(select(func.count()).select_from(ImageFile)),2)
        self.assertEqual(self.save.call_count,2)

    def test_browser_writable_r2_urls_are_copied_before_material_creation(self):
        settings = SimpleNamespace(r2_public_base_url="https://images.example")
        with patch("app.storage.get_settings", return_value=settings):
            for category, color in (("image-upload-tmp", "red"), ("creative", "blue")):
                with self.subTest(category=category), self.sessions() as db:
                    url = f"https://images.example/{category}/company/1/upload.png"
                    with patch.object(image_files, "read_image_object", return_value=picture(color)) as read:
                        result = main.confirm_material_import(MaterialImportConfirmInput(
                            template_id=1, urls=[url], request_key=f"import-{category}"), user=db.get(User, 1), db=db)
                    self.assertEqual(result["imported"], 1)
                    read.assert_called_once_with(f"{category}/company/1/upload.png", max_bytes=3 * 1024 * 1024)
                    asset = db.get(MaterialAsset, result["items"][0]["asset_id"])
                    image_file = db.get(ImageFile, asset.image_file_id)
                    self.assertTrue(image_file.object_key.startswith("images/company/1/"))
                    self.assertEqual(asset.url, image_file.url)
                    self.assertNotEqual(image_file.url, url)
                    # 临时源已删除或被覆盖后，导出仍仅解析已保存的正式地址。
                    with patch.object(image_files, "read_image_object", side_effect=AssertionError("源已不可用")):
                        products = [{"image_urls": [url], "sku_images": [{"image_url": url, "sku": asset.sku}]}]
                        image_files.resolve_export_images(db, 1, products)
                        self.assertEqual(products[0]["image_urls"], [image_file.url])
                        self.assertEqual(products[0]["sku_images"][0]["image_url"], image_file.url)
                        self.assertEqual(image_files.ingest_url(db, 1, url).id, image_file.id)
        self.assertEqual(self.save.call_count, 2)
        self.download.assert_not_called()

    def test_legacy_permanent_company_image_keeps_original_object(self):
        settings = SimpleNamespace(r2_public_base_url="https://images.example")
        url = "https://images.example/material/company/1/legacy.png"
        with self.sessions() as db, patch("app.storage.get_settings", return_value=settings), \
                patch.object(image_files, "read_image_object", return_value=picture()):
            image_file = image_files.ingest_url(db, 1, url)
            self.assertEqual(image_file.object_key, "material/company/1/legacy.png")
            self.assertEqual(image_file.url, url)
        self.save.assert_not_called()

    def test_existing_local_file_skips_upload_and_token_scoped(self):
        with self.sessions() as db:
            user=db.get(User,1)
            file=image_files.register_bytes(db,1,picture())
            self.create(db,file,"initial-request")
            response=main.presign_material_assets(MaterialUploadPresignInput(template_id=1,files=[{
                "content_type":"image/png","content_length":len(picture()),"sha256":file.sha256}]),user=user,db=db)[0]
            self.assertTrue(response["duplicate"])
            self.assertNotIn("upload_url",response)
            payload=MaterialUploadCommitInput(template_id=1,items=[{"file_token":response["file_token"],
                "name":"copy.png","request_key":"force-key-local","force_create":True}])
            for _ in range(2): self.assertEqual(main.commit_material_assets(payload,user=user,db=db)["created"],1)
            self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset)),2)
            with self.assertRaises(HTTPException): image_files.ticket_file(db,db.get(User,2),response["file_token"])
        self.assertEqual(self.save.call_count,1)

    def test_browser_claim_is_verified(self):
        from app.credentials import encrypt_secret
        value={"user":1,"company":1,"purpose":"image-upload","key":"image-upload-tmp/company/1/temp",
            "sha256":"0"*64,"size":len(picture()),"mime":"image/png","category":"material","exp":int(time.time())+100}
        with self.sessions() as db,patch.object(image_files,"read_image_object",return_value=picture()):
            user=db.get(User,1)
            with self.assertRaises(HTTPException):
                image_files.finish_upload(db,user,upload_token=encrypt_secret(json.dumps(value)),file_token=None)
            self.assertEqual(db.scalar(select(func.count()).select_from(ImageFile)),0)
            value["sha256"]=image_files.digest(picture())
            file=image_files.finish_upload(db,user,upload_token=encrypt_secret(json.dumps(value)),file_token=None)
            self.assertEqual(file.sha256,value["sha256"])
        self.assertEqual(self.save.call_count,1)

    def test_creative_upload_verified_and_reused_across_categories_and_companies(self):
        content = picture()
        payload = UploadPresignInput(content_type="image/png", content_length=len(content), sha256=image_files.digest(content))
        with self.sessions() as db, patch.object(image_files, "create_temporary_image_upload", return_value={
                "url": "https://images.example/image-upload-tmp/company/1/new.png", "upload_url": "https://upload.example/signed"}) as presign, \
                patch("app.storage.get_settings", return_value=SimpleNamespace(r2_public_base_url="https://images.example")):
            user = db.get(User, 1)
            target = main.presign_creative_asset(payload, user=user, db=db)
            self.assertIn("upload_url", target)
            with patch.object(image_files, "read_image_object", return_value=content):
                result = main.complete_image_upload(ImageUploadCompleteInput(category="creative",
                    upload_token=target["upload_token"]), user=user, db=db)
            self.assertIn("/images/company/1/", result["url"])
            presign.reset_mock()
            self.save.reset_mock()
            for category in ("creative", "material", "template-white"):
                reused = image_files.prepare_upload(db, user, sha256=payload.sha256,
                    mime_type=payload.content_type, size=payload.content_length, category=category)
                self.assertNotIn("upload_url", reused)
                self.assertEqual(reused["url"], result["url"])
                completed = image_files.finish_upload(db, user, upload_token=None,
                    file_token=reused["file_token"], category=category)
                self.assertEqual(completed.url, result["url"])
            presign.assert_not_called()
            self.save.assert_not_called()
            self.assertIn("upload_url", main.presign_creative_asset(payload, user=db.get(User, 2), db=db))
            presign.assert_called_once()

    def test_order_original_urls_export_only_for_own_company_and_backfill_skips_drafts(self):
        from app.models import ProductDraft
        from scripts.backfill_image_files import references
        url = "https://source.example/order.png"
        with self.sessions() as db:
            db.add(ProductLibrarySource(id=1, company_id=1, platform="TikTok", site="MY", shop_name="Shop"))
            db.add(ProductLibraryProduct(company_id=1, source_id=1, external_product_id="1", sku="ORDER",
                title="Order product", image_url=url))
            draft = ProductDraft(company_id=1, template_id=1, created_by=1, title="Order draft",
                image_urls=[url], sku_items=[{"sku": "ORDER", "image_url": url, "product_library_image_url": url}])
            db.add(draft)
            db.commit()
            products = [{"image_urls": [url], "sku_images": [{"sku": "ORDER", "image_url": url}]}]
            image_files.resolve_export_images(db, 1, products)
            self.assertEqual(products[0]["image_urls"], [url])
            with self.assertRaises(HTTPException):
                image_files.resolve_export_images(db, 2, products)
            self.assertFalse(any(row["url"] == url for row in references(db)))
            product = db.scalar(select(ProductLibraryProduct))
            product.image_url = "https://source.example/reimported.png"
            db.commit()
            self.assertFalse(any(row["url"] == url for row in references(db)))
        self.download.assert_not_called()
        self.save.assert_not_called()

    def test_import_force_uses_ticket_without_redownload(self):
        with self.sessions() as db:
            user=db.get(User,1)
            a=main.confirm_material_import(MaterialImportConfirmInput(template_id=1,urls=["https://source.example/a"],request_key="import-key-a"),user=user,db=db)
            b=main.confirm_material_import(MaterialImportConfirmInput(template_id=1,urls=["https://source.example/b"],request_key="import-key-b"),user=user,db=db)
            self.assertEqual(a["imported"],1)
            self.assertEqual(b["duplicates"],1)
            self.download.side_effect=AssertionError("强制创建不能下载")
            c=main.confirm_material_import(MaterialImportConfirmInput(template_id=2,file_token=b["items"][0]["file_token"],force_create=True,request_key="import-force"),user=user,db=db)
            self.assertEqual(c["imported"],1)
        self.assertEqual(self.save.call_count,1)

    def test_partial_failure_preserves_success(self):
        from app.image_download import ImageDownloadError
        self.download.side_effect=[picture(),ImageDownloadError("图片已删除")]
        with self.sessions() as db:
            result=main.confirm_material_import(MaterialImportConfirmInput(template_id=1,
                urls=["https://source.example/a","https://source.example/b"],request_key="partial-key"),user=db.get(User,1),db=db)
            self.assertEqual([row["outcome"] for row in result["items"]],["created","error"])
            self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset)),1)

    def test_export_only_reads_mapping_for_all_images(self):
        with self.sessions() as db:
            file=image_files.ingest_url(db,1,"https://source.example/a")
            self.download.side_effect=AssertionError("导出不能下载")
            self.save.side_effect=AssertionError("导出不能保存")
            products=[{"image_urls":["https://source.example/a"],"sku_images":[{"image_url":"https://source.example/a","sku":"SKU"}],
                "base_sku_by_image":{"https://source.example/a":"SKU"},"size_chart_url":"https://source.example/a"}]
            image_files.resolve_export_images(db,1,products)
            self.assertEqual(products[0]["image_urls"],[file.url])
            self.assertEqual(products[0]["sku_images"][0]["image_url"],file.url)
            self.assertEqual(products[0]["size_chart_url"],file.url)
            self.assertEqual(products[0]["base_sku_by_image"],{file.url:"SKU"})
            with self.assertRaises(HTTPException): image_files.resolve_export_images(db,2,[{"image_urls":["https://source.example/a"]}])
            with self.assertRaises(HTTPException): image_files.resolve_export_images(db,1,[{"image_urls":["https://missing.example/a"]}])

    def test_delete_keeps_file_and_recreates(self):
        with self.sessions() as db:
            file=image_files.register_bytes(db,1,picture())
            first=self.create(db,file,"first-request")
            db.delete(db.get(MaterialAsset,first["asset_id"]))
            db.commit()
            self.assertIsNotNone(db.get(ImageFile,file.id))
            self.assertEqual(self.create(db,file,"second-request")["outcome"],"created")
        self.assertEqual(self.save.call_count,1)

    def test_failed_storage_no_index(self):
        from app.storage import StorageError
        self.save.side_effect=StorageError("R2 暂不可用")
        with self.sessions() as db:
            with self.assertRaises(HTTPException): image_files.register_bytes(db,1,picture())
            self.assertEqual(db.scalar(select(func.count()).select_from(ImageFile)),0)

    def test_backfill_preview_and_idempotent_apply_preserve_old_skus(self):
        from scripts.backfill_image_files import run
        with self.sessions() as db:
            db.add_all([MaterialAsset(company_id=1,template_id=1,claimed_by=1,url="https://source.example/a",name="old",sku="OLD"),
                MaterialAsset(company_id=1,template_id=2,claimed_by=1,url="https://source.example/a",name="old2",sku="OLD2")])
            db.commit()
        with patch("builtins.print"):
            run(session_factory=self.sessions)
            self.download.assert_not_called()
            result=run(apply=True,session_factory=self.sessions)
            again=run(apply=True,session_factory=self.sessions)
        self.assertFalse(any(row["result"]=="error" for row in result+again))
        with self.sessions() as db:
            assets=db.scalars(select(MaterialAsset)).all()
            self.assertEqual({a.sku for a in assets},{"OLD","OLD2"})
            self.assertEqual(len({a.image_file_id for a in assets}),1)
        self.assertEqual(self.save.call_count,1)
