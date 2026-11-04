"""隔离验证 Grsai 直存和永久化；假 R2 明确禁止正文读取与上传。"""
import asyncio
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from botocore.exceptions import ClientError
from fastapi import HTTPException
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError
from alembic import command

from app import ai_image_storage as storage, ai_images, image_files, main, task_jobs, result_worker
from app import image_prepare_worker as worker
from app.ai_providers import GenerationRequest, GrsaiProvider
from app.config import Settings
from app.credentials import encrypt_secret
from app.database import Base
from app.models import (AIImageCandidate, AIImagePreparation, Company, ImageFile, MaterialAsset,
    PodTask, ProductDraft, ProductTemplate, Role, TaskQueueSetting, TaskStatus, User, UserAIProviderCredential)
from app.schemas import ClaimMaterials, DraftImagesConfirm, DraftImageApply, BatchImageReviewConfirm
from app.schema_version import alembic_config


class MetadataOnlyR2:
    def __init__(self):
        self.objects = {}
        self.copies = []
        self.reads = []
        self.fail_head = False

    def head_object(self, *, Bucket, Key):
        self.reads.append((Bucket, Key))
        if self.fail_head:
            raise OSError("offline")
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject")
        return dict(self.objects[Bucket, Key])

    def copy_object(self, **kwargs):
        source = self.objects[kwargs["CopySource"]["Bucket"], kwargs["CopySource"]["Key"]]
        if source["ETag"] != kwargs["CopySourceIfMatch"]:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "CopyObject")
        self.copies.append(kwargs)
        self.objects[kwargs["Bucket"], kwargs["Key"]] = dict(source, Metadata=kwargs["Metadata"],
            ContentType=kwargs["ContentType"], ETag='"target-etag-is-not-source-etag"')
        return {"CopyObjectResult": {"ETag": '"target-etag-is-not-source-etag"'}}

    def get_object(self, **kwargs):
        raise AssertionError("直存流程禁止 GetObject")

    def put_object(self, **kwargs):
        raise AssertionError("直存流程禁止上传正文")


