"""tool_failures 表：工具失败留痕，供 `/stats` 错误率与排查使用（阶段 8 F5.4）。

只记录**计入熔断的失败**（超时、工具自身错误、未预期异常）；`permission_denied` /
`invalid_arguments` / `cooldown` 属于调用前拒绝，不占熔断计数，也不写本表
（与 `docs/security.md` §9 一致）。保留期 7 天，见 `docs/database.md` §4。
"""

from __future__ import annotations

import time

import aiosqlite

from app.storage.tx import transaction

#: 保留天数（docs/database.md §4）。
RETENTION_DAYS = 7


async def record(
    connection: aiosqlite.Connection,
    *,
    tool: str,
    chat_id: int,
    error_code: str,
    created_at: int | None = None,
) -> None:
    """记一次工具失败；留痕失败不得影响工具结果（调用方另行兜底）。"""
    async with transaction(connection):
        await connection.execute(
            "INSERT INTO tool_failures (tool, chat_id, error_code, created_at) VALUES (?, ?, ?, ?)",
            (tool, chat_id, error_code, created_at if created_at is not None else int(time.time())),
        )


async def count(
    connection: aiosqlite.Connection,
    *,
    chat_id: int,
    since: int | None = None,
    until: int | None = None,
) -> int:
    """按群统计失败次数，可选时间区间（Unix 秒，左闭右开）。"""
    sql = "SELECT COUNT(*) FROM tool_failures WHERE chat_id = ?"
    params: list[object] = [chat_id]
    if since is not None:
        sql += " AND created_at >= ?"
        params.append(since)
    if until is not None:
        sql += " AND created_at < ?"
        params.append(until)
    cursor = await connection.execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    return int(row[0] or 0) if row is not None else 0


async def purge_old(
    connection: aiosqlite.Connection,
    *,
    days: int = RETENTION_DAYS,
    now: int | None = None,
) -> int:
    """删除超过保留期的失败记录（启动时与每小时 housekeeping 各执行一次）。"""
    cutoff = (now if now is not None else int(time.time())) - days * 86400
    async with transaction(connection):
        cursor = await connection.execute("DELETE FROM tool_failures WHERE created_at < ?", (cutoff,))
        deleted = cursor.rowcount
        await cursor.close()
    return int(deleted or 0)
