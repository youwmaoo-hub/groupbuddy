"""SQLite 连接与迁移：启动时只前进，user_version 高于代码则拒绝启动。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import aiosqlite

from app.config import Settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
MIGRATION_MARKER = re.compile(r"^-- ===== migration (\d+) =====$")
ADD_COLUMN_MARKER = re.compile(
    r"^ALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s+ADD\s+COLUMN\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
# 已确认的历史半升级形态：只有 usage.purpose 出现过"列已存在但 user_version 未推进"。
# 兼容只对这一张表 + 这一个列生效；其他任何重复 DDL（含其他 ADD COLUMN）都必须按真实错误抛出。
TOLERATED_REPLAYED_COLUMNS = frozenset({("usage", "purpose")})


class SchemaTooNewError(RuntimeError):
    """数据库由更新版本的代码创建，拒绝启动以免损坏数据。"""


def load_migrations(path: Path | None = None) -> list[list[str]]:
    """把 schema.sql 解析为按版本排序的 DDL 列表。"""
    text = (path or SCHEMA_PATH).read_text(encoding="utf-8")
    versions: dict[int, list[str]] = {}
    current: int | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current is not None:
            versions[current] = [statement.strip() for statement in "".join(buffer).split(";") if statement.strip()]

    for line in text.splitlines():
        found = MIGRATION_MARKER.match(line.strip())
        if found:
            flush()
            current = int(found.group(1))
            buffer = []
            continue
        if current is not None and not line.strip().startswith("--"):
            buffer.append(line + "\n")
    flush()

    return [versions[key] for key in sorted(versions)]


async def open_db(settings: Settings) -> aiosqlite.Connection:
    """打开连接、应用 PRAGMA、执行未应用的迁移。"""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = await aiosqlite.connect(settings.db_path)
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA journal_mode=WAL")
    await connection.execute("PRAGMA synchronous=NORMAL")
    await connection.execute("PRAGMA foreign_keys=ON")
    await connection.execute("PRAGMA busy_timeout=5000")
    await apply_migrations(connection)
    return connection


async def _column_exists(connection: aiosqlite.Connection, table: str, column: str) -> bool:
    """列是否已存在于该表，用于识别历史半升级库。"""
    cursor = await connection.execute(f"PRAGMA table_info({table})")
    try:
        rows = await cursor.fetchall()
    finally:
        await cursor.close()
    wanted = column.lower()
    return any(str(row[1]).lower() == wanted for row in rows)


async def _apply_statement(connection: aiosqlite.Connection, statement: str) -> None:
    """执行一条迁移语句；仅对已确认的历史半升级形态跳过"重复加列"。"""
    found = ADD_COLUMN_MARKER.match(statement)
    if found is not None:
        table, column = found.group(1).lower(), found.group(2).lower()
        if (table, column) in TOLERATED_REPLAYED_COLUMNS and await _column_exists(connection, table, column):
            return
    await connection.execute(statement)


async def apply_migrations(connection: aiosqlite.Connection, migrations: Iterable[list[str]] | None = None) -> int:
    """按序应用迁移；每块是一个显式事务，失败即回滚且不推进 user_version。"""
    batches = list(migrations if migrations is not None else load_migrations())
    cursor = await connection.execute("PRAGMA user_version")
    row = await cursor.fetchone()
    await cursor.close()
    version = int(row[0]) if row else 0

    if version > len(batches):
        raise SchemaTooNewError(
            f"数据库 schema 版本 {version} 高于代码支持的 {len(batches)}；请更新代码后再启动"
        )

    for index in range(version, len(batches)):
        # 遗留模式下 DDL/PRAGMA 会各自自动提交，必须显式开事务才能让整块原子。
        await connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in batches[index]:
                await _apply_statement(connection, statement)
            await connection.execute(f"PRAGMA user_version={index + 1}")
        except BaseException:
            await connection.rollback()
            raise
        await connection.commit()
    return len(batches)


async def close_db(connection: aiosqlite.Connection) -> None:
    await connection.close()


async def optimize(connection: aiosqlite.Connection) -> None:
    """跑一次 `PRAGMA optimize`（docs/database.md §5 维护）：SQLite 只在其认为划算时刷新统计信息。"""
    await connection.execute("PRAGMA optimize")
