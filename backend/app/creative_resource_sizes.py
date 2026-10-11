"""只读查询白底图文件大小；全进程限制 R2 并发并缓存成功结果。"""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import logging
from threading import Lock
from time import monotonic

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import get_settings
from .storage import _configuration, r2_object_key


logger = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 3600
CACHE_CAPACITY = 2000
_cache: OrderedDict[tuple[str, str, str], tuple[float, int]] = OrderedDict()
_cache_lock = Lock()
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="white-image-size")


@lru_cache(maxsize=4)
def _metadata_client(endpoint: str, access_key_id: str, secret_access_key: str):
    return boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key, region_name="auto",
        config=Config(
            signature_version="s3v4", s3={"addressing_style": "path"},
            connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 1},
            max_pool_connections=4,
        ),
    )


def _read_size(client, endpoint: str, bucket: str, key: str) -> dict:
    cache_key = (endpoint, bucket, key)
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and monotonic() - cached[0] < CACHE_TTL_SECONDS:
            _cache.move_to_end(cache_key)
            return {"size_bytes": cached[1], "status": "available"}
        _cache.pop(cache_key, None)
    try:
        size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
        if not isinstance(size, int) or size < 0:
            raise ValueError("无效的 R2 文件大小")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        status = "not_found" if code in {"404", "NoSuchKey", "NotFound"} else "unavailable"
        return {"size_bytes": None, "status": status}
    except Exception as exc:
        logger.warning("读取白底图大小失败：%s", type(exc).__name__)
        return {"size_bytes": None, "status": "unavailable"}
    with _cache_lock:
        _cache[cache_key] = (monotonic(), size)
        _cache.move_to_end(cache_key)
        while len(_cache) > CACHE_CAPACITY:
            _cache.popitem(last=False)
    return {"size_bytes": size, "status": "available"}


def read_white_image_sizes(company_id: int, images: list[tuple[int, str]]) -> list[dict]:
    settings = get_settings()
    keys = {
        image_id: key if key and key.startswith(f"template-white/company/{company_id}/") else None
        for image_id, url in images
        for key in [r2_object_key(url, settings)]
    }
    results = {}
    valid_keys = list(dict.fromkeys(key for key in keys.values() if key))
    if valid_keys:
        try:
            endpoint, access_key, secret_key, bucket, _ = _configuration(settings)
            client = _metadata_client(endpoint, access_key, secret_key)
            results = dict(zip(valid_keys, _executor.map(
                lambda key: _read_size(client, endpoint, bucket, key), valid_keys,
            )))
        except Exception as exc:
            logger.warning("白底图大小服务不可用：%s", type(exc).__name__)
    return [
        {"id": image_id, **(results.get(keys[image_id]) or {
            "size_bytes": None, "status": "invalid_url" if not keys[image_id] else "unavailable",
        })}
        for image_id, _ in images
    ]
