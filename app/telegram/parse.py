"""aiogram 与业务层之间的唯一映射：业务代码不认识 aiogram 类型（便于离线测试）。"""

from __future__ import annotations

from dataclasses import dataclass

MENTION = "mention"
TEXT_MENTION = "text_mention"


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    """一条待处理消息；所有字段都是普通 Python 类型。"""

    update_id: int
    chat_id: int
    chat_type: str
    message_id: int
    user_id: int
    text: str
    thread_id: int | None
    is_bot_author: bool
    reply_to_bot: bool
    mentions_bot: bool


def parse_update(
    update: object,
    *,
    bot_id: int,
    bot_username: str,
    aliases: tuple[str, ...] = (),
) -> IncomingMessage | None:
    """把 Telegram Update 转成 IncomingMessage；与本程序无关的更新返回 None。"""
    message = getattr(update, "message", None)
    if message is None:
        return None
    chat = getattr(message, "chat", None)
    author = getattr(message, "from_user", None)
    if chat is None or author is None:
        return None

    text = getattr(message, "text", None) or getattr(message, "caption", None) or ""
    mention_names = tuple(name.casefold() for name in (bot_username, *aliases) if name)

    return IncomingMessage(
        update_id=int(getattr(update, "update_id", 0)),
        chat_id=int(getattr(chat, "id", 0)),
        chat_type=str(getattr(chat, "type", "private")),
        message_id=int(getattr(message, "message_id", 0)),
        user_id=int(getattr(author, "id", 0)),
        text=str(text),
        thread_id=getattr(message, "message_thread_id", None),
        is_bot_author=bool(getattr(author, "is_bot", False)),
        reply_to_bot=_reply_to_bot(message, bot_id),
        mentions_bot=_mentions_bot(message, text, bot_id, mention_names),
    )


def _reply_to_bot(message: object, bot_id: int) -> bool:
    replied = getattr(message, "reply_to_message", None)
    if replied is None:
        return False
    author = getattr(replied, "from_user", None)
    return author is not None and int(getattr(author, "id", 0)) == bot_id


def _mentions_bot(message: object, text: str, bot_id: int, names: tuple[str, ...]) -> bool:
    for entity in getattr(message, "entities", None) or ():
        entity_type = getattr(entity, "type", "")
        if entity_type == TEXT_MENTION:
            mentioned = getattr(entity, "user", None)
            if mentioned is not None and int(getattr(mentioned, "id", 0)) == bot_id:
                return True
        elif entity_type == MENTION:
            offset = int(getattr(entity, "offset", 0))
            length = int(getattr(entity, "length", 0))
            mention = text[offset : offset + length].casefold()
            if mention and mention in {f"@{name}" for name in names}:
                return True
    return any(f"@{name}" in text.casefold() for name in names)
