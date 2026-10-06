"""每个 chat_id 串行、不同群可并行的 actor 队列；运行期间的新消息合并为下一轮一批。"""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from app.gate.debounce import Batch

logger = logging.getLogger(__name__)

MAX_BATCH_MESSAGES = 5


class ChatQueue:
    """同一 chat_id 同时只有一个回复任务；运行期间到达的消息合并进唯一待处理批次。"""

    def __init__(self, handler, *, max_batch_messages: int = MAX_BATCH_MESSAGES) -> None:
        self._handler = handler
        self._max_batch_messages = max(1, max_batch_messages)
        self._pending: dict[int, deque[Batch]] = {}
        self._events: dict[int, asyncio.Event] = {}
        self._workers: dict[int, asyncio.Task[None]] = {}
        self._running = True
        self._inflight = 0  # 已出队但仍在处理的批次数（drain 必须等它归零）

    async def submit(self, batch: Batch) -> None:
        """运行期间到达的消息不新开一轮：合并进该群唯一的待处理批次，只保留最新 N 条。"""
        pending = self._pending.setdefault(batch.chat_id, deque())
        if pending:
            previous = pending[-1]
            previous.items.extend(batch.items)
            previous.last_at = batch.last_at
            if len(previous.items) > self._max_batch_messages:
                dropped = len(previous.items) - self._max_batch_messages
                del previous.items[:dropped]
                logger.debug("批次超出上限，丢弃最早 %s 条（仍留在窗口里作历史）chat_id=%s", dropped, batch.chat_id)
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
