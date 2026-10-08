"""当前情绪：文案映射、TTL 与按群隔离（F4.5、docs/persona.md §2）。"""

from __future__ import annotations

import unittest

from app.session.mood import MOOD_TTL_SECONDS, MoodTracker, mood_label
from tests.offline.helpers import FakeClock


class MoodLabelTests(unittest.TestCase):
    def test_label_buckets(self) -> None:
        self.assertEqual(mood_label(0.5, 0.8), "心情不错，有点兴奋")
        self.assertEqual(mood_label(0.5, 0.1), "心情不错")
        self.assertEqual(mood_label(-0.5, 0.8), "有点烦躁")
        self.assertEqual(mood_label(-0.5, 0.1), "情绪有点低")
        self.assertEqual(mood_label(0.0, 0.9), "情绪平稳")


class MoodTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.mood = MoodTracker(clock=self.clock.monotonic)

    def test_unknown_chat_has_no_mood(self) -> None:
        self.assertIsNone(self.mood.describe(1))
        self.assertIsNone(self.mood.values(1))

    def test_record_then_describe(self) -> None:
        self.mood.record(1, 0.6, 0.7)
        self.assertEqual(self.mood.describe(1), "心情不错，有点兴奋")
        self.assertEqual(self.mood.values(1), (0.6, 0.7))

    def test_chats_are_isolated(self) -> None:
        self.mood.record(1, 0.6, 0.7)
        self.assertIsNone(self.mood.describe(2))

    def test_ttl_expires(self) -> None:
        self.mood.record(1, 0.6, 0.7)
        self.clock.advance(MOOD_TTL_SECONDS)
        self.assertIsNotNone(self.mood.describe(1))
        self.clock.advance(0.001)
        self.assertIsNone(self.mood.describe(1))

    def test_restart_clears_mood(self) -> None:
        self.mood.record(1, 0.6, 0.7)
        restarted = MoodTracker(clock=self.clock.monotonic)
        self.assertIsNone(restarted.describe(1))

    def test_latest_record_wins(self) -> None:
        self.mood.record(1, 0.6, 0.7)
        self.mood.record(1, -0.6, 0.1)
        self.assertEqual(self.mood.describe(1), "情绪有点低")


if __name__ == "__main__":
    unittest.main()
