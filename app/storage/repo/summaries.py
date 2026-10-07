"""summaries 表 + FTS 同步：SQL 唯一来源（docs/database.md §2、docs/memory.md §4）。

FTS 是 external content 表，内容同步由本模块显式维护（不用 trigger）；
检索一律 JOIN 主表并带 chat_id 条件，禁止跨群召回。
"""

from __future__ import annotations

import time

import aiosqlite

from app.storage.repo_models import PendingSummary, SearchHit, SummaryRow

SELECT_COLUMNS = "id, chat_id, thread_id, text, tokens, msg_from, msg_to, created_at"

INSERT_SQL = (
    "INSERT INTO summaries (chat_id, thread_id, text, tokens, msg_from, msg_to, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)
FTS_INSERT_SQL = "INSERT INTO summaries_fts (rowid, tokens) VALUES (?, ?)"
FTS_DELETE_SQL = "INSERT INTO summaries_fts (summaries_fts, rowid, tokens) VALUES ('delete', ?, ?)"
LATEST_SQL = (
    f"SELECT {SELECT_COLUMNS} FROM summaries WHERE chat_id = ? ORDER BY created_at DESC, id DESC LIMIT 1"
)
CURSOR_SQL = "SELECT COALESCE(MAX(msg_to), 0) FROM summaries WHERE chat_id = ?"
SEARCH_SQL = (
    "SELECT s.id, s.text, bm25(summaries_fts) AS rank FROM summaries_fts "
    "JOIN summaries s ON s.id = summaries_fts.rowid "
    "WHERE summaries_fts MATCH ? AND s.chat_id = ? ORDER BY rank LIMIT ?"
)
PRUNE_SQL = (
    "SELECT id, tokens FROM summaries WHERE chat_id = ? ORDER BY created_at DESC, id DESC LIMIT -1 OFFSET ?"
)
DELETE_SQL = "DELETE FROM summaries WHERE id = ?"


async def insert(
    connection: aiosqlite.Connection,
    *,
    chat_id: int,
    text: str,
    tokens: str,
    msg_from: int | None = None,
    msg_to: int | None = None,
    thread_id: int | None = None,
    created_at: int | None = None,
) -> int:
    """写一条摘要并同步 FTS；返回新行 id。"""
    cursor = await connection.execute(
        INSERT_SQL,
        (
            chat_id,
            thread_id,
            text,
            tokens,
            msg_from,
            msg_to,
            created_at if created_at is not None else int(time.time()),
        ),
    )
    summary_id = int(cursor.lastrowid or 0)
    await cursor.close()
    await connection.execute(FTS_INSERT_SQL, (summary_id, tokens))
    await connection.commit()
    return summary_id


async def latest(connection: aiosqlite.Connection, *, chat_id: int) -> SummaryRow | None:
    cursor = await connection.execute(LATEST_SQL, (chat_id,))
    row = await cursor.fetchone()
    await cursor.close()
    return None if row is None else SummaryRow.from_row(row)


async def cursor(connection: aiosqlite.Connection, *, chat_id: int) -> int:
    """摘要游标：已覆盖到的最大 message id（无摘要返回 0，重启后自然恢复）。"""
    cursor = await connection.execute(CURSOR_SQL, (chat_id,))
    row = await cursor.fetchone()
    await cursor.close()
    return int(row[0]) if row is not None and row[0] is not None else 0


async def search(
    connection: aiosqlite.Connection,
    *,
    chat_id: int,
    match_query: str,
    limit: int = 3,
) -> list[SearchHit]:
    """FTS 检索：必须带 chat_id（跨群召回属于缺陷）。"""
    if not match_query.strip():
        return []
    cursor = await connection.execute(SEARCH_SQL, (match_query, chat_id, limit))
    rows = await cursor.fetchall()
    await cursor.close()
    return [SearchHit(source=f"摘要#{int(row['id'])}", text=str(row["text"])) for row in rows]


PENDING_CHATS_SQL = (
    "SELECT m.chat_id AS chat_id, COUNT(*) AS messages, COALESCE(SUM(LENGTH(m.text)), 0) AS chars, "
    "COALESCE(MAX(m.created_at), 0) AS last_at FROM messages m "
    "WHERE m.noise = 0 AND m.id > COALESCE("
    "(SELECT MAX(msg_to) FROM summaries WHERE chat_id = m.chat_id), 0) "
    "GROUP BY m.chat_id"
)


async def pending_by_chat(connection: aiosqlite.Connection) -> list[tuple[int, PendingSummary]]:
    """哪些群有未摘要消息（调度器每轮一条 SQL）。"""
    cursor = await connection.execute(PENDING_CHATS_SQL)
    rows = await cursor.fetchall()
    await cursor.close()
    return [
        (
            int(row["chat_id"]),
            PendingSummary(
                messages=int(row["messages"]),
                chars=int(row["chars"]),
                last_at=int(row["last_at"]),
            ),
        )
        for row in rows
    ]


async def prune(connection: aiosqlite.Connection, *, chat_id: int, keep: int = 50) -> int:
    """每群保留最近 keep 条；删除时同步删 FTS（external content 需要旧 tokens）。"""
    cursor = await connection.execute(PRUNE_SQL, (chat_id, max(0, keep)))
    stale = await cursor.fetchall()
    await cursor.close()
    for row in stale:
        await connection.execute(FTS_DELETE_SQL, (int(row["id"]), str(row["tokens"])))
        await connection.execute(DELETE_SQL, (int(row["id"]),))
    if stale:
        await connection.commit()
    return len(stale)
