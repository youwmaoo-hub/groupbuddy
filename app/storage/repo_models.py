"""数据访问层的返回结构：与 aiogram 无关，便于离线测试。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StoredMessage:
    """messages 表的一行。"""

    id: int
    chat_id: int
    message_id: int
    thread_id: int | None
    user_id: int
    role: str
    text: str
    reply_to_message_id: int | None
    noise: bool
    created_at: int

    @classmethod
    def from_row(cls, row: Any) -> "StoredMessage":
        return cls(
            id=int(row["id"]),
            chat_id=int(row["chat_id"]),
            message_id=int(row["message_id"]),
            thread_id=row["thread_id"],
            user_id=int(row["user_id"]),
            role=str(row["role"]),
            text=str(row["text"]),
            reply_to_message_id=row["reply_to_message_id"],
            noise=bool(row["noise"]),
            created_at=int(row["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class StickerRow:
    """stickers 表的一行；file_id 只允许存在于数据层与出站边界。"""

    id: int
    chat_id: int
    file_id: str
    file_unique_id: str
    valence: float | None
    arousal: float | None
    tags: str | None
    last_used_at: int | None

    @classmethod
    def from_row(cls, row: Any) -> "StickerRow":
        return cls(
            id=int(row["id"]),
            chat_id=int(row["chat_id"]),
            file_id=str(row["file_id"]),
            file_unique_id=str(row["file_unique_id"]),
            valence=None if row["valence"] is None else float(row["valence"]),
            arousal=None if row["arousal"] is None else float(row["arousal"]),
            tags=None if row["tags"] is None else str(row["tags"]),
            last_used_at=None if row["last_used_at"] is None else int(row["last_used_at"]),
        )


@dataclass(frozen=True, slots=True)
class SummaryRow:
    """summaries 表的一行（滚动摘要，msg_to 是摘要游标）。"""

    id: int
    chat_id: int
    thread_id: int | None
    text: str
    tokens: str
    msg_from: int | None
    msg_to: int | None
    created_at: int

    @classmethod
    def from_row(cls, row: Any) -> "SummaryRow":
        return cls(
            id=int(row["id"]),
            chat_id=int(row["chat_id"]),
            thread_id=row["thread_id"],
            text=str(row["text"]),
            tokens=str(row["tokens"]),
            msg_from=row["msg_from"],
            msg_to=row["msg_to"],
            created_at=int(row["created_at"]),
        )


@dataclass(frozen=True, slots=True)
class NoteRow:
    """notes 表的一行（同名覆盖，version 递增）。"""

    id: int
    chat_id: int
    name: str
    text: str
    tokens: str
    version: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, row: Any) -> "NoteRow":
        return cls(
            id=int(row["id"]),
            chat_id=int(row["chat_id"]),
            name=str(row["name"]),
            text=str(row["text"]),
            tokens=str(row["tokens"]),
            version=int(row["version"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )


@dataclass(frozen=True, slots=True)
class SearchHit:
    """FTS 命中：带来源标记，便于模型区分"记忆"与当前对话。"""

    source: str  # 例如 "摘要#12" / "笔记:部署"
    text: str


@dataclass(frozen=True, slots=True)
class PendingSummary:
    """未摘要区间的统计（摘要触发判定用）。"""

    messages: int
    chars: int
    last_at: int
