"""面板鉴权与口令配置（唯一权威说明：docs/requirements.md F6.4、docs/security.md §2）。"""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.config import MIN_PANEL_TOKEN_CHARS, REDACTED, Settings
from app.control.auth import Level, PanelAuth, extract_token

ADMIN = "admin-token-123456"
READONLY = "readonly-token-1234"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"BOT_TOKEN": "test-token", "LLM_API_KEY": "test-key"}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


class ExtractTokenTests(unittest.TestCase):
    def test_bearer_token_is_extracted(self) -> None:
        self.assertEqual("abc", extract_token("Bearer abc"))
        self.assertEqual("abc", extract_token("bearer   abc  "))

    def test_other_headers_yield_nothing(self) -> None:
        for header in (None, "", "abc", "Basic abc", "Bearer", "Token abc"):
            with self.subTest(header=header):
                self.assertEqual("", extract_token(header))


class PanelAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.auth = PanelAuth(admin_token=ADMIN, readonly_token=READONLY)

    def test_levels_are_resolved_by_exact_match(self) -> None:
        self.assertEqual(Level.ADMIN, self.auth.level_for(ADMIN))
        self.assertEqual(Level.VIEWER, self.auth.level_for(READONLY))
        self.assertEqual(Level.NONE, self.auth.level_for("admin-token-12345"))
        self.assertEqual(Level.NONE, self.auth.level_for(""))
        self.assertEqual(Level.ADMIN, self.auth.level_for(" " + ADMIN))  # 两侧空白会被忽略
        self.assertEqual(Level.NONE, self.auth.level_for(ADMIN + "x"))

    def test_header_round_trip(self) -> None:
        self.assertEqual(Level.ADMIN, self.auth.level_from_header(f"Bearer {ADMIN}"))
        self.assertEqual(Level.VIEWER, self.auth.level_from_header(f"Bearer {READONLY}"))
        self.assertEqual(Level.NONE, self.auth.level_from_header(READONLY))

    def test_unconfigured_auth_is_not_configured(self) -> None:
        self.assertFalse(PanelAuth().configured)
        self.assertFalse(PanelAuth(admin_token="").configured)
        self.assertTrue(PanelAuth(readonly_token=READONLY).configured)

    def test_readonly_only_deployment_has_no_admin(self) -> None:
        auth = PanelAuth(readonly_token=READONLY)
        self.assertEqual(Level.VIEWER, auth.level_for(READONLY))
        self.assertEqual(Level.NONE, auth.level_for(ADMIN))


class PanelSettingsTests(unittest.TestCase):
    def test_panel_is_disabled_and_local_by_default(self) -> None:
        settings = _settings()
        self.assertFalse(settings.panel_enabled)
        self.assertEqual("127.0.0.1", settings.panel_host)
        self.assertEqual(8787, settings.panel_port)
        self.assertEqual("", settings.panel_token)
        self.assertEqual((), settings.panel_tokens)

    def test_short_panel_token_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            _settings(PANEL_TOKEN="short")
        self.assertIn(str(MIN_PANEL_TOKEN_CHARS), str(caught.exception))

    def test_token_is_stripped_and_kept_secret(self) -> None:
        settings = _settings(PANEL_TOKEN=f"  {ADMIN}  ", PANEL_READONLY_TOKEN=READONLY)
        self.assertEqual(ADMIN, settings.panel_token)
        self.assertIn(ADMIN, settings.secrets)
        self.assertIn(READONLY, settings.secrets)
        self.assertIn("test-token", settings.secrets)

    def test_describe_never_prints_tokens(self) -> None:
        summary = _settings(PANEL_TOKEN=ADMIN, PANEL_READONLY_TOKEN=READONLY).describe()
        self.assertNotIn(ADMIN, summary)
        self.assertNotIn(READONLY, summary)
        self.assertIn(REDACTED, summary)
        self.assertIn("PANEL_ENABLED=False", summary)

    def test_describe_marks_missing_tokens(self) -> None:
        self.assertIn("PANEL_TOKEN=(未配置)", _settings().describe())


if __name__ == "__main__":
    unittest.main()
