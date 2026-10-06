"""阶段 1 只做一次模型调用与输出规范化；工具循环属阶段 3。"""

from __future__ import annotations

import logging

from app.config import Settings
from app.llm.client import DeepSeekClient, LLMError, LLMReply
from app.llm.prompts import NO_REPLY

logger = logging.getLogger(__name__)

BACKTICK = chr(96)
_WRAPPERS = ('"', "'", BACKTICK, BACKTICK * 3, " ", "\n", "。", ".")


class Outcome:
    """一次回复的结果；text 为 None 表示本轮不说话。"""

    __slots__ = ("text", "reply")

    def __init__(self, text: str | None, reply: LLMReply | None = None) -> None:
        self.text = text
        self.reply = reply


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
    """把上下文交给模型，返回要不要说话的结果。"""

    def __init__(self, client: DeepSeekClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def reply(self, messages: list[dict[str, str]]) -> Outcome:
        try:
            reply = await self._client.complete(messages, model=self._settings.llm_model)
        except LLMError:
            logger.exception("模型调用失败，本轮不回复")
            return Outcome(None)
        return Outcome(normalize(reply.text), reply)
