"""send_sticker：模型只给情绪值，程序匹配本群贴纸并发送（F4.5）。

file_id 只在本模块内部从数据层传到出站边界，绝不进入返回值、日志或错误消息。
"""

from __future__ import annotations

import math
import time
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.storage.repo import stickers as stickers_repo
from app.storage.repo_models import StickerRow
from app.tools.registry import ToolContext, ToolError, ToolSpec

MIN_SCORE = 0.6
TAG_BONUS = 0.1
TIE_EPSILON = 0.05
DEFAULT_COOLDOWN_SECONDS = 30.0
MAX_TAGS = 8
MAX_TAG_CHARS = 32


class StickerStoreLike(Protocol):
    async def candidates(self, chat_id: int) -> list[StickerRow]: ...

    async def mark_used(self, sticker_id: int, used_at: int) -> None: ...


class StickerOutboundLike(Protocol):
    async def send_sticker(self, *, chat_id: int, chat_type: str, file_id: str) -> bool: ...


class MoodSinkLike(Protocol):
    def record(self, chat_id: int, valence: float, arousal: float) -> None: ...


class SendStickerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valence: float = Field(ge=-1.0, le=1.0)
    arousal: float = Field(ge=-1.0, le=1.0)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            if len(text) > MAX_TAG_CHARS:
                raise ValueError("标签过长")
            cleaned.append(text)
        return cleaned


def sticker_score(row: StickerRow, valence: float, arousal: float, wanted: tuple[str, ...]) -> float | None:
    """余弦相似度为主分 + tags 轻量加分；情绪缺失或零向量返回 None。"""
    if row.valence is None or row.arousal is None:
        return None
    norm = math.hypot(row.valence, row.arousal) * math.hypot(valence, arousal)
    if norm <= 1e-9:
        return None
    cosine = (row.valence * valence + row.arousal * arousal) / norm
    have = set(stickers_repo.decode_tags(row.tags))
    overlap = 0.0
    if have and wanted:
        overlap = len(have & set(wanted)) / len(set(wanted))
    return cosine + TAG_BONUS * overlap


def match_sticker(
    rows: list[StickerRow],
    *,
    valence: float,
    arousal: float,
    tags: tuple[str, ...],
) -> StickerRow | None:
    """低于阈值不返回；分数接近时优先 last_used_at 更早的（避免连续重复）。"""
    scored: list[tuple[float, int, StickerRow]] = []
    for row in rows:
        score = sticker_score(row, valence, arousal, tags)
        if score is None or score < MIN_SCORE:
            continue
        used = row.last_used_at if row.last_used_at is not None else 0
        scored.append((score, used, row))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    best = scored[0][0]
    near = [item for item in scored if best - item[0] <= TIE_EPSILON]
    near.sort(key=lambda item: item[1])
    return near[0][2]


class SendStickerTool:
    spec = ToolSpec(
        name="send_sticker",
        level="L2",
        description="用一张贴纸表达情绪：valence/arousal 各 -1..1，可选 tags。",
        args_model=SendStickerArgs,
        timeout_seconds=3.0,
    )

    def __init__(self, store, outbound, mood, *, clock=None, wall_clock=None) -> None:
        self._store = store
        self._outbound = outbound
        self._mood = mood
        self._clock = clock or time.monotonic  # 冷却计时：进程相对秒，不受系统时间跳变影响
        self._wall_clock = wall_clock or time.time  # last_used_at：Unix 秒（docs/database.md §1）
        self._last_sent: dict[int, float] = {}

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        now = self._clock()
        cooldown = cooldown_seconds(context.group)
        last = self._last_sent.get(context.chat_id)
        if last is not None and now - last < cooldown:
            return {
                "sent": False,
                "state": "cooldown",
                "retry_after": int(math.ceil(cooldown - (now - last))),
            }

        rows = await self._store.candidates(context.chat_id)
        matched = match_sticker(
            rows,
            valence=args.valence,  # type: ignore[attr-defined]
            arousal=args.arousal,  # type: ignore[attr-defined]
            tags=tuple(args.tags),  # type: ignore[attr-defined]
        )
        if matched is None:
            raise ToolError("not_found", "没有合适的贴纸")

        sent = await self._outbound.send_sticker(
            chat_id=context.chat_id,
            chat_type=context.chat_type,
            file_id=matched.file_id,
        )
        if not sent:
            raise ToolError("internal_error", "贴纸发送失败")

        self._last_sent[context.chat_id] = now
        await self._store.mark_used(matched.id, int(self._wall_clock()))
        self._mood.record(context.chat_id, float(args.valence), float(args.arousal))  # type: ignore[attr-defined]
        return {"sent": True, "sticker_id": matched.id}


def cooldown_seconds(group: dict[str, object]) -> float:
    """冷却秒数取群设置 sticker_cooldown（缺失或非法时回落到默认 30 秒）。"""
    raw = group.get("sticker_cooldown", DEFAULT_COOLDOWN_SECONDS)
    try:
        return max(0.0, float(raw))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_COOLDOWN_SECONDS
