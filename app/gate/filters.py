"""入口过滤：这些消息根本不进闸门、不花 token。"""

from __future__ import annotations

from dataclasses import dataclass

from app.telegram.parse import IncomingMessage

DROP_BOT_AUTHOR = "bot_author"
DROP_NO_TEXT = "no_text"
DROP_COMMAND = "command"
DROP_PRIVATE = "private_chat"

# 群聊是默认场景；其他类型（private/channel）默认不处理（docs/requirements.md §2.2）
GROUP_CHAT_TYPES = frozenset({"group", "supergroup"})


@dataclass(frozen=True, slots=True)
class ScreenResult:
    allowed: bool
    reason: str


def screen(message: IncomingMessage, *, allow_private_chat: bool = False) -> ScreenResult:
    """程序硬规则；先过滤再判断是否回应（docs/token.md 链 1）。"""
    if message.is_bot_author:
        # 其他 Bot 的消息与 Bot 自己的消息：产品规则，见 docs/security.md §12
        return ScreenResult(False, DROP_BOT_AUTHOR)
    if not allow_private_chat and message.chat_type not in GROUP_CHAT_TYPES:
        # 私聊默认完全不处理：不进模型、不调工具、不写 messages、0 token
        return ScreenResult(False, DROP_PRIVATE)
    if not message.text.strip():
        return ScreenResult(False, DROP_NO_TEXT)
    if message.text.lstrip().startswith("/"):
        # 群主命令属于阶段 8；阶段 1 一律忽略，避免误回复
        return ScreenResult(False, DROP_COMMAND)
    return ScreenResult(True, "ok")
