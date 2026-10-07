import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_settings import debug_scope, validate_erp_url


class RuntimeSettingsTests(unittest.TestCase):
    def test_http_requires_explicit_debug_and_loopback(self):
        for host in ("127.0.0.1", "localhost", "[::1]"):
            url = f"http://{host}:8001"
            with self.assertRaises(RuntimeError):
                validate_erp_url(url)
            self.assertEqual(validate_erp_url(url, local_debug=True), url)
        for host in ("192.168.1.5", "example.com", "127.0.0.1.example.com", "0.0.0.0"):
            with self.assertRaises(RuntimeError):
                validate_erp_url(f"http://{host}:8001", local_debug=True)

    def test_https_and_malformed_addresses(self):
        self.assertEqual(validate_erp_url("https://api.example.com/"), "https://api.example.com")
        for url in ("https://", "https://user:secret@example.com", "https://example.com?token=secret", "https://example.com:bad"):
            with self.assertRaises(RuntimeError):
                validate_erp_url(url)

    def test_debug_identity_is_stable_and_separated_by_server(self):
        first = debug_scope("http://127.0.0.1:8001")
        self.assertEqual(first, debug_scope("http://127.0.0.1:8001"))
        self.assertNotEqual(first, debug_scope("http://127.0.0.1:8002"))

