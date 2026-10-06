"""端到端离线闭环：去重 → 过滤 → debounce → 一次模型调用 → 出站 → 记账。"""

from __future__ import annotations

import unittest

from app.config import today_in_timezone
from app.gate.debounce import Debouncer
from app.gate.dedupe import UpdateDeduplicator
from app.gate.trigger import TriggerDetector
from app.llm.loop import Responder
from app.outbound.queue import OutboundQueue
from app.outbound.ratelimit import RateLimiter
from app.session.context import ContextBuilder
from app.session.runner import SessionRunner
from app.storage.repo import messages, usage
from tests.offline.helpers import (
    DbTestCase,
    FakeClock,
    FakeLLMClient,
    FakeSender,
    FakeSleep,
    make_incoming,
)


class PipelineTests(DbTestCase):
    def _build(self, *replies: str, fail: bool = False, rate_limited_times: int = 0) -> None:
        self.clock = FakeClock()
        self.debouncer = Debouncer(quiet_seconds=1.2, max_messages=5, clock=self.clock)
        self.llm = FakeLLMClient(*replies, fail=fail)
        self.sender = FakeSender(rate_limited_times=rate_limited_times)
        limiter = RateLimiter(group_per_minute=1000, private_per_second=1000.0, clock=self.clock)
        self.outbound = OutboundQueue(self.sender, limiter, sleep=FakeSleep(self.clock))
        self.runner = SessionRunner(
            settings=self.settings,
            connection=self.connection,
            deduplicator=UpdateDeduplicator(self.connection),
            detector=TriggerDetector(self.settings),
            debouncer=self.debouncer,
            context_builder=ContextBuilder(self.connection, self.settings),
            responder=Responder(self.llm, self.settings),
            outbound=self.outbound,
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

    async def test_rapid_messages_merge_into_one_model_call(self) -> None:
        self._build("好的，收到")
        await self._send(["你好 @bot", "在吗", "帮我看看", "回复一下"])
        batches = await self._flush()

        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0].items), 4)
        self.assertEqual(len(self.llm.calls), 1)
        payload = self.llm.calls[0]
        self.assertEqual(payload[0]["role"], "system")
        self.assertIn("## 人设", payload[0]["content"])
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
