"""updates 表：批次级去重（update_id 主键）。"""

from __future__ import annotations

import time

import aiosqlite

from app.storage.tx import transaction


async def mark_seen(connection: aiosqlite.Connection, update_id: int, chat_id: int | None) -> bool:
    """记录 update_id；首次返回 True，重复（Telegram 重放）返回 False。"""
    async with transaction(connection):
        cursor = await connection.execute(
            "INSERT OR IGNORE INTO updates (update_id, chat_id, received_at) VALUES (?, ?, ?)",
            (update_id, chat_id if chat_id is not None else 0, int(time.time())),
        )
        inserted = cursor.rowcount == 1
        await cursor.close()
    return inserted


async def is_seen(connection: aiosqlite.Connection, update_id: int) -> bool:
    cursor = await connection.execute("SELECT 1 FROM updates WHERE update_id = ?", (update_id,))
    row = await cursor.fetchone()
    await cursor.close()
    return row is not None


async def purge_old(connection: aiosqlite.Connection, older_than_seconds: int = 48 * 3600) -> int:
    """清理过期去重记录（docs/database.md §4）。"""
    cutoff = int(time.time()) - older_than_seconds
    async with transaction(connection):
        cursor = await connection.execute("DELETE FROM updates WHERE received_at < ?", (cutoff,))
        deleted = cursor.rowcount
        await cursor.close()
    return deleted
