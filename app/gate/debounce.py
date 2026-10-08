"""Debounce：连发合并成一次模型调用。

当前生产默认 `DEBOUNCE_SECONDS=0`、`DEBOUNCE_MAX_MESSAGES=1`（用户要求「关掉合并」）：
每条消息各自成一个批次、各自一次模型调用，回复目标就是那条消息本身。
`max_messages` 仍是通用旋钮：>1 时同一批内合并（省钱杠杆，测试与历史配置仍可用）。
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
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
    # 整批都是弱触发（未点名）才是 True；并入任何强触发消息后变 False
    proactive: bool = False


class Clock(Protocol):
    def monotonic(self) -> float: ...


class MonotonicClock:
    def monotonic(self) -> float:
        return time.monotonic()


class Debouncer:
    """纯逻辑；时间源注入，可离线测试且不真的等待。"""

    def __init__(self, *, quiet_seconds: float, max_messages: int, clock: Clock | None = None) -> None:
        self._quiet = max(0.0, quiet_seconds)
        self._max = max(1, max_messages)
        self._clock = clock or MonotonicClock()
        self._pending: dict[int, Batch] = {}
        # 已满、但还没被 due() 取走的批次：`max_messages=1`（关掉合并）时每条消息都走这里
        self._ready: deque[Batch] = deque()

    def add(self, chat_id: int, item: IncomingMessage, *, proactive: bool = False) -> Batch:
        now = self._clock.monotonic()
        batch = self._pending.get(chat_id)
        if batch is not None and batch.full:
            # 上一批已经满了：先结算成独立批次，别把新消息并进去（关掉合并的关键）
            self._ready.append(batch)
            batch = None
        if batch is None:
            batch = Batch(chat_id=chat_id, last_at=now, proactive=proactive)
            self._pending[chat_id] = batch
        else:
            batch.proactive = batch.proactive and proactive
        batch.items.append(item)
        batch.last_at = now
        if len(batch.items) >= self._max:
            batch.full = True
        return batch

    def due(self) -> list[Batch]:
        """取出静默期已到（或已满）的批次；先给已结算的，保持到达顺序。"""
        now = self._clock.monotonic()
        ready: list[Batch] = [self._ready.popleft() for _ in range(len(self._ready))]
        for chat_id, batch in list(self._pending.items()):
            if batch.full or now - batch.last_at >= self._quiet:
                ready.append(self._pending.pop(chat_id))
        return ready

    def next_deadline(self) -> float | None:
        """最早一批到期所需等待秒数；无待处理返回 None。"""
        if self._ready:
            return 0.0
        if not self._pending:
            return None
        now = self._clock.monotonic()
        waits = [max(0.0, self._quiet - (now - batch.last_at)) for batch in self._pending.values() if not batch.full]
        if any(batch.full for batch in self._pending.values()):
            return 0.0
        return min(waits) if waits else None

    def flush(self, chat_id: int) -> Batch | None:
        batch = self._pending.pop(chat_id, None)
        if batch is not None:
            return batch
        for index, candidate in enumerate(self._ready):
            if candidate.chat_id == chat_id:
                del self._ready[index]
                return candidate
        return None

    def flush_all(self) -> list[Batch]:
        batches = [*self._ready, *self._pending.values()]
        self._ready.clear()
        self._pending.clear()
        return batches

    @property
    def pending_chats(self) -> int:
        return len(self._pending) + len(self._ready)


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
