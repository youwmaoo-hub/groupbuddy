"""当前情绪：最近一次贴纸的 valence/arousal，进程内存、TTL 10 分钟（docs/persona.md §2）。"""

from __future__ import annotations

import time
from dataclasses import dataclass

MOOD_TTL_SECONDS = 600.0


@dataclass(frozen=True, slots=True)
class Mood:
    valence: float
    arousal: float
    updated_at: float


def mood_label(valence: float, arousal: float) -> str:
    """把 valence/arousal 映射成一句人话；只影响语气，不影响权限与事实判断。"""
    if valence >= 0.2:
        return "心情不错，有点兴奋" if arousal >= 0.5 else "心情不错"
    if valence <= -0.2:
        return "有点烦躁" if arousal >= 0.5 else "情绪有点低"
    return "情绪平稳"


class MoodTracker:
    """按 chat_id 记录；过期、未记录或重启后都不注入（不落库）。"""

    def __init__(self, *, ttl_seconds: float = MOOD_TTL_SECONDS, clock=None) -> None:
        self._ttl = max(0.0, ttl_seconds)
        self._clock = clock or time.monotonic
        self._moods: dict[int, Mood] = {}

    def record(self, chat_id: int, valence: float, arousal: float) -> None:
        self._moods[chat_id] = Mood(float(valence), float(arousal), self._clock())

    def values(self, chat_id: int) -> tuple[float, float] | None:
        mood = self._fresh(chat_id)
        return None if mood is None else (mood.valence, mood.arousal)

    def describe(self, chat_id: int) -> str | None:
        mood = self._fresh(chat_id)
        return None if mood is None else mood_label(mood.valence, mood.arousal)

    def _fresh(self, chat_id: int) -> Mood | None:
        mood = self._moods.get(chat_id)
        if mood is None:
            return None
        if self._clock() - mood.updated_at > self._ttl:
            self._moods.pop(chat_id, None)
            return None
        return mood
