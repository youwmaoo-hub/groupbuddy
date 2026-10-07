"""usage 表：运行侧 token 记账。"""

from __future__ import annotations

import time

import aiosqlite


async def record(
    connection: aiosqlite.Connection,
    *,
    chat_id: int,
    user_id: int,
    day: str,
    model: str,
    input_tokens: int = 0,
    cached_tokens: int = 0,
    output_tokens: int = 0,
    tool_calls: int = 0,
    tool_ms: int = 0,
    purpose: str = "chat",
    created_at: int | None = None,
) -> None:
    """记一次模型调用；purpose 区分用途（chat / summary 等），记账失败不得影响回复。"""
    await connection.execute(
        "INSERT INTO usage (chat_id, user_id, day, model, input_tokens, cached_tokens, output_tokens, tool_calls, tool_ms, purpose, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            chat_id,
            user_id,
            day,
            model,
            input_tokens,
            cached_tokens,
            output_tokens,
            tool_calls,
            tool_ms,
            purpose,
            created_at if created_at is not None else int(time.time()),
        ),
    )
    await connection.commit()


async def summary_for_day(
    connection: aiosqlite.Connection,
    day: str,
    chat_id: int | None = None,
    purpose: str | None = None,
) -> dict[str, int]:
    """按天聚合（可选按群 / 按用途），用于 /stats 与成本核对。"""
    sql = (
        "SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS input_tokens, "
        "COALESCE(SUM(cached_tokens),0) AS cached_tokens, COALESCE(SUM(output_tokens),0) AS output_tokens, "
        "COALESCE(SUM(tool_calls),0) AS tool_calls, COALESCE(SUM(tool_ms),0) AS tool_ms FROM usage WHERE day = ?"
    )
    params: list[object] = [day]
    if chat_id is not None:
        sql += " AND chat_id = ?"
        params.append(chat_id)
    if purpose is not None:
        sql += " AND purpose = ?"
        params.append(purpose)
    cursor = await connection.execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    return dict(row) if row is not None else {
        "calls": 0,
        "input_tokens": 0,
        "cached_tokens": 0,
        "output_tokens": 0,
        "tool_calls": 0,
        "tool_ms": 0,
    }
