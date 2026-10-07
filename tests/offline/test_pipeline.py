"""端到端离线闭环：去重 → 过滤 → debounce → 一次模型调用 → 出站 → 记账。"""

from __future__ import annotations

import asyncio
import unittest

from app.config import today_in_timezone
from app.gate.debounce import Batch, Debouncer
from app.gate.dedupe import UpdateDeduplicator
from app.gate.limits import ProactiveLimiter
from app.gate.queue import ChatQueue
from app.gate.trigger import TriggerDetector
from app.llm.loop import Responder
from app.ops.admin import AdminRegistry
from app.ops.commands import DENIED_TEXT, CommandService
from app.ops.health import HealthState
from app.ops.quota import DAILY_EXHAUSTED_TEXT, QuotaGuard
from app.outbound.queue import OutboundQueue
from app.outbound.ratelimit import RateLimiter
from app.session.context import ContextBuilder
from app.session.mood import MoodTracker
from app.session.runner import SessionRunner
from app.storage.repo import chat_settings, messages, stickers, updates, usage
from app.session.retrieval import term_tokens
from app.storage.repo import summaries as summaries_repo
from app.storage.repo.stickers import DbStickerStore
from app.tools.builtin import build_registry
from app.tools.executor import ToolExecutor
from app.tools.policy import Policy
from tests.offline.helpers import (
    DbTestCase,
    FakeClock,
    FakeLLMClient,
    FakeSender,
    FakeSleep,
    make_incoming,
    make_settings,
    tool_reply,
)


