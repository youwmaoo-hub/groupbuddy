"""会话编排：去重 → 硬过滤 → 触发判定 → 存储 → debounce → 一次模型调用 → 出站。"""

from __future__ import annotations

import logging
import time

import aiosqlite

from app.config import Settings, today_in_timezone
from app.gate.debounce import Batch, Debouncer
from app.gate.dedupe import UpdateDeduplicator
from app.gate.filters import screen
from app.gate.trigger import TriggerDetector
from app.llm.loop import Outcome, Responder
from app.outbound.queue import OutboundQueue
from app.session.context import ContextBuilder
from app.storage.repo import messages, usage
from app.telegram.parse import IncomingMessage

logger = logging.getLogger(__name__)

ASSISTANT_ROLE = "assistant"
USER_ROLE = "user"


class SessionRunner:
    """唯一把各层接起来的地方；不含 aiogram 依赖。"""

    def __init__(
        self,
        *,
        settings: Settings,
        connection: aiosqlite.Connection,
        deduplicator: UpdateDeduplicator,
        detector: TriggerDetector,
        debouncer: Debouncer,
        context_builder: ContextBuilder,
        responder: Responder,
        outbound: OutboundQueue,
    ) -> None:
        self._settings = settings
        self._connection = connection
        self._dedup = deduplicator
        self._detector = detector
        self._debouncer = debouncer
        self._context = context_builder
        self._responder = responder
        self._outbound = outbound

    async def handle(self, incoming: IncomingMessage) -> None:
        """接收路径：必须立刻返回，绝不等待模型。"""
        if not await self._dedup.first_seen(incoming.update_id, incoming.chat_id):
            logger.debug("重复 update 丢弃 chat_id=%s update_id=%s", incoming.chat_id, incoming.update_id)
            return

        result = screen(incoming)
        if not result.allowed:
            logger.debug("过滤丢弃 chat_id=%s 原因=%s", incoming.chat_id, result.reason)
            return

        await messages.insert(
            self._connection,
            chat_id=incoming.chat_id,
            message_id=incoming.message_id,
            user_id=incoming.user_id,
            role=USER_ROLE,
            text=incoming.text,
            thread_id=incoming.thread_id,
            reply_to_message_id=None,
        )

        decision = self._detector.decide(incoming)
        if decision.should_respond:
            self._debouncer.add(incoming.chat_id, incoming)
        logger.debug("触发判定 chat_id=%s 结果=%s 原因=%s", incoming.chat_id, decision.verdict, decision.reason)

    async def handle_batch(self, batch: Batch) -> None:
        """Agent Loop：一次模型调用；工具循环属阶段 3。"""
        payload = await self._context.build(batch)
        outcome = await self._responder.reply(payload)
        await self._record_usage(batch, outcome)  # 只要调用了模型就记账，哪怕本轮不说话
        if outcome.text is None:
            logger.info("本轮不说话 chat_id=%s", batch.chat_id)
            return

        latest = batch.items[-1]
        await self._outbound.enqueue(
            chat_id=batch.chat_id,
            chat_type=latest.chat_type,
            text=outcome.text,
            reply_to_message_id=latest.message_id,
        )
        await self._store_assistant(batch, outcome.text)

    async def _store_assistant(self, batch: Batch, text: str) -> None:
        """Bot 自己的发言也要入库（否则下一轮看不到自己说过什么）。"""
        latest = batch.items[-1]
        for offset in range(3):
            synthetic_id = -(int(time.time() * 1000) + offset)
            inserted = await messages.insert(
                self._connection,
                chat_id=batch.chat_id,
                message_id=synthetic_id,
                user_id=latest.user_id,
                role=ASSISTANT_ROLE,
                text=text,
            )
            if inserted:
                return
        logger.warning("Bot 发言入库失败 chat_id=%s", batch.chat_id)

    async def _record_usage(self, batch: Batch, outcome: Outcome) -> None:
        """记账失败不得影响回复（docs/database.md §6）。"""
        reply = outcome.reply
        if reply is None:
            return
        try:
            await usage.record(
                self._connection,
                chat_id=batch.chat_id,
                user_id=batch.items[-1].user_id,
                day=today_in_timezone(self._settings),
                model=reply.model,
                input_tokens=reply.input_tokens,
                cached_tokens=reply.cached_tokens,
                output_tokens=reply.output_tokens,
            )
        except Exception:
            logger.exception("记账失败 chat_id=%s", batch.chat_id)
