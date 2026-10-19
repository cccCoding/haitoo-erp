"""可选真实 MySQL 回归；只允许专用临时数据库，不操作业务库。"""
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.models import Company, Role, SupplyJob, User
from app.supply_common import now


@unittest.skipUnless(os.getenv("SUPPLY_TEST_DATABASE_URL"), "需要专用 MySQL 测试连接")
class SupplyMysqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(os.environ["SUPPLY_TEST_DATABASE_URL"])
        if url.get_backend_name() not in {"mysql", "mariadb"} or not (url.database or "").startswith("haitoo_supply_validation_"):
            raise RuntimeError("货盘 MySQL 测试仅允许 haitoo_supply_validation_ 前缀的临时数据库")
        cls.engine = create_engine(url, pool_pre_ping=True)
        cls.sessions = sessionmaker(bind=cls.engine, autoflush=False)
        from app.db_migrate import upgrade_database
        with cls.engine.begin() as connection:
            upgrade_database(connection)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.extra_company_ids = []
        key = uuid4().hex
        with self.sessions() as db:
            company = Company(name=f"Supply test {key}")
            db.add(company); db.flush()
            self.company_id = company.id
            members = [User(company_id=company.id, role=Role.MEMBER, supply_admin=True,
                name="Worker", email=f"{key}-{index}@example.com", password_hash="test") for index in range(3)]
            db.add_all(members); db.flush()
            self.user_ids = [member.id for member in members]
            db.commit()

    def tearDown(self):
        with self.sessions() as db:
            db.execute(update(SupplyJob).where(SupplyJob.company_id.in_(
                [self.company_id, *self.extra_company_ids])).values(state="cancelled"))
            db.commit()

    def job(self, index=0):
        with self.sessions() as db:
            item = SupplyJob(company_id=self.company_id, user_id=self.user_ids[index], strategy_id=1,
                template_id=1, category_catalog_id=1, idempotency_key=uuid4().hex, request_hash="a" * 64,
                snapshot={}, category_blob=b"test", checkpoint={}, progress={})
            db.add(item); db.commit()
            return item.id

    def test_real_migration_and_external_role(self):
        with self.sessions() as db:
            user = User(company_id=self.company_id, name="Supply", email=f"{uuid4().hex}@example.com",
                password_hash="test", role=Role.SUPPLY_USER, supply_expires_at=now() + timedelta(days=30))
            db.add(user); db.commit()
            self.assertEqual(db.execute(text("SELECT role FROM users WHERE id=:id"), {"id": user.id}).scalar_one(), "SUPPLY_USER")
            self.assertEqual(db.execute(text("SELECT version_num FROM alembic_version")).scalar_one(), "20261016_38")
        columns = {column["name"]: column for column in inspect(self.engine).get_columns("supply_jobs")}
        self.assertNotIn("download_revoked", columns)
        self.assertEqual(str(columns["category_blob"]["type"]), "MEDIUMBLOB")

    def test_statistics_with_large_snapshots_and_small_sort_buffer(self):
        from app.supply_catalog import statistics
        with self.sessions() as db:
            for index, (agent_id, state, links) in enumerate((
                (1, "completed", 10), (1, "completed", 3), (1, "failed", 7),
                (None, "completed", 2), (None, "running", 8), (2, "cancelled", 6),
            )):
                db.add(SupplyJob(company_id=self.company_id, user_id=self.user_ids[index % 3],
                    agent_id=agent_id, agent_name=f"历史代理{index}", template_id=1, category_catalog_id=1,
                    idempotency_key=uuid4().hex, request_hash="a" * 64, category_blob=b"test",
                    state=state, snapshot={"strategy": {"link_count": links},
                        "candidates": [{"description": "x" * 524288}]}))
            db.commit()
        with self.sessions() as db:
            previous = db.scalar(text("SELECT @@SESSION.sort_buffer_size"))
            try:
                db.execute(text("SET SESSION sort_buffer_size = 32768"))
                result = statistics(user=db.get(User, self.user_ids[0]), db=db)
                agents = {row["agent_id"]: row for row in result["agents"]}
                self.assertEqual(result["summary"]["job_count"], 6)
                self.assertEqual(agents[1], {"agent_id": 1, "agent_name": "历史代理2", "job_count": 3,
                    "success_count": 2, "user_count": 2, "link_count": 13, "download_count": 0})
                self.assertEqual(agents[None]["link_count"], 2)
                self.assertEqual(agents[2]["link_count"], 0)
            finally:
                db.execute(text("SET SESSION sort_buffer_size = :size"), {"size": previous})

    def test_parallel_claims_respect_company_limit(self):
        from app.supply_worker import claim_job
        for index in range(3):
            self.job(index)
        barrier = threading.Barrier(3)
        def claim(index):
            barrier.wait(timeout=10)
            return claim_job(self.sessions, owner=f"mysql-worker-{index}")
        with ThreadPoolExecutor(max_workers=3) as pool:
            claims = list(pool.map(claim, range(3)))
        claimed = [value for value in claims if value]
        self.assertEqual(len(claimed), 2)
        self.assertEqual(len({value[0] for value in claimed}), 2)

    def test_one_claim_and_stale_epoch_is_fenced(self):
        from app.supply_worker import LostLease, claim_job, mutate
        identity = self.job()
        barrier = threading.Barrier(2)
        def claim(index):
            barrier.wait(timeout=10)
            return claim_job(self.sessions, owner=f"single-{index}")
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = [value for value in pool.map(claim, range(2)) if value]
        self.assertEqual(len(claims), 1)
        with self.sessions() as db:
            db.get(SupplyJob, identity).lease_expires_at = now() - timedelta(seconds=1)
            db.commit()
        replacement = claim_job(self.sessions, owner="replacement")
        self.assertEqual(replacement[0], identity)
        with self.assertRaises(LostLease):
            mutate(*claims[0], lambda db, job: setattr(job, "stage", "stale"), self.sessions)
        mutate(*replacement, lambda db, job: setattr(job, "stage", "current"), self.sessions)

    def test_large_full_company_backlog_does_not_starve_other_company(self):
        from app.supply_worker import claim_job
        self.job(0); self.job(1)
        self.assertIsNotNone(claim_job(self.sessions, owner="busy-1"))
        self.assertIsNotNone(claim_job(self.sessions, owner="busy-2"))
        with self.sessions() as db:
            for index in range(101):
                user = User(company_id=self.company_id, role=Role.MEMBER, name="Queued",
                    email=f"{uuid4().hex}@example.com", password_hash="test")
                db.add(user); db.flush()
                db.add(SupplyJob(company_id=self.company_id, user_id=user.id, strategy_id=1,
                    template_id=1, category_catalog_id=1, idempotency_key=uuid4().hex,
                    request_hash="a" * 64, snapshot={}, category_blob=b"test", checkpoint={}, progress={}))
            company = Company(name=f"Other {uuid4().hex}")
            db.add(company); db.flush()
            self.extra_company_ids.append(company.id)
            user = User(company_id=company.id, role=Role.MEMBER, name="Other",
                email=f"{uuid4().hex}@example.com", password_hash="test")
            db.add(user); db.flush()
            job = SupplyJob(company_id=company.id, user_id=user.id, strategy_id=1,
                template_id=1, category_catalog_id=1, idempotency_key=uuid4().hex,
                request_hash="a" * 64, snapshot={}, category_blob=b"test", checkpoint={}, progress={})
            db.add(job); db.commit()
            target = job.id
        self.assertEqual(claim_job(self.sessions, owner="other-company")[0], target)

    def test_manager_revoke_refreshes_repeatable_read_snapshot(self):
        from app.supply_catalog import lock_actor
        authenticated = threading.Event()
        def old_request():
            with self.sessions() as db:
                actor = db.get(User, self.user_ids[0])
                actor._supply_token_version = actor.token_version
                self.assertTrue(actor.supply_admin)
                authenticated.set()
                try:
                    lock_actor(db, actor, manager=True)
                except HTTPException as exc:
                    return exc.status_code
                return 200
        with self.sessions() as db:
            db.scalar(select(Company).where(Company.id == self.company_id).with_for_update())
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(old_request)
                self.assertTrue(authenticated.wait(timeout=10))
                db.get(User, self.user_ids[0]).supply_admin = False
                db.commit()
                self.assertEqual(future.result(timeout=10), 403)
