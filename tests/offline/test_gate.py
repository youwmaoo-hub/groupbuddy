"""闸门层：去重、硬过滤、触发判定、debounce 合并、Update 映射。"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.gate.debounce import Batch, Debouncer
from app.gate.dedupe import UpdateDeduplicator
from app.gate.filters import DROP_BOT_AUTHOR, DROP_COMMAND, DROP_NO_TEXT, DROP_PRIVATE, screen
from app.gate.limits import ProactiveLimiter, RepeatGuard
from app.gate.queue import ChatQueue
from app.gate.trigger import TriggerDetector
from app.telegram.parse import parse_update
from tests.offline.helpers import DbTestCase, FakeClock, make_incoming, make_settings


def make_update(
    *,
    update_id: int,
    text: str,
    entities: tuple = (),
    thread_id: int | None = None,
    chat_id: int = -100,
    user_id: int = 77,
    is_bot: bool = False,
    reply_to: object | None = None,
) -> SimpleNamespace:
    """仿造 aiogram 的 Update 结构（鸭子类型，无需安装 aiogram 类型）。"""
    return SimpleNamespace(
        update_id=update_id,
        message=SimpleNamespace(
            message_id=1,
            text=text,
            caption=None,
            message_thread_id=thread_id,
            reply_to_message=reply_to,
            entities=entities,
            chat=SimpleNamespace(id=chat_id, type="supergroup"),
            from_user=SimpleNamespace(id=user_id, is_bot=is_bot),
        ),
    )


class FilterTests(unittest.TestCase):
    def test_normal_message_passes(self) -> None:
        self.assertTrue(screen(make_incoming(update_id=1, chat_id=1, message_id=1, text="你好")).allowed)

    def test_bot_author_is_dropped(self) -> None:
        result = screen(make_incoming(update_id=1, chat_id=1, message_id=1, text="你好", is_bot_author=True))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, DROP_BOT_AUTHOR)

    def test_empty_text_is_dropped(self) -> None:
        self.assertEqual(
            screen(make_incoming(update_id=1, chat_id=1, message_id=1, text="   ")).reason,
            DROP_NO_TEXT,
        )

    def test_commands_are_dropped_without_the_command_channel(self) -> None:
        self.assertEqual(
            screen(make_incoming(update_id=1, chat_id=1, message_id=1, text=" /stats")).reason,
            DROP_COMMAND,
        )

    def test_commands_pass_when_the_command_channel_asks(self) -> None:
        # 群主命令通道（阶段 8）先于本过滤器分发命令（docs/security.md §2 第 3 步）
        result = screen(
            make_incoming(update_id=1, chat_id=1, message_id=1, text="/settings"),
            allow_commands=True,
        )
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "ok")

    def test_private_chat_is_dropped_by_default(self) -> None:
        # 私聊里手打 @Bot 也必须被丢弃：0 token、不写库（docs/requirements.md §2.2）
        result = screen(
            make_incoming(update_id=1, chat_id=1, message_id=1, text="@bot 你好", chat_type="private")
        )
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, DROP_PRIVATE)

    def test_channel_post_is_dropped(self) -> None:
        result = screen(
            make_incoming(update_id=1, chat_id=1, message_id=1, text="公告", chat_type="channel")
        )
        self.assertEqual(result.reason, DROP_PRIVATE)

    def test_private_chat_passes_when_switch_enabled(self) -> None:
        result = screen(
            make_incoming(update_id=1, chat_id=1, message_id=1, text="你好", chat_type="private"),
            allow_private_chat=True,
        )
        self.assertTrue(result.allowed)


def make_batch(chat_id: int, message_ids: list[int]) -> Batch:
    items = [
        make_incoming(update_id=1000 + message_id, chat_id=chat_id, message_id=message_id, text=f"m{message_id}")
        for message_id in message_ids
    ]
    return Batch(chat_id=chat_id, items=items, last_at=0.0, full=False)


class ChatQueueTests(unittest.IsolatedAsyncioTestCase):
    """同群同一时间只有一个回复任务；运行期间的新消息合并为下一轮一批。"""

    async def test_new_messages_wait_for_next_round(self) -> None:
        first_started = asyncio.Event()
        release = asyncio.Event()
        seen: list[list[int]] = []

        async def handler(batch: Batch) -> None:
            seen.append([item.message_id for item in batch.items])
            if len(seen) == 1:
                first_started.set()
                await release.wait()

        queue = ChatQueue(handler, max_batch_messages=5)
        await queue.submit(make_batch(1, [1, 2]))
        await first_started.wait()
        await queue.submit(make_batch(1, [3]))
        await queue.submit(make_batch(1, [4]))
        self.assertEqual(len(seen), 1)  # 正在处理时绝不开始下一轮
        release.set()
        await queue.drain(5.0)
        await queue.stop()
        self.assertEqual(seen, [[1, 2], [3, 4]])  # 结束后只补跑一轮

    async def test_pending_batch_keeps_newest_only(self) -> None:
        first_started = asyncio.Event()
        release = asyncio.Event()
        seen: list[list[int]] = []

        async def handler(batch: Batch) -> None:
            seen.append([item.message_id for item in batch.items])
            if len(seen) == 1:
                first_started.set()
                await release.wait()

        queue = ChatQueue(handler, max_batch_messages=3)
        await queue.submit(make_batch(9, [1, 2]))
        await first_started.wait()
        for message_id in (3, 4, 5, 6):
            await queue.submit(make_batch(9, [message_id]))
        release.set()
        await queue.drain(5.0)
        await queue.stop()
        self.assertEqual(seen, [[1, 2], [4, 5, 6]])


class TriggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self._tmp.name), BOT_ALIASES="小助手")
        self.clock = FakeClock()
        self.limiter = ProactiveLimiter(cooldown_seconds=20.0, clock=self.clock)
        self.repeats = RepeatGuard(window_seconds=300.0, clock=self.clock)
        self.detector = TriggerDetector(self.settings, self.limiter, self.repeats)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_strong_triggers(self) -> None:
        detector = self.detector
        cases = [
            (make_incoming(update_id=1, chat_id=1, message_id=1, text="问题"), "mention"),
            (
                make_incoming(
                    update_id=2, chat_id=1, message_id=2, text="问题", mentions_bot=False, reply_to_bot=True
                ),
                "reply_to_bot",
            ),
            (
                make_incoming(update_id=3, chat_id=1, message_id=3, text="小助手在吗", mentions_bot=False),
                "alias",
            ),
        ]
        for incoming, expected in cases:
            with self.subTest(expected=expected):
                decision = detector.decide(incoming)
                self.assertTrue(decision.should_respond)
                self.assertEqual(decision.reason, expected)

    def test_plain_chatter_is_answered_generically(self) -> None:
        """没命中任何内容原因码也接话：用 general 兜底（用户要求「大部分都接」）。"""
        decision = self.detector.decide(
            make_incoming(update_id=9, chat_id=1, message_id=9, text="哈哈哈哈", mentions_bot=False)
        )
        self.assertEqual((decision.verdict, decision.reason), ("respond", "general"))
        self.assertTrue(decision.proactive)

    def test_reply_to_another_bot_is_background(self) -> None:
        # 人类在跟别的 Bot 对话时本 Bot 不插嘴：不前进模型、不占冷却（docs/requirements.md §2.1）
        decision = self.detector.decide(
            make_incoming(
                update_id=20,
                chat_id=1,
                message_id=20,
                text="这个怎么解决",
                mentions_bot=False,
                reply_to_other_bot=True,
            )
        )
        self.assertEqual(decision.verdict, "ignore")
        self.assertEqual(decision.reason, "other_bot_reply")

    def test_reply_to_another_bot_still_answers_when_addressed(self) -> None:
        decision = self.detector.decide(
            make_incoming(
                update_id=21,
                chat_id=1,
                message_id=21,
                text="小助手你看",
                mentions_bot=False,
                reply_to_other_bot=True,
            )
        )
        self.assertTrue(decision.should_respond)
        self.assertEqual(decision.reason, "alias")

    def test_unaddressed_question_is_a_proactive_candidate(self) -> None:
        decision = self.detector.decide(
            make_incoming(update_id=11, chat_id=1, message_id=11, text="这个怎么解决", mentions_bot=False)
        )
        self.assertEqual(decision.verdict, "respond")
        self.assertEqual(decision.reason, "question")
        self.assertTrue(decision.proactive)

    def test_troubleshoot_and_resource_words_trigger(self) -> None:
        cases = (("导入的时候报错了", "troubleshoot"), ("看看 https://example.com/a", "resource"))
        for index, (text, reason) in enumerate(cases):
            with self.subTest(reason=reason):
                decision = self.detector.decide(
                    make_incoming(
                        update_id=20 + index,
                        chat_id=5,
                        message_id=20 + index,
                        text=text,
                        mentions_bot=False,
                    )
                )
                self.assertEqual((decision.verdict, decision.reason), ("respond", reason))

    def test_followup_near_bot_reply(self) -> None:
        decision = self.detector.decide(
            make_incoming(update_id=31, chat_id=1, message_id=31, text="然后继续讲讲", mentions_bot=False),
            since_bot_reply=2,
        )
        self.assertEqual((decision.verdict, decision.reason), ("respond", "followup"))

    def test_followup_outside_window_falls_back_to_general(self) -> None:
        """追问窗口只决定「原因码」，不再决定「回不回」：窗口外照样接话，只是标 general。"""
        for gap in (0, 6):
            with self.subTest(gap=gap):
                decision = self.detector.decide(
                    make_incoming(
                        update_id=32 + gap,
                        chat_id=1,
                        message_id=32 + gap,
                        text=f"然后继续讲讲{gap}",
                        mentions_bot=False,
                    ),
                    since_bot_reply=gap,
                )
                self.assertEqual((decision.verdict, decision.reason), ("respond", "general"))

    def test_bot_author_is_never_answered(self) -> None:
        """人类中心（阶段 8）：其他 Bot 的消息即使 @ 本 Bot 也不回，避免 Bot↔Bot 循环。"""
        decision = self.detector.decide(
            make_incoming(
                update_id=50,
                chat_id=1,
                message_id=50,
                text="@bot 你好",
                mentions_bot=True,
                is_bot_author=True,
            )
        )
        self.assertEqual((decision.verdict, decision.reason), ("ignore", "bot_author"))

    def test_topic_message_after_bot_reply_is_a_candidate(self) -> None:
        decision = self.detector.decide(
            make_incoming(update_id=60, chat_id=1, message_id=60, text="爬山记得带防晒霜", mentions_bot=False),
            since_bot_reply=3,
            bot_last_text="周末去爬山我带帐篷",
        )
        self.assertEqual((decision.verdict, decision.reason), ("respond", "topic"))
        self.assertTrue(decision.proactive)

    def test_topic_window_and_stopwords(self) -> None:
        cases = (
            (9, "周末去爬山我带帐篷", "爬山记得带防晒霜"),  # 超出同话题窗口
            (3, "这样就可以了吧", "这个东西可以吗"),  # 只共享停用 2 字组
        )
        for index, (gap, bot_text, text) in enumerate(cases):
            with self.subTest(gap=gap):
                decision = self.detector.decide(
                    make_incoming(update_id=70 + index, chat_id=2, message_id=70 + index, text=text),
                    since_bot_reply=gap,
                    bot_last_text=bot_text,
                )
                self.assertNotEqual(decision.reason, "topic")

    def test_emotion_message_is_a_candidate(self) -> None:
        decision = self.detector.decide(
            make_incoming(update_id=80, chat_id=1, message_id=80, text="刚上线就崩了，我破防了", mentions_bot=False)
        )
        self.assertEqual((decision.verdict, decision.reason), ("respond", "emotion"))

    def test_quiet_open_after_a_long_silence(self) -> None:
        """久静后开口只是原因码：安静期不足也接话（general），够久才标 quiet_open。"""
        cases = ((None, "quiet_open"), (20, "quiet_open"), (19, "general"))
        for index, (gap, expected) in enumerate(cases):
            with self.subTest(gap=gap):
                decision = self.detector.decide(
                    make_incoming(
                        update_id=90 + index,
                        chat_id=3,
                        message_id=90 + index,
                        text=f"周末准备去爬山，爬完回来吃火锅（第{index}次）",
                        mentions_bot=False,
                    ),
                    since_bot_reply=gap,
                )
                self.assertEqual((decision.verdict, decision.reason), ("respond", expected))

    def test_short_ack_is_still_answered_at_gate_level(self) -> None:
        """闸门不做「值不值得回」的取舍：短句兜底 general；噪声过滤在 runner 里更早完成。"""
        decision = self.detector.decide(
            make_incoming(update_id=95, chat_id=3, message_id=95, text="嗯嗯，行", mentions_bot=False),
            since_bot_reply=None,
        )
        self.assertEqual((decision.verdict, decision.reason), ("respond", "general"))

    def test_repeated_message_from_same_user_is_ignored(self) -> None:
        """去重：同一个人在同一群反复发同一句，只接第一次（用户要求「重复的过滤掉」）。"""
        first = make_incoming(
            update_id=97, chat_id=7, message_id=97, text="在吗", user_id=9, mentions_bot=False
        )
        again = make_incoming(
            update_id=98, chat_id=7, message_id=98, text="在吗", user_id=9, mentions_bot=False
        )
        self.assertEqual(self.detector.decide(first).reason, "question")
        decision = self.detector.decide(again)
        self.assertEqual((decision.verdict, decision.reason), ("ignore", "repeat"))

    def test_new_weak_triggers_still_respect_the_limiter(self) -> None:
        self.limiter.record(4)
        decision = self.detector.decide(
            make_incoming(update_id=96, chat_id=4, message_id=96, text="今天摸鱼摸得有点过分", mentions_bot=False)
        )
        self.assertEqual((decision.verdict, decision.reason), ("wait", "cooldown"))

    def test_cooldown_suppresses_proactive_reply(self) -> None:
        self.limiter.record(1)
        decision = self.detector.decide(
            make_incoming(update_id=41, chat_id=1, message_id=41, text="这个怎么弄", mentions_bot=False)
        )
        self.assertEqual((decision.verdict, decision.reason), ("wait", "cooldown"))
        self.assertFalse(decision.should_respond)

    def test_no_window_quota_any_more(self) -> None:
        """窗口上限已删除：隔 21 秒连续接话 3 次后第 4 次仍然放行（用户要求删掉 300s/3 条）。"""
        for index in range(3):
            self.assertTrue(self.detector.decide(
                make_incoming(
                    update_id=42 + index, chat_id=1, message_id=42 + index, text=f"这个怎么弄{index}", mentions_bot=False
                )
            ).should_respond)
            self.limiter.record(1)
            self.clock.advance(21.0)
        decision = self.detector.decide(
            make_incoming(update_id=46, chat_id=1, message_id=46, text="这个怎么弄4", mentions_bot=False)
        )
        self.assertEqual((decision.verdict, decision.reason), ("respond", "question"))

    def test_strong_trigger_ignores_cooldown(self) -> None:
        self.limiter.record(1)
        decision = self.detector.decide(
            make_incoming(update_id=43, chat_id=1, message_id=43, text="@bot 在吗")
        )
        self.assertEqual((decision.verdict, decision.reason), ("respond", "mention"))
        self.assertFalse(decision.proactive)


class DebounceTests(unittest.TestCase):
    def test_max_one_gives_each_message_its_own_batch(self) -> None:
        """生产默认（关掉合并）：DEBOUNCE_MAX_MESSAGES=1 + 0 秒静默 → 每条消息各自成批。"""
        clock = FakeClock()
        debouncer = Debouncer(quiet_seconds=0.0, max_messages=1, clock=clock)
        for index in range(3):
            debouncer.add(1, make_incoming(update_id=index, chat_id=1, message_id=index, text=f"m{index}"))
        batches = debouncer.due()
        self.assertEqual([[item.message_id for item in batch.items] for batch in batches], [[0], [1], [2]])
        self.assertEqual(debouncer.due(), [])

    def test_rapid_messages_merge_into_one_batch(self) -> None:
        clock = FakeClock()
        debouncer = Debouncer(quiet_seconds=1.2, max_messages=5, clock=clock)
        for index in range(4):
            debouncer.add(1, make_incoming(update_id=index, chat_id=1, message_id=index, text=f"m{index}"))
            clock.advance(0.3)
        self.assertEqual(debouncer.due(), [])
        self.assertAlmostEqual(debouncer.next_deadline(), 0.9, places=6)  # 返回剩余等待秒数
        clock.advance(1.0)
        batches = debouncer.due()
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0].items), 4)
        self.assertFalse(batches[0].full)

    def test_max_messages_flushes_immediately(self) -> None:
        clock = FakeClock()
        debouncer = Debouncer(quiet_seconds=1.2, max_messages=3, clock=clock)
        for index in range(3):
            debouncer.add(7, make_incoming(update_id=index, chat_id=7, message_id=index, text=f"m{index}"))
        batches = debouncer.due()
        self.assertEqual(len(batches), 1)
        self.assertTrue(batches[0].full)

    def test_chats_are_independent(self) -> None:
        clock = FakeClock()
        debouncer = Debouncer(quiet_seconds=1.0, max_messages=5, clock=clock)
        debouncer.add(1, make_incoming(update_id=1, chat_id=1, message_id=1, text="a"))
        clock.advance(2.0)
        debouncer.add(2, make_incoming(update_id=2, chat_id=2, message_id=2, text="b"))
        batches = debouncer.due()
        self.assertEqual([batch.chat_id for batch in batches], [1])

    def test_strong_message_clears_proactive_flag(self) -> None:
        clock = FakeClock()
        debouncer = Debouncer(quiet_seconds=1.2, max_messages=5, clock=clock)
        first = debouncer.add(
            1, make_incoming(update_id=1, chat_id=1, message_id=1, text="这个怎么弄"), proactive=True
        )
        self.assertTrue(first.proactive)
        batch = debouncer.add(1, make_incoming(update_id=2, chat_id=1, message_id=2, text="@bot 在吗"))
        self.assertFalse(batch.proactive)


class DedupeGateTests(DbTestCase):
    async def test_duplicate_update_reported_once(self) -> None:
        dedupe = UpdateDeduplicator(self.connection)
        self.assertTrue(await dedupe.first_seen(555, 1))
        self.assertFalse(await dedupe.first_seen(555, 1))


class ParseTests(unittest.TestCase):
    def test_parse_update_maps_plain_values(self) -> None:
        incoming = parse_update(
            make_update(update_id=12345, text="你好", thread_id=9),
            bot_id=999,
            bot_username="my_bot",
        )
        self.assertIsNotNone(incoming)
        assert incoming is not None
        self.assertEqual(incoming.update_id, 12345)
        self.assertEqual(incoming.chat_id, -100)
        self.assertEqual(incoming.text, "你好")
        self.assertEqual(incoming.thread_id, 9)
        self.assertFalse(incoming.mentions_bot)
        self.assertFalse(incoming.is_bot_author)
        self.assertFalse(incoming.reply_to_bot)

    def test_mention_by_text_is_detected(self) -> None:
        incoming = parse_update(
            make_update(update_id=3, text="帮我看看 @my_bot"),
            bot_id=999,
            bot_username="my_bot",
        )
        assert incoming is not None
        self.assertTrue(incoming.mentions_bot)
        self.assertEqual(incoming.text, "帮我看看 @my_bot")

    def test_mention_entity_is_detected(self) -> None:
        entity = SimpleNamespace(type="mention", offset=0, length=7, user=None)
        incoming = parse_update(
            make_update(update_id=4, text="@my_bot 在吗", entities=(entity,)),
            bot_id=999,
            bot_username="my_bot",
        )
        assert incoming is not None
        self.assertTrue(incoming.mentions_bot)

    def test_text_mention_entity_matches_bot_id(self) -> None:
        entity = SimpleNamespace(type="text_mention", user=SimpleNamespace(id=999))
        incoming = parse_update(
            make_update(update_id=5, text="你好", entities=(entity,)),
            bot_id=999,
            bot_username="my_bot",
        )
        assert incoming is not None
        self.assertTrue(incoming.mentions_bot)

    def test_reply_to_bot_is_detected(self) -> None:
        reply = SimpleNamespace(from_user=SimpleNamespace(id=999))
        incoming = parse_update(
            make_update(update_id=6, text="继续", reply_to=reply),
            bot_id=999,
            bot_username="my_bot",
        )
        assert incoming is not None
        self.assertTrue(incoming.reply_to_bot)
        self.assertFalse(incoming.reply_to_other_bot)

    def test_reply_to_another_bot_is_flagged_as_background(self) -> None:
        reply = SimpleNamespace(from_user=SimpleNamespace(id=888, is_bot=True))
        incoming = parse_update(
            make_update(update_id=8, text="继续", reply_to=reply),
            bot_id=999,
            bot_username="my_bot",
        )
        assert incoming is not None
        self.assertFalse(incoming.reply_to_bot)
        self.assertTrue(incoming.reply_to_other_bot)

    def test_reply_to_a_human_is_not_flagged(self) -> None:
        reply = SimpleNamespace(from_user=SimpleNamespace(id=777, is_bot=False))
        incoming = parse_update(
            make_update(update_id=9, text="继续", reply_to=reply),
            bot_id=999,
            bot_username="my_bot",
        )
        assert incoming is not None
        self.assertFalse(incoming.reply_to_bot)
        self.assertFalse(incoming.reply_to_other_bot)

    def test_bot_author_is_flagged(self) -> None:
        incoming = parse_update(
            make_update(update_id=7, text="我也是 Bot", user_id=888, is_bot=True),
            bot_id=999,
            bot_username="my_bot",
        )
        assert incoming is not None
        self.assertTrue(incoming.is_bot_author)

    def test_returns_none_without_message(self) -> None:
        self.assertIsNone(parse_update(SimpleNamespace(update_id=1, message=None), bot_id=1, bot_username="b"))


if __name__ == "__main__":
    unittest.main()