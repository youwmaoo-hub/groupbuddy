"""端到端离线闭环：去重 → 过滤 → debounce → 一次模型调用 → 出站 → 记账。"""

from __future__ import annotations

import asyncio
import unittest

from app.config import today_in_timezone
from app.gate.debounce import Debouncer
from app.gate.dedupe import UpdateDeduplicator
from app.gate.limits import ProactiveLimiter
from app.gate.queue import ChatQueue
from app.gate.trigger import TriggerDetector
from app.llm.loop import Responder
from app.outbound.queue import OutboundQueue
from app.outbound.ratelimit import RateLimiter
from app.session.context import ContextBuilder
from app.session.runner import SessionRunner
from app.storage.repo import chat_settings, messages, updates, usage
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
    ) -> None:
        self.clock = FakeClock()
        self.debouncer = Debouncer(quiet_seconds=1.2, max_messages=5, clock=self.clock)
        self.proactive = ProactiveLimiter(
            cooldown_seconds=20.0, window_seconds=300.0, max_per_window=3, clock=self.clock
        )
        tool_settings = self.settings
        if search_backend != "none":
            tool_settings = self.settings.model_copy(update={"search_backend": search_backend})
        self.registry = build_registry(tool_settings)
        self.policy = Policy(self.registry)
        self.tools = ToolExecutor(self.registry, self.policy, clock=self.clock.monotonic)
        self.llm = FakeLLMClient(*replies, fail=fail, on_complete=on_complete)
        self.sender = FakeSender(rate_limited_times=rate_limited_times)
        limiter = RateLimiter(group_per_minute=1000, private_per_second=1000.0, clock=self.clock)
        self.outbound = OutboundQueue(self.sender, limiter, sleep=FakeSleep(self.clock))
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
        self.assertEqual(self.llm.tool_names[0], ["calc", "read_file"])
        tool_messages = [item for item in self.llm.calls[1] if item.get("role") == "tool"]
        self.assertIn("6", str(tool_messages[0]["content"]))
        summary = await self._usage()
        self.assertEqual(summary["tool_calls"], 1)

    async def test_search_web_not_exposed_by_default(self) -> None:
        self._build("好")
        await self._send(["@bot 帮我查一下"])
        await self._flush()
        self.assertEqual(self.llm.tool_names[0], ["calc", "read_file"])

    async def test_search_web_exposed_with_fake_backend(self) -> None:
        self._build(tool_reply("search_web", {"query": "天气"}), "查到一条", search_backend="fake")
        await self._send(["@bot 查一下天气"])
        await self._flush()
        self.assertEqual(self.llm.tool_names[0], ["calc", "read_file", "search_web"])
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
        self.assertEqual(len(await messages.recent(self.connection, chat_id=1, limit=10)), 1)

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


if __name__ == "__main__":
    unittest.main()
