"""只读统计 R2 图片桶中现存图片的文件大小，不下载图片。"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import sys
from time import monotonic
from typing import TextIO

from botocore.exceptions import BotoCoreError, ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings, get_settings
from app.storage import StorageError, _r2_client


# 对象列表不返回 Content-Type，按扩展名判断图片；不逐张请求或下载对象。
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp", ".tif", ".tiff", ".svg"}
HEADERS = ("统计范围", "文件数量", "总大小", "平均大小")


@dataclass
class SizeStatistics:
    count: int = 0
    total_bytes: int = 0

    def add(self, size: int) -> None:
        self.count += 1
        self.total_bytes += size

    def cells(self, label: str) -> tuple[str, ...]:
        average = self.total_bytes / self.count if self.count else 0
        return (label, str(self.count), readable_size(self.total_bytes), readable_size(average))


def readable_size(size: float) -> str:
    size /= 1024
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    raise AssertionError("无法格式化大小")


def create_client(settings: Settings):
    endpoint = settings.r2_endpoint
    if not endpoint and settings.r2_account_id:
        endpoint = f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"
    required = (
        (endpoint, "R2_ENDPOINT 或 R2_ACCOUNT_ID"),
        (settings.r2_access_key_id, "R2_ACCESS_KEY_ID"),
        (settings.r2_secret_access_key, "R2_SECRET_ACCESS_KEY"),
        (settings.r2_bucket, "R2_BUCKET"),
    )
    for value, name in required:
        if not value:
            raise StorageError(f"未配置 {name}")
    return _r2_client(endpoint.rstrip("/"), settings.r2_access_key_id, settings.r2_secret_access_key)


def collect_statistics(
    client, bucket: str, prefix: str = "", *, progress: TextIO | None = None,
) -> list[tuple[str, SizeStatistics]]:
    all_objects, images, others = SizeStatistics(), SizeStatistics(), SizeStatistics()
    directories: dict[str, SizeStatistics] = {}
    started_at = monotonic()
    page_count = 0
    if progress is not None:
        print(f"开始扫描 R2 图片桶：{bucket}；对象前缀：{prefix or '（全部）'}；总对象数未知。",
              file=progress, flush=True)
    pages = client.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=prefix, PaginationConfig={"PageSize": 1000},
    )
    for page_count, page in enumerate(pages, start=1):
        for item in page.get("Contents", []):
            key, size = item["Key"], item["Size"]
            all_objects.add(size)
            if key.endswith("/") or PurePosixPath(key).suffix.lower() not in IMAGE_EXTENSIONS:
                others.add(size)
                continue
            images.add(size)
            directory = key.split("/", 1)[0] + "/" if "/" in key else "（桶根目录）"
            directories.setdefault(directory, SizeStatistics()).add(size)
        if progress is not None:
            print(f"已读取第 {page_count} 页；已扫描 {all_objects.count} 个对象，"
                  f"累计 {readable_size(all_objects.total_bytes)}；"
                  f"图片 {images.count} 张，共 {readable_size(images.total_bytes)}；"
                  f"耗时 {monotonic() - started_at:.1f} 秒。", file=progress, flush=True)
    if progress is not None:
        print(f"扫描完成：共 {page_count} 页、{all_objects.count} 个对象；"
              f"图片 {images.count} 张，共 {readable_size(images.total_bytes)}；"
              f"耗时 {monotonic() - started_at:.1f} 秒。", file=progress, flush=True)
    return [("全部对象", all_objects), ("图片合计", images), ("非图片对象", others)] + [
        (directory, directories[directory]) for directory in sorted(directories)
    ]


def write_report(rows: list[tuple[str, SizeStatistics]], output: TextIO, output_format: str) -> None:
    cells = [HEADERS, *(stats.cells(label) for label, stats in rows)]
    if output_format == "csv":
        csv.writer(output).writerows(cells)
        return
    # 使用制表符分列，所有大小仅显示二进制单位。
    for row in cells:
        output.write("\t".join(" ".join(cell.split()) for cell in row) + "\n")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读统计 R2 图片文件数量与大小，不下载图片")
    parser.add_argument("--prefix", default="", help="对象 key 前缀，例如 generated/；默认整个图片桶")
    parser.add_argument("--format", choices=("table", "csv"), default="table", help="输出格式，默认中文终端表格")
    parser.add_argument("--no-progress", action="store_true", help="关闭 stderr 中的扫描进度")
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        client = create_client(settings)
        rows = collect_statistics(client, settings.r2_bucket, args.prefix,
                                  progress=None if args.no_progress else sys.stderr)
    except StorageError as exc:
        print(f"R2 配置错误：{exc}", file=sys.stderr)
        return 1
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "未知错误")
        print(f"R2 列表读取失败（{code}），请检查桶名称及对象列表读取权限。", file=sys.stderr)
        return 1
    except BotoCoreError as exc:
        print(f"R2 连接失败（{type(exc).__name__}），请检查连接与配置。", file=sys.stderr)
        return 1
    if args.format == "table":
        print(f"图片桶：{settings.r2_bucket}；对象前缀：{args.prefix or '（全部）'}")
        print("图片按扩展名识别；大小使用 KiB、MiB、GiB、TiB，单位之间按 1024 换算。")
    write_report(rows, sys.stdout, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
