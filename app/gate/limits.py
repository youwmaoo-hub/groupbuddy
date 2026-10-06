"""主动发言的冷却与每窗口上限：程序侧判定，被压住的消息 0 token。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from app.gate.debounce import Clock, MonotonicClock

LIMIT_OK = "ok"
LIMIT_COOLDOWN = "cooldown"
LIMIT_QUOTA = "quota"


@dataclass(frozen=True, slots=True)
class LimitDecision:
    allowed: bool
    reason: str


class ProactiveLimiter:
    """每群独立：Bot 不主动连续插话（docs/requirements.md §2.1）。

    强触发（@Bot / 回复 / 别名）不经过这里；状态在进程内存中，重启后归零。
    """

    def __init__(
        self,
        *,
        cooldown_seconds: float,
        window_seconds: float,
        max_per_window: int,
        clock: Clock | None = None,
    ) -> None:
        self._cooldown = max(0.0, cooldown_seconds)
        self._window = max(0.0, window_seconds)
        self._max = max(0, max_per_window)
        self._clock = clock or MonotonicClock()
        self._spoken: dict[int, deque[float]] = {}

    def check(self, chat_id: int) -> LimitDecision:
        """额度用尽 → quota；距上次主动发言不足冷却 → cooldown。"""
        now = self._clock.monotonic()
        recent = self._prune(chat_id, now)
        if self._max <= 0 or len(recent) >= self._max:
            return LimitDecision(False, LIMIT_QUOTA)
        if recent and now - recent[-1] < self._cooldown:
            return LimitDecision(False, LIMIT_COOLDOWN)
        return LimitDecision(True, LIMIT_OK)

    def record(self, chat_id: int) -> None:
        """在"主动发言真的发出去了"之后调用，不是判定通过时。"""
        now = self._clock.monotonic()
        self._prune(chat_id, now).append(now)

    def _prune(self, chat_id: int, now: float) -> deque[float]:
        recent = self._spoken.setdefault(chat_id, deque())
        while recent and now - recent[0] > self._window:
            recent.popleft()
        return recent


__all__ = ["LIMIT_COOLDOWN", "LIMIT_OK", "LIMIT_QUOTA", "LimitDecision", "ProactiveLimiter"]