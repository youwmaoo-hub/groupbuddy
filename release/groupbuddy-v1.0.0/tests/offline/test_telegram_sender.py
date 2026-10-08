"""Telegram 发送器离线测试：异常翻译与「不设置 parse_mode」（app/telegram/sender.py、T25）。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import SendMessage

from app.outbound.queue import RateLimited, SendFailed
from app.telegram.sender import AiogramSender

METHOD = SendMessage(chat_id=1, text="x")


class _FakeBot:
    """只实现 sender 用到的两个方法；调用参数原样记录。"""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._error = error

    async def send_message(self, **kwargs: object) -> object:
        self.calls.append(("send_message", kwargs))
        if self._error is not None:
            raise self._error
        return SimpleNamespace(message_id=7)

    async def send_sticker(self, **kwargs: object) -> object:
        self.calls.append(("send_sticker", kwargs))
        if self._error is not None:
            raise self._error
        return SimpleNamespace(message_id=8)


class SendMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_id_is_returned_and_parse_mode_is_not_set(self) -> None:
        bot = _FakeBot()
        sender = AiogramSender(bot)  # type: ignore[arg-type]

        message_id = await sender.send_message(chat_id=-100, text="**粗体** [x](y)", reply_to_message_id=5)

        self.assertEqual(7, message_id)
        name, kwargs = bot.calls[0]
        self.assertEqual("send_message", name)
        self.assertEqual(-100, kwargs["chat_id"])
        self.assertEqual("**粗体** [x](y)", kwargs["text"])
        self.assertEqual(5, kwargs["reply_to_message_id"])
        # 模型输出里的 Markdown 不应触发 Telegram 解析错误
        self.assertNotIn("parse_mode", kwargs)

    async def test_without_reply_target_the_field_is_still_passed_as_none(self) -> None:
        bot = _FakeBot()
        sender = AiogramSender(bot)  # type: ignore[arg-type]

        await sender.send_message(chat_id=1, text="hi")

        self.assertIsNone(bot.calls[0][1]["reply_to_message_id"])

    async def test_retry_after_becomes_rate_limited_with_the_same_delay(self) -> None:
        error = TelegramRetryAfter(METHOD, "flood control", 12)
        sender = AiogramSender(_FakeBot(error=error))  # type: ignore[arg-type]

        with self.assertRaises(RateLimited) as caught:
            await sender.send_message(chat_id=1, text="hi")

        self.assertEqual(12.0, caught.exception.retry_after)
        self.assertIs(error, caught.exception.__cause__)

    async def test_api_error_becomes_send_failed_with_the_original_text(self) -> None:
        error = TelegramBadRequest(METHOD, "chat not found")
        sender = AiogramSender(_FakeBot(error=error))  # type: ignore[arg-type]

        with self.assertRaises(SendFailed) as caught:
            await sender.send_message(chat_id=1, text="hi")

        self.assertIn("TelegramBadRequest", str(caught.exception))
        self.assertIn("chat not found", str(caught.exception))
        self.assertIs(error, caught.exception.__cause__)


class SendStickerTests(unittest.IsolatedAsyncioTestCase):
    async def test_file_id_is_sent_untouched(self) -> None:
        bot = _FakeBot()
        sender = AiogramSender(bot)  # type: ignore[arg-type]

        message_id = await sender.send_sticker(chat_id=-100, file_id="CAACAgIAAxkBAAE")

        self.assertEqual(8, message_id)
        name, kwargs = bot.calls[0]
        self.assertEqual("send_sticker", name)
        self.assertEqual({"chat_id": -100, "sticker": "CAACAgIAAxkBAAE"}, kwargs)

    async def test_retry_after_becomes_rate_limited(self) -> None:
        error = TelegramRetryAfter(METHOD, "flood control", 3)
        sender = AiogramSender(_FakeBot(error=error))  # type: ignore[arg-type]

        with self.assertRaises(RateLimited) as caught:
            await sender.send_sticker(chat_id=1, file_id="f")

        self.assertEqual(3.0, caught.exception.retry_after)
        self.assertIs(error, caught.exception.__cause__)

    async def test_api_error_becomes_send_failed(self) -> None:
        error = TelegramBadRequest(METHOD, "sticker file is invalid")
        sender = AiogramSender(_FakeBot(error=error))  # type: ignore[arg-type]

        with self.assertRaises(SendFailed) as caught:
            await sender.send_sticker(chat_id=1, file_id="f")

        self.assertIn("TelegramBadRequest", str(caught.exception))
        self.assertIn("sticker file is invalid", str(caught.exception))
        self.assertIs(error, caught.exception.__cause__)
