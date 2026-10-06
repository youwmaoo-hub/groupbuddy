"""配置层：脱敏、别名解析、按 TIMEZONE 归属日期。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.config import REDACTED, redact, today_in_timezone
from tests.offline.helpers import make_settings


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_describe_masks_secrets(self) -> None:
        settings = make_settings(self.tmp)
        text = settings.describe()
        self.assertNotIn("test-token", text)
        self.assertNotIn("test-key", text)
        self.assertIn(REDACTED, text)
        self.assertIn("deepseek-flash", text)

    def test_redact_replaces_all_secrets(self) -> None:
        settings = make_settings(self.tmp)
        text = redact("token=test-token key=test-key", settings.secrets)
        self.assertNotIn("test-token", text)
        self.assertNotIn("test-key", text)

    def test_aliases_support_chinese_comma(self) -> None:
        settings = make_settings(self.tmp, BOT_ALIASES="小助手，helper , ,")
        self.assertEqual(settings.aliases, ("小助手", "helper"))

    def test_today_follows_timezone(self) -> None:
        settings = make_settings(self.tmp, TIMEZONE="Asia/Shanghai")
        moment = datetime(2026, 1, 1, 16, 30, tzinfo=timezone.utc)  # 北京时间次日 00:30
        self.assertEqual(today_in_timezone(settings, moment), "2026-01-02")

    def test_today_falls_back_on_bad_timezone(self) -> None:
        settings = make_settings(self.tmp, TIMEZONE="Not/AZone")
        moment = datetime(2026, 1, 1, 16, 30, tzinfo=timezone.utc)
        self.assertEqual(today_in_timezone(settings, moment), moment.astimezone().strftime("%Y-%m-%d"))


if __name__ == "__main__":
    unittest.main()
