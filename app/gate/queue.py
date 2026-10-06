"""每个 chat_id 串行、不同群可并行的 actor 队列。"""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from app.gate.debounce import Batch

logger = logging.getLogger(__name__)

MAX_PENDING_BATCHES = 8


class ChatQueue:
    """同一 chat_id 同时只有一个 Agent Loop；溢出时合并而不是丢弃。"""

    def __init__(self, handler, *, max_pending: int = MAX_PENDING_BATCHES) -> None:
        self._handler = handler
        self._max_pending = max(1, max_pending)
        self._pending: dict[int, deque[Batch]] = {}
        self._events: dict[int, asyncio.Event] = {}
        self._workers: dict[int, asyncio.Task[None]] = {}
        self._running = True
        self._inflight = 0  # 已出队但仍在处理的批次数（drain 必须等它归零）

    async def submit(self, batch: Batch) -> None:
        pending = self._pending.setdefault(batch.chat_id, deque())
        if len(pending) >= self._max_pending:
            previous = pending[-1]
            logger.warning("队列溢出，合并批次 chat_id=%s merged=%s", batch.chat_id, len(batch.items))
            previous.items.extend(batch.items)
            previous.last_at = batch.last_at
        else:
            pending.append(batch)
        self._event(batch.chat_id).set()
        self._ensure_worker(batch.chat_id)

    async def drain(self, timeout: float = 10.0) -> None:
        """等待已入队批次处理完（优雅关闭用）。"""
        deadline = asyncio.get_running_loop().time() + timeout
        while any(self._pending.values()) or self._inflight:
            if asyncio.get_running_loop().time() >= deadline:
                logger.warning("排空超时，仍有未处理批次")
                return
            await asyncio.sleep(0.05)

    async def stop(self) -> None:
        self._running = False
        for event in self._events.values():
            event.set()
        if self._workers:
            await asyncio.gather(*self._workers.values(), return_exceptions=True)
        self._workers.clear()

    def _event(self, chat_id: int) -> asyncio.Event:
        return self._events.setdefault(chat_id, asyncio.Event())

    def _ensure_worker(self, chat_id: int) -> None:
        task = self._workers.get(chat_id)
        if task is None or task.done():
            self._workers[chat_id] = asyncio.create_task(self._run(chat_id), name=f"chat-worker-{chat_id}")

    async def _run(self, chat_id: int) -> None:
        event = self._event(chat_id)
        pending = self._pending.setdefault(chat_id, deque())
        while self._running:
            while pending:
                batch = pending.popleft()
                self._inflight += 1
                try:
                    await self._handler(batch)
                except Exception:  # 单群失败不影响其他群
                    logger.exception("处理批次失败 chat_id=%s", chat_id)
                finally:
                    self._inflight -= 1
            event.clear()
            await event.wait()
