"""chat_settings 表：每个群的设置，缺失即按默认值。"""

from __future__ import annotations

import time

import aiosqlite

from app.storage.tx import transaction

DEFAULTS: dict[str, object] = {
    "mode": "normal",
    "allow_search": 1,
    "allow_read": 1,
    "allow_write": 0,
    "allow_code": 0,
    "allow_sticker": 1,
    "allow_host_info": 0,
    "sticker_cooldown": 30,
    "persona_override": None,
    "owner_user_id": None,
}

COLUMNS = tuple(DEFAULTS)


async def get(connection: aiosqlite.Connection, chat_id: int) -> dict[str, object]:
    """返回该群设置；没有记录时返回默认值（不写库）。"""
    cursor = await connection.execute("SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,))
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return {"chat_id": chat_id, **DEFAULTS}
    return dict(row)


async def list_all(connection: aiosqlite.Connection, *, limit: int) -> list[dict[str, object]]:
    """列出被配置过的群（面板群列表用），按最近更新排序。

    只读：面板展示与机器人 `/settings` 读的是同一张表、同一份默认值语义。
    """
    columns = ", ".join(("chat_id", *COLUMNS))
    cursor = await connection.execute(
        f"SELECT {columns} FROM chat_settings ORDER BY updated_at DESC, chat_id ASC LIMIT ?",
        (int(limit),),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [dict(row) for row in rows]


async def upsert(connection: aiosqlite.Connection, chat_id: int, **changes: object) -> None:
    """写入/更新设置字段，只接受已知列。

    只写调用方给出的列，不再读-改-写：两个并发更新改不同字段时不会互相覆盖（技术债 T12）。
    首次插入时未给出的列取表默认值（与 `DEFAULTS` 一致）。
    """
    unknown = set(changes) - set(COLUMNS)
    if unknown:
        raise ValueError(f"未知的设置字段: {sorted(unknown)}")
    columns = tuple(changes)
    names = ", ".join(("chat_id", *columns, "updated_at"))
    placeholders = ", ".join("?" for _ in range(len(columns) + 2))
    assignments = ", ".join(f"{column}=excluded.{column}" for column in (*columns, "updated_at"))
    async with transaction(connection):
        await connection.execute(
            f"INSERT INTO chat_settings ({names}) VALUES ({placeholders}) "
            f"ON CONFLICT (chat_id) DO UPDATE SET {assignments}",
            (chat_id, *[changes[column] for column in columns], int(time.time())),
        )
