"""为业务回归创建已保存图片索引，不调用外部存储。"""
from io import BytesIO
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.image_files import add_address, by_url, digest
from app.models import ImageFile


def mock_image_storage(test_case):
    """替换网络与 R2，保留图片解码、内容去重和数据库登记的真实流程。"""
    content = BytesIO()
    Image.new("RGB", (4, 4), "red").save(content, format="PNG")
    download = test_case.enterContext(patch("app.image_files.download_image",
        new=AsyncMock(return_value=content.getvalue())))
    def save(content, mime, company_id, sha256):
        key = f"images/company/{company_id}/{sha256}.png"
        return key, f"https://images.example/{key}"
    upload = test_case.enterContext(patch("app.image_files.save_content_image", side_effect=save))
    return download, upload


def index_urls(db, company_id, urls):
    files = []
    for url in dict.fromkeys(url for url in urls if url):
        image_file = by_url(db, company_id, url)
        if not image_file:
            image_file = ImageFile(company_id=company_id, sha256=digest(url), object_key=f"fixture/{digest(url)}.png",
                url=url, mime_type="image/png", size_bytes=100)
            db.add(image_file)
            db.flush()
            add_address(db, company_id, url, image_file)
        files.append(image_file)
    db.commit()
    return files
