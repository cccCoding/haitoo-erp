"""核对重复引用与重复对象分开统计，且全程不修改数据库或 R2。"""
from io import StringIO
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.image_files import digest
from app.models import Company, ImageAddress, ImageFile, MaterialAsset
from scripts.image_duplicate_statistics import collect, list_sizes


class DuplicateStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.settings = Settings(_env_file=None, r2_public_base_url="https://images.example", r2_bucket="images")
        self.canonical = "material/company/1/a.png"
        self.other = "material/company/2/a.png"
        self.old = "material/company/1/old.png"
        self.creative = "creative/company/1/old.png"
        self.third = "material/company/1/b.png"
        self.conflict = "material/company/1/conflict.png"
        with self.sessions() as db:
            db.add_all([Company(id=1, name="甲"), Company(id=2, name="乙")])
            for identity, company, sha, key, size in [(1, 1, "a", self.canonical, 1024),
                    (2, 2, "a", self.other, 1024), (3, 1, "b", self.third, 2048)]:
                db.add(ImageFile(id=identity, company_id=company, sha256=sha * 64, object_key=key,
                    url=f"https://images.example/{key}", mime_type="image/png", size_bytes=size))
            for identity, company, key in [(1, 1, self.old), (1, 1, self.old + "?alias=1"),
                    (1, 1, self.creative), (1, 1, "image-upload-tmp/company/1/tmp.png"),
                    (1, 1, self.other), (1, 1, self.conflict + "?old=1"),
                    (3, 1, self.conflict + "?old=2")]:
                url = f"https://images.example/{key}"
                db.add(ImageAddress(company_id=company, url_hash=digest(url), url=url, image_file_id=identity))
            url = "https://external.example/a.png"
            db.add(ImageAddress(company_id=1, url_hash=digest(url), url=url, image_file_id=1))
            for identity, company, file_id in [(1, 1, 1), (2, 1, 1), (3, 1, 1),
                    (4, 2, 2), (5, 1, None), (6, 1, 3)]:
                db.add(MaterialAsset(id=identity, company_id=company, image_file_id=file_id,
                    url="https://example/a.png", name="素材", sku=f"S{identity}", claimed_by=1))
            db.commit()

    def report(self, **kwargs):
        with self.sessions() as db:
            return collect(db, self.settings, **kwargs)

    def test_references_do_not_multiply_physical_bytes_and_cross_company_files_are_kept(self):
        def only_reads(connection, cursor, statement, parameters, context, many):
            self.assertEqual(statement.lstrip().split()[0].upper(), "SELECT")
        event.listen(self.engine, "before_cursor_execute", only_reads)
        report = self.report()
        totals = report["totals"]
        self.assertEqual(totals["files"], 3)  # 跨公司相同 SHA 保留独立文件。
        self.assertEqual(totals["file_bytes"], 4096)
        self.assertEqual(totals["materials"], 6)
        self.assertEqual(totals["unlinked_materials"], 1)
        self.assertEqual(totals["duplicate_material_groups"], 1)
        self.assertEqual(totals["extra_materials"], 2)
        self.assertEqual(totals["candidate_objects"], 2)
        self.assertEqual(totals["candidate_bytes"], 2048)
        self.assertEqual({row["object_key"] for row in report["r2_candidates"]}, {self.old, self.creative})
        self.assertEqual(self.report(company_id=1)["totals"]["candidate_bytes"], 2048)
        self.assertEqual(self.report(company_id=2)["totals"]["candidate_bytes"], 0)

    def test_listing_excludes_deleted_and_changed_objects_without_hiding_material_duplicates(self):
        report = self.report(object_sizes={self.canonical: 1024, self.other: 1024,
            self.third: 2048, self.creative: 999})
        self.assertEqual(report["totals"]["candidate_bytes"], 0)
        self.assertEqual(report["totals"]["missing_candidates"], 1)
        self.assertEqual(report["totals"]["changed_candidates"], 1)
        self.assertEqual(report["totals"]["extra_materials"], 2)
        report = self.report(object_sizes={self.old: 1024, self.creative: 1024})
        self.assertEqual(report["totals"]["candidate_objects"], 0)
        self.assertEqual(report["totals"]["invalid_canonical_files"], 3)

    def test_r2_verification_only_lists_objects(self):
        client = Mock()
        client.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": self.old, "Size": 1024}]},
            {"Contents": [{"Key": self.canonical, "Size": 1024}]}]
        with patch("scripts.image_duplicate_statistics.create_client", return_value=client), \
                patch("sys.stderr", new=StringIO()):
            sizes = list_sizes(self.settings)
        self.assertEqual(sizes, {self.old: 1024, self.canonical: 1024})
        client.get_paginator.assert_called_once_with("list_objects_v2")
        client.get_object.assert_not_called()
        client.delete_object.assert_not_called()
        self.assertEqual(self.report(object_sizes=sizes)["totals"]["candidate_bytes"], 1024)


if __name__ == "__main__":
    unittest.main()
