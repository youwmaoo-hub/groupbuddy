"""冷备份与校验（阶段 9，契约见 `docs/database.md` §5）。"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sqlite3
import unittest
from pathlib import Path

from app.storage import backup
from app.storage.repo import chat_settings
from tests.offline.helpers import DbTestCase

ROOT = Path(__file__).resolve().parents[2]


def _load_cli():
    """按路径加载 `scripts/backup_db.py`（`scripts/` 不是包，用 importlib 更稳）。"""
    spec = importlib.util.spec_from_file_location("scripts_backup_db", ROOT / "scripts" / "backup_db.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BackupModuleTests(DbTestCase):
    async def test_backup_of_a_live_database_creates_a_verified_snapshot(self) -> None:
        await chat_settings.upsert(self.connection, chat_id=7, mode="smart")
        dest = self.tmp / "storage" / "backups"

        info = backup.create_backup(self.settings.db_path, dest)

        self.assertTrue(info.ok, info.integrity)
        self.assertEqual(info.integrity, "ok")
        self.assertEqual(info.user_version, 4)
        self.assertEqual(info.counts["chat_settings"], 1)
        self.assertTrue(info.path.is_file())
        self.assertEqual(info.path.parent, dest)
        # 快照必须是单个自洽文件：不能留下 -wal/-shm sidecar。
        self.assertEqual([path.name for path in dest.iterdir()], [info.path.name])

        # 快照里必须有被备份那一刻的数据，且源库仍可用（备份不锁死工作连接）。
        snapshot = sqlite3.connect(f"file:{info.path}?mode=ro", uri=True)
        try:
            row = snapshot.execute("SELECT mode FROM chat_settings WHERE chat_id=7").fetchone()
        finally:
            snapshot.close()
        self.assertEqual(row, ("smart",))
        cursor = await self.connection.execute("SELECT COUNT(*) FROM chat_settings")
        self.assertEqual((await cursor.fetchone())[0], 1)
        await cursor.close()

    async def test_prune_keeps_only_the_newest_snapshots(self) -> None:
        dest = self.tmp / "storage" / "backups"
        dest.mkdir(parents=True)
        for stamp in ("20260101-0000", "20260102-0000", "20260103-0000"):
            (dest / f"bot.db.{stamp}").write_bytes(b"old")

        info = backup.create_backup(self.settings.db_path, dest, keep=2)

        remaining = sorted(path.name for path in dest.glob("bot.db.*"))
        self.assertEqual(len(remaining), 2)
        self.assertIn(info.path.name, remaining)
        self.assertIn("bot.db.20260103-0000", remaining)
        self.assertEqual(len(info.removed), 2)

    async def test_keep_zero_disables_pruning(self) -> None:
        dest = self.tmp / "storage" / "backups"
        dest.mkdir(parents=True)
        (dest / "bot.db.20260101-0000").write_bytes(b"old")

        info = backup.create_backup(self.settings.db_path, dest, keep=0)

        self.assertEqual(info.removed, ())
        self.assertEqual(len(list(dest.glob("bot.db.*"))), 2)

    async def test_snapshot_name_is_unique_within_the_same_minute(self) -> None:
        dest = self.tmp / "storage" / "backups"
        dest.mkdir(parents=True)
        when = 1_800_000_000.0  # 固定时刻，避免依赖真实时钟
        first = backup.snapshot_path(dest, when=when)
        first.write_bytes(b"first")

        second = backup.snapshot_path(dest, when=when)

        self.assertNotEqual(first, second)
        self.assertTrue(second.name.endswith("-2"), second.name)

    async def test_missing_database_is_reported_without_creating_a_snapshot(self) -> None:
        cli = _load_cli()
        dest = self.tmp / "storage" / "backups"

        code = cli.main(["--db", str(self.tmp / "storage" / "missing.db"), "--dest", str(dest)])

        self.assertEqual(code, 2)
        self.assertEqual(list(dest.glob("bot.db.*")), [])

    async def test_cli_writes_one_line_without_credentials(self) -> None:
        cli = _load_cli()
        dest = self.tmp / "storage" / "backups"
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            code = cli.main(["--db", str(self.settings.db_path), "--dest", str(dest)])

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("integrity=ok", output)
        self.assertIn(f"user_version={4}", output)
        self.assertNotIn("test-token", output)
        self.assertNotIn("test-key", output)
        self.assertEqual(len(list(dest.glob("bot.db.*"))), 1)


if __name__ == "__main__":
    unittest.main()
