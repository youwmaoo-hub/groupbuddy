"""日志层离线测试：凭据脱敏过滤器与根 logger 装配（AGENTS.md 硬规则 11、T25）。"""

from __future__ import annotations

import io
import logging
import tempfile
import unittest
from pathlib import Path

from app.config import REDACTED
from app.logging_setup import SecretFilter, get_logger, setup_logging
from tests.offline.helpers import make_settings

NOISY_LOGGERS = ("aiogram", "httpx", "httpcore", "openai")


def _record(msg: object, args: object = (), name: str = "app") -> logging.LogRecord:
    return logging.LogRecord(name, logging.INFO, __file__, 10, msg, args, None)  # type: ignore[arg-type]


class SecretFilterTests(unittest.TestCase):
    """过滤器在落盘/落终端之前替换凭据：msg 与 args（tuple/dict）三条路径。"""

    def test_message_text_is_redacted(self) -> None:
        record = _record("API_KEY=test-key")
        self.assertTrue(SecretFilter(("test-key",)).filter(record))
        self.assertEqual(f"API_KEY={REDACTED}", record.msg)

    def test_tuple_arguments_are_redacted(self) -> None:
        record = _record("令牌 %s 已加载", ("test-token",))
        SecretFilter(("test-token",)).filter(record)
        self.assertEqual((REDACTED,), record.args)
        self.assertNotIn("test-token", record.getMessage())

    def test_dict_arguments_are_redacted(self) -> None:
        record = _record("令牌 %(token)s 已加载", {"token": "test-token", "other": "ok"})
        SecretFilter(("test-token",)).filter(record)
        self.assertEqual({"token": REDACTED, "other": "ok"}, record.args)

    def test_all_secrets_are_replaced_wherever_they_appear(self) -> None:
        record = _record("bot=test-token llm=test-key")
        SecretFilter(("test-token", "test-key")).filter(record)
        self.assertEqual(f"bot={REDACTED} llm={REDACTED}", record.msg)

    def test_unrelated_text_is_untouched(self) -> None:
        record = _record("普通日志 %s", ("hello",))
        SecretFilter(("test-token",)).filter(record)
        self.assertEqual("普通日志 %s", record.msg)
        self.assertEqual(("hello",), record.args)

    def test_empty_secrets_change_nothing(self) -> None:
        record = _record("测试", ("x",))
        self.assertTrue(SecretFilter(()).filter(record))
        self.assertEqual(("x",), record.args)

    def test_filtered_output_reaches_the_handler_redacted(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(SecretFilter(("test-token",)))
        logger = logging.getLogger("tests.offline.redaction")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            logger.info("令牌 %s", "test-token")
        finally:
            logger.removeHandler(handler)
            handler.close()
        output = stream.getvalue()
        self.assertIn(REDACTED, output)
        self.assertNotIn("test-token", output)


class SetupLoggingTests(unittest.TestCase):
    """setup_logging 装配根 logger；测试结束后必须还原全局状态。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = logging.getLogger()
        self._saved_handlers = root.handlers[:]
        self._saved_level = root.level
        self._saved_noisy = {name: logging.getLogger(name).level for name in NOISY_LOGGERS}
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        root = logging.getLogger()
        for handler in root.handlers:
            handler.close()
        root.handlers[:] = self._saved_handlers
        root.setLevel(self._saved_level)
        for name, level in self._saved_noisy.items():
            logging.getLogger(name).setLevel(level)

    def test_handlers_filters_and_file_are_wired(self) -> None:
        settings = make_settings(Path(self._tmp.name))
        logger = setup_logging(settings)

        self.assertEqual("app", logger.name)
        root = logging.getLogger()
        self.assertEqual(2, len(root.handlers))
        for handler in root.handlers:
            self.assertTrue(any(isinstance(item, SecretFilter) for item in handler.filters))
            self.assertIsNotNone(handler.formatter)

        path = settings.log_dir / settings.log_file
        self.assertTrue(path.exists())

        logger.info("令牌 %s", settings.secrets[0])
        for handler in root.handlers:
            handler.flush()
        text = path.read_text(encoding="utf-8")
        self.assertIn("配置加载完成", text)
        self.assertIn(REDACTED, text)
        for secret in settings.secrets:
            self.assertNotIn(secret, text)

    def test_level_and_third_party_noise_follow_settings(self) -> None:
        settings = make_settings(Path(self._tmp.name), LOG_LEVEL="DEBUG")
        setup_logging(settings)

        self.assertEqual(logging.DEBUG, logging.getLogger().level)
        for name in NOISY_LOGGERS:
            self.assertEqual(logging.WARNING, logging.getLogger(name).level)

    def test_get_logger_returns_the_named_logger(self) -> None:
        self.assertIs(logging.getLogger("app.session.runner"), get_logger("app.session.runner"))
