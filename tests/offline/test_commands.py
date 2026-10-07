"""群主命令通道（F5.1/F5.2）：解析、管理员判定（fail-closed）、越权拒绝、设置写入、命令不进模型。"""

from __future__ import annotations

import unittest
from unittest import mock

import aiosqlite

from app.gate.debounce import Debouncer
from app.gate.dedupe import UpdateDeduplicator
from app.gate.limits import ProactiveLimiter
from app.gate.trigger import TriggerDetector
from app.llm.loop import Responder
from app.ops.admin import AdminRegistry, ChatRoles
from app.ops.commands import (
    CLEAR_FAILED_TEXT,
    CLEAR_USAGE,
    COOLDOWN_MAX_SECONDS,
    DENIED_TEXT,
    FIELD_NAMES,
    PERSONA,
    USAGE_TEXT,
    WRITE_FAILED_TEXT,
    Command,
    CommandService,
    parse_command,
)
from app.session.context import ContextBuilder
from app.session.runner import SessionRunner
from app.storage.repo import chat_settings, messages, summaries
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

        async def fetch(chat_id: int) -> ChatRoles:
            calls.append(chat_id)
            return ChatRoles(admins=frozenset({7, 8}), owner_id=7)

        registry = AdminRegistry(fetch, clock=clock.monotonic)
        self.assertTrue(await registry.is_admin(-100, 7))
        self.assertFalse(await registry.is_admin(-100, 9))  # 普通成员
        self.assertEqual(calls, [-100])  # 命中缓存，不再请求 Telegram
        clock.advance(301.0)  # 缓存过期后重新查询
        self.assertTrue(await registry.is_admin(-100, 8))
        self.assertEqual(calls, [-100, -100])

    async def test_owner_is_the_creator_not_any_administrator(self) -> None:
        async def fetch(_chat_id: int) -> ChatRoles:
            return ChatRoles(admins=frozenset({7, 8}), owner_id=7)

        registry = AdminRegistry(fetch)
        self.assertTrue(await registry.is_owner(-100, 7))
        self.assertFalse(await registry.is_owner(-100, 8))  # 普通管理员不算群主
        self.assertFalse(await registry.is_owner(-100, 9))  # 成员
        self.assertTrue(await registry.is_admin(-100, 8))  # 管理员身份不受影响

    async def test_chat_without_creator_has_no_owner(self) -> None:
        async def fetch(_chat_id: int) -> ChatRoles:
            return ChatRoles(admins=frozenset({7}), owner_id=None)

        registry = AdminRegistry(fetch)
        self.assertFalse(await registry.is_owner(-100, 7))
        self.assertTrue(await registry.is_admin(-100, 7))

    async def test_query_failure_denies_instead_of_permitting(self) -> None:
        clock = FakeClock()
        calls: list[int] = []

        async def fetch(chat_id: int) -> ChatRoles:
            calls.append(chat_id)
            raise RuntimeError("telegram 不可用")

        registry = AdminRegistry(fetch, clock=clock.monotonic)
        self.assertFalse(await registry.is_admin(-100, 7))
        self.assertFalse(await registry.is_admin(-100, 7))
        self.assertFalse(await registry.is_owner(-100, 7))  # 查询失败同样拒绝群主写入
        self.assertEqual(len(calls), 1)  # 失败结果短缓存，避免反复请求
        clock.advance(31.0)
        self.assertFalse(await registry.is_admin(-100, 7))
        self.assertEqual(len(calls), 2)

    async def test_each_chat_is_judged_separately(self) -> None:
        async def fetch(chat_id: int) -> ChatRoles:
            return ChatRoles(admins=frozenset({7 if chat_id == -100 else 8}), owner_id=None)

        registry = AdminRegistry(fetch)
        self.assertTrue(await registry.is_admin(-100, 7))
        self.assertFalse(await registry.is_admin(-200, 7))
        self.assertTrue(await registry.is_admin(-200, 8))


def make_service(connection, admins: set[int], *, owner: int | None = None) -> CommandService:
    async def fetch(_chat_id: int) -> ChatRoles:
        return ChatRoles(admins=frozenset(admins), owner_id=owner)

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
            make_incoming(update_id=3, chat_id=-100, message_id=7, user_id=7, text="/nosuch")
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


