"""SQLite 连接与迁移：启动时只前进，user_version 高于代码则拒绝启动。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import aiosqlite

from app.config import Settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
MIGRATION_MARKER = re.compile(r"^-- ===== migration (\d+) =====$")


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


async def apply_migrations(connection: aiosqlite.Connection, migrations: Iterable[list[str]] | None = None) -> int:
    """按序应用迁移；返回当前 schema 版本。"""
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
        for statement in batches[index]:
            await connection.execute(statement)
        await connection.execute(f"PRAGMA user_version={index + 1}")
        await connection.commit()
    return len(batches)


async def close_db(connection: aiosqlite.Connection) -> None:
    await connection.close()
