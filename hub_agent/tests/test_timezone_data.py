"""模拟 Windows 没有系统时区库，验证随包携带的站点时区。"""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

AGENT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_ROOT))
from plugins.tiktok import site_timezone


class TimezoneDataTests(unittest.TestCase):
    def test_site_date_range_without_system_timezone_database(self):
        # 独立进程避免已有 ZoneInfo 缓存或 macOS 系统时区掩盖资源缺失。
        result = subprocess.run(
            [sys.executable, '-c', '''
from datetime import datetime, timedelta, timezone
from plugins.tiktok import PROFILES, site_timezone
for site, _ in PROFILES:
    zone = site_timezone(site)
    local = datetime(2026, 11, 11, 20, tzinfo=timezone.utc).astimezone(zone)
    assert local.isoformat() == '2026-11-12T04:00:00+08:00'
    today = local.replace(hour=0, minute=0, second=0, microsecond=0)
    assert (today-timedelta(days=29)).strftime('%Y-%m-%d') == '2026-10-14'
    assert (today+timedelta(days=1)).strftime('%Y-%m-%d') == '2026-11-13'
'''],
            cwd=AGENT_ROOT, env={**os.environ, 'PYTHONTZPATH': ''},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_timezone_reports_actionable_error(self):
        with patch('plugins.tiktok.ZoneInfo', side_effect=ZoneInfoNotFoundError('missing')):
            with self.assertRaisesRegex(RuntimeError, '缺少站点时区数据'):
                site_timezone('MY')
