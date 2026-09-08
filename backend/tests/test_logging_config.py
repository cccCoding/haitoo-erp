import logging
import unittest
from datetime import datetime, timezone

from app.logging_config import Iso8601Formatter, configure_logging


class LoggingConfigTests(unittest.TestCase):
    def test_formatter_includes_milliseconds_and_timezone(self) -> None:
        record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello", (), None)
        record.created = datetime(2026, 9, 8, 1, 2, 3, 456000, tzinfo=timezone.utc).timestamp()
        formatter = Iso8601Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", timezone_name="Asia/Hong_Kong")

        output = formatter.format(record)

        self.assertEqual(output, "2026-09-08T09:02:03.456+08:00 | INFO | app.test | hello")

    def test_invalid_timezone_falls_back_to_utc(self) -> None:
        formatter = Iso8601Formatter("%(asctime)s", timezone_name="invalid/timezone")
        record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello", (), None)

        self.assertTrue(formatter.format(record).endswith("+00:00"))

    def test_uvicorn_access_log_is_replaced_by_application_request_log(self) -> None:
        configure_logging()

        access_logger = logging.getLogger("uvicorn.access")
        self.assertEqual(access_logger.handlers, [])
        self.assertFalse(access_logger.propagate)
        self.assertEqual(logging.getLogger("httpx").level, logging.WARNING)


if __name__ == "__main__":
    unittest.main()
