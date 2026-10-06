"""Debounce：1–2 秒内的连发合并成一次模型调用（省钱的主要杠杆）。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Protocol

from app.telegram.parse import IncomingMessage


@dataclass(slots=True)
class Batch:
    """合并后的一批消息；items 至少一条，按到达顺序排列。"""

    chat_id: int
    items: list[IncomingMessage] = field(default_factory=list)
    last_at: float = 0.0
    full: bool = False


class Clock(Protocol):
    def monotonic(self) -> float: ...


class MonotonicClock:
    def monotonic(self) -> float:
        return time.monotonic()


class Debouncer:
    """纯逻辑；时间源注入，可离线测试且不真的等待。"""

    def __init__(self, *, quiet_seconds: float, max_messages: int, clock: Clock | None = None) -> None:
        self._quiet = quiet_seconds
        self._max = max(1, max_messages)
        self._clock = clock or MonotonicClock()
        self._pending: dict[int, Batch] = {}

    def add(self, chat_id: int, item: IncomingMessage) -> None:
        now = self._clock.monotonic()
        batch = self._pending.get(chat_id)
        if batch is None:
            batch = Batch(chat_id=chat_id, last_at=now)
            self._pending[chat_id] = batch
        batch.items.append(item)
        batch.last_at = now
        if len(batch.items) >= self._max:
            batch.full = True

    def due(self) -> list[Batch]:
        """取出静默期已到（或已满）的批次。"""
        now = self._clock.monotonic()
        ready: list[Batch] = []
        for chat_id, batch in list(self._pending.items()):
            if batch.full or now - batch.last_at >= self._quiet:
                ready.append(self._pending.pop(chat_id))
        return ready

    def next_deadline(self) -> float | None:
        """最早一批到期所需等待秒数；无待处理返回 None。"""
        if not self._pending:
            return None
        now = self._clock.monotonic()
        waits = [max(0.0, self._quiet - (now - batch.last_at)) for batch in self._pending.values() if not batch.full]
        if any(batch.full for batch in self._pending.values()):
            return 0.0
        return min(waits) if waits else None

    def flush(self, chat_id: int) -> Batch | None:
        return self._pending.pop(chat_id, None)

    def flush_all(self) -> list[Batch]:
        batches = list(self._pending.values())
        self._pending.clear()
        return batches

    @property
    def pending_chats(self) -> int:
        return len(self._pending)


async def run_debounce_loop(
    debouncer: Debouncer,
    submit,
    *,
    stop: asyncio.Event,
    poll_seconds: float = 0.1,
) -> None:
    """后台循环：把到期批次交给队列；不阻塞接收路径。"""
    while not stop.is_set():
        for batch in debouncer.due():
            await submit(batch)
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            continue
