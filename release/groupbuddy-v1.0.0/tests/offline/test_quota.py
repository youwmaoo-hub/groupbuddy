"""F5.3：日/月 token 配额的边界行为（docs/token.md §4.1）。

判定只读 `usage`，所以这里同时锁住"统计口径"与"拒绝语义"。
"""

from __future__ import annotations

import unittest

from app.ops.quota import DAILY_EXHAUSTED_TEXT, MONTHLY_EXHAUSTED_TEXT, QuotaGuard
from app.storage.repo import usage
from tests.offline.helpers import DbTestCase, make_settings

TODAY = "2026-10-07"
YESTERDAY = "2026-10-06"
LAST_MONTH = "2026-09-30"


class QuotaGuardTests(DbTestCase):
    def _guard(self, *, daily: int = 0, monthly: int = 0, today: str = TODAY) -> QuotaGuard:
        settings = make_settings(
            self.tmp,
            QUOTA_DAILY_TOKENS=daily,
            QUOTA_MONTHLY_TOKENS=monthly,
        )
        return QuotaGuard(self.connection, settings, today=lambda: today)

    async def _spend(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        chat_id: int = 1,
        day: str = TODAY,
        purpose: str = "chat",
    ) -> None:
        await usage.record(
            self.connection,
            chat_id=chat_id,
            user_id=42,
            day=day,
            model="deepseek-flash",
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            output_tokens=output_tokens,
            purpose=purpose,
        )

    async def test_unconfigured_quota_is_unlimited(self) -> None:
        guard = self._guard()
        await self._spend(input_tokens=5_000_000, output_tokens=5_000_000)
        self.assertFalse(guard.enabled)
        self.assertIsNone(await guard.check(1))

    async def test_zero_is_the_same_as_unconfigured(self) -> None:
        guard = self._guard(daily=0, monthly=0)
        await self._spend(input_tokens=100)
        self.assertIsNone(await guard.check(1))

    async def test_under_the_limit_is_allowed(self) -> None:
        guard = self._guard(daily=100)
        await self._spend(input_tokens=40, output_tokens=40)
        self.assertEqual(await usage.tokens_used(self.connection, chat_id=1, day_prefix=TODAY), 80)
        self.assertIsNone(await guard.check(1))

    async def test_exactly_at_the_limit_is_rejected(self) -> None:
        guard = self._guard(daily=100)
        await self._spend(input_tokens=60, output_tokens=40)
        self.assertEqual(await guard.check(1), DAILY_EXHAUSTED_TEXT)

    async def test_over_the_limit_is_rejected(self) -> None:
        guard = self._guard(daily=100)
        await self._spend(input_tokens=200)
        self.assertEqual(await guard.check(1), DAILY_EXHAUSTED_TEXT)

    async def test_daily_and_monthly_report_their_own_limit(self) -> None:
        daily_guard = self._guard(daily=100, monthly=1000)
        await self._spend(input_tokens=100)
        self.assertEqual(await daily_guard.check(1), DAILY_EXHAUSTED_TEXT)

        monthly_guard = self._guard(daily=1000, monthly=100)
        self.assertEqual(await monthly_guard.check(1), MONTHLY_EXHAUSTED_TEXT)

    async def test_daily_is_checked_before_monthly(self) -> None:
        guard = self._guard(daily=100, monthly=100)
        await self._spend(input_tokens=100)
        self.assertEqual(await guard.check(1), DAILY_EXHAUSTED_TEXT)

    async def test_previous_day_does_not_count_toward_today(self) -> None:
        guard = self._guard(daily=100)
        await self._spend(input_tokens=100, day=YESTERDAY)
        self.assertIsNone(await guard.check(1))

    async def test_previous_month_does_not_count_toward_this_month(self) -> None:
        guard = self._guard(monthly=100)
        await self._spend(input_tokens=100, day=LAST_MONTH)
        self.assertIsNone(await guard.check(1))

    async def test_each_chat_has_its_own_quota(self) -> None:
        guard = self._guard(daily=100)
        await self._spend(input_tokens=100, chat_id=2)
        self.assertIsNone(await guard.check(1))
        self.assertEqual(await guard.check(2), DAILY_EXHAUSTED_TEXT)

    async def test_cached_tokens_are_not_counted_twice(self) -> None:
        # cached_tokens 已含在 input_tokens（prompt_tokens）里，只按输入+输出计
        guard = self._guard(daily=100)
        await self._spend(input_tokens=60, cached_tokens=60, output_tokens=39)
        self.assertEqual(await usage.tokens_used(self.connection, chat_id=1, day_prefix=TODAY), 99)
        self.assertIsNone(await guard.check(1))
        await self._spend(output_tokens=1)
        self.assertEqual(await guard.check(1), DAILY_EXHAUSTED_TEXT)

    async def test_background_usage_counts_toward_the_group_quota(self) -> None:
        # 摘要等后台调用同样花该群的钱，所以计入该群配额（口径写进 docs/token.md §4.1）
        guard = self._guard(daily=100)
        await self._spend(input_tokens=60, output_tokens=40, purpose="summary")
        self.assertEqual(await guard.check(1), DAILY_EXHAUSTED_TEXT)

    async def test_purpose_filter_is_optional(self) -> None:
        await self._spend(input_tokens=10, purpose="chat")
        await self._spend(input_tokens=20, purpose="summary")
        self.assertEqual(await usage.tokens_used(self.connection, chat_id=1, day_prefix=TODAY), 30)
        self.assertEqual(
            await usage.tokens_used(self.connection, chat_id=1, day_prefix=TODAY, purpose="chat"),
            10,
        )

    async def test_no_rows_means_zero(self) -> None:
        guard = self._guard(daily=1000, monthly=1000)
        self.assertEqual(await usage.tokens_used(self.connection, chat_id=1, day_prefix=TODAY), 0)
        self.assertEqual(await usage.tokens_used(self.connection, chat_id=1, day_prefix="2026-10"), 0)
        self.assertIsNone(await guard.check(1))


if __name__ == "__main__":
    unittest.main()
