"""stickers 表读写：SQL 唯一来源（docs/database.md §2、阶段 5）。"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from typing import Protocol

import aiosqlite

from app.storage.repo_models import StickerRow

COLUMNS = ("chat_id", "file_id", "file_unique_id", "valence", "arousal", "tags", "last_used_at", "created_at")

UPSERT_SQL = (
    "INSERT INTO stickers (chat_id, file_id, file_unique_id, valence, arousal, tags, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT (chat_id, file_unique_id) DO UPDATE SET "
    "file_id=excluded.file_id, valence=excluded.valence, arousal=excluded.arousal, tags=excluded.tags"
)
SELECT_SQL = (
    "SELECT id, chat_id, file_id, file_unique_id, valence, arousal, tags, last_used_at "
    "FROM stickers WHERE chat_id = ? ORDER BY id"
)
SELECT_ONE_SQL = "SELECT id FROM stickers WHERE chat_id = ? AND file_unique_id = ?"
MARK_USED_SQL = "UPDATE stickers SET last_used_at = ? WHERE id = ?"


def encode_tags(tags: Iterable[str]) -> str | None:
    """tags 以 JSON 数组文本存储；空列表存 NULL。"""
    clean = [str(tag).strip() for tag in tags if str(tag).strip()]
    return json.dumps(clean, ensure_ascii=False) if clean else None


def decode_tags(raw: object) -> tuple[str, ...]:
    """容错解析：非法内容当作没有标签，不抛异常。"""
    if not raw:
        return ()
    try:
        parsed = json.loads(str(raw))
    except (ValueError, TypeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item) for item in parsed)


async def register(
    connection: aiosqlite.Connection,
    *,
    chat_id: int,
    file_id: str,
    file_unique_id: str,
    valence: float | None = None,
    arousal: float | None = None,
    tags: Iterable[str] = (),
    created_at: int | None = None,
) -> int:
    """登记/更新一张贴纸，返回内部 id（同群同 file_unique_id 覆盖）。"""
    await connection.execute(
        UPSERT_SQL,
        (
            chat_id,
            file_id,
            file_unique_id,
            valence,
            arousal,
            encode_tags(tags),
            created_at if created_at is not None else int(time.time()),
        ),
    )
    await connection.commit()
    cursor = await connection.execute(SELECT_ONE_SQL, (chat_id, file_unique_id))
    row = await cursor.fetchone()
    await cursor.close()
    return int(row[0]) if row is not None else 0


async def candidates(connection: aiosqlite.Connection, *, chat_id: int) -> list[StickerRow]:
    """本群可用贴纸；严格带 chat_id 条件（跨群读取属于缺陷）。"""
    cursor = await connection.execute(SELECT_SQL, (chat_id,))
    rows = await cursor.fetchall()
    await cursor.close()
    return [StickerRow.from_row(row) for row in rows]


async def mark_used(connection: aiosqlite.Connection, *, sticker_id: int, used_at: int) -> None:
    await connection.execute(MARK_USED_SQL, (used_at, sticker_id))
    await connection.commit()


class StickerStore(Protocol):
    async def candidates(self, chat_id: int) -> list[StickerRow]: ...

    async def mark_used(self, sticker_id: int, used_at: int) -> None: ...


class DbStickerStore:
    """给工具注入的薄适配器：工具只需要这两个动作，SQL 仍留在本模块。"""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    async def candidates(self, chat_id: int) -> list[StickerRow]:
        return await candidates(self._connection, chat_id=chat_id)

    async def mark_used(self, sticker_id: int, used_at: int) -> None:
        await mark_used(self._connection, sticker_id=sticker_id, used_at=used_at)