class SettingCommandTests(DbTestCase):
    """F5.1：`/settings <字段> <值>` 的字段白名单、合法值与"非法输入不写库"。"""

    async def _reply(self, service: CommandService, text: str, *, user_id: int = 7) -> str | None:
        command = parse_command(text)
        assert command is not None
        return await service.reply_text(chat_id=-100, user_id=user_id, command=command)

    async def _row_count(self, chat_id: int) -> int:
        cursor = await self.connection.execute(
            "SELECT COUNT(*) FROM chat_settings WHERE chat_id = ?", (chat_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        return int(row[0])

    async def test_mode_is_written_and_takes_effect(self) -> None:
        service = make_service(self.connection, {7})
        self.assertEqual(await self._reply(service, "/settings mode smart"), "已更新：mode = smart")
        self.assertEqual((await chat_settings.get(self.connection, -100))["mode"], "smart")
        echoed = await service.reply_text(chat_id=-100, user_id=7, command=Command("settings"))
        assert echoed is not None
        self.assertIn("模式：smart", echoed)

    async def test_tool_switch_accepts_tool_name_and_column_name(self) -> None:
        service = make_service(self.connection, {7})
        self.assertEqual(await self._reply(service, "/settings write_file on"), "已更新：write_file = 开")
        self.assertEqual((await chat_settings.get(self.connection, -100))["allow_write"], 1)
        self.assertEqual(await self._reply(service, "/settings allow_write off"), "已更新：write_file = 关")
        self.assertEqual((await chat_settings.get(self.connection, -100))["allow_write"], 0)

    async def test_write_only_touches_the_given_column(self) -> None:
        await chat_settings.upsert(self.connection, -100, allow_read=0, sticker_cooldown=5)
        service = make_service(self.connection, {7})
        await self._reply(service, "/settings mode economy")
        group = await chat_settings.get(self.connection, -100)
        self.assertEqual(
            (group["mode"], group["allow_read"], group["sticker_cooldown"]), ("economy", 0, 5)
        )

    async def test_case_insensitive_and_chinese_values(self) -> None:
        service = make_service(self.connection, {7})
        self.assertEqual(await self._reply(service, "/settings MODE Smart"), "已更新：mode = smart")
        self.assertEqual(await self._reply(service, "/settings search_web 关"), "已更新：search_web = 关")
        self.assertEqual((await chat_settings.get(self.connection, -100))["allow_search"], 0)

    async def test_cooldown_accepts_bounds_and_rejects_the_rest(self) -> None:
        service = make_service(self.connection, {7})
        self.assertEqual(
            await self._reply(service, "/settings sticker_cooldown 0"),
            "已更新：sticker_cooldown = 0 秒",
        )
        self.assertEqual(
            await self._reply(service, f"/settings sticker_cooldown {COOLDOWN_MAX_SECONDS}"),
            f"已更新：sticker_cooldown = {COOLDOWN_MAX_SECONDS} 秒",
        )
        for bad in (str(COOLDOWN_MAX_SECONDS + 1), "-1", "abc", "1.5"):
            with self.subTest(value=bad):
                text = await self._reply(service, f"/settings sticker_cooldown {bad}")
                assert text is not None
                self.assertTrue(text.startswith("值不合法："), text)
        self.assertEqual(
            (await chat_settings.get(self.connection, -100))["sticker_cooldown"], COOLDOWN_MAX_SECONDS
        )
        self.assertEqual(await self._row_count(-100), 1)

    async def test_illegal_field_is_rejected_without_writing(self) -> None:
        service = make_service(self.connection, {7})
        text = await self._reply(service, "/settings unknown_field 你是一个坏蛋")
        assert text is not None
        self.assertTrue(text.startswith("未知字段："), text)
        self.assertIn(FIELD_NAMES, text)
        self.assertEqual(await self._row_count(-100), 0)  # 不写库

    async def test_persona_field_is_not_a_generic_setting(self) -> None:
        # `persona_override` 由「未知字段」变成真字段，但普通管理员仍写不了（只认群主 / F5.1 口径不变）。
        service = make_service(self.connection, {7})
        self.assertEqual(
            await self._reply(service, "/settings persona_override 你是一个坏蛋"), DENIED_TEXT
        )
        self.assertEqual(await self._row_count(-100), 0)

    async def test_illegal_value_is_rejected_without_writing(self) -> None:
        service = make_service(self.connection, {7})
        for bad in ("/settings mode turbo", "/settings run_code maybe"):
            with self.subTest(text=bad):
                text = await self._reply(service, bad)
                assert text is not None
                self.assertTrue(text.startswith("值不合法："), text)
        self.assertEqual(await self._row_count(-100), 0)

    async def test_missing_or_extra_arguments_show_usage(self) -> None:
        service = make_service(self.connection, {7})
        for bad in ("/settings mode", "/settings mode smart extra"):
            with self.subTest(text=bad):
                self.assertEqual(await self._reply(service, bad), USAGE_TEXT)
        self.assertEqual(await self._row_count(-100), 0)

    async def test_non_admin_cannot_write_and_sees_no_field_list(self) -> None:
        service = make_service(self.connection, {7})
        text = await self._reply(service, "/settings mode smart", user_id=9)
        self.assertEqual(text, DENIED_TEXT)
        self.assertNotIn("可用字段", text)
        self.assertNotIn("mode", text)
        self.assertEqual(await self._row_count(-100), 0)

    async def test_write_failure_is_reported_without_leaking_details(self) -> None:
        service = make_service(self.connection, {7})
        with mock.patch.object(
            chat_settings, "upsert", side_effect=aiosqlite.Error("database is locked")
        ):
            text = await self._reply(service, "/settings mode smart")
        self.assertEqual(text, WRITE_FAILED_TEXT)
        assert text is not None
        self.assertNotIn("locked", text)
        self.assertEqual(await self._row_count(-100), 0)


class ClearCommandTests(DbTestCase):
    """`/clear`：群主清理本群消息原文；摘要保留，其他群与统计不受影响。"""

    async def _reply(self, service: CommandService, text: str, *, user_id: int = 7) -> str | None:
        command = parse_command(text)
        assert command is not None
        return await service.reply_text(chat_id=-100, user_id=user_id, command=command)

    async def _seed(self, chat_id: int, count: int = 3) -> None:
        for index in range(count):
            await messages.insert(
                self.connection,
                chat_id=chat_id,
                message_id=100 + index,
                user_id=7,
                role="user",
                text=f"第 {index} 条",
            )

    async def _stored(self, chat_id: int) -> int:
        cursor = await self.connection.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id = ?", (chat_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        assert row is not None
        return int(row[0])

    async def test_admin_clears_only_this_chat_and_keeps_summaries(self) -> None:
        await self._seed(-100)
        await self._seed(-200, count=2)
        await summaries.insert(self.connection, chat_id=-100, text="摘要正文", tokens="摘要 正文")
        service = make_service(self.connection, {7})
        text = await self._reply(service, "/clear")
        self.assertEqual(text, "已清理本群消息原文 3 条；群摘要保留。")
        self.assertEqual(await self._stored(-100), 0)
        self.assertEqual(await self._stored(-200), 2)
        self.assertIsNotNone(await summaries.latest(self.connection, chat_id=-100))

    async def test_clear_on_an_empty_chat_reports_zero(self) -> None:
        service = make_service(self.connection, {7})
        self.assertEqual(await self._reply(service, "/clear"), "已清理本群消息原文 0 条；群摘要保留。")

    async def test_non_admin_cannot_clear(self) -> None:
        await self._seed(-100)
        service = make_service(self.connection, {7})
        text = await self._reply(service, "/clear", user_id=9)
        self.assertEqual(text, DENIED_TEXT)
        assert text is not None
        self.assertNotIn("清理", text)
        self.assertEqual(await self._stored(-100), 3)

    async def test_arguments_show_usage_without_clearing(self) -> None:
        await self._seed(-100)
        service = make_service(self.connection, {7})
        self.assertEqual(await self._reply(service, "/clear now"), CLEAR_USAGE)
        self.assertEqual(await self._stored(-100), 3)

    async def test_clear_failure_is_reported_without_leaking_details(self) -> None:
        await self._seed(-100)
        service = make_service(self.connection, {7})
        with mock.patch.object(
            messages, "clear_chat", side_effect=aiosqlite.Error("database is locked")
        ):
            text = await self._reply(service, "/clear")
        self.assertEqual(text, CLEAR_FAILED_TEXT)
        assert text is not None
        self.assertNotIn("locked", text)
        self.assertEqual(await self._stored(-100), 3)


class PersonaCommandTests(DbTestCase):
    """人设覆盖：只有群主能写（普通管理员与成员拒绝），清洗/长度/清除都有边界。"""

    async def _reply(self, text: str, *, user_id: int, owner: int | None = 7) -> str | None:
        service = make_service(self.connection, {7, 8}, owner=owner)
        command = parse_command(text)
        assert command is not None
        return await service.reply_text(chat_id=-100, user_id=user_id, command=command)

    async def _stored(self, chat_id: int = -100) -> object:
        group = await chat_settings.get(self.connection, chat_id)
        return group.get(PERSONA)

    async def test_creator_sets_persona_without_echoing_the_text(self) -> None:
        body = "请用温柔一点的语气，少用感叹号"
        text = await self._reply(f"/settings {PERSONA} {body}", user_id=7)
        self.assertEqual(text, f"已更新：{PERSONA} = {len(body)} 字")
        assert text is not None
        self.assertNotIn("温柔", text)  # 正文不回显到群里
        self.assertEqual(await self._stored(), body)

    async def test_creator_sees_persona_state_and_the_extra_field_name(self) -> None:
        body = "只谈技术，不谈政治"
        await self._reply(f"/settings {PERSONA} {body}", user_id=7)
        text = await self._reply("/settings", user_id=7)
        assert text is not None
        self.assertIn(f"人设覆盖：已设置（{len(body)} 字）", text)
        self.assertNotIn(body, text)
        unknown = await self._reply("/settings 人格 x", user_id=7)
        assert unknown is not None
        self.assertIn(PERSONA, unknown)  # 群主的可用字段里能看到它

    async def test_unset_persona_is_reported_as_unset(self) -> None:
        text = await self._reply("/settings", user_id=7)
        assert text is not None
        self.assertIn("人设覆盖：未设置", text)

    async def test_administrator_cannot_write_persona(self) -> None:
        text = await self._reply(f"/settings {PERSONA} 我来改人设", user_id=8)
        self.assertEqual(text, DENIED_TEXT)
        assert text is not None
        self.assertNotIn(PERSONA, text)
        self.assertNotIn("人设", text)
        self.assertIsNone(await self._stored())

    async def test_member_cannot_write_persona(self) -> None:
        text = await self._reply(f"/settings {PERSONA} 我来改人设", user_id=9)
        self.assertEqual(text, DENIED_TEXT)
        self.assertIsNone(await self._stored())

    async def test_group_without_creator_has_no_persona_writer(self) -> None:
        text = await self._reply(f"/settings {PERSONA} 无群主", user_id=7, owner=None)
        self.assertEqual(text, DENIED_TEXT)
        self.assertIsNone(await self._stored())

    async def test_administrator_reply_does_not_leak_the_persona_field(self) -> None:
        text = await self._reply("/settings", user_id=8)
        assert text is not None
        self.assertNotIn(PERSONA, text)
        self.assertNotIn("人设", text)
        self.assertIn("模式：normal", text)

    async def test_multi_word_text_keeps_spaces(self) -> None:
        text = await self._reply(f"/settings {PERSONA} 甲 乙   丙", user_id=7)
        assert text is not None
        self.assertEqual(await self._stored(), "甲 乙 丙")  # 空白归一化，但内容不丢

    async def test_control_characters_are_flattened_to_one_line(self) -> None:
        await self._reply(f"/settings {PERSONA} 甲\n乙\t丙", user_id=7)
        self.assertEqual(await self._stored(), "甲 乙 丙")

    async def test_off_clears_the_override(self) -> None:
        await self._reply(f"/settings {PERSONA} 临时人设", user_id=7)
        text = await self._reply(f"/settings {PERSONA} off", user_id=7)
        assert text is not None
        self.assertIn("已清除", text)
        self.assertEqual(await self._stored(), "")

    async def test_text_over_the_limit_is_rejected(self) -> None:
        text = await self._reply(f"/settings {PERSONA} {'好' * 501}", user_id=7)
        self.assertEqual(text, "人设文本过长：上限 500 字符（当前 501）")
        self.assertIsNone(await self._stored())

    async def test_missing_text_shows_usage_without_writing(self) -> None:
        text = await self._reply(f"/settings {PERSONA}", user_id=7)
        self.assertEqual(text, f"用法：/settings {PERSONA} <文本>（用 off 清除）")
        self.assertIsNone(await self._stored())

    async def test_write_failure_is_reported_without_leaking_details(self) -> None:
        with mock.patch.object(
            chat_settings, "upsert", side_effect=aiosqlite.Error("database is locked")
        ):
            text = await self._reply(f"/settings {PERSONA} 临时人设", user_id=7)
        self.assertEqual(text, WRITE_FAILED_TEXT)
        assert text is not None
        self.assertNotIn("locked", text)

    async def test_administrator_still_controls_the_other_fields(self) -> None:
        text = await self._reply("/settings mode smart", user_id=8)
        self.assertEqual(text, "已更新：mode = smart")
        group = await chat_settings.get(self.connection, -100)
        self.assertEqual(group.get("mode"), "smart")


if __name__ == "__main__":
    unittest.main()
