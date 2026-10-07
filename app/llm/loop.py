"""工具循环：一次或多次模型调用 + 工具执行，最后做输出规范化（docs/architecture.md §3）。"""

from __future__ import annotations

import json
import logging
import time
from typing import Protocol

from app.config import Settings
from app.llm.client import ChatMessage, DeepSeekClient, LLMError, LLMReply
from app.llm.prompts import NO_REPLY

logger = logging.getLogger(__name__)

BACKTICK = chr(96)
_WRAPPERS = ('"', "'", BACKTICK, BACKTICK * 3, " ", "\n", "。", ".")

#: `max_output_tokens` 未显式传入时用 `LLM_MAX_OUTPUT_TOKENS`；
#: 显式传 `None` = 不限输出（docs/token.md §5 的 unrestricted）。
_DEFAULT_LIMIT = object()


class Outcome:
    """一次回复的结果；text 为 None 表示本轮不说话。"""

    __slots__ = ("text", "reply", "tool_calls", "tool_ms")

    def __init__(
        self,
        text: str | None,
        reply: LLMReply | None = None,
        *,
        tool_calls: int = 0,
        tool_ms: int = 0,
    ) -> None:
        self.text = text
        self.reply = reply
        self.tool_calls = tool_calls
        self.tool_ms = tool_ms


class ToolExecutorLike(Protocol):
    """app/tools/executor.py 的实现；此处只用协议，避免 llm 层反向依赖工具层。"""

    def specs_for(self, context: object) -> list[dict[str, object]]: ...

    async def execute(self, context: object, name: str, arguments: str) -> dict[str, object]: ...


def normalize(text: str) -> str | None:
    """去掉包裹符号；NO_REPLY 与空内容都表示不说话。"""
    cleaned = text.strip()
    stripped = cleaned
    while stripped and stripped[0] in _WRAPPERS:
        stripped = stripped[1:].strip()
    while stripped and stripped[-1] in _WRAPPERS:
        stripped = stripped[:-1].strip()
    if not cleaned or not stripped:
        return None
    if stripped.upper() == NO_REPLY:
        return None
    return cleaned


class Responder:
    """把上下文交给模型：有工具时走工具循环，最后返回要不要说话。"""

    def __init__(
        self,
        client: DeepSeekClient,
        settings: Settings,
        tools: ToolExecutorLike | None = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._tools = tools

    async def reply(
        self,
        messages: list[ChatMessage],
        *,
        context: object | None = None,
        max_rounds: int | None = None,
        max_output_tokens: int | None | object = _DEFAULT_LIMIT,
    ) -> Outcome:
        """`max_output_tokens` 由调用方按模式给出（docs/token.md §5）；None = 不限。"""
        limit = self._settings.llm_max_output_tokens if max_output_tokens is _DEFAULT_LIMIT else max_output_tokens
        specs = self._specs(context)
        if not specs:
            return await self._single_call(messages, max_tokens=limit)

        rounds = max(0, self._settings.tool_max_rounds if max_rounds is None else max_rounds)
        history: list[ChatMessage] = list(messages)
        input_tokens = cached_tokens = output_tokens = 0
        tool_calls = 0
        tool_ms = 0
        model = self._settings.llm_model
        for index in range(rounds + 1):
            allow_tools = specs if index < rounds else None  # 最后一轮不带工具，强制给答案
            try:
                reply = await self._client.complete(
                    history,
                    model=self._settings.llm_model,
                    max_tokens=limit,
                    tools=allow_tools,
                )
            except LLMError:
                logger.exception("模型调用失败，本轮不回复")
                return Outcome(
                    None,
                    _usage_reply(model, input_tokens, cached_tokens, output_tokens),
                    tool_calls=tool_calls,
                    tool_ms=tool_ms,
                )
            model = reply.model or model
            input_tokens += reply.input_tokens
            cached_tokens += reply.cached_tokens
            output_tokens += reply.output_tokens
            if not reply.tool_calls or allow_tools is None:
                return Outcome(
                    normalize(reply.text),
                    _aggregate(model, input_tokens, cached_tokens, output_tokens),
                    tool_calls=tool_calls,
                    tool_ms=tool_ms,
                )
            history.append(_assistant_tool_message(reply))
            for call in reply.tool_calls:
                started = time.perf_counter()
                payload = await self._tools.execute(context, call.name, call.arguments)  # type: ignore[union-attr]
                tool_ms += int((time.perf_counter() - started) * 1000)
                tool_calls += 1
                history.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(payload, ensure_ascii=False)}
                )
        return Outcome(
            None,
            _aggregate(model, input_tokens, cached_tokens, output_tokens),
            tool_calls=tool_calls,
            tool_ms=tool_ms,
        )

    async def _single_call(self, messages: list[ChatMessage], *, max_tokens: int | None = None) -> Outcome:
        try:
            reply = await self._client.complete(messages, model=self._settings.llm_model, max_tokens=max_tokens)
        except LLMError:
            logger.exception("模型调用失败，本轮不回复")
            return Outcome(None)
        return Outcome(normalize(reply.text), reply)

    def _specs(self, context: object | None) -> list[dict[str, object]] | None:
        if self._tools is None or context is None:
            return None
        return self._tools.specs_for(context) or None


def _usage_reply(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> LLMReply | None:
    """一次都没计费时返回 None，避免把失败的一轮也记成一次模型调用。"""
    if input_tokens == 0 and cached_tokens == 0 and output_tokens == 0:
        return None
    return _aggregate(model, input_tokens, cached_tokens, output_tokens)


def _aggregate(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> LLMReply:
    """多轮调用的累计用量；文本留空，只用于记账。"""
    return LLMReply(
        text="",
        model=model,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        output_tokens=output_tokens,
    )


def _assistant_tool_message(reply: LLMReply) -> ChatMessage:
    return {
        "role": "assistant",
        "content": reply.text or "",
        "tool_calls": [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
            for call in reply.tool_calls
        ],
    }
