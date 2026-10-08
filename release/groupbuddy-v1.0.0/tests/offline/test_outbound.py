"""出站层：4096 分段、限速、429 重试、失败放弃。"""

from __future__ import annotations

import unittest

from app.outbound.queue import OutboundQueue, split_message
from app.outbound.ratelimit import RateLimiter
from tests.offline.helpers import FakeClock, FakeSender, FakeSleep

LIMIT = 4096
FENCE = chr(96) * 3


class SplitTests(unittest.TestCase):
    def test_short_text_unchanged(self) -> None:
        self.assertEqual(split_message("你好"), ["你好"])

    def test_text_at_limit_is_one_chunk(self) -> None:
        self.assertEqual(len(split_message("a" * LIMIT)), 1)

    def test_plain_text_is_split_within_limit(self) -> None:
        long_text = "".join("这是第%d句。" % index for index in range(1500))
        chunks = split_message(long_text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= LIMIT for chunk in chunks))

    def test_char_split_when_no_sentence_break(self) -> None:
        chunks = split_message("a" * (LIMIT * 2 + 5))
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(chunk) <= LIMIT for chunk in chunks))
        self.assertEqual("".join(chunks), "a" * (LIMIT * 2 + 5))

    def test_fenced_code_block_stays_balanced(self) -> None:
        body = "\n".join("print(%d)" % index for index in range(1200))
        text = "看这段代码：\n" + FENCE + "python\n" + body + "\n" + FENCE + "\n就这样。"
        chunks = split_message(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= LIMIT for chunk in chunks))
        for chunk in chunks:
            self.assertEqual(chunk.count(FENCE) % 2, 0, chunk[:60])


class RateLimiterTests(unittest.TestCase):
    def test_group_window_blocks_after_limit(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter(group_per_minute=2, private_per_second=1.0, clock=clock)
        for _ in range(2):
            self.assertEqual(limiter.delay(chat_id=1, chat_type="supergroup"), 0.0)
            limiter.record(chat_id=1, chat_type="supergroup")
        self.assertGreater(limiter.delay(chat_id=1, chat_type="supergroup"), 0.0)
        clock.advance(61.0)
        self.assertEqual(limiter.delay(chat_id=1, chat_type="supergroup"), 0.0)

    def test_retry_after_is_per_chat(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter(group_per_minute=10, private_per_second=1.0, clock=clock)
        limiter.apply_retry_after(chat_id=1, retry_after=30.0)
        self.assertGreater(limiter.delay(chat_id=1, chat_type="private"), 0.0)
        self.assertEqual(limiter.delay(chat_id=2, chat_type="private"), 0.0)


class OutboundQueueTests(unittest.IsolatedAsyncioTestCase):
    def _queue(self, sender: FakeSender, *, max_attempts: int = 3) -> OutboundQueue:
        self.clock = FakeClock()
        limiter = RateLimiter(group_per_minute=1000, private_per_second=1000.0, clock=self.clock)
        return OutboundQueue(sender, limiter, max_attempts=max_attempts, sleep=FakeSleep(self.clock))

    async def test_reply_only_on_first_chunk(self) -> None:
        sender = FakeSender()
        queue = self._queue(sender)
        await queue.enqueue(chat_id=1, chat_type="supergroup", text="a" * 9000, reply_to_message_id=77)
        await queue.drain(5.0)
        await queue.stop()
        self.assertGreaterEqual(len(sender.sent), 3)
        self.assertEqual(sender.sent[0]["reply_to_message_id"], 77)
        self.assertTrue(all(item["reply_to_message_id"] is None for item in sender.sent[1:]))

    async def test_rate_limited_message_is_retried(self) -> None:
        sender = FakeSender(rate_limited_times=1)
        queue = self._queue(sender)
        await queue.enqueue(chat_id=1, chat_type="supergroup", text="你好")
        await queue.drain(5.0)
        await queue.stop()
        self.assertEqual(len(sender.sent), 1)

    async def test_gives_up_after_max_attempts(self) -> None:
        sender = FakeSender(rate_limited_times=5)
        queue = self._queue(sender, max_attempts=2)
        await queue.enqueue(chat_id=1, chat_type="supergroup", text="你好")
        await queue.drain(5.0)
        await queue.stop()
        self.assertEqual(sender.sent, [])

    async def test_send_failure_drops_remaining_chunks(self) -> None:
        sender = FakeSender(fail_times=1)
        queue = self._queue(sender)
        await queue.enqueue(chat_id=1, chat_type="supergroup", text="a" * 9000)
        await queue.drain(5.0)
        await queue.stop()
        self.assertEqual(sender.sent, [])


class StickerRateLimiterTests(unittest.TestCase):
    def test_sticker_channel_is_one_per_twenty_seconds(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter(group_per_minute=1000, private_per_second=1000.0, clock=clock)
        self.assertEqual(limiter.delay(chat_id=1, chat_type="supergroup", kind="sticker"), 0.0)
        limiter.record(chat_id=1, chat_type="supergroup", kind="sticker")
        self.assertGreater(limiter.delay(chat_id=1, chat_type="supergroup", kind="sticker"), 19.0)
        self.assertEqual(limiter.delay(chat_id=1, chat_type="supergroup"), 0.0)  # 文本通道不受影响
        clock.advance(20.0)
        self.assertEqual(limiter.delay(chat_id=1, chat_type="supergroup", kind="sticker"), 0.0)

    def test_sticker_channel_is_per_chat(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter(group_per_minute=1000, private_per_second=1000.0, clock=clock)
        limiter.record(chat_id=1, chat_type="supergroup", kind="sticker")
        self.assertEqual(limiter.delay(chat_id=2, chat_type="supergroup", kind="sticker"), 0.0)


class StickerQueueTests(unittest.IsolatedAsyncioTestCase):
    def _queue(self, sender: FakeSender, *, max_attempts: int = 3) -> OutboundQueue:
        self.clock = FakeClock()
        limiter = RateLimiter(group_per_minute=1000, private_per_second=1000.0, clock=self.clock)
        return OutboundQueue(sender, limiter, max_attempts=max_attempts, sleep=FakeSleep(self.clock))

    async def test_send_sticker_success(self) -> None:
        sender = FakeSender()
        queue = self._queue(sender)
        self.assertTrue(await queue.send_sticker(chat_id=1, chat_type="supergroup", file_id="F1"))
        self.assertEqual(sender.stickers, [{"chat_id": 1, "file_id": "F1"}])

    async def test_send_sticker_retries_after_rate_limit(self) -> None:
        sender = FakeSender(rate_limited_times=1)
        queue = self._queue(sender)
        self.assertTrue(await queue.send_sticker(chat_id=1, chat_type="supergroup", file_id="F1"))
        self.assertEqual(len(sender.stickers), 1)

    async def test_send_sticker_gives_up_after_max_attempts(self) -> None:
        sender = FakeSender(rate_limited_times=5)
        queue = self._queue(sender, max_attempts=2)
        self.assertFalse(await queue.send_sticker(chat_id=1, chat_type="supergroup", file_id="F1"))
        self.assertEqual(sender.stickers, [])

    async def test_send_sticker_failure_returns_false(self) -> None:
        sender = FakeSender(sticker_fail_times=1)
        queue = self._queue(sender)
        self.assertFalse(await queue.send_sticker(chat_id=1, chat_type="supergroup", file_id="F1"))


if __name__ == "__main__":
    unittest.main()
