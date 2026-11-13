"""SKU 使用上限的文件配置与非默认额度。"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.config import Settings


class SkuLimitConfigTests(unittest.TestCase):
    def test_default_and_env_file_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings(_env_file=None).sku_use_limit, 3)
            with tempfile.TemporaryDirectory() as directory:
                env_file = Path(directory) / '.env'
                env_file.write_text('SKU_USE_LIMIT=5\n')
                self.assertEqual(Settings(_env_file=env_file).sku_use_limit, 5)
                os.environ['SKU_USE_LIMIT'] = '7'
                self.assertEqual(Settings(_env_file=env_file).sku_use_limit, 7)

    def test_invalid_limits_rejected(self):
        for value in ('0', '-1', '1.5', 'bad', '2147483648'):
            with self.subTest(value=value), patch.dict(os.environ, {'SKU_USE_LIMIT': value}):
                with self.assertRaises(ValidationError):
                    Settings(_env_file=None)

    def test_configured_limit_controls_allocation_and_error_message(self):
        # 独立进程覆盖启动时读取配置，避免改变其他测试已导入的额度常量。
        code = '''
from app.supply_quota import SKU_USE_LIMIT, allocate_links, validate_link_quota
assert SKU_USE_LIMIT == 5
candidates = [{"id": 1, "sku": "SKU1", "url": "https://img/1"}]
links = allocate_links(candidates, 1, 5, "seed", {}, sample=lambda items, count, rng: items[:count])
assert len(links) == 5
validate_link_quota(links, {})
for operation in (
    lambda: allocate_links(candidates, 1, 6, "seed", {}, sample=lambda *args: []),
    lambda: validate_link_quota(links, {"SKU1": 1}),
):
    try:
        operation()
    except ValueError as exc:
        assert "累计最多使用 5 次" in str(exc), str(exc)
    else:
        raise AssertionError("未按配置拦截超限")
'''
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                                env={**os.environ, 'SKU_USE_LIMIT': '5'}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
