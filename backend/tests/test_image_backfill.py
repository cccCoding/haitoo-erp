"""回填的旧库兼容、并发限流、缓存恢复和部署增量测试；不访问实际 R2。"""
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from alembic import command
from sqlalchemy import create_engine, event, inspect, select, text, update
from sqlalchemy.orm import sessionmaker

from app import image_files
from app.database import Base
from app.image_download import ImageDownloadError
from app.models import MaterialAsset
from app.schema_version import alembic_config, schema_heads
from app.storage import StorageError
from scripts import backfill_image_files as backfill
from scripts import image_backfill_cache as cache_module
from tests.test_image_files import picture


class ImageBackfillTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.directory)
        self.engine = create_engine(f"sqlite:///{self.root / 'test.db'}")
        self.addCleanup(self.engine.dispose)
        self.sessions = sessionmaker(bind=self.engine)
        self.cache_dir = self.root / "cache"
        self.stdout = self.enterContext(redirect_stdout(StringIO()))
        self.stderr = self.enterContext(redirect_stderr(StringIO()))

    def seed(self, urls):
        Base.metadata.create_all(self.engine)
        with self.sessions() as db:
            for identity, company, url in urls:
                db.add(MaterialAsset(id=identity, company_id=company, url=url, name="历史素材",
                    sku=f"OLD{identity}", claimed_by=1))
            db.commit()

    def run_backfill(self, **kwargs):
        return backfill.run(session_factory=self.sessions, verbose=False, **kwargs)

    def mock_storage(self):
        def save(content, mime, company, sha):
            return f"images/company/{company}/{sha}.png", f"https://images.example/images/company/{company}/{sha}.png"
        return self.enterContext(patch.object(image_files, "save_content_image", side_effect=save))

    def test_prepare_reads_real_36_schema_without_new_columns_or_writes(self):
        with self.engine.begin() as connection:
            command.upgrade(alembic_config(connection), "20261013_36")
            connection.execute(text("INSERT INTO material_assets (id, company_id, url, name, sku, claimed_by, created_at, usage_status) VALUES (1, 1, 'https://source.example/material', 'legacy', 'OLD', 1, CURRENT_TIMESTAMP, 'unused')"))
            connection.execute(text("INSERT INTO product_templates (id, company_id, name, cover_url, size_chart_url, is_platform, status, color_count, sku_count) VALUES (1, 1, 'legacy', 'https://source.example/cover', 'https://source.example/size', 0, 'published', 1, 1)"))
            connection.execute(text("INSERT INTO product_drafts (id, company_id, template_id, title, status, workflow_stage, image_urls, sku_items, carousel_items, export_count, created_at, updated_at) VALUES (1, 1, 1, 'legacy', 'pending_publish', 'pending', '[\"https://source.example/draft\"]', '[]', '[]', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO pod_tasks (id, company_id, template_id, created_by, task_type, status, parameters, result_urls, result_map, failure_ignored, submit_attempts, created_at) VALUES (1, 1, 1, 1, 'sku_image', 'COMPLETED', '{\"print_url\":\"https://source.example/print\"}', '[\"https://source.example/result\"]', '[]', 0, 0, CURRENT_TIMESTAMP)"))
        backfill.assert_prepare_schema(self.engine)
        self.assertNotIn("image_files", inspect(self.engine).get_table_names())

        def forbid_writes(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP"}:
                raise AssertionError(f"预缓存不允许写数据库：{statement}")
        event.listen(self.engine, "before_cursor_execute", forbid_writes)
        self.addCleanup(event.remove, self.engine, "before_cursor_execute", forbid_writes)
        save = self.mock_storage()
        with patch.object(cache_module, "download_image", AsyncMock(return_value=picture())) as download:
            rows = self.run_backfill(prepare=True, cache_dir=self.cache_dir, workers=4)
        self.assertEqual(len(rows), 7)  # 尺码图同时被模板和草稿引用。
        self.assertEqual(download.call_count, 6)
        self.assertTrue(all(row["result"] == "prepared" for row in rows))
        save.assert_not_called()
        with self.engine.connect() as connection:
            self.assertEqual(schema_heads(connection)[0], {"20261013_36"})

    def test_prepare_resume_then_apply_uses_cache_and_catches_new_references(self):
        url = "https://source.example/a"
        self.seed([(1, 1, url), (2, 1, url), (3, 2, url)])
        with patch.object(cache_module, "download_image", AsyncMock(return_value=picture())) as download:
            first = self.run_backfill(prepare=True, cache_dir=self.cache_dir, workers=4)
            second = self.run_backfill(prepare=True, cache_dir=self.cache_dir, workers=4)
        self.assertEqual(download.call_count, 2)  # 公司隔离，同公司相同链接只下载一次。
        self.assertTrue(all(row["result"] == "prepared" for row in first))
        self.assertTrue(all(row["result"] == "cached" for row in second))
        with self.sessions() as db:
            db.add(MaterialAsset(id=4, company_id=1, url="https://source.example/delta", name="新增", sku="NEW", claimed_by=1))
            db.commit()
        save = self.mock_storage()
        with patch.object(image_files, "download_image", AsyncMock(return_value=picture("blue"))) as delta:
            result = self.run_backfill(apply=True, cache_dir=self.cache_dir)
            # 模拟文件登记已提交、素材关联尚未提交时进程中断。
            with self.sessions() as db:
                db.execute(update(MaterialAsset).where(MaterialAsset.id == 1).values(image_file_id=None))
                db.commit()
            again = self.run_backfill(apply=True, cache_dir=self.cache_dir)
        delta.assert_called_once_with("https://source.example/delta")
        self.assertEqual(save.call_count, 3)
        self.assertTrue(all(row["result"] == "saved" for row in result + again))
        self.assertEqual(Counter(row["source"] for row in result), {"cache": 3, "network": 1})
        self.assertTrue(all(row["source"] == "indexed" for row in again))
        with self.sessions() as db:
            assets = db.scalars(select(MaterialAsset).order_by(MaterialAsset.id)).all()
            self.assertEqual([asset.sku for asset in assets], ["OLD1", "OLD2", "OLD3", "NEW"])
            self.assertEqual(assets[0].image_file_id, assets[1].image_file_id)
            self.assertNotEqual(assets[0].image_file_id, assets[2].image_file_id)

    def test_prepared_r2_reads_only_and_apply_copies_browser_writable_objects(self):
        permanent = "https://images.example/material/company/1/legacy.png"
        creative = "https://images.example/creative/company/1/input.png"
        self.seed([(1, 1, permanent), (2, 1, creative)])
        save = self.mock_storage()
        settings = SimpleNamespace(r2_public_base_url="https://images.example")
        with patch("app.storage.get_settings", return_value=settings), \
                patch.object(cache_module, "read_image_object", side_effect=[picture(), picture("blue")]) as read, \
                patch.object(cache_module, "download_image", side_effect=AssertionError("R2 图片不走外链")):
            prepared = self.run_backfill(prepare=True, cache_dir=self.cache_dir)
            self.assertTrue(all(row["result"] == "prepared" for row in prepared))
            save.assert_not_called()
            self.assertEqual(read.call_count, 2)
            result = self.run_backfill(apply=True, cache_dir=self.cache_dir)
        self.assertTrue(all(row["source"] == "cache" for row in result))
        save.assert_called_once()
        with self.sessions() as db:
            self.assertEqual(image_files.by_url(db, 1, permanent).url, permanent)
            self.assertNotIn("/creative/", image_files.by_url(db, 1, creative).url)

    def test_cli_reports_failure_exit_code_and_limits_are_passed_to_runner(self):
        with patch("sys.argv", ["backfill", "--apply", "--workers", "6", "--limit", "100"]), \
                patch.object(backfill, "assert_schema_current"), \
                patch("app.storage._configuration", side_effect=StorageError("未配置")), \
                patch.object(backfill, "run", return_value={"errors": 2}) as run:
            with self.assertRaises(SystemExit) as failure:
                backfill.main()
        self.assertEqual(failure.exception.code, 1)
        self.assertEqual(run.call_args.kwargs["workers"], 6)
        self.assertEqual(run.call_args.kwargs["limit"], 100)
        self.assertFalse(run.call_args.kwargs["collect_results"])

    def test_partial_failure_retry_and_report_latest_result(self):
        self.seed([(1, 1, "https://source.example/bad"), (2, 1, "https://source.example/good")])
        report = self.root / "first.jsonl"

        async def download(url):
            if url.endswith("bad"):
                raise ImageDownloadError("图片地址必须位于公网")
            return picture()

        with patch.object(cache_module, "download_image", side_effect=download):
            rows = self.run_backfill(prepare=True, cache_dir=self.cache_dir, report=report, workers=2)
        self.assertEqual(Counter(row["result"] for row in rows), {"error": 1, "prepared": 1})
        with patch.object(cache_module, "download_image", AsyncMock(return_value=picture())) as retry:
            rows = self.run_backfill(prepare=True, cache_dir=self.cache_dir, retry_from=report, report=report)
        retry.assert_called_once_with("https://source.example/bad")
        self.assertEqual(len(rows), 1)
        self.assertEqual(backfill._failed_addresses(report), set())
        self.assertEqual(len(report.read_text().splitlines()), 3)

    def test_report_append_repairs_only_incomplete_tail(self):
        self.seed([(1, 1, "https://source.example/a")])
        report = self.root / "interrupted.jsonl"
        old = {"company_id": 1, "url": "https://source.example/a", "result": "error"}
        for tail in (b'\n{"model": "Mater', b''):
            with self.subTest(tail=tail):
                report.write_bytes(json.dumps(old).encode() + tail)
                self.run_backfill(report=report)
                lines = [json.loads(line) for line in report.read_text().splitlines()]
                self.assertEqual(len(lines), 2)
                self.assertEqual(lines[0], old)
                self.assertEqual(lines[1]["result"], "would_save")
                self.assertEqual(backfill._failed_addresses(report), set())

    def test_retry_report_tolerates_partial_utf8_tail(self):
        report = self.root / "partial-utf8.jsonl"
        old = {"company_id": 1, "url": "https://source.example/a", "result": "error"}
        report.write_bytes(json.dumps(old).encode() + b'\n{"error":"' + "图片".encode()[:-1])
        self.assertEqual(backfill._failed_addresses(report), {(1, "https://source.example/a")})

    def test_legacy_whitespace_urls_link_all_assets_without_rewriting_skus(self):
        self.seed([(1, 1, " \nhttps://source.example/a\t"), (2, 1, "https://source.example/a")])
        self.mock_storage()
        with patch.object(image_files, "download_image", AsyncMock(return_value=picture())) as download:
            self.run_backfill(apply=True)
        download.assert_called_once_with("https://source.example/a")
        with self.sessions() as db:
            assets = db.scalars(select(MaterialAsset).order_by(MaterialAsset.id)).all()
            self.assertIsNotNone(assets[0].image_file_id)
            self.assertEqual(assets[0].image_file_id, assets[1].image_file_id)
            self.assertEqual(assets[0].url, " \nhttps://source.example/a\t")

    def test_corrupt_cache_fails_closed_and_can_be_reprepared(self):
        url = "https://source.example/a"
        self.seed([(1, 1, url)])
        with patch.object(cache_module, "download_image", AsyncMock(return_value=picture())):
            self.run_backfill(prepare=True, cache_dir=self.cache_dir)
        blob = next((self.cache_dir / "1" / "files").iterdir())
        blob.write_bytes(b"broken")
        save = self.mock_storage()
        rows = self.run_backfill(apply=True, cache_dir=self.cache_dir)
        self.assertIn("缓存校验失败", rows[0]["error"])
        save.assert_not_called()
        # 删除损坏条目的元数据后重跑即可重建，未损坏的缓存不受影响。
        next((self.cache_dir / "1" / "addresses").iterdir()).unlink()
        with patch.object(cache_module, "download_image", AsyncMock(return_value=picture())):
            rows = self.run_backfill(prepare=True, cache_dir=self.cache_dir)
        self.assertEqual(rows[0]["result"], "prepared")

    def test_interrupted_prepare_blob_without_metadata_is_not_a_cache_hit(self):
        self.seed([(1, 1, "https://source.example/a")])
        original = cache_module.ImageBackfillCache._write_atomic

        def interrupted(path, content):
            if path.suffix == ".json":
                raise OSError("磁盘中断")
            original(path, content)

        with patch.object(cache_module, "download_image", AsyncMock(return_value=picture())) as download:
            with patch.object(cache_module.ImageBackfillCache, "_write_atomic", side_effect=interrupted):
                rows = self.run_backfill(prepare=True, cache_dir=self.cache_dir)
            self.assertEqual(rows[0]["result"], "error")
            rows = self.run_backfill(prepare=True, cache_dir=self.cache_dir)
        self.assertEqual(download.call_count, 2)
        self.assertEqual(rows[0]["result"], "prepared")

    def test_parallel_workers_limit_origin_concurrency_and_write_valid_report(self):
        self.seed([(index + 1, 1, f"https://host{index % 2}.example/{index}") for index in range(12)])
        lock = threading.Lock()
        active = Counter()
        peak = Counter()
        threads = set()

        def prepare(company, url):
            host = url.split("/")[2]
            with lock:
                active[host] += 1
                active["all"] += 1
                peak[host] = max(peak[host], active[host])
                peak["all"] = max(peak["all"], active["all"])
                threads.add(threading.get_ident())
            time.sleep(0.02)
            with lock:
                active[host] -= 1
                active["all"] -= 1
            return False

        report = self.root / "parallel.jsonl"
        with patch.object(cache_module.ImageBackfillCache, "prepare", side_effect=prepare):
            summary = self.run_backfill(prepare=True, cache_dir=self.cache_dir, workers=4,
                per_host=1, report=report, collect_results=False, progress_seconds=0.01)
        self.assertEqual(summary["completed_urls"], 12)
        self.assertEqual(summary["errors"], 0)
        self.assertGreater(len(threads), 1)
        self.assertEqual(peak["all"], 2)
        self.assertEqual(peak["host0.example"], 1)
        self.assertEqual(peak["host1.example"], 1)
        lines = [json.loads(line) for line in report.read_text().splitlines()]
        self.assertEqual({row["id"] for row in lines}, set(range(1, 13)))
        progress = [json.loads(line) for line in self.stderr.getvalue().splitlines()]
        self.assertTrue(any(row["event"] == "progress" for row in progress))
        self.assertEqual(progress[-1]["eta_seconds"], 0)

    def test_limit_counts_unique_company_urls_and_preview_does_not_download(self):
        self.seed([(1, 1, "https://source.example/a"), (2, 1, "https://source.example/a"),
            (3, 2, "https://source.example/a")])
        with patch.object(image_files, "download_image", side_effect=AssertionError("预览不能下载")):
            summary = self.run_backfill(limit=1, collect_results=False)
        self.assertEqual(summary["available_urls"], 2)
        self.assertEqual(summary["total_urls"], 1)
        self.assertEqual(summary["completed_references"], 2)
        self.assertTrue(summary["limited"])

    def test_changed_asset_url_is_not_linked_to_stale_snapshot(self):
        old_url, new_url = "https://source.example/a", "https://source.example/changed"
        self.seed([(1, 1, old_url)])
        save = self.mock_storage()

        async def download(url):
            with self.sessions() as db:
                db.execute(update(MaterialAsset).where(MaterialAsset.id == 1).values(url=new_url))
                db.commit()
            return picture()

        with patch.object(image_files, "download_image", side_effect=download):
            self.run_backfill(apply=True)
        with self.sessions() as db:
            asset = db.get(MaterialAsset, 1)
            self.assertEqual(asset.url, new_url)
            self.assertIsNone(asset.image_file_id)
        save.assert_called_once()

    def test_invalid_options_and_unsupported_prepare_schema(self):
        for kwargs in ({"prepare": True}, {"prepare": True, "apply": True, "cache_dir": self.cache_dir},
                       {"workers": 33}, {"per_host": 0}, {"limit": 0}, {"progress_seconds": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.run_backfill(**kwargs)
        with self.assertRaisesRegex(RuntimeError, "预缓存要求"):
            backfill.assert_prepare_schema(self.engine)

    def test_reference_paging_preserves_all_rows_and_company_scope(self):
        self.seed([(index, 1, f"https://source.example/{index}") for index in range(1, 503)] +
            [(503, 2, "https://source.example/other")])
        with self.sessions() as db:
            rows = list(backfill.references(db, company_id=1))
        self.assertEqual(len(rows), 502)
        self.assertEqual(rows[-1]["id"], 502)


if __name__ == "__main__":
    unittest.main()
