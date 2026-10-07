"""notes 表 + FTS 同步：SQL 唯一来源（docs/database.md §2、docs/memory.md §6）。"""

from __future__ import annotations

import time

import aiosqlite

from app.storage.repo_models import NoteRow, SearchHit

SELECT_COLUMNS = "id, chat_id, name, text, tokens, version, created_at, updated_at"

UPSERT_SQL = (
    "INSERT INTO notes (chat_id, name, text, tokens, version, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, 1, ?, ?) "
    "ON CONFLICT (chat_id, name) DO UPDATE SET "
    "text=excluded.text, tokens=excluded.tokens, version=notes.version + 1, updated_at=excluded.updated_at"
)
SELECT_ONE_SQL = f"SELECT {SELECT_COLUMNS} FROM notes WHERE chat_id = ? AND name = ?"
FTS_INSERT_SQL = "INSERT INTO notes_fts (rowid, tokens) VALUES (?, ?)"
FTS_DELETE_SQL = "INSERT INTO notes_fts (notes_fts, rowid, tokens) VALUES ('delete', ?, ?)"
SEARCH_SQL = (
    "SELECT n.id, n.name, n.text, bm25(notes_fts) AS rank FROM notes_fts "
    "JOIN notes n ON n.id = notes_fts.rowid "
    "WHERE notes_fts MATCH ? AND n.chat_id = ? ORDER BY rank LIMIT ?"
)


async def upsert(
    connection: aiosqlite.Connection,
    *,
    chat_id: int,
    name: str,
    text: str,
    tokens: str,
    updated_at: int | None = None,
) -> int:
    """同名覆盖（version+1），并同步 FTS：先 delete 旧 tokens 再插新。"""
    previous = await get(connection, chat_id=chat_id, name=name)
    moment = updated_at if updated_at is not None else int(time.time())
    await connection.execute(UPSERT_SQL, (chat_id, name, text, tokens, moment, moment))
    row = await get(connection, chat_id=chat_id, name=name)
    note_id = 0 if row is None else row.id
    if previous is not None:
        await connection.execute(FTS_DELETE_SQL, (previous.id, previous.tokens))
    if note_id:
        await connection.execute(FTS_INSERT_SQL, (note_id, tokens))
    await connection.commit()
    return note_id


async def get(connection: aiosqlite.Connection, *, chat_id: int, name: str) -> NoteRow | None:
    cursor = await connection.execute(SELECT_ONE_SQL, (chat_id, name))
    row = await cursor.fetchone()
    await cursor.close()
    return None if row is None else NoteRow.from_row(row)


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
    return [SearchHit(source=f"笔记:{row['name']}", text=str(row["text"])) for row in rows]
