"""只读概览服务：面板首屏要的计数、配额与日志尾巴（docs/architecture.md §10）。

两条纪律：
- 心跳只有一个来源——机器人进程写出的 `storage/health.json`（docs/deployment.md §7）。
  心跳缺失就如实说"没有心跳"，面板不自己编一份"看起来正常"的状态；
- 日志尾巴经 `app.config.redact` 再脱敏一次才出站：日志本身已过脱敏过滤器，
  这里做的是纵深防御，而不是唯一防线。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiosqlite

from app.config import Settings, redact, today_in_timezone
from app.ops import health
from app.storage.repo import messages, usage

logger = logging.getLogger(__name__)

#: 日志尾巴最多读这么多字节：面板不需要整份日志，避免把磁盘 IO 放大成一次大读。
LOG_TAIL_BYTES = 256 * 1024

#: 日志尾巴默认行数上限（面板可传更小的值）。
DEFAULT_LOG_LINES = 200
MAX_LOG_LINES = 1000


@dataclass(frozen=True, slots=True)
class Overview:
    """首屏快照：心跳（可能为 None）+ 库内计数 + 当日用量与配额。"""

    instance: str | None
    health_ok: bool | None
    heartbeat_at: float | None
    heartbeat_age_s: float | None
    started_at: float | None
    uptime_s: float | None
    last_update_at: float | None
    outbound_pending: int | None
    db_ok: bool
    chats: int
    messages: int
    day: str
    calls: int
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    tool_calls: int
    quota_daily_tokens: int
    quota_monthly_tokens: int


async def build(
    connection: aiosqlite.Connection,
    settings: Settings,
    *,
    health_path: Path,
    now: datetime | None = None,
) -> Overview:
    """组装首屏快照；任何一项失败都降级为 0/None，不让面板整页报错。"""
    snapshot = health.read_snapshot(health_path)
    day = today_in_timezone(settings, now)

    db_ok = True
    chats = 0
    message_count = 0
    try:
        db_ok = True
        totals = await messages.totals(connection)
        chats = totals["chats"]
        message_count = totals["messages"]
    except Exception:
        db_ok = False
        logger.warning("面板概览：数据库读取失败", exc_info=True)

    calls = input_tokens = cached_tokens = output_tokens = tool_calls = 0
    try:
        day_totals = await usage.summary_for_day(connection, day)
        calls = int(day_totals["calls"])
        input_tokens = int(day_totals["input_tokens"])
        cached_tokens = int(day_totals["cached_tokens"])
        output_tokens = int(day_totals["output_tokens"])
        tool_calls = int(day_totals["tool_calls"])
    except Exception:
        logger.warning("面板概览：用量读取失败", exc_info=True)

    checked_at = float(snapshot.get("checked_at") or 0) if snapshot else 0.0
    return Overview(
        instance=_text(snapshot.get("instance")) if snapshot else None,
        health_ok=bool(snapshot.get("ok")) if snapshot else None,
        heartbeat_at=checked_at or None,
        heartbeat_age_s=_age(snapshot, now=now),
        started_at=_float_or_none(snapshot.get("started_at")) if snapshot else None,
        uptime_s=_float_or_none(snapshot.get("uptime_s")) if snapshot else None,
        last_update_at=_float_or_none(snapshot.get("last_update_at")) if snapshot else None,
        outbound_pending=_int_or_none(snapshot.get("outbound_pending")) if snapshot else None,
        db_ok=db_ok,
        chats=chats,
        messages=message_count,
        day=day,
        calls=calls,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        output_tokens=output_tokens,
        tool_calls=tool_calls,
        quota_daily_tokens=settings.quota_daily_tokens,
        quota_monthly_tokens=settings.quota_monthly_tokens,
    )


def tail_log(settings: Settings, *, lines: int = DEFAULT_LOG_LINES) -> list[str]:
    """读取机器人日志的尾部若干行并再次脱敏；文件不存在返回空表（不是错误）。"""
    count = max(1, min(int(lines), MAX_LOG_LINES))
    path = settings.log_dir / settings.log_file
    try:
        raw = _read_tail(path, LOG_TAIL_BYTES)
    except OSError:
        logger.warning("面板读取日志失败 path=%s", path, exc_info=True)
        return []
    if not raw:
        return []
    text = redact(raw, settings.secrets)
    return text.splitlines()[-count:]


def _read_tail(path: Path, budget: int) -> str:
    """只读文件尾部 `budget` 字节；按 UTF-8 解码，坏字节一律替换，不让日志把面板打挂。"""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - budget))
        return handle.read().decode("utf-8", errors="replace")


def _age(snapshot: dict[str, object], *, now: datetime | None) -> float | None:
    """心跳距今多少秒：面板用它判断"机器人还在不在"。"""
    if not snapshot:
        return None
    checked_at = _float_or_none(snapshot.get("checked_at"))
    if checked_at is None:
        return None
    moment = now.timestamp() if now is not None else datetime.now().timestamp()
    return max(0.0, moment - checked_at)


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    number = _float_or_none(value)
    return None if number is None else int(number)