class PipelineTests(DbTestCase):
    def _build(
        self,
        *replies: object,
        fail: bool = False,
        rate_limited_times: int = 0,
        on_complete=None,
        search_backend: str = "none",
        sticker_fail_times: int = 0,
        commands=None,
        quota=None,
        health=None,
        failure_recorder=None,
    ) -> None:
        self.clock = FakeClock()
        self.debouncer = Debouncer(quiet_seconds=1.2, max_messages=5, clock=self.clock)
        self.proactive = ProactiveLimiter(
            cooldown_seconds=20.0, window_seconds=300.0, max_per_window=3, clock=self.clock
        )
        self.llm = FakeLLMClient(*replies, fail=fail, on_complete=on_complete)
        self.sender = FakeSender(rate_limited_times=rate_limited_times, sticker_fail_times=sticker_fail_times)
        limiter = RateLimiter(
            group_per_minute=1000, private_per_second=1000.0, sticker_per_second=1000.0, clock=self.clock
        )
        self.outbound = OutboundQueue(self.sender, limiter, sleep=FakeSleep(self.clock))
        self.mood = MoodTracker(clock=self.clock.monotonic)
        tool_settings = self.settings
        if search_backend != "none":
            tool_settings = self.settings.model_copy(update={"search_backend": search_backend})
        self.registry = build_registry(
            tool_settings,
            store=DbStickerStore(self.connection),
            outbound=self.outbound,
            mood=self.mood,
        )
        self.policy = Policy(self.registry)
        self.tools = ToolExecutor(
            self.registry, self.policy, clock=self.clock.monotonic, failure_recorder=failure_recorder
        )
        self.runner = SessionRunner(
            settings=self.settings,
            connection=self.connection,
            deduplicator=UpdateDeduplicator(self.connection),
            detector=TriggerDetector(self.settings, self.proactive),
            limiter=self.proactive,
            debouncer=self.debouncer,
            context_builder=ContextBuilder(self.connection, self.settings),
            responder=Responder(self.llm, self.settings, self.tools),
            outbound=self.outbound,
            tools=self.tools,
            mood=self.mood,
            commands=commands,
            quota=quota,
            health=health,
        )
    async def _send(self, texts, *, chat_id: int = 1, start_update: int = 100, start_message: int = 10) -> None:
        for index, text in enumerate(texts):
            await self.runner.handle(
                make_incoming(
                    update_id=start_update + index,
                    chat_id=chat_id,
                    message_id=start_message + index,
                    text=text,
                )
            )

    async def _flush(self):
        self.clock.advance(2.0)
        batches = self.debouncer.due()
        for batch in batches:
            await self.runner.handle_batch(batch)
        await self.outbound.drain(5.0)
        await self.outbound.stop()
        return batches

    async def _usage(self) -> dict:
        return await usage.summary_for_day(self.connection, today_in_timezone(self.settings))

    async def test_calc_tool_runs_end_to_end_and_is_recorded(self) -> None:
        self._build(tool_reply("calc", {"expression": "2*3"}), "等于 6")
        await self._send(["@bot 2*3 等于几"])
        await self._flush()
        self.assertEqual([item["text"] for item in self.sender.sent], ["等于 6"])
        self.assertEqual(self.llm.tool_names[0], ["calc", "read_file", "send_sticker"])
        tool_messages = [item for item in self.llm.calls[1] if item.get("role") == "tool"]
        self.assertIn("6", str(tool_messages[0]["content"]))
        summary = await self._usage()
        self.assertEqual(summary["tool_calls"], 1)

    async def test_search_web_not_exposed_by_default(self) -> None:
        self._build("好")
        await self._send(["@bot 帮我查一下"])
        await self._flush()
        self.assertEqual(self.llm.tool_names[0], ["calc", "read_file", "send_sticker"])

    async def test_search_web_exposed_with_fake_backend(self) -> None:
        self._build(tool_reply("search_web", {"query": "天气"}), "查到一条", search_backend="fake")
        await self._send(["@bot 查一下天气"])
        await self._flush()
        self.assertEqual(self.llm.tool_names[0], ["calc", "read_file", "search_web", "send_sticker"])
        self.assertEqual([item["text"] for item in self.sender.sent], ["查到一条"])
        tool_messages = [item for item in self.llm.calls[1] if item.get("role") == "tool"]
        self.assertIn("results", str(tool_messages[0]["content"]))

    async def test_unknown_tool_call_is_denied_and_model_answers(self) -> None:
        self._build(tool_reply("run_code", {}), "这个我做不了")
        await self._send(["@bot 帮我跑段代码"])
        await self._flush()
        self.assertEqual([item["text"] for item in self.sender.sent], ["这个我做不了"])
        tool_messages = [item for item in self.llm.calls[1] if item.get("role") == "tool"]
        self.assertIn("permission_denied", str(tool_messages[0]["content"]))

    async def test_read_file_tool_runs_end_to_end(self) -> None:
        workspace = self.settings.workspace_root / "1"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "note.txt").write_text("群里的笔记", encoding="utf-8")
        self._build(tool_reply("read_file", {"path": "note.txt"}), "读到了")
        await self._send(["@bot 看一下 note.txt"])
        await self._flush()
        self.assertEqual([item["text"] for item in self.sender.sent], ["读到了"])
        self.assertIn("read_file", self.llm.tool_names[0])
        tool_messages = [item for item in self.llm.calls[1] if item.get("role") == "tool"]
        self.assertIn("群里的笔记", str(tool_messages[0]["content"]))

    async def test_write_file_needs_group_switch(self) -> None:
        write_call = tool_reply("write_file", {"path": "out.txt", "content": "hi"})
        self._build(
            write_call,
            "可能不行",
            tool_reply("write_file", {"path": "out.txt", "content": "hi"}, call_id="call-2"),
            "记好了",
        )
        await self._send(["@bot 帮我记下来"])
        self.clock.advance(2.0)
        for batch in self.debouncer.due():
            await self.runner.handle_batch(batch)
        await self.outbound.drain(5.0)
        self.assertNotIn("write_file", self.llm.tool_names[0])
        self.assertFalse((self.settings.workspace_root / "1" / "out.txt").exists())
        tool_messages = [item for item in self.llm.calls[1] if item.get("role") == "tool"]
        self.assertIn("permission_denied", str(tool_messages[0]["content"]))

        await chat_settings.upsert(self.connection, 1, allow_write=1)
        await self.runner.handle(make_incoming(update_id=800, chat_id=1, message_id=90, text="@bot 再记一次"))
        self.clock.advance(2.0)
        for batch in self.debouncer.due():
            await self.runner.handle_batch(batch)
        await self.outbound.drain(5.0)
        await self.outbound.stop()
        self.assertIn("write_file", self.llm.tool_names[2])
        self.assertEqual((self.settings.workspace_root / "1" / "out.txt").read_text(encoding="utf-8"), "hi")

    async def test_send_sticker_end_to_end_and_file_id_stays_out(self) -> None:
        file_id = "CAACAgIAAxkBAAEtradefile"
        await stickers.register(
            self.connection,
            chat_id=1,
            file_id=file_id,
            file_unique_id="UNIQ1",
            valence=1.0,
            arousal=1.0,
            tags=["开心"],
        )
        self._build(tool_reply("send_sticker", {"valence": 1.0, "arousal": 1.0, "tags": ["开心"]}), "发了个贴纸")
        await self._send(["@bot 开心一下"])
        await self._flush()
        self.assertEqual([item["text"] for item in self.sender.sent], ["发了个贴纸"])
        self.assertEqual([item["file_id"] for item in self.sender.stickers], [file_id])
        self.assertNotIn(file_id, str(self.llm.calls))
        self.assertEqual((await self._usage())["tool_calls"], 1)

    async def test_mood_is_injected_on_the_next_turn(self) -> None:
        await stickers.register(
            self.connection, chat_id=1, file_id="F1", file_unique_id="U1", valence=1.0, arousal=1.0
        )
        self._build(tool_reply("send_sticker", {"valence": 1.0, "arousal": 1.0}), "发了个贴纸")
        await self._send(["@bot 开心一下"])
        self.clock.advance(2.0)
        for batch in self.debouncer.due():
            await self.runner.handle_batch(batch)
        await self.outbound.drain(5.0)
        await self.runner.handle(make_incoming(update_id=810, chat_id=1, message_id=95, text="@bot 在吗"))
        self.clock.advance(2.0)
        for batch in self.debouncer.due():
            await self.runner.handle_batch(batch)
        await self.outbound.drain(5.0)
        await self.outbound.stop()
        last_payload = self.llm.calls[-1]
        self.assertEqual(last_payload[-1]["role"], "system")
        self.assertIn("心情不错", str(last_payload[-1]["content"]))

    async def test_summary_memory_block_is_injected(self) -> None:
        await summaries_repo.insert(
            self.connection,
            chat_id=1,
            text="当前话题：部署脚本",
            tokens=term_tokens("当前话题：部署脚本"),
            msg_from=1,
            msg_to=1,
        )
        self._build("好的")
        await self._send(["@bot 在的"])
        await self._flush()
        payload = self.llm.calls[0]
        self.assertEqual(payload[1]["role"], "system")
        self.assertTrue(str(payload[1]["content"]).startswith("## 记忆"))
        self.assertIn("最近摘要：", str(payload[1]["content"]))
        self.assertTrue(str(payload[0]["content"]).startswith("## 全局人格"))

    async def test_retrieval_snippets_are_injected_on_recall(self) -> None:
        await summaries_repo.insert(
            self.connection,
            chat_id=1,
            text="之前讨论过部署脚本的写法",
            tokens=term_tokens("之前讨论过部署脚本的写法"),
        )
        self._build("我记得")
        await self._send(["@bot 之前那个部署脚本怎么搞的"])
        await self._flush()
        memory = str(self.llm.calls[0][1]["content"])
        self.assertIn("相关记录：", memory)
        self.assertIn("[摘要#", memory)

    async def test_budget_trims_old_history_and_keeps_current(self) -> None:
        self.settings = make_settings(self.tmp, HISTORY_BUDGET_CHARS=80)
        old_text = "很久以前的旧消息" * 6
        for index in range(6):
            await messages.insert(
                self.connection,
                chat_id=1,
                message_id=500 + index,
                user_id=42,
                role="user",
                text=f"{old_text}{index}",
            )
        self._build("好")
        await self._send(["@bot 现在的问题是什么"])
        await self._flush()
        contents = [str(item["content"]) for item in self.llm.calls[0]]
        self.assertTrue(any("现在的问题是什么" in item for item in contents))
        self.assertFalse(any(f"{old_text}0" in item for item in contents))
        self.assertGreater(self.runner._context.consume_trimmed(1), 0)

    async def test_oversized_batch_survives_budget_trim(self) -> None:
        # 本轮文本自身就超过预算时，仍然不允许裁掉本轮消息（docs/memory.md §2 硬约束）
        self.settings = make_settings(self.tmp, HISTORY_BUDGET_CHARS=60)
        old_text = "很久以前的旧消息" * 6
        for index in range(6):
            await messages.insert(
                self.connection,
                chat_id=1,
                message_id=600 + index,
                user_id=42,
                role="user",
                text=f"{old_text}{index}",
            )
        self._build("好")
        first = "@bot " + "本轮消息甲" * 8
        second = "@bot " + "本轮消息乙" * 8
        await self._send([first, second])
        await self._flush()
        contents = [str(item["content"]) for item in self.llm.calls[0]]
        self.assertIn(first, contents)
        self.assertIn(second, contents)
        self.assertFalse(any(f"{old_text}0" in item for item in contents))
        # 旧实现会把本轮一起裁掉（8 条）；现在只裁掉 6 条旧历史
        self.assertEqual(self.runner._context.consume_trimmed(1), 6)

    def test_window_size_tiers(self) -> None:
        self._build()
        builder = self.runner._context

        def batch_of(*texts: str) -> Batch:
            items = [
                make_incoming(update_id=900 + index, chat_id=1, message_id=900 + index, text=text)
                for index, text in enumerate(texts)
            ]
            return Batch(chat_id=1, items=items, last_at=0.0, full=False)

        fence = chr(96) * 3
        self.assertEqual(builder.window_size(batch_of("哈哈")), self.settings.history_chitchat)
        self.assertEqual(builder.window_size(batch_of("普通的一句话，随便聊聊")), self.settings.history_default)
        self.assertEqual(builder.window_size(batch_of("之前那个怎么搞的")), self.settings.history_complex)
        self.assertEqual(builder.window_size(batch_of(f"看代码 {fence}x{fence}")), self.settings.history_complex)

    async def test_send_sticker_needs_group_switch(self) -> None:
        await chat_settings.upsert(self.connection, 1, allow_sticker=0)
        self._build(tool_reply("send_sticker", {"valence": 1.0, "arousal": 1.0}), "不发")
        await self._send(["@bot 发个贴纸"])
        await self._flush()
        self.assertNotIn("send_sticker", self.llm.tool_names[0])
        tool_messages = [item for item in self.llm.calls[1] if item.get("role") == "tool"]
        self.assertIn("permission_denied", str(tool_messages[0]["content"]))

    async def test_rapid_messages_merge_into_one_model_call(self) -> None:
        self._build("好的，收到")
        await self._send(["你好 @bot", "在吗", "帮我看看", "回复一下"])
        batches = await self._flush()

        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0].items), 4)
        self.assertEqual(len(self.llm.calls), 1)
        payload = self.llm.calls[0]
        self.assertEqual(payload[0]["role"], "system")
        self.assertIn("## 全局人格", payload[0]["content"])
        contents = [item["content"] for item in payload]
        self.assertIn("你好 @bot", contents)
        self.assertEqual(contents[-1], "回复一下")

        self.assertEqual(len(self.sender.sent), 1)
        self.assertEqual(self.sender.sent[0]["chat_id"], 1)
        self.assertEqual(self.sender.sent[0]["text"], "好的，收到")
        self.assertEqual(self.sender.sent[0]["reply_to_message_id"], 13)

        rows = await messages.recent(self.connection, chat_id=1, limit=20)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[-1].role, "assistant")
        self.assertEqual((await self._usage())["calls"], 1)

    async def test_duplicate_update_does_not_call_model_twice(self) -> None:
        self._build("第一次")
        await self._send(["问一下"])
        await self._flush()
        await self.runner.handle(make_incoming(update_id=100, chat_id=1, message_id=10, text="问一下"))
        self.clock.advance(2.0)
        self.assertEqual(self.debouncer.due(), [])
        self.assertEqual(len(self.llm.calls), 1)
        self.assertEqual(len(self.sender.sent), 1)

    async def test_chats_are_isolated(self) -> None:
        self._build("回复A", "回复B")
        await self._send(["A群的内容"], chat_id=1, start_update=100, start_message=10)
        await self._send(["B群的内容"], chat_id=2, start_update=200, start_message=20)
        batches = await self._flush()

        self.assertEqual([batch.chat_id for batch in batches], [1, 2])
        first = [item["content"] for item in self.llm.calls[0]]
        second = [item["content"] for item in self.llm.calls[1]]
        self.assertIn("A群的内容", first)
        self.assertNotIn("B群的内容", first)
        self.assertIn("B群的内容", second)
        self.assertNotIn("A群的内容", second)
        self.assertEqual([item["chat_id"] for item in self.sender.sent], [1, 2])

    async def test_no_reply_still_records_usage(self) -> None:
        self._build("NO_REPLY")
        await self._send(["随便说说"])
        await self._flush()
        self.assertEqual(self.sender.sent, [])
        self.assertEqual((await self._usage())["calls"], 1)

    async def test_model_failure_keeps_bot_silent(self) -> None:
        self._build(fail=True)
        await self._send(["问一下"])
        await self._flush()
        self.assertEqual(self.sender.sent, [])
        self.assertEqual((await self._usage())["calls"], 0)

    async def test_unaddressed_message_is_stored_but_not_sent_to_model(self) -> None:
        self._build("不该被调用")
        await self.runner.handle(
            make_incoming(update_id=300, chat_id=1, message_id=30, text="哈哈哈哈", mentions_bot=False)
        )
        self.clock.advance(2.0)
        self.assertEqual(self.debouncer.due(), [])
        self.assertEqual(self.llm.calls, [])
        stored = await messages.recent(self.connection, chat_id=1, limit=10, include_noise=True)
        self.assertEqual(len(stored), 1)
        self.assertTrue(stored[0].noise)  # F3.2：入库即打噪声标，但默认不进上下文
        self.assertEqual(await messages.recent(self.connection, chat_id=1, limit=10), [])

    async def test_private_chat_is_silent_and_free(self) -> None:
        # docs/requirements.md §2.2：私聊默认完全不处理
        self._build("不该被调用")
        await self.runner.handle(
            make_incoming(
                update_id=500, chat_id=7, message_id=50, text="@bot 你好", chat_type="private"
            )
        )
        self.clock.advance(2.0)
        self.assertEqual(self.debouncer.due(), [])
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(await messages.recent(self.connection, chat_id=7, limit=10), [])
        self.assertEqual((await self._usage())["calls"], 0)
        # 只保留必要的 Telegram 元数据
        self.assertTrue(await updates.is_seen(self.connection, 500))

    async def test_private_chat_replies_when_switch_enabled(self) -> None:
        self.settings = make_settings(self.tmp, ALLOW_PRIVATE_CHAT=True)
        self._build("私聊也可以")
        await self.runner.handle(
            make_incoming(update_id=600, chat_id=7, message_id=60, text="你好", chat_type="private")
        )
        batches = await self._flush()
        self.assertEqual([batch.chat_id for batch in batches], [7])
        self.assertEqual([item["chat_id"] for item in self.sender.sent], [7])

    async def test_new_messages_do_not_join_the_running_round(self) -> None:
        arrived = asyncio.Event()

        async def on_complete() -> None:
            # 模型正在调用时，群里又来了一条消息
            await self.runner.handle(make_incoming(update_id=900, chat_id=1, message_id=90, text="我又来一条"))
            arrived.set()

        self._build("第一轮", "第二轮", on_complete=on_complete)
        queue = ChatQueue(self.runner.handle_batch, max_batch_messages=5)
        await self._send(["第一条", "第二条"])
        self.clock.advance(2.0)
        batches = self.debouncer.due()
        self.assertEqual(len(batches), 1)
        await queue.submit(batches[0])
        await arrived.wait()
        await queue.drain(5.0)
        await self.outbound.drain(5.0)

        self.assertEqual(len(self.llm.calls), 1)  # 运行期间不产生第二次模型调用
        first = [item["content"] for item in self.llm.calls[0]]
        self.assertNotIn("我又来一条", first)  # 新消息不加入本轮上下文
        self.assertEqual(len(await messages.recent(self.connection, chat_id=1, limit=10)), 4)

        # 本轮结束后：新消息按下一轮处理，恰好一次新调用
        self.clock.advance(2.0)
        next_batches = self.debouncer.due()
        self.assertEqual(len(next_batches), 1)
        await queue.submit(next_batches[0])
        await queue.drain(5.0)
        await queue.stop()
        await self.outbound.drain(5.0)
        await self.outbound.stop()
        self.assertEqual(len(self.llm.calls), 2)
        self.assertIn("我又来一条", [item["content"] for item in self.llm.calls[1]])
        self.assertEqual((await self._usage())["calls"], 2)

    async def test_unaddressed_question_gets_a_proactive_reply(self) -> None:
        # F2.2/F2.3：不需要 @ 也能接话
        self._build("我看到啦")
        await self.runner.handle(
            make_incoming(update_id=700, chat_id=1, message_id=70, text="这个怎么弄", mentions_bot=False)
        )
        batches = await self._flush()
        self.assertTrue(batches[0].proactive)
        self.assertEqual(len(self.llm.calls), 1)
        self.assertEqual([item["text"] for item in self.sender.sent], ["我看到啦"])

    async def test_proactive_cooldown_keeps_following_questions_silent(self) -> None:
        # F2.4：主动说过话之后的冷却期内，未点名的问题不再回应（0 token）
        self._build("先回一句", "不该被调用")
        await self.runner.handle(
            make_incoming(update_id=710, chat_id=1, message_id=71, text="这个怎么弄", mentions_bot=False)
        )
        await self._flush()
        self.assertEqual(len(self.llm.calls), 1)
        for index, text in enumerate(("那这个呢", "另一个问题怎么解决")):
            await self.runner.handle(
                make_incoming(
                    update_id=711 + index,
                    chat_id=1,
                    message_id=72 + index,
                    text=text,
                    mentions_bot=False,
                )
            )
        self.clock.advance(2.0)
        self.assertEqual(self.debouncer.due(), [])
        self.assertEqual(len(self.llm.calls), 1)
        self.assertEqual(len(self.sender.sent), 1)

    async def test_followup_after_bot_reply_is_answered(self) -> None:
        # F2.3：点名回复不占冷却，紧接着的续问（未点名）仍会接话
        self._build("第一句", "第二句")
        await self.runner.handle(
            make_incoming(update_id=720, chat_id=1, message_id=81, text="@bot 在吗")
        )
        self.clock.advance(2.0)
        for batch in self.debouncer.due():
            await self.runner.handle_batch(batch)
        await self.runner.handle(
            make_incoming(update_id=721, chat_id=1, message_id=82, text="然后继续讲讲", mentions_bot=False)
        )
        self.clock.advance(2.0)
        batches = self.debouncer.due()
        self.assertEqual(len(batches), 1)
        self.assertTrue(batches[0].proactive)
        for batch in batches:
            await self.runner.handle_batch(batch)
        await self.outbound.drain(5.0)
        await self.outbound.stop()
        self.assertEqual(len(self.llm.calls), 2)
        self.assertEqual([item["text"] for item in self.sender.sent], ["第一句", "第二句"])

    async def test_bot_author_message_is_dropped_before_storage(self) -> None:
        self._build("不该被调用")
        await self.runner.handle(
            make_incoming(update_id=400, chat_id=1, message_id=40, text="我是别的 Bot", is_bot_author=True)
        )
        self.clock.advance(2.0)
        self.assertEqual(self.llm.calls, [])
        self.assertEqual(await messages.recent(self.connection, chat_id=1, limit=10), [])

    async def test_settings_command_takes_effect_on_the_next_turn(self) -> None:
        """F5.1：管理员改设置当轮生效，且命令本身不进模型、不记账。"""

        async def fetch(_chat_id: int) -> set[int]:
            return {42}

        self._build("好", commands=CommandService(self.connection, AdminRegistry(fetch)))
        await self._send(["/settings mode smart", "/settings write_file on"])
        await self.outbound.drain(5.0)
        self.assertEqual(self.llm.calls, [])  # 命令 0 token
        self.assertEqual((await self._usage())["calls"], 0)  # 命令不记账
        self.assertEqual(
            [item["text"] for item in self.sender.sent],
            ["已更新：mode = smart", "已更新：write_file = 开"],
        )

        await self._send(["@bot 在吗"], start_update=200, start_message=20)
        await self._flush()
        group = await chat_settings.get(self.connection, 1)
        self.assertEqual((group["mode"], group["allow_write"]), ("smart", 1))
        self.assertIn("write_file", self.llm.tool_names[0])  # 工具开关当轮生效
        self.assertIn("模式：smart", str(self.llm.calls[0][0]["content"]))  # 模式当轮进入固定段

    async def _seed_tokens(self, tokens: int, *, chat_id: int = 1, purpose: str = "chat") -> None:
        await usage.record(
            self.connection,
            chat_id=chat_id,
            user_id=42,
            day=today_in_timezone(self.settings),
            model="deepseek-flash",
            input_tokens=tokens,
            purpose=purpose,
        )

    async def test_quota_exhaustion_skips_the_model_call(self) -> None:
        """F5.3：达到上限时本轮不调用模型、不记账，只回一条明确提示。"""
        self.settings = make_settings(self.tmp, QUOTA_DAILY_TOKENS=100)
        await self._seed_tokens(100)
        self._build("不该被调用", quota=QuotaGuard(self.connection, self.settings))
        await self._send(["@bot 在吗"])
        await self._flush()

        self.assertEqual(self.llm.calls, [])  # 配额拒绝后不产生本次模型调用
        self.assertEqual([item["text"] for item in self.sender.sent], [DAILY_EXHAUSTED_TEXT])
        self.assertEqual((await self._usage())["calls"], 1)  # 只有预置的那次，本轮不记账
        stored = await messages.recent(self.connection, chat_id=1, limit=10)
        self.assertEqual([row.role for row in stored], ["user"])  # 没有 Bot 发言入库

    async def test_quota_over_the_limit_skips_the_model_call(self) -> None:
        self.settings = make_settings(self.tmp, QUOTA_DAILY_TOKENS=100)
        await self._seed_tokens(250)
        self._build("不该被调用", quota=QuotaGuard(self.connection, self.settings))
        await self._send(["@bot 在吗"])
        await self._flush()
        self.assertEqual(self.llm.calls, [])
        self.assertEqual([item["text"] for item in self.sender.sent], [DAILY_EXHAUSTED_TEXT])

    async def test_quota_just_under_the_limit_is_allowed(self) -> None:
        self.settings = make_settings(self.tmp, QUOTA_MONTHLY_TOKENS=100)
        await self._seed_tokens(99)
        self._build("好", quota=QuotaGuard(self.connection, self.settings))
        await self._send(["@bot 在吗"])  # 99 < 100：本月额度还够
        await self._flush()
        self.assertEqual(len(self.llm.calls), 1)
        self.assertEqual([item["text"] for item in self.sender.sent], ["好"])

    async def test_quota_under_the_limit_still_calls_the_model(self) -> None:
        self.settings = make_settings(self.tmp, QUOTA_DAILY_TOKENS=1000)
        await self._seed_tokens(10)
        self._build("好", quota=QuotaGuard(self.connection, self.settings))
        await self._send(["@bot 在吗"])
        await self._flush()
        self.assertEqual(len(self.llm.calls), 1)
        self.assertEqual([item["text"] for item in self.sender.sent], ["好"])

    async def test_unconfigured_quota_is_unlimited_end_to_end(self) -> None:
        self._build("好", quota=QuotaGuard(self.connection, self.settings))
        await self._seed_tokens(1_000_000)
        await self._send(["@bot 在吗"])
        await self._flush()
        self.assertEqual(len(self.llm.calls), 1)

    async def test_settings_command_does_not_consume_quota(self) -> None:
        """命令不调用模型，因此既不记账也不消耗该群配额。"""

        async def fetch(_chat_id: int) -> set[int]:
            return {42}

        self.settings = make_settings(self.tmp, QUOTA_DAILY_TOKENS=100)
        self._build(
            "好",
            commands=CommandService(self.connection, AdminRegistry(fetch)),
            quota=QuotaGuard(self.connection, self.settings),
        )
        await self._send(["/settings mode smart"])
        await self.outbound.drain(5.0)
        self.assertEqual(self.llm.calls, [])
        self.assertEqual((await self._usage())["calls"], 0)

        await self._send(["@bot 在吗"], start_update=200, start_message=20)
        await self._flush()
        self.assertEqual(len(self.llm.calls), 1)  # 配额没被命令吃掉
        self.assertEqual([item["text"] for item in self.sender.sent][-1], "好")

    def _commands_with(self, *, admins=(42,), health=None):
        async def fetch(_chat_id: int) -> set[int]:
            return set(admins)

        return CommandService(self.connection, AdminRegistry(fetch), settings=self.settings, health=health)

    async def _command(self, text: str, *, user_id: int = 42, update_id: int = 500, message_id: int = 500) -> None:
        await self.runner.handle(
            make_incoming(
                update_id=update_id, chat_id=1, message_id=message_id, text=text, user_id=user_id
            )
        )
        await self.outbound.drain(5.0)

    async def test_stats_command_is_admin_only_and_does_not_call_the_model(self) -> None:
        """F5.4：/stats 只读、0 token、不进模型；非管理员被拒。"""
        health = HealthState(instance_id="bot-1")
        self._build(commands=self._commands_with(health=health), health=health)
        await self._command("/stats")

        self.assertEqual(self.llm.calls, [])
        self.assertEqual((await self._usage())["calls"], 0)
        text = str(self.sender.sent[0]["text"])
        self.assertIn("本群运行统计", text)
        self.assertNotIn("test-token", text)

        await self._command("/stats", user_id=9, update_id=501, message_id=501)
        self.assertEqual(self.sender.sent[-1]["text"], DENIED_TEXT)
        self.assertNotIn("统计", str(self.sender.sent[-1]["text"]))

    async def test_health_command_reports_status_without_internals(self) -> None:
        health = HealthState(instance_id="bot-1")
        self._build(commands=self._commands_with(health=health), health=health)
        await self._command("/health")

        self.assertEqual(self.llm.calls, [])
        self.assertEqual((await self._usage())["calls"], 0)
        text = str(self.sender.sent[0]["text"])
        self.assertIn("状态：正常", text)
        self.assertIn("数据库：可读", text)
        self.assertNotIn("test-key", text)

        await self._command("/health", user_id=9, update_id=502, message_id=502)
        self.assertEqual(self.sender.sent[-1]["text"], DENIED_TEXT)

    async def test_health_state_tracks_processed_updates(self) -> None:
        health = HealthState(instance_id="bot-1")
        self._build("好", commands=self._commands_with(health=health), health=health)
        self.assertIsNone((await health.snapshot())["last_update_at"])

        await self._send(["@bot 在吗"])
        await self._flush()

        self.assertIsNotNone((await health.snapshot())["last_update_at"])

    async def test_settings_mode_takes_effect_on_the_next_message(self) -> None:
        """F5.1 + §5：管理员改 mode 后，下一条普通消息按新模式执行，不用重启。"""
        self._build("好", "好", commands=self._commands_with())
        await self._command("/settings mode economy")
        self.assertIn("mode = economy", str(self.sender.sent[-1]["text"]))
        self.assertEqual(self.llm.calls, [])  # 命令 0 token，不进模型

        await self._send(["@bot 在吗"], start_update=200, start_message=20)
        await self._flush()
        self.assertEqual(self.llm.max_tokens, [256])  # economy：短
        self.assertEqual(self.llm.tool_names[-1], ["calc"])  # economy：只 L0

        await self._command("/settings mode unrestricted", update_id=501, message_id=501)
        self.assertEqual(len(self.llm.calls), 1)  # 命令仍然不进模型
        group = await chat_settings.get(self.connection, 1)
        self.assertEqual(group["mode"], "unrestricted")

        await self._send(["@bot 在吗"], start_update=300, start_message=30)
        await self._flush()
        self.assertIsNone(self.llm.max_tokens[-1])  # unrestricted：不限
        tools = self.llm.tool_names[-1]
        self.assertIn("write_file", tools)  # unrestricted：全部已注册工具（不看群开关）
        self.assertIn("host_info", tools)

    async def test_smart_mode_offers_readonly_tools_without_the_group_switch(self) -> None:
        """§5：smart＝允许的等级 + 更多工具（只读档不受群开关限制）。"""
        await chat_settings.upsert(self.connection, 1, allow_search=0)
        self._build("好", "好", search_backend="fake")
        await self._send(["@bot 在吗"], start_update=200, start_message=20)
        await self._flush()
        self.assertNotIn("search_web", self.llm.tool_names[-1])  # normal：开关关着就不给

        await chat_settings.upsert(self.connection, 1, mode="smart")
        await self._send(["@bot 在吗"], start_update=300, start_message=30)
        await self._flush()
        self.assertIn("search_web", self.llm.tool_names[-1])  # smart：只读档额外放行

    async def test_economy_and_smart_change_the_history_window(self) -> None:
        """窗口差异要体现在发给模型的上下文里，而不是只看「模式：xxx」文本。"""
        for index in range(15):
            await messages.insert(
                self.connection, chat_id=1, message_id=100 + index, user_id=8, role="user", text=f"旧历史{index}"
            )
        await chat_settings.upsert(self.connection, 1, mode="economy")
        self._build("好", "好")
        await self._send(["@bot 在吗"], start_update=200, start_message=200)
        await self._flush()
        economy_payload = " ".join(str(item.get("content", "")) for item in self.llm.calls[0])
        self.assertEqual(economy_payload.count("旧历史"), 9)  # 窗口 10：9 条历史 + 本轮

        await chat_settings.upsert(self.connection, 1, mode="smart")
        await self._send(["@bot 在吗"], start_update=300, start_message=300)
        await self._flush()
        smart_payload = " ".join(str(item.get("content", "")) for item in self.llm.calls[1])
        self.assertEqual(smart_payload.count("旧历史"), 15)  # 窗口 50：全部历史都在


if __name__ == "__main__":
    unittest.main()
