"""aiogram 适配层离线测试：update → IncomingMessage → runner，异常不外抛（T25）。

不经过 aiogram 分发：直接取 Router 上注册的回调，传鸭子类型的 update（见 tests/offline/test_gate.py 同一思路）。
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from app.telegram import handlers as handlers_module
from app.telegram.handlers import build_router
from app.telegram.parse import IncomingMessage

BOT_ID = 99
BOT_USERNAME = "mybot"


def _update(
    *,
    update_id: int = 5,
    chat_id: int = -100,
    user_id: int = 42,
    text: str = "@mybot 你好",
    message_id: int = 11,
    with_message: bool = True,
) -> SimpleNamespace:
    if not with_message:
        return SimpleNamespace(update_id=update_id, message=None)
    return SimpleNamespace(
        update_id=update_id,
        message=SimpleNamespace(
            chat=SimpleNamespace(id=chat_id, type="supergroup"),
            from_user=SimpleNamespace(id=user_id, is_bot=False),
            text=text,
            caption=None,
            message_id=message_id,
            message_thread_id=None,
            entities=None,
            reply_to_message=None,
        ),
    )


class _FakeRunner:
    """记录 handle 收到的消息；可注入失败。"""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.handled: list[IncomingMessage] = []
        self._error = error

    async def handle(self, incoming: IncomingMessage) -> None:
        self.handled.append(incoming)
        if self._error is not None:
            raise self._error


def _callback(router: object):
    """取出 @router.message() 注册的回调（绕过 aiogram 的分发与依赖注入）。"""
    return router.message.handlers[0].callback  # type: ignore[attr-defined]


class BuildRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_is_parsed_and_forwarded_to_the_runner(self) -> None:
        runner = _FakeRunner()
        router = build_router(runner=runner, bot_id=BOT_ID, bot_username=BOT_USERNAME)  # type: ignore[arg-type]
        update = _update()

        await _callback(router)(message=update.message, event_update=update)

        self.assertEqual(1, len(runner.handled))
        incoming = runner.handled[0]
        self.assertEqual(5, incoming.update_id)
        self.assertEqual(-100, incoming.chat_id)
        self.assertEqual(11, incoming.message_id)
        self.assertEqual(42, incoming.user_id)
        self.assertEqual("supergroup", incoming.chat_type)
        self.assertEqual("@mybot 你好", incoming.text)
        self.assertTrue(incoming.mentions_bot)
        self.assertFalse(incoming.is_bot_author)

    async def test_configured_alias_is_recognized_as_a_mention(self) -> None:
        runner = _FakeRunner()
        router = build_router(
            runner=runner,  # type: ignore[arg-type]
            bot_id=BOT_ID,
            bot_username=BOT_USERNAME,
            aliases=("alias",),
        )
        update = _update(text="@alias 在吗")

        await _callback(router)(message=update.message, event_update=update)

        self.assertTrue(runner.handled[0].mentions_bot)

    async def test_unrelated_update_is_ignored(self) -> None:
        runner = _FakeRunner()
        router = build_router(runner=runner, bot_id=BOT_ID, bot_username=BOT_USERNAME)  # type: ignore[arg-type]
        update = _update(with_message=False)

        await _callback(router)(message=None, event_update=update)

        self.assertEqual([], runner.handled)

    async def test_runner_failure_is_swallowed_and_logged(self) -> None:
        runner = _FakeRunner(error=RuntimeError("boom"))
        router = build_router(runner=runner, bot_id=BOT_ID, bot_username=BOT_USERNAME)  # type: ignore[arg-type]
        update = _update()

        with mock.patch.object(handlers_module.logger, "exception") as logged:
            await _callback(router)(message=update.message, event_update=update)

        # 接收路径不允许把异常抛回 aiogram，否则会打断轮询
        logged.assert_called_once()
        args = logged.call_args.args
        self.assertEqual("消息处理失败 chat_id=%s update_id=%s", args[0])
        self.assertIn(-100, args)
        self.assertIn(5, args)
