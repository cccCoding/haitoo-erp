"""历史图片的磁盘缓存；元数据最后原子落盘，中断后可安全重跑。"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from app.image_download import MAX_IMAGE_BYTES, decode_image, download_image
from app.image_files import digest
from app.storage import r2_object_key, read_image_object


class ImageBackfillCache:
    def __init__(self, directory):
        self.directory = Path(directory)

    def _company_dir(self, company_id):
        if not isinstance(company_id, int) or company_id <= 0:
            raise ValueError("缓存公司 ID 必须为正整数")
        return self.directory / str(company_id)

    def read(self, company_id, url):
        directory = self._company_dir(company_id)
        metadata_path = directory / "addresses" / f"{digest(url)}.json"
        if not metadata_path.exists():
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        sha = metadata.get("sha256", "")
        if metadata.get("url") != url or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("图片缓存元数据不合法，请移除该地址缓存后重新预缓存")
        path = directory / "files" / sha
        if not path.exists():
            return None
        with path.open("rb") as stream:
            content = stream.read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES or len(content) != metadata.get("size_bytes") or digest(content) != sha:
            raise ValueError("图片缓存校验失败，请移除该地址缓存后重新预缓存")
        return content

    @staticmethod
    def _write_atomic(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def prepare(self, company_id, url):
        content = self.read(company_id, url)
        if content is not None:
            return True
        key = r2_object_key(url)
        content = read_image_object(key) if key else asyncio.run(download_image(url))
        mime = decode_image(content)
        sha = digest(content)
        directory = self._company_dir(company_id)
        self._write_atomic(directory / "files" / sha, content)
        metadata = {"url": url, "sha256": sha, "mime_type": mime, "size_bytes": len(content)}
        self._write_atomic(directory / "addresses" / f"{digest(url)}.json",
            json.dumps(metadata, ensure_ascii=False).encode("utf-8"))
        return False