class DirectStorageTests(TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.settings = Settings(_env_file=None, grsai_direct_storage_enabled=True,
            r2_endpoint="https://r2.invalid", r2_bucket="formal", r2_public_base_url="https://images.example",
            r2_ai_pending_bucket="pending", r2_ai_pending_public_base_url="https://pending.example",
            r2_ai_storage_access_key_id="fake", r2_ai_storage_secret_access_key="fake")
        self.r2 = MetadataOnlyR2()
        for module in (storage, ai_images, worker):
            self.enterContext(patch.object(module, "get_settings", return_value=self.settings))
        self.enterContext(patch.object(storage, "_r2_client", return_value=self.r2))
        for symbol in ("download_image", "read_image_object", "save_content_image", "decode_image"):
            self.enterContext(patch.object(image_files, symbol, side_effect=AssertionError("禁止处理正文")))
        with self.sessions() as db:
            db.add_all([Company(id=1, name="One", grsai_storage_id="company-oss"), Company(id=2, name="Two"),
                User(id=1, company_id=1, name="Operator", email="one@example.com", user_code="AA", password_hash="x", role=Role.MEMBER),
                User(id=2, company_id=1, name="Admin", email="admin@example.com", password_hash="x", role=Role.COMPANY_ADMIN),
                User(id=3, company_id=2, name="Other", email="other@example.com", password_hash="x", role=Role.MEMBER),
                User(id=4, company_id=1, name="Designer", email="design@example.com", user_code="DD", password_hash="x", role=Role.DESIGNER),
                ProductTemplate(id=1, company_id=1, name="Y1", cover_url="https://images.example/reference.png"),
                TaskQueueSetting(id=1), UserAIProviderCredential(company_id=1,user_id=1,provider="grsai",secret_encrypted=encrypt_secret("test-key"))])
            db.commit()

    def get_db(self):
        with self.sessions() as db:
            yield db

    def task(self, owner=1, task_type="sku_image", draft_id=None):
        with self.sessions() as db:
            task = PodTask(company_id=1, template_id=1, created_by=owner, task_type=task_type,
                draft_id=draft_id, status=TaskStatus.QUEUED, provider="grsai", provider_model="nano-banana-fast",
                parameters={"print_urls": ["https://images.example/print.png"], "ratio": "1:1", "quality": "1K",
                    "draft_id": draft_id, "source_sku": "SKU"}, result_urls=[], result_map=[])
            db.add(task); db.flush()
            context = ai_images.freeze_storage_context(db, task)
            task.provider_task_id = f"provider-{task.id}"
            task.status = TaskStatus.RUNNING
            db.commit()
            return task.id, dict(context)

    def register(self, count=1, **kwargs):
        task_id, context = self.task(**kwargs)
        urls = []
        for index in range(count):
            key = f"{context['path']}/{index}.png"
            urls.append(f"https://pending.example/{key}")
            self.r2.objects["pending", key] = {"ContentLength": 100, "ContentType": "image/png",
                "LastModified": datetime.now(timezone.utc), "ETag": f'"source-{task_id}-{index}"'}
        ai_images.persist_candidates(task_id, f"provider-{task_id}", context["run_id"], urls, self.sessions)
        with self.sessions() as db:
            task = db.get(PodTask, task_id)
            task.result_urls = urls
            task.result_map = main.map_task_results(task, urls)
            task.status = TaskStatus.AWAITING_SELECTION
            db.commit()
            ids = list(db.scalars(select(AIImageCandidate.id).where(AIImageCandidate.task_id == task_id)))
        return task_id, urls, ids

    def prepare(self, ids, key="request-1"):
        with self.sessions() as db:
            return ai_images.create_preparation(ai_images.PreparationInput(candidate_ids=ids,request_key=key),db.get(User,1),db)

    def run_candidate(self):
        identity = worker.claim_one(self.sessions)
        self.assertIsNotNone(identity)
        return asyncio.run(worker.process_one(identity, self.sessions))

    def test_config_precedence_freezing_reset_and_roles(self):
        task_id, context = self.task()
        self.assertEqual(context["oss_id"], "company-oss")
        with self.sessions() as db:
            admin, member = db.get(User,2), db.get(User,1)
            ai_images.set_member_storage(1,ai_images.MemberStorageInput(mode="custom",storage_id="personal"),admin,db)
            self.assertEqual(ai_images.freeze_storage_context(db,db.get(PodTask,task_id)),context)
        self.assertEqual(self.task()[1]["oss_id"],"personal")
        with self.sessions() as db:
            ai_images.set_member_storage(4,ai_images.MemberStorageInput(mode="legacy"),db.get(User,2),db)
        self.assertEqual(self.task(owner=4)[1]["mode"],"legacy")
        with self.sessions() as db:
            answer=ai_images.reset_members_storage(db.get(User,2),db)
            self.assertEqual(answer["updated"],2)
            self.assertIsNotNone(db.scalar(select(UserAIProviderCredential)))
            main.reset_failed_task(db.get(PodTask,task_id)); db.commit()
            new=ai_images.freeze_storage_context(db,db.get(PodTask,task_id))
            self.assertNotEqual(new["run_id"],context["run_id"])
        self.settings.grsai_direct_storage_enabled=False
        self.assertEqual(self.task()[1]["mode"],"legacy")

    def test_both_models_send_headers(self):
        for model in ("nano-banana-fast","gpt-image-2"):
            request=GenerationRequest(model,"prompt","https://images.example/a",[],"1:1","1K",1,1,"idempotent","oss","pending/task")
            client=AsyncMock()
            client.post.return_value=httpx.Response(200,request=httpx.Request("POST","https://grsai.example"),json={"id":"generated"})
            asyncio.run(GrsaiProvider().submit(request,"key",self.settings,client))
            self.assertEqual(client.post.call_args.kwargs["headers"]["oss-id"],"oss")
            self.assertEqual(client.post.call_args.kwargs["headers"]["oss-path"],"pending/task")

    def test_copy_claim_and_replay_without_body_or_hash(self):
        task_id, urls, ids=self.register(2)
        job=self.prepare(ids)
        self.assertEqual(job["state"],"running")
        self.assertEqual(self.run_candidate(),"ready")
        self.assertEqual(self.run_candidate(),"ready")
        with self.sessions() as db:
            result=ai_images.get_preparation(job["id"],db.get(User,1),db)
            self.assertEqual(result["ready"],2)
            self.assertEqual(db.scalar(select(func.count()).select_from(ImageFile)),2)
            self.assertTrue(all(f.sha256 is None for f in db.scalars(select(ImageFile))))
            payload=ClaimMaterials(result_urls=urls,request_key="claim-key")
            first=main.claim_task_materials(task_id,payload,db.get(User,1),db)
            second=main.claim_task_materials(task_id,payload,db.get(User,1),db)
            self.assertEqual(first["claimed"],2)
            self.assertTrue(all(item.get("replayed") for item in second["items"]))
            self.assertEqual(db.scalar(select(func.count()).select_from(MaterialAsset)),2)
            self.assertFalse(any(a.url.startswith("https://pending") for a in db.scalars(select(MaterialAsset))))
        self.assertEqual(len(self.r2.copies),2)
        self.assertTrue(all("Body" not in call for call in self.r2.copies))
        self.assertEqual(self.prepare(ids)["state"],"ready")
        self.assertIsNone(worker.claim_one(self.sessions))

    def test_storage_identity_is_random_persisted_and_reused_on_registration_and_copy_retry(self):
        task_id, urls, ids = self.register(2)
        with self.sessions() as db:
            rows = list(db.scalars(select(AIImageCandidate).order_by(AIImageCandidate.id)))
            identities = {row.id: row.storage_uid for row in rows}
            self.assertEqual(len(set(identities.values())), 2)
            for value in identities.values():
                self.assertRegex(value, r'^[0-9a-f]{32}$')
            run_id = db.get(PodTask, task_id).storage_context['run_id']
        ai_images.persist_candidates(task_id, f'provider-{task_id}', run_id, urls, self.sessions)
        self.prepare(ids)
        identity = worker.claim_one(self.sessions)
        first = worker.read_copy(identity, self.sessions)
        self.assertEqual(first['target_key'], f'images/company/1/ai/{identities[identity[0]]}.png')
        with self.sessions() as db:
            self.assertEqual(db.get(AIImageCandidate, identity[0]).storage_uid, identities[identity[0]])
        self.assertEqual(worker.read_copy(identity, self.sessions)['target_key'], first['target_key'])
        storage.copy_object(**first)
        with self.sessions() as db:
            db.get(AIImageCandidate, identity[0]).lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.run_candidate(), 'ready')
        self.assertEqual(len(self.r2.copies), 1)
        with self.sessions() as db:
            row = db.get(AIImageCandidate, identity[0])
            self.assertEqual(db.get(ImageFile, row.image_file_id).object_key, first['target_key'])

    def test_legacy_candidate_keeps_numeric_path_and_recovers_unregistered_copy(self):
        _, urls, ids = self.register()
        with self.sessions() as db:
            db.get(AIImageCandidate, ids[0]).storage_uid = None
            db.commit()
        self.prepare(ids)
        identity = worker.claim_one(self.sessions)
        values = worker.read_copy(identity, self.sessions)
        self.assertEqual(values['target_key'], f'images/company/1/ai/{ids[0]}.png')
        _, old_url = storage.copy_object(**values)
        with self.sessions() as db:
            row = db.get(AIImageCandidate, ids[0])
            row.expires_at = datetime.utcnow() - timedelta(days=1)
            row.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.run_candidate(), 'ready')
        with self.sessions() as db:
            row = db.get(AIImageCandidate, ids[0])
            self.assertIsNone(row.storage_uid)
            self.assertEqual(image_files.ingest_url(db, 1, urls[0]).url, old_url)
            self.assertEqual(db.get(ImageFile, row.image_file_id).object_key, values['target_key'])
        self.assertEqual(len(self.r2.copies), 1)

    def test_storage_identity_constraint_allows_legacy_nulls_but_rejects_duplicates(self):
        _, _, ids = self.register(2)
        with self.sessions() as db:
            first, second = (db.get(AIImageCandidate, candidate_id) for candidate_id in ids)
            second.storage_uid = first.storage_uid
            with self.assertRaises(IntegrityError):
                db.flush()
            db.rollback()
            for candidate_id in ids:
                db.get(AIImageCandidate, candidate_id).storage_uid = None
            db.commit()
            self.assertEqual(db.scalar(select(func.count()).select_from(AIImageCandidate).where(AIImageCandidate.storage_uid.is_(None))), 2)

    def test_r2_failure_logs_identify_each_stage_without_third_party_message_or_headers(self):
        _, _, ids = self.register()
        self.prepare(ids)
        identity = worker.claim_one(self.sessions)
        values = worker.read_copy(identity, self.sessions)
        for stage in ('target_head', 'source_head', 'copy', 'verify_target'):
            with self.subTest(stage=stage):
                self.r2.objects.pop(('formal', values['target_key']), None)
                original_head, original_copy = self.r2.head_object, self.r2.copy_object
                operation = 'CopyObject' if stage == 'copy' else 'HeadObject'
                error = ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'third-party-secret'},
                    'ResponseMetadata': {'HTTPStatusCode': 403, 'RequestId': 'request-123',
                        'RetryAttempts': 0, 'HTTPHeaders': {'authorization': 'private-signature'}}}, operation)
                target_reads = 0
                def checked_head(**kwargs):
                    nonlocal target_reads
                    if kwargs['Bucket'] == 'formal':
                        target_reads += 1
                    if (stage == 'target_head' and kwargs['Bucket'] == 'formal'
                            or stage == 'source_head' and kwargs['Bucket'] == 'pending'
                            or stage == 'verify_target' and kwargs['Bucket'] == 'formal' and target_reads == 2):
                        raise error
                    return original_head(**kwargs)
                def checked_copy(**kwargs):
                    if stage == 'copy':
                        raise error
                    return original_copy(**kwargs)
                with patch.object(self.r2, 'head_object', side_effect=checked_head), patch.object(self.r2, 'copy_object', side_effect=checked_copy), self.assertLogs(storage.logger, level='WARNING') as output:
                    with self.assertRaises(ClientError):
                        storage.copy_object(**values)
                context = json.loads(output.records[-1].getMessage().split(' | ', 1)[1])
                self.assertEqual(context['stage'], stage)
                self.assertEqual(context['operation'], operation)
                self.assertEqual(context['error_code'], 'AccessDenied')
                self.assertEqual(context['http_status'], 403)
                self.assertEqual(context['request_id'], 'request-123')
                self.assertEqual((context['source_bucket'], context['target_bucket']), ('pending', 'formal'))
                self.assertEqual((context['source_key'], context['target_key']), (values['source_key'], values['target_key']))
                self.assertNotIn('third-party-secret', '\n'.join(output.output))
                self.assertNotIn('private-signature', '\n'.join(output.output))

    def test_normal_missing_target_does_not_warn_and_worker_403_is_actionable(self):
        _, _, ids = self.register()
        self.prepare(ids)
        with self.assertNoLogs(storage.logger, level='WARNING'):
            self.assertEqual(self.run_candidate(), 'ready')
        _, _, ids = self.register()
        self.prepare(ids, 'forbidden-job')
        error = ClientError({'Error': {'Code': '403', 'Message': 'private-error'},
            'ResponseMetadata': {'HTTPStatusCode': 403}}, 'HeadObject')
        with patch.object(self.r2, 'head_object', side_effect=error), self.assertLogs(worker.logger, level='WARNING') as output:
            self.assertEqual(self.run_candidate(), 'queued')
        context = json.loads(output.records[-1].getMessage().split(' | ', 1)[1])
        self.assertEqual(context['candidate_id'], ids[0])
        self.assertEqual(context['http_status'], 403)
        self.assertEqual(context['operation'], 'HeadObject')
        self.assertEqual((context['source_bucket'], context['target_bucket']), ('pending', 'formal'))
        self.assertNotIn('private-error', '\n'.join(output.output))
        with self.sessions() as db:
            self.assertIn('403', db.get(AIImageCandidate, ids[0]).error)

    def test_http_endpoints_enforce_roles_and_return_async_progress(self):
        _, _, ids=self.register()
        selected=[2]
        def authenticated():
            with self.sessions() as db:
                return db.get(User,selected[0])
        with patch.dict(main.app.dependency_overrides,{main.get_db:self.get_db,main.authenticated_user:authenticated}):
            client=TestClient(main.app)
            self.assertEqual(client.get('/company/grsai-storage').status_code,200)
            self.assertEqual(client.put('/company/grsai-storage',json={'storage_id':'new-default'}).status_code,200)
            selected[0]=1
            self.assertEqual(client.put('/company/grsai-storage',json={'storage_id':'forbidden'}).status_code,403)
            response=client.post('/ai-image-preparations',json={'candidate_ids':ids,'request_key':'http-job'})
            self.assertEqual(response.status_code,202,response.text)
            identity=response.json()['id']
            self.assertEqual(client.get(f'/ai-image-preparations/{identity}').json()['state'],'running')
            selected[0]=3
            self.assertEqual(client.get(f'/ai-image-preparations/{identity}').status_code,404)
            self.assertEqual(client.post('/ai-image-preparations',json={'candidate_ids':ids,'request_key':'forbidden'}).status_code,404)
        self.assertFalse(self.r2.copies)

    def test_unprepared_expired_invalid_changed_and_tenant_guards(self):
        task_id, urls, ids=self.register()
        with self.sessions() as db:
            with self.assertRaises(HTTPException) as error:
                image_files.ingest_url(db,1,urls[0])
            self.assertEqual(error.exception.detail["code"],"IMAGE_PREPARATION_REQUIRED")
            with self.assertRaises(HTTPException):
                ai_images.create_preparation(ai_images.PreparationInput(candidate_ids=ids,request_key="other"),db.get(User,3),db)
            row=db.get(AIImageCandidate,ids[0]); row.expires_at=datetime.utcnow()-timedelta(seconds=1); db.commit()
            with self.assertRaises(HTTPException) as expired:
                image_files.ingest_url(db,1,urls[0])
            self.assertEqual(expired.exception.status_code,410)
        self.prepare(ids)
        self.assertEqual(self.run_candidate(),"expired")
        _, _, ids=self.register()
        with self.sessions() as db:
            row=db.get(AIImageCandidate,ids[0])
            self.r2.objects[row.bucket,row.object_key]["ETag"]='"changed"'
        self.prepare(ids,"changed")
        self.assertEqual(self.run_candidate(),"invalid")
        self.assertFalse(self.r2.copies)

    def test_job_idempotency_conflict_and_retry_limits(self):
        _, _, ids=self.register(2)
        self.prepare(ids)
        self.assertEqual(self.prepare(ids[::-1])["id"],1)
        with self.assertRaises(HTTPException) as conflict:
            self.prepare(ids[:1])
        self.assertEqual(conflict.exception.status_code,409)
        with self.sessions() as db:
            for row in db.scalars(select(AIImageCandidate)):
                row.state="invalid"
            db.commit()
        _, _, ids=self.register()
        job=self.prepare(ids,"retry-only")
        self.r2.fail_head=True
        for attempt in range(4):
            identity=worker.claim_one(self.sessions)
            self.assertIsNotNone(identity)
            state=asyncio.run(worker.process_one(identity,self.sessions))
            self.assertEqual(state,"queued" if attempt<3 else "failed")
            with self.sessions() as db:
                candidate=db.get(AIImageCandidate,identity[0])
                candidate.available_at=datetime.utcnow()-timedelta(seconds=1); db.commit()
        self.r2.fail_head=False
        with self.sessions() as db:
            result=ai_images.retry_preparation(job["id"],db.get(User,1),db)
            self.assertEqual(result["state"],"running")
        self.assertEqual(self.run_candidate(),"ready")
        self.assertEqual(len(self.r2.copies),1)

    def test_copy_recovery_after_database_failure_and_expiration(self):
        _, urls, ids=self.register()
        self.prepare(ids)
        identity=worker.claim_one(self.sessions)
        values=worker.read_copy(identity,self.sessions)
        storage.copy_object(**values)
        with self.sessions() as db:
            row=db.get(AIImageCandidate,ids[0]); row.expires_at=datetime.utcnow()-timedelta(days=1)
            row.lease_expires_at=datetime.utcnow()-timedelta(seconds=1); db.commit()
        self.assertEqual(self.run_candidate(),"ready")
        self.assertEqual(len(self.r2.copies),1)
        with self.sessions() as db:
            self.assertTrue(image_files.ingest_url(db,1,urls[0]).url.startswith("https://images.example/"))

    def test_lease_epoch_blocks_stale_result_and_company_concurrency(self):
        _, _, ids=self.register(3)
        self.prepare(ids)
        old=worker.claim_one(self.sessions)
        self.assertIsNotNone(worker.claim_one(self.sessions))
        self.assertIsNone(worker.claim_one(self.sessions))
        with self.sessions() as db:
            db.get(AIImageCandidate,old[0]).lease_expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
        new=worker.claim_one(self.sessions)
        self.assertNotEqual(old,new)
        with self.assertRaises(worker.LostLease):
            worker.finish(old,result=("old","https://images.example/old"),session_factory=self.sessions)

    def test_worker_rechecks_account_permissions_and_admin_can_retry(self):
        _,_,ids=self.register();job=self.prepare(ids)
        with self.sessions() as db:
            db.get(User,1).is_active=False;db.commit()
        self.assertEqual(self.run_candidate(),'failed')
        self.assertFalse(self.r2.copies)
        with self.sessions() as db:
            ai_images.retry_preparation(job['id'],db.get(User,2),db)
        self.assertEqual(self.run_candidate(),'ready')
        self.assertEqual(len(self.r2.copies),1)

    def test_registration_metadata_paths_formats_and_order(self):
        task_id, context=self.task()
        urls=[f"https://wrong.example/{context['path']}/a.png",f"https://pending.example/{context['path']}/b.webp"]
        self.r2.objects["pending",context["path"]+"/b.webp"]={"ContentLength":100,"ContentType":"application/octet-stream",
            "ETag":'"source"',"LastModified":datetime.now(timezone.utc)}
        ai_images.persist_candidates(task_id,f"provider-{task_id}",context["run_id"],urls,self.sessions)
        with self.sessions() as db:
            rows=list(db.scalars(select(AIImageCandidate).order_by(AIImageCandidate.position)))
            self.assertEqual([r.state for r in rows],["invalid","pending"])
            self.assertEqual(rows[1].mime_type,"image/webp")
            self.assertEqual(db.get(PodTask,task_id).provider_result_urls,urls)
        for url in ("https://pending.example/a/../secret.png","https://pending.example/a/%252e%252e/x.png",
                    "https://pending.example/a.png?secret=x","https://pending.example.evil/a.png"):
            self.assertIsNone(storage.key_from_url(url,"https://pending.example"))

    def test_result_worker_recovers_saved_urls_without_polling_again(self):
        task_id, context=self.task()
        key=context["path"]+"/a.png";urls=["https://pending.example/"+key]
        self.r2.objects["pending",key]={"ContentLength":100,"ContentType":"image/png","ETag":'"source"',"LastModified":datetime.now(timezone.utc)}
        poll=AsyncMock(return_value=urls)
        # read_context 需要模型配置；复用系统默认初始化。
        with self.sessions() as db:
            main.initialize_system_defaults(db)
        with patch.object(task_jobs,"get_db",self.get_db),patch.object(task_jobs,"poll_async_generation",poll):
            self.r2.fail_head=True
            self.assertEqual(asyncio.run(result_worker.process_result(task_id)),"retry")
            self.r2.fail_head=False
            self.assertEqual(asyncio.run(result_worker.process_result(task_id)),"succeeded")
        self.assertEqual(poll.await_count,1)
        with self.sessions() as db:
            self.assertEqual(db.get(PodTask,task_id).status,TaskStatus.AWAITING_SELECTION)

    def test_cross_company_copy_with_null_hash(self):
        _,urls,ids=self.register();self.prepare(ids);self.run_candidate()
        with self.sessions() as db:
            image=image_files.ingest_cross_url(db,2,1,urls[0])
            self.assertEqual(image.company_id,2)
            self.assertIsNone(image.sha256)
            self.assertIsNone(image_files.by_content(db,2,None))
            self.assertEqual(image_files.ingest_cross_url(db,2,1,urls[0]).id,image.id)
        self.assertEqual(len(self.r2.copies),2)

    def test_final_confirmation_and_apply_cannot_persist_pending(self):
        with self.sessions() as db:
            db.add(ProductDraft(id=1,company_id=1,template_id=1,title="Draft title",created_by=1,
                workflow_stage="carousel_pending",sku_items=[{"sku":"SKU","image_url":"https://external.example/a.png"}]))
            db.commit()
        task_id,urls,ids=self.register(task_type="carousel",draft_id=1)
        payload=DraftImagesConfirm(image_items=[{"task_id":task_id,"sku":"SKU","result_url":urls[0]}],advance_workflow=False)
        with self.sessions() as db:
            with self.assertRaises(HTTPException) as error:
                main.confirm_draft_images(1,payload,db.get(User,1),db)
            self.assertEqual(error.exception.status_code,409)
        self.prepare(ids);self.run_candidate()
        with self.sessions() as db:
            response=main.confirm_draft_images(1,payload,db.get(User,1),db)
            self.assertTrue(response["published_image_urls"][0].startswith("https://images.example/"))
            self.assertEqual(db.get(PodTask,task_id).selected_result_url,urls[0])

    def test_single_apply_and_batch_review_require_preparation(self):
        for draft_id, mode in ((1,'single'),(2,'batch')):
            with self.sessions() as db:
                db.add(ProductDraft(id=draft_id,company_id=1,template_id=1,title='Draft',created_by=1,
                    workflow_stage='carousel_pending',sku_items=[{'sku':'SKU','image_url':'https://external.example/a.png'}]))
                db.commit()
            task_id,urls,ids=self.register(task_type='carousel',draft_id=draft_id)
            def apply(db):
                if mode=='single':
                    return main.apply_draft_image_result(draft_id,task_id,DraftImageApply(result_url=urls[0]),db.get(User,1),db)
                return main.confirm_batch_image_review(BatchImageReviewConfirm(task_type='carousel',next_stage='ready_to_publish',
                    selections=[{'draft_id':draft_id,'task_id':task_id,'result_urls':urls}]),db.get(User,1),db)
            with self.sessions() as db:
                with self.assertRaises(HTTPException) as error:
                    apply(db)
                self.assertEqual(error.exception.status_code,409)
                db.rollback()
            self.prepare(ids,f'prepare-{mode}');self.run_candidate()
            with self.sessions() as db:
                apply(db)
                self.assertTrue(db.get(ProductDraft,draft_id).carousel_items[0]['image_url'].startswith('https://images.example/'))

    def test_formal_file_source_identity_uniqueness(self):
        _,_,ids=self.register();self.prepare(ids);self.run_candidate()
        with self.sessions() as db:
            candidate=db.get(AIImageCandidate,ids[0]);file=db.get(ImageFile,candidate.image_file_id)
            first=ai_images.register_formal(db,1,file.object_key,file.url,file.size_bytes,file.mime_type,'grsai_generated',str(ids[0]))
            second=ai_images.register_formal(db,1,file.object_key,file.url,file.size_bytes,file.mime_type,'grsai_generated',str(ids[0]))
            self.assertEqual(first.id,second.id)
            self.assertEqual(db.scalar(select(func.count()).select_from(ImageFile)),1)

    def test_thousand_candidates_queue_without_copy_in_http_and_source_uniqueness(self):
        _, _, ids=self.register(1000)
        result=self.prepare(ids)
        self.assertEqual(result["total"],1000)
        self.assertEqual(result["ready"],0)
        self.assertFalse(self.r2.copies)
        with self.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(AIImagePreparation)),1)
            self.assertNotIn("storage_context",main.serialize_record(db.get(PodTask,1)))
        queries=[]
        def count(connection,cursor,statement,parameters,context,many):
            queries.append(statement)
        event.listen(self.engine,'before_cursor_execute',count)
        try:
            with self.sessions() as db:
                answer=ai_images.get_preparation(result['id'],db.get(User,1),db)
                self.assertEqual(answer['total'],1000)
        finally:
            event.remove(self.engine,'before_cursor_execute',count)
        self.assertLess(len(queries),12,'1000 张进度查询不能逐张访问数据库')

    def test_backfill_skips_candidates_and_hashless_files(self):
        from scripts import backfill_image_files as backfill
        task_id,urls,ids=self.register()
        rows=[{'company_id':1,'url':urls[0],'model':'PodTask','id':task_id}]
        with patch.object(backfill,'references',return_value=iter(rows)),patch('scripts.image_backfill_cache.ImageBackfillCache.prepare',side_effect=AssertionError('不能为 AI 文件下载补算哈希')):
            answer=backfill.run(prepare=True,cache_dir='/private/tmp/haitoo-ai-backfill-test',session_factory=self.sessions,verbose=False)
        self.assertEqual(answer[0]['result'],'skipped_ai')


