"""摘要：滚动增量 + 固定模板 + 异步调度（F3.3、docs/memory.md §4）。

滚动式：上次摘要 + 新增消息 → 新摘要；写入失败不推进游标，重启后按数据库游标继续。
"""

from __future__ import annotations

import asyncio
import logging
import time

import aiosqlite

from app.config import Settings, today_in_timezone
from app.llm.client import LLMError
from app.session.retrieval import term_tokens
from app.storage.repo import messages as messages_repo
from app.storage.repo import summaries as summaries_repo
from app.storage.repo import usage as usage_repo
from app.storage.repo_models import PendingSummary, StoredMessage

logger = logging.getLogger(__name__)

SUMMARY_KEEP = 50
MAX_INPUT_MESSAGES = 200

SUMMARY_FIELDS = (
    "当前话题",
    "正在做的事",
    "已完成",
    "待完成",
    "偏好/约束",
    "关键实体（人名、项目名、文件）",
)

SUMMARY_SYSTEM_PROMPT = (
    "你在维护群聊的滚动摘要：只按给定字段填空，不要罗列消息、不要评论、不要编造；"
    "输出不超过 300 字；字段名保留；没有内容的字段写「无」。"
)


def build_summary_prompt(previous: str | None, rows: list[StoredMessage]) -> list[dict[str, str]]:
    """模板固定：system=字段与约束，user=上次摘要 + 新增消息。"""
    lines = ["请输出以下字段：", *[f"- {field}：" for field in SUMMARY_FIELDS]]
    if previous:
        lines.extend(["", "上次摘要：", previous.strip()])
    lines.append("")
    lines.append("新增消息（时间升序）：")
    for row in rows:
        who = "Bot" if row.role == "assistant" else f"用户{row.user_id}"
        lines.append(f"- {who}: {row.text.strip()}")
    return [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines)},
    ]


def compress_prompt(previous: str | None, rows: list[StoredMessage], draft: str) -> list[dict[str, str]]:
    prompt = build_summary_prompt(previous, rows)
    prompt.append({"role": "user", "content": f"上一次输出过长（{len(draft)} 字）。请压缩到 300 字以内，只保留字段与要点："})
    prompt.append({"role": "assistant", "content": draft})
    prompt.append({"role": "user", "content": "请重新输出压缩后的摘要。"})
    return prompt


def clean_summary(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


class SummaryService:
    """按群串行、可重试、幂等的摘要写入（不阻塞回复）。"""

    def __init__(self, connection: aiosqlite.Connection, client, settings: Settings, *, clock=None) -> None:
        self._connection = connection
        self._client = client
        self._settings = settings
        # 时钟必须与 messages.created_at / pending.last_at 同域（Unix 秒），否则静默触发恒不成立。
        self._clock = clock or time.time
        self._locks: dict[int, asyncio.Lock] = {}

    async def cursor(self, chat_id: int) -> int:
        return await summaries_repo.cursor(self._connection, chat_id=chat_id)

    async def pending(self, chat_id: int) -> PendingSummary:
        start = await self.cursor(chat_id)
        return await messages_repo.pending_since(self._connection, chat_id=chat_id, after_id=start)

    def should_summarize(self, pending: PendingSummary) -> bool:
        """任一触发：条数够 / 字符够且有一定量 / 静默够久且有新消息。"""
        if pending.messages <= 0:
            return False
        if pending.messages >= self._settings.summary_min_messages:
            return True
        if pending.chars >= self._settings.history_budget_chars and pending.messages >= 10:
            return True
        if pending.last_at and (self._clock() - pending.last_at) >= self._settings.summary_quiet_seconds:
            return True
        return False

    async def summarize(self, chat_id: int) -> bool:
        """写入成功返回 True；任何失败都不写库、不推进游标（幂等重试）。"""
        lock = self._locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            start = await self.cursor(chat_id)
            rows = await messages_repo.since(self._connection, chat_id=chat_id, after_id=start, limit=MAX_INPUT_MESSAGES)
            if not rows:
                return False

            previous_row = await summaries_repo.latest(self._connection, chat_id=chat_id)
            previous = None if previous_row is None else previous_row.text
            reply = await self._call(build_summary_prompt(previous, rows))
            if reply is None:
                return False
            text = clean_summary(reply.text)
            if len(text) > self._settings.summary_max_chars:
                retry = await self._call(compress_prompt(previous, rows, text))
                if retry is None:
                    return False
                text = clean_summary(retry.text)
                reply = retry
                if len(text) > self._settings.summary_max_chars:
                    logger.warning("摘要超过上限，放弃本次 chat_id=%s chars=%s", chat_id, len(text))
                    return False
            if not text:
                return False

            if await self.cursor(chat_id) != start:  # 幂等：区间已被别的任务覆盖
                logger.info("摘要区间已被覆盖，跳过 chat_id=%s", chat_id)
                return False

            await summaries_repo.insert(
                self._connection,
                chat_id=chat_id,
                text=text,
                tokens=term_tokens(text),
                msg_from=rows[0].id,
                msg_to=rows[-1].id,
            )
            await summaries_repo.prune(self._connection, chat_id=chat_id, keep=SUMMARY_KEEP)
            await self._record_usage(chat_id, reply)
            logger.info("摘要已更新 chat_id=%s messages=%s chars=%s", chat_id, len(rows), len(text))
            return True

    async def _call(self, prompt: list[dict[str, str]]):
        try:
            return await self._client.complete(
                prompt,
                model=self._settings.llm_model,
                max_tokens=self._settings.summary_max_output_tokens,
            )
        except LLMError:
            logger.warning("摘要调用失败", exc_info=True)
            return None

    async def _record_usage(self, chat_id: int, reply) -> None:
        try:
            await usage_repo.record(
                self._connection,
                chat_id=chat_id,
                user_id=0,  # 摘要不由某个用户触发
                day=today_in_timezone(self._settings),
                model=reply.model,
                input_tokens=reply.input_tokens,
                cached_tokens=reply.cached_tokens,
                output_tokens=reply.output_tokens,
                purpose="summary",
            )
        except Exception:
            logger.exception("摘要记账失败 chat_id=%s", chat_id)


class SummaryScheduler:
    """后台循环：异步、按群串行、可优雅停止；不阻塞正常回复。"""

    def __init__(
        self,
        service: SummaryService,
        connection: aiosqlite.Connection,
        *,
        poll_seconds: float,
        stop: asyncio.Event,
    ) -> None:
        self._service = service
        self._connection = connection
        self._poll_seconds = max(1.0, poll_seconds)
        self._stop = stop

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception("摘要调度本轮失败")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._poll_seconds)
            except asyncio.TimeoutError:
                continue

    async def tick(self) -> int:
        written = 0
        for chat_id, pending in await summaries_repo.pending_by_chat(self._connection):
            if not self._service.should_summarize(pending):
                continue
            if await self._service.summarize(chat_id):
                written += 1
        return written
