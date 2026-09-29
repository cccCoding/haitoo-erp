import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import main
from app.database import Base, get_db
from app.login_rate_limit import (
    EMAIL_WINDOW,
    IP_WINDOW,
    clear_email_failures,
    client_ip,
    count_ip_attempt,
    lock_email_failures,
    record_email_failure,
)
from app.models import Role, User
from app.security import hash_password


class LoginRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.db"
        self.engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False, "timeout": 20})
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            db.add(User(email="member@example.com", name="Member", password_hash=hash_password("CorrectPassword123"), role=Role.MEMBER))
            db.commit()

        def override_get_db():
            with self.session_factory() as db:
                yield db

        main.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        main.app.dependency_overrides.clear()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def login(self, email: str, password: str = "WrongPassword"):
        return self.client.post("/auth/login", json={"email": email, "password": password})

    def test_ip_limit_allows_twenty_attempts_then_returns_429(self) -> None:
        for index in range(20):
            self.assertEqual(self.login(f"missing-{index}@example.com").status_code, 401)
        response = self.login("another@example.com")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"], "尝试过于频繁，请稍后再试")
        self.assertGreater(int(response.headers["Retry-After"]), 0)

    def test_email_limit_allows_five_failures_then_resets_after_success(self) -> None:
        for _ in range(4):
            self.assertEqual(self.login("member@example.com").status_code, 401)
        self.assertEqual(self.login("member@example.com", "CorrectPassword123").status_code, 200)
        for _ in range(5):
            self.assertEqual(self.login("member@example.com").status_code, 401)
        response = self.login("member@example.com", "CorrectPassword123")
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["Retry-After"]), 0)
        self.assertEqual(self.login("another@example.com", "WrongPassword").status_code, 401)

    def test_ip_and_email_windows_expire_and_keys_are_independent(self) -> None:
        started = datetime(2026, 9, 29, 10, 0, 0)
        with self.session_factory() as db:
            for _ in range(20):
                count_ip_attempt(db, "192.0.2.1", started)
            with self.assertRaises(HTTPException) as caught:
                count_ip_attempt(db, "192.0.2.1", started + IP_WINDOW - timedelta(seconds=1))
            self.assertEqual(caught.exception.status_code, 429)
            count_ip_attempt(db, "192.0.2.2", started)
            count_ip_attempt(db, "192.0.2.1", started + IP_WINDOW)

            for _ in range(5):
                row = lock_email_failures(db, "missing@example.com", started)
                record_email_failure(db, row, started)
            with self.assertRaises(HTTPException) as caught:
                lock_email_failures(db, "MISSING@example.com", started + EMAIL_WINDOW - timedelta(seconds=1))
            self.assertEqual(caught.exception.status_code, 429)
            other = lock_email_failures(db, "other@example.com", started)
            clear_email_failures(db, other)
            expired = lock_email_failures(db, "missing@example.com", started + EMAIL_WINDOW)
            record_email_failure(db, expired, started + EMAIL_WINDOW)

    def test_separate_sessions_share_atomic_ip_counter(self) -> None:
        now = datetime(2026, 9, 29, 10, 0, 0)

        def attempt(_: int) -> int:
            with self.session_factory() as db:
                try:
                    count_ip_attempt(db, "192.0.2.10", now)
                except HTTPException as exc:
                    return exc.status_code
                return 200

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(attempt, range(25)))
        self.assertEqual(results.count(200), 20)
        self.assertEqual(results.count(429), 5)

    def test_separate_sessions_serialize_email_failures(self) -> None:
        now = datetime(2026, 9, 29, 10, 0, 0)

        def failure(_: int) -> int:
            with self.session_factory() as db:
                try:
                    counter = lock_email_failures(db, "member@example.com", now)
                except HTTPException as exc:
                    return exc.status_code
                record_email_failure(db, counter, now)
                return 401

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(failure, range(8)))
        self.assertEqual(results.count(401), 5)
        self.assertEqual(results.count(429), 3)

    def test_client_ip_ignores_forged_headers_on_direct_and_public_peers(self) -> None:
        def request(peer: str, headers: list[tuple[bytes, bytes]]) -> Request:
            return Request({"type": "http", "method": "POST", "path": "/auth/login", "headers": headers, "client": (peer, 1234), "server": ("example.com", 443), "scheme": "https"})

        forged = request("192.0.2.20", [(b"cf-connecting-ip", b"203.0.113.9"), (b"x-real-ip", b"203.0.113.8"), (b"x-forwarded-for", b"203.0.113.7")])
        with patch("app.login_rate_limit.get_settings", return_value=SimpleNamespace(login_client_ip_source="peer")):
            self.assertEqual(client_ip(forged), "192.0.2.20")
        with patch("app.login_rate_limit.get_settings", return_value=SimpleNamespace(login_client_ip_source="auto")):
            self.assertEqual(client_ip(forged), "192.0.2.20")
            self.assertEqual(client_ip(request("172.20.0.5", [(b"cf-connecting-ip", b"203.0.113.9"), (b"x-real-ip", b"203.0.113.8")])), "203.0.113.9")
            self.assertEqual(client_ip(request("172.20.0.5", [(b"x-real-ip", b"203.0.113.8"), (b"x-forwarded-for", b"198.51.100.1")])), "203.0.113.8")
            self.assertEqual(client_ip(request("172.20.0.5", [(b"cf-connecting-ip", b"bad"), (b"x-real-ip", b"203.0.113.8")])), "172.20.0.5")


if __name__ == "__main__":
    unittest.main()
