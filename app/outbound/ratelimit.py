"""出站限速：自设更保守的阈值，429 只退避该群（docs/security.md §8）。"""

from __future__ import annotations

import time
from collections import deque
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...


class MonotonicClock:
    def monotonic(self) -> float:
        return time.monotonic()


class RateLimiter:
    """滑动窗口限速 + 429 退避；纯逻辑，时钟可注入。"""

    def __init__(
        self,
        *,
        group_per_minute: int,
        private_per_second: float,
        max_backoff: float = 60.0,
        clock: Clock | None = None,
    ) -> None:
        self._group_window = 60.0
        self._group_max = max(1, group_per_minute)
        self._private_window = 1.0
        self._private_max = max(1, int(round(private_per_second)))
        self._max_backoff = max_backoff
        self._clock = clock or MonotonicClock()
        self._sends: dict[tuple[str, int], deque[float]] = {}
        self._backoff_until: dict[int, float] = {}

    def delay(self, *, chat_id: int, chat_type: str) -> float:
        """还需要等待多少秒才能发送。"""
        now = self._clock.monotonic()
        return max(self._window_delay(chat_id, chat_type, now), self._backoff_until.get(chat_id, 0.0) - now)

    def record(self, *, chat_id: int, chat_type: str) -> None:
        """成功发送后登记，参与窗口计算。"""
        now = self._clock.monotonic()
        history = self._sends.setdefault((chat_type, chat_id), deque())
        history.append(now)
        self._prune(history, now, self._window_seconds(chat_type))

    def apply_retry_after(self, *, chat_id: int, retry_after: float) -> float:
        """Telegram 返回 429：只退避该群，上限 max_backoff。"""
        now = self._clock.monotonic()
        wait = min(max(0.0, retry_after), self._max_backoff)
        self._backoff_until[chat_id] = max(self._backoff_until.get(chat_id, 0.0), now + wait)
        return wait

    def _window_seconds(self, chat_type: str) -> float:
        return self._group_window if _is_group(chat_type) else self._private_window

    def _window_max(self, chat_type: str) -> int:
        return self._group_max if _is_group(chat_type) else self._private_max

    def _window_delay(self, chat_id: int, chat_type: str, now: float) -> float:
        history = self._sends.setdefault((chat_type, chat_id), deque())
        window = self._window_seconds(chat_type)
        self._prune(history, now, window)
        if len(history) < self._window_max(chat_type):
            return 0.0
        return max(0.0, window - (now - history[0]))

    @staticmethod
    def _prune(history: deque[float], now: float, window: float) -> None:
        while history and now - history[0] >= window:
            history.popleft()


def _is_group(chat_type: str) -> bool:
    return chat_type in ("group", "supergroup")
