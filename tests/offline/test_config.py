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

    def test_bot_instance_groups_credentials(self) -> None:
        settings = make_settings(self.tmp)
        instance = settings.bot_instance()
        self.assertEqual(instance.instance_id, "default")
        self.assertEqual(instance.bot_token, "test-token")
        self.assertEqual(instance.llm.api_key, "test-key")
        self.assertEqual(instance.llm.model, "deepseek-flash")
        self.assertIn("test-token", instance.secret_values())
        self.assertIn("test-key", instance.secret_values())
        self.assertEqual(set(instance.secret_values()), set(settings.secrets))

    def test_bot_instance_id_can_be_overridden(self) -> None:
        settings = make_settings(self.tmp, BOT_INSTANCE_ID="alpha")
        self.assertEqual(settings.bot_instance().instance_id, "alpha")
        self.assertIn("BOT_INSTANCE_ID=alpha", settings.describe())

    def test_aliases_support_chinese_comma(self) -> None:
        settings = make_settings(self.tmp, BOT_ALIASES="小助手，helper , ,")
        self.assertEqual(settings.aliases, ("小助手", "helper"))

    def test_reply_max_chars_defaults_to_280_and_can_be_disabled(self) -> None:
        self.assertEqual(make_settings(self.tmp).reply_max_chars, 280)
        self.assertEqual(make_settings(self.tmp, REPLY_MAX_CHARS="0").reply_max_chars, 0)
        self.assertEqual(make_settings(self.tmp, REPLY_MAX_CHARS="120").reply_max_chars, 120)

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