class DirectStorageMigrationTests(TestCase):
    def test_random_identity_migration_preserves_existing_candidates_and_formal_urls(self):
        engine = create_engine('sqlite://')
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            config = alembic_config(connection)
            command.upgrade(config, '20261104_62')
            for identity in (1, 2):
                connection.execute(text("INSERT INTO ai_image_candidates "
                    "(id,company_id,task_id,run_id,position,source_url,url_hash,bucket,object_key,state,attempts,lease_epoch,created_at) "
                    "VALUES (:id,1,:id,'legacy-run',0,:url,:hash,'pending',:key,'pending',0,0,CURRENT_TIMESTAMP)"),
                    {'id': identity, 'url': f'https://pending.example/{identity}.png', 'hash': str(identity) * 64, 'key': f'pending/{identity}.png'})
            connection.execute(text("INSERT INTO image_files "
                "(id,company_id,sha256,object_key,url,mime_type,size_bytes,created_at,source_type,source_ref,validation_method) "
                "VALUES (1,1,NULL,'images/company/1/ai/2.png','https://images.example/images/company/1/ai/2.png',"
                "'image/png',100,CURRENT_TIMESTAMP,'grsai_generated','2','provider_metadata')"))
            command.upgrade(config, 'head')
            self.assertEqual(connection.execute(text('SELECT storage_uid FROM ai_image_candidates ORDER BY id')).all(), [(None,), (None,)])
            self.assertEqual(connection.execute(text('SELECT object_key,url FROM image_files WHERE id=1')).one(),
                ('images/company/1/ai/2.png', 'https://images.example/images/company/1/ai/2.png'))
            self.assertTrue(any(row['column_names'] == ['storage_uid'] for row in inspect(connection).get_unique_constraints('ai_image_candidates')))
            command.downgrade(config, '20261104_62')
            self.assertNotIn('storage_uid', {row['name'] for row in inspect(connection).get_columns('ai_image_candidates')})
            command.upgrade(config, 'head')
            connection.execute(text('UPDATE ai_image_candidates SET storage_uid=:uid WHERE id=2'), {'uid': 'a' * 32})
            with self.assertRaisesRegex(RuntimeError, '存在随机存储标识'):
                command.downgrade(config, '20261104_62')
            self.assertEqual(connection.execute(text('SELECT storage_uid FROM ai_image_candidates WHERE id=2')).scalar_one(), 'a' * 32)

    def test_random_identity_mysql_migration_has_nullable_column_without_rewriting_objects(self):
        for dialect in ('mysql', 'mariadb'):
            with self.subTest(dialect=dialect):
                output = StringIO()
                config = alembic_config()
                config.output_buffer = output
                with patch('app.config.get_settings', return_value=SimpleNamespace(database_url=f'{dialect}+pymysql://test@localhost/test')):
                    command.upgrade(config, '20261104_62:20261104_63', sql=True)
                sql = output.getvalue()
                self.assertIn('ADD COLUMN storage_uid VARCHAR(32)', sql)
                self.assertIn('uq_ai_candidate_storage_uid UNIQUE (storage_uid)', sql)
                self.assertNotIn('UPDATE image_files', sql)
                self.assertNotIn('UPDATE ai_image_candidates SET storage_uid', sql)

    def test_upgrade_preserves_hashes_allows_nulls_and_blocks_unsafe_downgrade(self):
        engine=create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            config=alembic_config(connection)
            command.upgrade(config,"20261103_61")
            connection.execute(text("INSERT INTO image_files (id,company_id,sha256,object_key,url,mime_type,size_bytes,created_at) VALUES (1,1,:sha,'old','https://old.example','image/png',100,CURRENT_TIMESTAMP)"),{"sha":"a"*64})
            command.upgrade(config,"head")
            self.assertEqual(connection.execute(text("SELECT sha256,validation_method FROM image_files WHERE id=1")).one(),("a"*64,"full_decode"))
            for identity in (2,3):
                connection.execute(text("INSERT INTO image_files (id,company_id,sha256,object_key,url,mime_type,size_bytes,created_at,source_type,source_ref,validation_method) VALUES (:id,1,NULL,:key,:url,'image/png',100,CURRENT_TIMESTAMP,'grsai_generated',:ref,'provider_metadata')"),{"id":identity,"key":str(identity),"url":f"https://images.example/{identity}","ref":str(identity)})
            with self.assertRaisesRegex(RuntimeError,"存在无哈希"):
                command.downgrade(config,"20261103_61")
