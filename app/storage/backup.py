"""SQLite 冷备份与校验（阶段 9，契约见 `docs/database.md` §5）。

用标准库 `sqlite3` 的 `Connection.backup()` 做一致性快照：不走 `aiosqlite`、不占用 Bot 的
工作连接、不需要凭据，因此可以在 Bot 运行中执行（备份期间不阻塞服务）。

- 备份文件命名 `<dest_dir>/bot.db.YYYYMMDD-HHMM`；同一分钟内重复执行会追加 `-2`、`-3` 后缀。
- 备份后立刻用 `PRAGMA integrity_check` 校验，并统计关键表的行数供人工核对。
- 保留最近 `keep` 份（默认 7，与 `docs/database.md` §5 的 `BACKUP_KEEP` 默认值一致），更旧的删除。
- 只做全量冷快照：不做 WAL 增量归档、不做主从、不做跨机同步（契约明确排除）。
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_KEEP = 7
SNAPSHOT_PREFIX = "bot.db."

#: 只认 `<前缀>YYYYMMDD-HHMM`（可选 `-N` 去重后缀），避免把 `-wal` / `-shm` 当成快照。
SNAPSHOT_NAME = re.compile(rf"^{re.escape(SNAPSHOT_PREFIX)}\d{{8}}-\d{{4}}(-\d+)?$")

#: 校验时统计行数的表（缺失的表记为 -1，不算损坏：旧库或未来库都可能少表）。
COUNTED_TABLES = (
    "chat_settings",
    "messages",
    "notes",
    "stickers",
    "summaries",
    "tool_failures",
    "updates",
    "usage",
)


@dataclass(frozen=True, slots=True)
class SnapshotInfo:
    """一次快照的结果（只含计数与时间，不含任何凭据或数据内容）。"""

    path: Path
    bytes: int
    integrity: str
    user_version: int
    counts: dict[str, int]
    removed: tuple[Path, ...] = ()

    @property
    def ok(self) -> bool:
        return self.integrity == "ok"


def snapshot_path(dest_dir: Path, *, when: float | None = None) -> Path:
    """返回本次备份要写的路径（已存在则追加 `-2`、`-3` 后缀）。"""
    moment = time.time() if when is None else when
    stamp = time.strftime("%Y%m%d-%H%M", time.localtime(moment))
    candidate = dest_dir / f"{SNAPSHOT_PREFIX}{stamp}"
    index = 2
    while candidate.exists():
        candidate = dest_dir / f"{SNAPSHOT_PREFIX}{stamp}-{index}"
        index += 1
    return candidate


def copy_database(source: Path, target: Path) -> None:
    """把 `source` 一致性复制到 `target`；源库只读打开，不写入、不升级锁。

    源库是 WAL 模式时 `Connection.backup()` 会把 WAL 标志一起复制过去，快照旁边就会多出
    `-wal`/`-shm`。快照必须是**单个自洽文件**（恢复时直接替换 `bot.db`），所以复制完成后
    把目标改回回滚日志模式，并清掉残留的 sidecar。
    """
    origin = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        origin.execute("PRAGMA busy_timeout=5000")
        destination = sqlite3.connect(target)
        try:
            origin.backup(destination)
            destination.commit()
            destination.execute("PRAGMA journal_mode=DELETE")
            destination.commit()
        finally:
            destination.close()
    finally:
        origin.close()
    for suffix in ("-wal", "-shm"):
        Path(f"{target}{suffix}").unlink(missing_ok=True)


def verify_snapshot(path: Path) -> SnapshotInfo:
    """对快照做完整性检查并统计行数（只读打开，不修改快照）。"""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        counts: dict[str, int] = {}
        for table in COUNTED_TABLES:
            try:
                counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.Error:
                counts[table] = -1
    finally:
        connection.close()
    return SnapshotInfo(path=path, bytes=path.stat().st_size, integrity=integrity, user_version=version, counts=counts)


def prune_snapshots(dest_dir: Path, *, keep: int) -> tuple[Path, ...]:
    """按文件名（含时间戳）保留最近 `keep` 份；`keep <= 0` 表示不清理。

    只匹配 `SNAPSHOT_NAME`（普通文件），不会误删 `-wal`/`-shm` 或人工放入的其他文件。
    """
    if keep <= 0:
        return ()
    snapshots = sorted(
        (path for path in dest_dir.iterdir() if path.is_file() and SNAPSHOT_NAME.match(path.name)),
        key=lambda item: item.name,
        reverse=True,
    )
    removed: list[Path] = []
    for path in snapshots[keep:]:
        path.unlink(missing_ok=True)
        removed.append(path)
    return tuple(removed)


def create_backup(db_path: Path, dest_dir: Path, *, keep: int = DEFAULT_KEEP, when: float | None = None) -> SnapshotInfo:
    """备份 + 校验 + 清理旧快照；数据库不存在时抛 `FileNotFoundError`。"""
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = snapshot_path(dest_dir, when=when)
    copy_database(db_path, target)
    info = verify_snapshot(target)
    removed = prune_snapshots(dest_dir, keep=keep)
    return SnapshotInfo(
        path=info.path,
        bytes=info.bytes,
        integrity=info.integrity,
        user_version=info.user_version,
        counts=info.counts,
        removed=removed,
    )
