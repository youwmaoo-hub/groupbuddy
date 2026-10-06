"""闸门层：去重、硬过滤、触发判定、debounce 合并、Update 映射。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.gate.debounce import Debouncer
from app.gate.dedupe import UpdateDeduplicator
from app.gate.filters import DROP_BOT_AUTHOR, DROP_COMMAND, DROP_NO_TEXT, screen
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

    def test_commands_are_deferred_to_stage_8(self) -> None:
        self.assertEqual(
            screen(make_incoming(update_id=1, chat_id=1, message_id=1, text=" /stats")).reason,
            DROP_COMMAND,
        )


class TriggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self._tmp.name), BOT_ALIASES="小助手")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_strong_triggers(self) -> None:
        detector = TriggerDetector(self.settings)
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

    def test_plain_chatter_is_ignored(self) -> None:
        detector = TriggerDetector(self.settings)
        decision = detector.decide(
            make_incoming(update_id=9, chat_id=1, message_id=9, text="哈哈哈哈", mentions_bot=False)
        )
        self.assertFalse(decision.should_respond)
        self.assertEqual(decision.reason, "not_addressed")


class DebounceTests(unittest.TestCase):
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