"""主动发言闸门：冷却与每窗口上限（F2.4，程序侧 0 token）。"""

from __future__ import annotations

import unittest

from app.gate.limits import LIMIT_COOLDOWN, LIMIT_OK, LIMIT_QUOTA, ProactiveLimiter
from tests.offline.helpers import FakeClock


class ProactiveLimiterTests(unittest.TestCase):
    def _limiter(self, **overrides: object) -> ProactiveLimiter:
        values: dict[str, object] = {"cooldown_seconds": 20.0, "window_seconds": 300.0, "max_per_window": 3}
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

    def test_window_quota_blocks_and_frees_after_window(self) -> None:
        limiter = self._limiter()
        for _ in range(3):
            limiter.record(1)
            self.clock.advance(30.0)
        self.assertEqual(limiter.check(1).reason, LIMIT_QUOTA)
        self.clock.advance(300.0)
        self.assertTrue(limiter.check(1).allowed)

    def test_chats_are_isolated(self) -> None:
        limiter = self._limiter()
        limiter.record(1)
        self.assertFalse(limiter.check(1).allowed)
        self.assertTrue(limiter.check(2).allowed)

    def test_zero_max_disables_proactive_replies(self) -> None:
        limiter = self._limiter(max_per_window=0)
        self.assertEqual(limiter.check(1).reason, LIMIT_QUOTA)


if __name__ == "__main__":
    unittest.main()