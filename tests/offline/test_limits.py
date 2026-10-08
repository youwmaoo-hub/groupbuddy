"""主动发言闸门：冷却 + 重复消息过滤（F2.4，程序侧 0 token）。

用户口径（2026-10-08）：保留 20 秒冷却，删掉「每 300 秒最多 3 条」的窗口上限，
新增「同一人同一句话反复发」的重复过滤。
"""

from __future__ import annotations

import unittest

from app.gate.limits import LIMIT_COOLDOWN, LIMIT_OK, ProactiveLimiter, RepeatGuard
from tests.offline.helpers import FakeClock


class ProactiveLimiterTests(unittest.TestCase):
    def _limiter(self, **overrides: object) -> ProactiveLimiter:
        values: dict[str, object] = {"cooldown_seconds": 20.0}
        values.update(overrides)
        self.clock = FakeClock()
        return ProactiveLimiter(clock=self.clock, **values)  # type: ignore[arg-type]

    def test_first_proactive_reply_is_allowed(self) -> None:
        decision = self._limiter().check(1)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, LIMIT_OK)

    def test_cooldown_blocks_then_expires(self) -> None:
        limiter = self._limiter()
        limiter.record(1)
        self.assertEqual(limiter.check(1).reason, LIMIT_COOLDOWN)
        self.clock.advance(19.0)
        self.assertEqual(limiter.check(1).reason, LIMIT_COOLDOWN)
        self.clock.advance(1.0)
        self.assertTrue(limiter.check(1).allowed)

    def test_no_window_quota_any_more(self) -> None:
        """窗口上限已删除：只要过了冷却，隔多久都能继续接话（F2.4 现状）。"""
        limiter = self._limiter()
        for _ in range(5):
            self.assertTrue(limiter.check(1).allowed)
            limiter.record(1)
            self.clock.advance(21.0)
        self.assertTrue(limiter.check(1).allowed)

    def test_chats_are_isolated(self) -> None:
        limiter = self._limiter()
        limiter.record(1)
        self.assertFalse(limiter.check(1).allowed)
        self.assertTrue(limiter.check(2).allowed)

    def test_zero_cooldown_disables_throttling(self) -> None:
        limiter = self._limiter(cooldown_seconds=0)
        limiter.record(1)
        self.assertTrue(limiter.check(1).allowed)


class RepeatGuardTests(unittest.TestCase):
    def _guard(self, **overrides: object) -> RepeatGuard:
        values: dict[str, object] = {"window_seconds": 300.0}
        values.update(overrides)
        self.clock = FakeClock()
        return RepeatGuard(clock=self.clock, **values)  # type: ignore[arg-type]

    def test_same_text_from_same_user_is_a_repeat(self) -> None:
        guard = self._guard()
        self.assertFalse(guard.is_repeat(1, 7, "在吗"))
        self.assertTrue(guard.is_repeat(1, 7, " 在吗 "))  # 去空白后相同
        self.assertTrue(guard.is_repeat(1, 7, "在吗"))
        self.assertFalse(guard.is_repeat(1, 8, "在吗"))  # 换个人不算重复
        self.assertFalse(guard.is_repeat(2, 7, "在吗"))  # 换个群不算重复

    def test_case_and_width_are_normalized(self) -> None:
        guard = self._guard()
        guard.is_repeat(1, 7, "Hello World")
        self.assertTrue(guard.is_repeat(1, 7, "hello   world"))

    def test_repeat_expires_after_the_window(self) -> None:
        guard = self._guard(window_seconds=300.0)
        guard.is_repeat(1, 7, "在吗")
        self.clock.advance(299.0)
        self.assertTrue(guard.is_repeat(1, 7, "在吗"))
        self.clock.advance(2.0)
        self.assertFalse(guard.is_repeat(1, 7, "在吗"))

    def test_window_records_are_pruned(self) -> None:
        guard = self._guard(window_seconds=10.0)
        for index in range(50):
            guard.is_repeat(1, 7, f"第 {index} 句")
        self.clock.advance(11.0)
        self.assertFalse(guard.is_repeat(1, 7, "全新的一句"))


if __name__ == "__main__":
    unittest.main()
