"""上下文构建：固定段在前，动态段在后（docs/token.md 链 2）。"""

from __future__ import annotations

import aiosqlite

from app.config import Settings
from app.gate.debounce import Batch
from app.llm.prompts import build_messages, build_system_prompt
from app.storage.repo import chat_settings, messages
from app.storage.repo_models import StoredMessage


class ContextBuilder:
    def __init__(self, connection: aiosqlite.Connection, settings: Settings) -> None:
        self._connection = connection
        self._settings = settings

    async def build(self, batch: Batch) -> list[dict[str, str]]:
        """窗口按 chat_id 过滤，绝不跨群；本轮用户消息永不丢。

        本轮边界：只取"处理开始时已入库"的消息（docs/architecture.md §5），
        模型调用期间新到的消息不会回填进本轮，留给下一轮。
        """
        group = await chat_settings.get(self._connection, batch.chat_id)
        system_prompt = build_system_prompt(
            persona=self._settings.persona,
            mode=str(group.get("mode", "normal")),
        )
        until_id = await messages.max_id(self._connection, chat_id=batch.chat_id)
        history = await messages.recent(
            self._connection,
            chat_id=batch.chat_id,
            limit=self._settings.history_default,
            until_id=until_id,
        )
        latest = batch.items[-1] if batch.items else None
        if latest is not None and not any(item.message_id == latest.message_id for item in history):
            history = [*history, _as_stored(latest)]
        return build_messages(system_prompt, history)


def _as_stored(item) -> StoredMessage:
    """兜底：窗口太小或写入尚不可见时，仍需带上本轮消息。"""
    return StoredMessage(
        id=0,
        chat_id=item.chat_id,
        message_id=item.message_id,
        thread_id=item.thread_id,
        user_id=item.user_id,
        role="user",
        text=item.text,
        reply_to_message_id=None,
        noise=False,
        created_at=0,
    )
