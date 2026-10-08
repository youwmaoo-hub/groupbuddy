"""主动发言闸门（进程内状态）：冷却，以及「重复消息过滤」；被压住的判定 0 token。"""

from __future__ import annotations

from dataclasses import dataclass

from app.gate.debounce import Clock, MonotonicClock

LIMIT_OK = "ok"
LIMIT_COOLDOWN = "cooldown"

#: 重复表最多跟踪多少个 (chat_id, user_id)；超过就清掉窗口外的旧记录（进程内状态，不落库）。
MAX_TRACKED_SENDERS = 512


@dataclass(frozen=True, slots=True)
class LimitDecision:
    allowed: bool
    reason: str


class ProactiveLimiter:
    """每群独立：两次「主动接话」之间至少间隔 N 秒（默认 20，docs/requirements.md §2.1）。

    强触发（@Bot / 回复 / 别名）不经过这里；状态在进程内存中，重启后归零。
    历史上的「每窗口上限」已按需求删除：现在只保留冷却一道闸门。
    """

    def __init__(self, *, cooldown_seconds: float, clock: Clock | None = None) -> None:
        self._cooldown = max(0.0, cooldown_seconds)
        self._clock = clock or MonotonicClock()
        self._last_spoken: dict[int, float] = {}

    def check(self, chat_id: int) -> LimitDecision:
        """距上次主动发言不足冷却 → cooldown（本轮 0 token、只入库、不补答）。"""
        last = self._last_spoken.get(chat_id)
        if last is not None and self._clock.monotonic() - last < self._cooldown:
            return LimitDecision(False, LIMIT_COOLDOWN)
        return LimitDecision(True, LIMIT_OK)

    def record(self, chat_id: int) -> None:
        """在「主动发言真的发出去了」之后调用，不是判定通过时。"""
        self._last_spoken[chat_id] = self._clock.monotonic()


class RepeatGuard:
    """同一个群、同一个人重复发同样的内容 → 判为重复、不回（「重复的过滤掉」）。

    只看「未点名」的候选消息：点名/回复/别名永不经过这里（被叫到一定要回）。
    命中时不刷新时间戳，所以连续刷屏会持续判为重复，直到窗口过去。
    """

    def __init__(self, *, window_seconds: float, clock: Clock | None = None) -> None:
        self._window = max(0.0, window_seconds)
        self._clock = clock or MonotonicClock()
        self._seen: dict[tuple[int, int], tuple[str, float]] = {}

    def is_repeat(self, chat_id: int, user_id: int, text: str) -> bool:
        if self._window <= 0:  # 0 = 关闭重复过滤
            return False
        now = self._clock.monotonic()
        self._prune(now)
        key = (chat_id, user_id)
        normalized = _normalize(text)
        previous = self._seen.get(key)
        if previous is not None and previous[0] == normalized and now - previous[1] <= self._window:
            return True
        self._seen[key] = (normalized, now)
        return False

    def _prune(self, now: float) -> None:
        """进程内状态不落库：超过上限先清过期项，仍超就丢掉最旧的，避免字典无限增长。"""
        if len(self._seen) <= MAX_TRACKED_SENDERS:
            return
        for key in [key for key, (_, at) in self._seen.items() if now - at > self._window]:
            self._seen.pop(key, None)
        while len(self._seen) > MAX_TRACKED_SENDERS:
            self._seen.pop(min(self._seen, key=lambda key: self._seen[key][1]), None)


def _normalize(text: str) -> str:
    """去空白差异与大小写：' 哈哈 ' 与 '哈哈' 视为同一条。"""
    return " ".join(text.split()).casefold()


__all__ = [
    "LIMIT_COOLDOWN",
    "LIMIT_OK",
    "MAX_TRACKED_SENDERS",
    "LimitDecision",
    "ProactiveLimiter",
    "RepeatGuard",
]
