"""上下文构建：固定段在前，动态段在后（docs/token.md 链 2）。"""

from __future__ import annotations

import aiosqlite

from app import modes
from app.config import Settings
from app.gate.debounce import Batch
from app.llm.prompts import build_messages, build_system_prompt
from app.session import retrieval
from app.storage.repo import chat_settings, messages, summaries
from app.storage.repo_models import StoredMessage

MEMORY_HEADING = "## 记忆"
COMPLEX_TEXT_CHARS = 400


class ContextBuilder:
    """唯一上下文组装点：固定段 → 记忆块 → 历史窗口 → 本轮 → 情绪（docs/token.md 链 2）。"""

    def __init__(self, connection: aiosqlite.Connection, settings: Settings) -> None:
        self._connection = connection
        self._settings = settings
        self._trimmed: dict[int, int] = {}

    async def build(
        self,
        batch: Batch,
        *,
        group: dict[str, object] | None = None,
        allowed_tools: tuple[str, ...] = (),
        mood: str | None = None,
    ) -> list[dict[str, str]]:
        """窗口按 chat_id 过滤，绝不跨群；本轮用户消息永不丢。

        本轮边界：只取"处理开始时已入库"的消息（docs/architecture.md §5），
        模型调用期间新到的消息不会回填进本轮，留给下一轮。

        group 由调用方传入可避免重复查询；allowed_tools 决定 System3 里可选的工具；
        mood 非空时作为动态段末条注入（docs/persona.md §2、docs/token.md 链 2）。
        mode 同时决定窗口大小（docs/token.md §5）。
        """
        current = group if group is not None else await chat_settings.get(self._connection, batch.chat_id)
        mode = modes.normalize(current.get("mode"))
        system_prompt = build_system_prompt(
            persona=self._settings.persona,
            mode=mode,
            allowed_tools=allowed_tools,
        )
        until_id = await messages.max_id(self._connection, chat_id=batch.chat_id)
        history = await messages.recent(
            self._connection,
            chat_id=batch.chat_id,
            limit=self.window_size(batch, mode=mode),
            until_id=until_id,
        )
        latest = batch.items[-1] if batch.items else None
        if latest is not None and not any(item.message_id == latest.message_id for item in history):
            history = [*history, _as_stored(latest)]

        # 先按"本轮 + 情绪"的占用裁剪历史；记忆块随后再占用剩余预算
        reserved = sum(len(item.text) for item in batch.items) + len(mood or "")
        keep = frozenset(item.message_id for item in batch.items)
        history, dropped = self._trim(history, reserved=reserved, keep=keep)

        memory = await self._memory_lines(batch, dropped=dropped)
        if memory:
            memory_text = MEMORY_HEADING + "\n" + "\n".join(memory)
            reserved += len(memory_text)
            history, extra = self._trim(history, reserved=reserved, keep=keep)
            dropped += extra
        if dropped:
            self._trimmed[batch.chat_id] = dropped

        payload = build_messages(system_prompt, history, mood=mood)
        if memory:
            payload.insert(1, {"role": "system", "content": MEMORY_HEADING + "\n" + "\n".join(memory)})
        return payload

    def window_size(self, batch: Batch, mode: str = modes.NORMAL) -> int:
        """economy 固定 10、smart/unrestricted 固定 50（docs/token.md §5）；normal 按意图分档。

        normal 的纯规则分档：复杂 50 / 闲聊 10 / 默认 20（docs/memory.md §2）。
        """
        fixed = modes.profile_for(mode).window
        if fixed is not None:
            return fixed
        texts = [item.text for item in batch.items]
        joined = "\n".join(texts)
        if (
            any("```" in text for text in texts)
            or any(len(text) >= COMPLEX_TEXT_CHARS for text in texts)
            or "http://" in joined
            or "https://" in joined
            or retrieval.retrieval_wanted(texts)
        ):
            return self._settings.history_complex
        if texts and all(len(text) < 10 for text in texts) and not any("?" in text or "？" in text for text in texts):
            return self._settings.history_chitchat
        return self._settings.history_default

    def consume_trimmed(self, chat_id: int) -> int:
        """最近一次组装被预算裁掉的历史条数（观测/测试用，不参与决策）。"""
        return self._trimmed.pop(chat_id, 0)

    def _trim(
        self,
        history: list[StoredMessage],
        *,
        reserved: int,
        keep: frozenset[int] = frozenset(),
    ) -> tuple[list[StoredMessage], int]:
        """超预算从最旧历史开始丢；本轮消息永不丢（即使本轮自身已超预算）。"""
        budget = self._settings.history_budget_chars
        dropped = 0
        total = reserved + sum(len(row.text) for row in history)
        while history and total > budget:
            if history[0].message_id in keep:
                # 本轮消息是最新的：到它就是只剩本轮，不能再裁
                break
            total -= len(history[0].text)
            history.pop(0)
            dropped += 1
        return history, dropped

    async def _memory_lines(self, batch: Batch, *, dropped: int) -> list[str]:
        """记忆块：最近 1 条摘要 + 按需检索片段（查不到就不注入）。"""
        lines: list[str] = []
        latest = await summaries.latest(self._connection, chat_id=batch.chat_id)
        if latest is not None:
            lines.append("最近摘要：" + " ".join(latest.text.split()))

        start = await summaries.cursor(self._connection, chat_id=batch.chat_id)
        pending = await messages.pending_since(self._connection, chat_id=batch.chat_id, after_id=start)
        snippets = await retrieval.search_memory(
            self._connection,
            chat_id=batch.chat_id,
            text=" ".join(item.text for item in batch.items),
            trimmed=dropped,
            has_unsummarized=pending.messages > 0,
        )
        if snippets:
            lines.append("相关记录：")
            lines.extend(f"- {line}" for line in snippets)
        return lines


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
