"""messages 表：消息原文落库与窗口查询。"""

from __future__ import annotations

import time

import aiosqlite

from app.storage.repo_models import PendingSummary, StoredMessage
from app.storage.tx import transaction

INSERT_SQL = """
INSERT INTO messages (chat_id, message_id, thread_id, user_id, role, text, reply_to_message_id, noise, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (chat_id, message_id) DO NOTHING
"""


async def insert(
    connection: aiosqlite.Connection,
    *,
    chat_id: int,
    message_id: int,
    user_id: int,
    role: str,
    text: str,
    thread_id: int | None = None,
    reply_to_message_id: int | None = None,
    noise: bool = False,
    created_at: int | None = None,
) -> bool:
    """写入一条消息；同一群内 message_id 重复视为重放，返回 False。"""
    async with transaction(connection):
        cursor = await connection.execute(
            INSERT_SQL,
            (
                chat_id,
                message_id,
                thread_id,
                user_id,
                role,
                text,
                reply_to_message_id,
                1 if noise else 0,
                created_at if created_at is not None else int(time.time()),
            ),
        )
        inserted = cursor.rowcount == 1
        await cursor.close()
    return inserted


async def recent(
    connection: aiosqlite.Connection,
    *,
    chat_id: int,
    limit: int,
    include_noise: bool = False,
    thread_id: int | None = None,
    until_id: int | None = None,
) -> list[StoredMessage]:
    """取该群最近 limit 条（时间升序返回）；窗口按 chat_id 过滤，绝不跨群。

    until_id 是本轮边界快照：只取"开始处理这一轮时已入库"的消息。
    """
    conditions = ["chat_id = ?"]
    params: list[object] = [chat_id]
    if not include_noise:
        conditions.append("noise = 0")
    if thread_id is not None:
        conditions.append("thread_id = ?")
        params.append(thread_id)
    if until_id is not None:
        conditions.append("id <= ?")
        params.append(until_id)

    sql = (
        f"SELECT * FROM (SELECT * FROM messages WHERE {' AND '.join(conditions)} "
        "ORDER BY created_at DESC, id DESC LIMIT ?) ORDER BY created_at ASC, id ASC"
    )
    params.append(limit)
    cursor = await connection.execute(sql, params)
    rows = await cursor.fetchall()
    await cursor.close()
    return [StoredMessage.from_row(row) for row in rows]


RANGE_SQL = (
    "SELECT * FROM messages WHERE chat_id = ? AND noise = 0 AND id > ? ORDER BY id LIMIT ?"
)
PENDING_SQL = (
    "SELECT COUNT(*) AS messages, COALESCE(SUM(LENGTH(text)), 0) AS chars, "
    "COALESCE(MAX(created_at), 0) AS last_at FROM messages "
    "WHERE chat_id = ? AND noise = 0 AND id > ?"
)


async def since(
    connection: aiosqlite.Connection,
    *,
    chat_id: int,
    after_id: int,
    limit: int = 200,
) -> list[StoredMessage]:
    """摘要输入：游标之后的消息（噪声已排除，时间升序）。"""
    cursor = await connection.execute(RANGE_SQL, (chat_id, after_id, max(1, limit)))
    rows = await cursor.fetchall()
    await cursor.close()
    return [StoredMessage.from_row(row) for row in rows]


async def pending_since(connection: aiosqlite.Connection, *, chat_id: int, after_id: int) -> PendingSummary:
    """未摘要区间的条数/字符数/最后时间（摘要触发判定用）。"""
    cursor = await connection.execute(PENDING_SQL, (chat_id, after_id))
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return PendingSummary(messages=0, chars=0, last_at=0)
    return PendingSummary(messages=int(row["messages"]), chars=int(row["chars"]), last_at=int(row["last_at"]))


async def max_id(connection: aiosqlite.Connection, *, chat_id: int) -> int:
    """该群当前最大行 id，用作本轮边界快照；无消息返回 0。"""
    cursor = await connection.execute(
        "SELECT COALESCE(MAX(id), 0) FROM messages WHERE chat_id = ?", (chat_id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    return int(row[0]) if row is not None else 0


async def since_last_assistant(connection: aiosqlite.Connection, *, chat_id: int) -> int | None:
    """Bot 上一条发言之后（不含该条、含当前这条）的消息条数；从未发言返回 None。

    只用于追问判定（F2.3）：Bot 刚说完话的几条之内才算"接着上面的话"。
    """
    cursor = await connection.execute(
        "SELECT (SELECT COUNT(*) FROM messages WHERE chat_id = ? AND role = 'assistant') AS spoken, "
        "(SELECT COUNT(*) FROM messages WHERE chat_id = ? AND id > COALESCE("
        "(SELECT MAX(id) FROM messages WHERE chat_id = ? AND role = 'assistant'), 0)) AS gap",
        (chat_id, chat_id, chat_id),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None or int(row[0]) == 0:
        return None
    return int(row[1])


async def last_assistant_text(connection: aiosqlite.Connection, *, chat_id: int) -> str | None:
    """Bot 上一条发言的原文；从未发言或原文为空返回 None。

    只用于「同话题」弱触发（阶段 8）：判断新消息是否在接着 Bot 自己的话题聊。
    """
    cursor = await connection.execute(
        "SELECT text FROM messages WHERE chat_id = ? AND role = 'assistant' "
        "AND text IS NOT NULL ORDER BY id DESC LIMIT 1",
        (chat_id,),
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is None or not str(row[0]).strip():
        return None
    return str(row[0])


async def totals(connection: aiosqlite.Connection) -> dict[str, int]:
    """面板概览用：消息总数与出现过的群数量（只做计数，不读任何原文）。"""
    cursor = await connection.execute("SELECT COUNT(*), COUNT(DISTINCT chat_id) FROM messages")
    row = await cursor.fetchone()
    await cursor.close()
    if row is None:
        return {"chats": 0, "messages": 0}
    return {"chats": int(row[1]), "messages": int(row[0])}


async def chat_activity(connection: aiosqlite.Connection, *, limit: int) -> list[dict[str, object]]:
    """最近活跃的群（面板群列表用）：只给计数与最后消息时间，不返回原文。

    面板不做聊天记录浏览（docs/requirements.md F6.5）：运维视图只需要知道
    「哪个群在用、最后一次说话是什么时候」，原文留在库里面板无权查看。
    """
    cursor = await connection.execute(
        "SELECT chat_id, COUNT(*) AS messages, MAX(created_at) AS last_at "
        "FROM messages GROUP BY chat_id ORDER BY last_at DESC LIMIT ?",
        (int(limit),),
    )
    rows = await cursor.fetchall()
    await cursor.close()
    return [
        {"chat_id": int(row[0]), "messages": int(row[1]), "last_at": int(row[2])}
        for row in rows
    ]


async def clear_chat(connection: aiosqlite.Connection, chat_id: int) -> int:
    """/clear 用：删除该群消息原文，不影响其他群。"""
    async with transaction(connection):
        cursor = await connection.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        deleted = cursor.rowcount
        await cursor.close()
    return deleted
