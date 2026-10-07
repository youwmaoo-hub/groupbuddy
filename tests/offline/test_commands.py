"""群主命令通道（F5.2）：解析、管理员判定（fail-closed）、越权拒绝、命令不进模型。"""

from __future__ import annotations

import unittest

from app.gate.debounce import Debouncer
from app.gate.dedupe import UpdateDeduplicator
from app.gate.limits import ProactiveLimiter
from app.gate.trigger import TriggerDetector
from app.llm.loop import Responder
from app.ops.admin import AdminRegistry
from app.ops.commands import DENIED_TEXT, Command, CommandService, parse_command
from app.session.context import ContextBuilder
from app.session.runner import SessionRunner
from app.storage.repo import chat_settings, messages
from tests.offline.helpers import DbTestCase, FakeClock, FakeLLMClient, make_incoming


class ParseCommandTests(unittest.TestCase):
    def test_plain_command(self) -> None:
        command = parse_command("/settings")
        assert command is not None
        self.assertEqual((command.name, command.args, command.mention), ("settings", (), ""))

    def test_leading_space_and_arguments(self) -> None:
        command = parse_command("  /settings allow_write 1")
        assert command is not None
        self.assertEqual(command.name, "settings")
        self.assertEqual(command.args, ("allow_write", "1"))

    def test_mention_of_this_bot_is_accepted(self) -> None:
        command = parse_command("/settings@my_bot", bot_username="my_bot")
        assert command is not None
        self.assertEqual((command.name, command.mention), ("settings", "my_bot"))

    def test_mention_of_other_bot_is_ignored(self) -> None:
        self.assertIsNone(parse_command("/settings@other_bot", bot_username="my_bot"))

    def test_name_is_case_folded(self) -> None:
        command = parse_command("/Settings")
        assert command is not None
        self.assertEqual(command.name, "settings")

    def test_non_commands_return_none(self) -> None:
        for text in ("你好", "", "   ", "/", "//", "/ settings"):
            with self.subTest(text=text):
                self.assertIsNone(parse_command(text))


class AdminRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_admins_come_from_telegram_and_are_cached(self) -> None:
        clock = FakeClock()
        calls: list[int] = []

        async def fetch(chat_id: int) -> set[int]:
            calls.append(chat_id)
            return {7, 8}

        registry = AdminRegistry(fetch, clock=clock.monotonic)
        self.assertTrue(await registry.is_admin(-100, 7))
        self.assertFalse(await registry.is_admin(-100, 9))  # 普通成员
        self.assertEqual(calls, [-100])  # 命中缓存，不再请求 Telegram
        clock.advance(301.0)  # 缓存过期后重新查询
        self.assertTrue(await registry.is_admin(-100, 8))
        self.assertEqual(calls, [-100, -100])

    async def test_query_failure_denies_instead_of_permitting(self) -> None:
        clock = FakeClock()
        calls: list[int] = []

        async def fetch(chat_id: int) -> set[int]:
            calls.append(chat_id)
            raise RuntimeError("telegram 不可用")

        registry = AdminRegistry(fetch, clock=clock.monotonic)
        self.assertFalse(await registry.is_admin(-100, 7))
        self.assertFalse(await registry.is_admin(-100, 7))
        self.assertEqual(len(calls), 1)  # 失败结果短缓存，避免反复请求
        clock.advance(31.0)
        self.assertFalse(await registry.is_admin(-100, 7))
        self.assertEqual(len(calls), 2)

    async def test_each_chat_is_judged_separately(self) -> None:
        async def fetch(chat_id: int) -> set[int]:
            return {7} if chat_id == -100 else {8}

        registry = AdminRegistry(fetch)
        self.assertTrue(await registry.is_admin(-100, 7))
        self.assertFalse(await registry.is_admin(-200, 7))
        self.assertTrue(await registry.is_admin(-200, 8))


def make_service(connection, admins: set[int]) -> CommandService:
    async def fetch(_chat_id: int) -> set[int]:
        return set(admins)

    return CommandService(connection, AdminRegistry(fetch))


class CommandServiceTests(DbTestCase):
    async def test_admin_sees_current_settings(self) -> None:
        await chat_settings.upsert(self.connection, -100, mode="smart", allow_write=1)
        service = make_service(self.connection, {7})
        text = await service.reply_text(chat_id=-100, user_id=7, command=Command("settings"))
        assert text is not None
        self.assertIn("模式：smart", text)
        self.assertIn("write_file：开", text)
        self.assertIn("read_file：开", text)
        self.assertIn("host_info：关", text)
        self.assertIn("贴纸冷却：30 秒", text)

    async def test_defaults_are_shown_when_row_is_missing(self) -> None:
        service = make_service(self.connection, {7})
        text = await service.reply_text(chat_id=-100, user_id=7, command=Command("settings"))
        assert text is not None
        self.assertIn("模式：normal", text)

    async def test_non_admin_is_denied_without_leaking_settings(self) -> None:
        await chat_settings.upsert(self.connection, -100, mode="smart")
        service = make_service(self.connection, {7})
        text = await service.reply_text(chat_id=-100, user_id=9, command=Command("settings"))
        self.assertEqual(text, DENIED_TEXT)
        for leaked in ("模式", "smart", "allow_", "write_file", "管理员名单"):
            self.assertNotIn(leaked, text)

    async def test_admin_lookup_failure_denies(self) -> None:
        service = make_service(self.connection, set())
        text = await service.reply_text(chat_id=-100, user_id=7, command=Command("settings"))
        self.assertEqual(text, DENIED_TEXT)

    async def test_unknown_command_is_silent(self) -> None:
        service = make_service(self.connection, {7})
        self.assertIsNone(await service.reply_text(chat_id=-100, user_id=7, command=Command("nope")))


