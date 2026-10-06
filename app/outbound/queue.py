"""所有 Telegram 出站消息的唯一出口（AGENTS.md 硬规则 12）。

含长消息分段：按 段落→代码块→句子→字符 逐级切分，不切断代码块（docs/security.md §10）。
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

from app.outbound.ratelimit import RateLimiter

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096
MAX_PENDING_MESSAGES = 16


class Sender(Protocol):
    """真实实现见 app/telegram/sender.py；测试用假实现。"""

    async def send_message(self, *, chat_id: int, text: str, reply_to_message_id: int | None = None) -> int: ...

    async def send_sticker(self, *, chat_id: int, file_id: str) -> int: ...


class RateLimited(Exception):
    """发送被限速，带 Telegram 给的 retry_after 秒数。"""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry_after={retry_after}")
        self.retry_after = retry_after


class SendFailed(Exception):
    """不可重试的发送失败（封禁、参数错误等）。"""


@dataclass(slots=True)
class OutboundMessage:
    chat_id: int
    chat_type: str
    text: str
    reply_to_message_id: int | None = None
    attempts: int = 0
    chunks: list[str] = field(default_factory=list)


_SENTENCE_END = re.compile(r"(?<=[。！？!?；;\n])")


def split_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """切成不超过 limit 的片段；每段都是完整可读文本。"""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buffer = ""
    for segment in _segments(text):
        if len(segment) > limit:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_split_oversized(segment, limit))
            continue
        candidate = f"{buffer}\n\n{segment}" if buffer else segment
        if len(candidate) <= limit:
            buffer = candidate
        else:
            chunks.append(buffer)
            buffer = segment
    if buffer:
        chunks.append(buffer)
    return [chunk for chunk in chunks if chunk]


def _segments(text: str) -> list[str]:
    """原子段：整块围栏代码块，或一个段落。"""
    segments: list[str] = []
    buffer: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        stripped = line.strip()
        if fence is None:
            if stripped.startswith("```"):
                if buffer:
                    segments.append("\n".join(buffer))
                    buffer = []
                if stripped == "```":
                    segments.append(line)
                    continue
                fence = stripped
                buffer = [line]
                continue
            if not stripped:
                if buffer:
                    segments.append("\n".join(buffer))
                    buffer = []
                continue
            buffer.append(line)
            continue
        buffer.append(line)
        if stripped == "```":
            segments.append("\n".join(buffer))
            buffer = []
            fence = None
    if buffer:
        segments.append("\n".join(buffer))
    return segments


def _split_oversized(segment: str, limit: int) -> list[str]:
    """超长段：代码块按行重组围栏，普通文本按句子再按字符切。"""
    lines = segment.split("\n")
    first = lines[0].strip() if lines else ""
    if first.startswith("```"):
        header = first if first != "```" else "```"
        body = lines[1:]
        if body and body[-1].strip() == "```":
            body = body[:-1]
        return _pack(body, limit, prefix=f"{header}\n", suffix="\n```")
    return _pack([part for part in _SENTENCE_END.split(segment) if part], limit)


def _pack(units: list[str], limit: int, prefix: str = "", suffix: str = "") -> list[str]:
    budget = max(1, limit - len(prefix) - len(suffix))
    pieces: list[str] = []
    buffer: list[str] = []
    size = 0
    for unit in units:
        if len(unit) > budget:
            for start in range(0, len(unit), budget):
                piece = unit[start : start + budget]
                if buffer:
                    pieces.append(prefix + "\n".join(buffer) + suffix)
                    buffer = []
                    size = 0
                pieces.append(prefix + piece + suffix)
            continue
        addition = len(unit) + 1
        if size + addition > budget and buffer:
            pieces.append(prefix + "\n".join(buffer) + suffix)
            buffer = []
            size = 0
        buffer.append(unit)
        size += addition
    if buffer:
        pieces.append(prefix + "\n".join(buffer) + suffix)
    return pieces


class OutboundQueue:
    """每群串行发送、限速、429 退避重试；业务代码只调用 enqueue。"""

    def __init__(
        self,
        sender: Sender,
        limiter: RateLimiter,
        *,
        chunk_limit: int = TELEGRAM_MESSAGE_LIMIT,
        max_attempts: int = 3,
        max_pending: int = MAX_PENDING_MESSAGES,
        sleep=asyncio.sleep,
    ) -> None:
        self._sender = sender
        self._limiter = limiter
        self._chunk_limit = chunk_limit
        self._max_attempts = max(1, max_attempts)
        self._max_pending = max(1, max_pending)
        self._sleep = sleep
        self._pending: dict[int, deque[OutboundMessage]] = {}
        self._events: dict[int, asyncio.Event] = {}
        self._workers: dict[int, asyncio.Task[None]] = {}
        self._running = True
        self._inflight = 0  # 已出队但仍在发送的消息数（drain 必须等它归零）
        self._locks: dict[int, asyncio.Lock] = {}  # 同群串行：文本与贴纸不交错

    async def enqueue(
        self,
        *,
        chat_id: int,
        chat_type: str,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> None:
        message = OutboundMessage(
            chat_id=chat_id,
            chat_type=chat_type,
            text=text,
            reply_to_message_id=reply_to_message_id,
            chunks=split_message(text, self._chunk_limit),
        )
        queue = self._pending.setdefault(chat_id, deque())
        if len(queue) >= self._max_pending:
            logger.warning("出站队列已满，丢弃旧消息 chat_id=%s", chat_id)
            queue.popleft()
        queue.append(message)
        self._event(chat_id).set()
        self._ensure_worker(chat_id)

    async def drain(self, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while any(self._pending.values()) or self._inflight:
            if time.monotonic() >= deadline:
                logger.warning("出站排空超时")
                return
            await self._sleep(0.05)

    async def stop(self) -> None:
        self._running = False
        for event in self._events.values():
            event.set()
        if self._workers:
            await asyncio.gather(*self._workers.values(), return_exceptions=True)
        self._workers.clear()

    def _event(self, chat_id: int) -> asyncio.Event:
        return self._events.setdefault(chat_id, asyncio.Event())

    def _lock(self, chat_id: int) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())

    def _ensure_worker(self, chat_id: int) -> None:
        task = self._workers.get(chat_id)
        if task is None or task.done():
            self._workers[chat_id] = asyncio.create_task(self._run(chat_id), name=f"outbound-{chat_id}")

    async def _run(self, chat_id: int) -> None:
        event = self._event(chat_id)
        queue = self._pending.setdefault(chat_id, deque())
        while self._running:
            while queue:
                message = queue.popleft()
                self._inflight += 1
                try:
                    await self._deliver(message)
                finally:
                    self._inflight -= 1
            event.clear()
            await event.wait()

    async def _deliver(self, message: OutboundMessage) -> None:
        async with self._lock(message.chat_id):
            await self._deliver_locked(message)

    async def _deliver_locked(self, message: OutboundMessage) -> None:
        for chunk in message.chunks:
            while True:
                wait = self._limiter.delay(chat_id=message.chat_id, chat_type=message.chat_type)
                if wait > 0:
                    await self._sleep(wait)
                try:
                    await self._sender.send_message(
                        chat_id=message.chat_id,
                        text=chunk,
                        reply_to_message_id=message.reply_to_message_id,
                    )
                except RateLimited as error:
                    message.attempts += 1
                    backoff = self._limiter.apply_retry_after(
                        chat_id=message.chat_id, retry_after=error.retry_after
                    )
                    if message.attempts >= self._max_attempts:
                        logger.warning("限速重试超限，放弃该消息 chat_id=%s", message.chat_id)
                        return
                    await self._sleep(min(backoff + random.uniform(0, 0.5), 60.0))
                    continue
                except SendFailed:
                    logger.warning("发送失败，放弃剩余分段 chat_id=%s", message.chat_id)
                    return
                self._limiter.record(chat_id=message.chat_id, chat_type=message.chat_type)
                message.reply_to_message_id = None
                break

    async def send_sticker(self, *, chat_id: int, chat_type: str, file_id: str) -> bool:
        """贴纸专用发送：同群与文本串行、走贴纸限速与 429 退避；失败返回 False。

        file_id 只在这里与 Sender 之间传递，绝不进入日志与返回值之外的地方。
        """
        async with self._lock(chat_id):
            attempts = 0
            while True:
                wait = self._limiter.delay(chat_id=chat_id, chat_type=chat_type, kind="sticker")
                if wait > 0:
                    await self._sleep(wait)
                try:
                    await self._sender.send_sticker(chat_id=chat_id, file_id=file_id)
                except RateLimited as error:
                    attempts += 1
                    backoff = self._limiter.apply_retry_after(chat_id=chat_id, retry_after=error.retry_after)
                    if attempts >= self._max_attempts:
                        logger.warning("贴纸限速重试超限，放弃 chat_id=%s", chat_id)
                        return False
                    await self._sleep(min(backoff + random.uniform(0, 0.5), 60.0))
                    continue
                except SendFailed:
                    logger.warning("贴纸发送失败 chat_id=%s", chat_id)
                    return False
                self._limiter.record(chat_id=chat_id, chat_type=chat_type, kind="sticker")
                return True