class _RecordingOutbound:
    """只记录出站内容；真实实现是 app/outbound/queue.py。"""

    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def enqueue(
        self,
        *,
        chat_id: int,
        chat_type: str,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> None:
        self.sent.append(
            {
                "chat_id": chat_id,
                "chat_type": chat_type,
                "text": text,
                "reply_to_message_id": reply_to_message_id,
            }
        )


def build_runner(connection, settings, *, outbound, llm, commands) -> SessionRunner:
    limiter = ProactiveLimiter(cooldown_seconds=20.0, window_seconds=300.0, max_per_window=3)
    return SessionRunner(
        settings=settings,
        connection=connection,
        deduplicator=UpdateDeduplicator(connection),
        detector=TriggerDetector(settings, limiter),
        limiter=limiter,
        debouncer=Debouncer(quiet_seconds=1.0, max_messages=5),
        context_builder=ContextBuilder(connection, settings),
        responder=Responder(llm, settings, None),
        outbound=outbound,
        commands=commands,
        bot_username="my_bot",
    )


class RunnerCommandTests(DbTestCase):
    async def test_admin_command_replies_without_touching_model_or_history(self) -> None:
        llm = FakeLLMClient()
        outbound = _RecordingOutbound()
        runner = build_runner(
            self.connection,
            self.settings,
            outbound=outbound,
            llm=llm,
            commands=make_service(self.connection, {7}),
        )
        incoming = make_incoming(
            update_id=1, chat_id=-100, message_id=5, user_id=7, text="/settings"
        )
        await runner.handle(incoming)
        self.assertEqual(len(outbound.sent), 1)
        self.assertEqual(outbound.sent[0]["chat_id"], -100)
        self.assertEqual(outbound.sent[0]["reply_to_message_id"], 5)
        self.assertIn("当前群设置", str(outbound.sent[0]["text"]))
        self.assertEqual(llm.calls, [])  # 命令不进模型
        self.assertEqual(await messages.recent(self.connection, chat_id=-100, limit=10), [])

        await runner.handle(incoming)  # 同一个 update 重放：去重只回一次
        self.assertEqual(len(outbound.sent), 1)

    async def test_non_admin_command_is_rejected(self) -> None:
        outbound = _RecordingOutbound()
        runner = build_runner(
            self.connection,
            self.settings,
            outbound=outbound,
            llm=FakeLLMClient(),
            commands=make_service(self.connection, {7}),
        )
        await runner.handle(
            make_incoming(update_id=2, chat_id=-100, message_id=6, user_id=9, text="/settings")
        )
        self.assertEqual([entry["text"] for entry in outbound.sent], [DENIED_TEXT])

    async def test_unknown_command_is_silently_dropped(self) -> None:
        outbound = _RecordingOutbound()
        runner = build_runner(
            self.connection,
            self.settings,
            outbound=outbound,
            llm=FakeLLMClient(),
            commands=make_service(self.connection, {7}),
        )
        await runner.handle(
            make_incoming(update_id=3, chat_id=-100, message_id=7, user_id=7, text="/clear")
        )
        self.assertEqual(outbound.sent, [])

    async def test_private_chat_command_is_dropped(self) -> None:
        outbound = _RecordingOutbound()
        runner = build_runner(
            self.connection,
            self.settings,
            outbound=outbound,
            llm=FakeLLMClient(),
            commands=make_service(self.connection, {7}),
        )
        await runner.handle(
            make_incoming(
                update_id=4,
                chat_id=7,
                message_id=8,
                user_id=7,
                text="/settings",
                chat_type="private",
            )
        )
        self.assertEqual(outbound.sent, [])

    async def test_command_from_other_bot_mention_is_dropped(self) -> None:
        outbound = _RecordingOutbound()
        runner = build_runner(
            self.connection,
            self.settings,
            outbound=outbound,
            llm=FakeLLMClient(),
            commands=make_service(self.connection, {7}),
        )
        await runner.handle(
            make_incoming(
                update_id=5, chat_id=-100, message_id=9, user_id=7, text="/settings@other_bot"
            )
        )
        self.assertEqual(outbound.sent, [])


if __name__ == "__main__":
    unittest.main()
