"""存储层：迁移幂等、消息去重与排序、设置默认值、记账。"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import aiosqlite

from app.storage.db import apply_migrations, load_migrations
from app.storage.repo import chat_settings, messages, updates, usage
from tests.offline.helpers import DbTestCase


class MigrationTests(DbTestCase):
    async def test_load_migrations(self) -> None:
        versions = load_migrations()
        self.assertEqual(len(versions), 3)
        self.assertEqual(len(versions[0]), 6)
        self.assertEqual(len(versions[1]), 1)
        self.assertEqual(len(versions[2]), 7)

    async def test_apply_is_idempotent(self) -> None:
        self.assertEqual(await apply_migrations(self.connection), 3)


class UpdateDedupeTests(DbTestCase):
    async def test_first_seen_once(self) -> None:
        self.assertTrue(await updates.mark_seen(self.connection, 100, 1))
        self.assertFalse(await updates.mark_seen(self.connection, 100, 1))
        self.assertTrue(await updates.is_seen(self.connection, 100))

    async def test_purge_removes_old_rows(self) -> None:
        await updates.mark_seen(self.connection, 200, 1)
        await self.connection.execute("UPDATE updates SET received_at = received_at - 100000 WHERE update_id = 200")
        await self.connection.commit()
        self.assertEqual(await updates.purge_old(self.connection, older_than_seconds=3600), 1)
        self.assertFalse(await updates.is_seen(self.connection, 200))


class MessageRepoTests(DbTestCase):
    async def test_insert_is_deduplicated(self) -> None:
        first = await messages.insert(
            self.connection, chat_id=1, message_id=10, user_id=42, role="user", text="hi"
        )
        second = await messages.insert(
            self.connection, chat_id=1, message_id=10, user_id=42, role="user", text="hi"
        )
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(len(await messages.recent(self.connection, chat_id=1, limit=10)), 1)

    async def test_same_message_id_in_other_chat_is_kept(self) -> None:
        await messages.insert(self.connection, chat_id=1, message_id=10, user_id=42, role="user", text="a")
        kept = await messages.insert(
            self.connection, chat_id=2, message_id=10, user_id=42, role="user", text="b"
        )
        self.assertTrue(kept)
        self.assertEqual([m.text for m in await messages.recent(self.connection, chat_id=2, limit=10)], ["b"])

    async def test_recent_skips_noise_and_respects_chat(self) -> None:
        for index in range(3):
            await messages.insert(
                self.connection,
                chat_id=1,
                message_id=100 + index,
                user_id=42,
                role="user",
                text=f"m{index}",
                noise=index == 1,
                created_at=1000 + index,
            )
        await messages.insert(
            self.connection, chat_id=2, message_id=200, user_id=7, role="user", text="other", created_at=1005
        )
        rows = await messages.recent(self.connection, chat_id=1, limit=10)
        self.assertEqual([row.text for row in rows], ["m0", "m2"])
        self.assertEqual(len(await messages.recent(self.connection, chat_id=1, limit=1)), 1)
        self.assertEqual([row.text for row in await messages.recent(self.connection, chat_id=1, limit=10, include_noise=True)], ["m0", "m1", "m2"])


    async def test_max_id_is_zero_without_messages(self) -> None:
        self.assertEqual(await messages.max_id(self.connection, chat_id=1), 0)

    async def test_recent_stops_at_round_snapshot(self) -> None:
        for index in range(3):
            await messages.insert(
                self.connection,
                chat_id=1,
                message_id=100 + index,
                user_id=42,
                role="user",
                text=f"m{index}",
                created_at=1000 + index,
            )
        snapshot = await messages.max_id(self.connection, chat_id=1)
        await messages.insert(
            self.connection,
            chat_id=1,
            message_id=200,
            user_id=42,
            role="user",
            text="后到的消息",
            created_at=1010,
        )
        rows = await messages.recent(self.connection, chat_id=1, limit=10, until_id=snapshot)
        self.assertEqual([row.text for row in rows], ["m0", "m1", "m2"])
        self.assertGreater(await messages.max_id(self.connection, chat_id=1), snapshot)


class ChatSettingsTests(DbTestCase):
    async def test_defaults_when_missing(self) -> None:
        group = await chat_settings.get(self.connection, 999)
        self.assertEqual(group["mode"], "normal")
        self.assertEqual(group["allow_write"], 0)
        self.assertEqual(group["sticker_cooldown"], 30)

    async def test_upsert_merges_changes(self) -> None:
        await chat_settings.upsert(self.connection, 1, allow_write=1)
        await chat_settings.upsert(self.connection, 1, mode="smart")
        group = await chat_settings.get(self.connection, 1)
        self.assertEqual(group["mode"], "smart")
        self.assertEqual(group["allow_write"], 1)

    async def test_unknown_field_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await chat_settings.upsert(self.connection, 1, nope=1)

    async def test_upsert_writes_only_given_columns(self) -> None:
        # T12：单条 UPSERT，不做读-改-写（读到的旧快照会覆盖并发写入）
        await chat_settings.upsert(self.connection, 1, allow_write=1)
        await chat_settings.upsert(self.connection, 1, mode="smart")
        await chat_settings.upsert(self.connection, 1, allow_code=1)
        cursor = await self.connection.execute(
            "SELECT mode, allow_write, allow_code FROM chat_settings WHERE chat_id = 1"
        )
        row = await cursor.fetchone()
        await cursor.close()
        self.assertEqual(tuple(row), ("smart", 1, 1))

    async def test_upsert_does_not_read_before_write(self) -> None:
        # T12 的根因就是这次读取：pytest 化后若重新引入读-改-写，本用例会失败
        with mock.patch.object(
            chat_settings, "get", side_effect=AssertionError("upsert 不应读取当前设置")
        ):
            await chat_settings.upsert(self.connection, 3, mode="economy")
        group = await chat_settings.get(self.connection, 3)
        self.assertEqual(group["mode"], "economy")
        self.assertEqual(group["sticker_cooldown"], 30)  # 未给出的列取表默认值


class UsageRepoTests(DbTestCase):
    async def test_summary_aggregates_day_and_chat(self) -> None:
        for chat_id, tokens in ((1, 10), (1, 20), (2, 5)):
            await usage.record(
                self.connection,
                chat_id=chat_id,
                user_id=42,
                day="2026-10-06",
                model="deepseek-flash",
                input_tokens=tokens,
                cached_tokens=tokens // 2,
                output_tokens=tokens,
            )
        summary = await usage.summary_for_day(self.connection, "2026-10-06")
        self.assertEqual(summary["calls"], 3)
        self.assertEqual(summary["input_tokens"], 35)
        one_chat = await usage.summary_for_day(self.connection, "2026-10-06", chat_id=1)
        self.assertEqual(one_chat["calls"], 2)
        self.assertEqual(one_chat["cached_tokens"], 15)



class MigrationAtomicityTests(unittest.IsolatedAsyncioTestCase):
    """迁移块必须原子；兼容范围仅限已确认的 usage.purpose 历史半升级。"""

    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def _connect(self, name: str = "mig.db") -> aiosqlite.Connection:
        return await aiosqlite.connect(self.tmp / name)

    @staticmethod
    async def _user_version(connection: aiosqlite.Connection) -> int:
        cursor = await connection.execute("PRAGMA user_version")
        row = await cursor.fetchone()
        await cursor.close()
        return int(row[0])

    @staticmethod
    async def _table_names(connection: aiosqlite.Connection) -> set[str]:
        cursor = await connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        rows = await cursor.fetchall()
        await cursor.close()
        return {str(row[0]) for row in rows}

    @staticmethod
    async def _column_names(connection: aiosqlite.Connection, table: str) -> list[str]:
        cursor = await connection.execute(f"PRAGMA table_info({table})")
        rows = await cursor.fetchall()
        await cursor.close()
        return [str(row[1]) for row in rows]

    async def test_failed_block_leaves_no_partial_state(self) -> None:
        connection = await self._connect()
        try:
            batches = [["CREATE TABLE alpha (id INTEGER)", "INSERT INTO missing_table (x) VALUES (1)"]]
            with self.assertRaises(sqlite3.OperationalError):
                await apply_migrations(connection, batches)
            self.assertEqual(await self._user_version(connection), 0)
            self.assertNotIn("alpha", await self._table_names(connection))
            # 失败后没有悬挂事务：同一个连接可以继续正常迁移
            self.assertEqual(await apply_migrations(connection, [["CREATE TABLE gamma (id INTEGER)"]]), 1)
            self.assertIn("gamma", await self._table_names(connection))
        finally:
            await connection.close()

    async def test_successful_blocks_advance_version_atomically(self) -> None:
        connection = await self._connect()
        try:
            batches = [["CREATE TABLE alpha (id INTEGER)"], ["CREATE TABLE beta (id INTEGER)"]]
            self.assertEqual(await apply_migrations(connection, batches), 2)
            self.assertEqual(await self._user_version(connection), 2)
            names = await self._table_names(connection)
            self.assertIn("alpha", names)
            self.assertIn("beta", names)
        finally:
            await connection.close()

    async def test_later_block_failure_keeps_earlier_version(self) -> None:
        connection = await self._connect()
        try:
            batches = [
                ["CREATE TABLE alpha (id INTEGER)"],
                ["CREATE TABLE beta (id INTEGER)", "INSERT INTO missing_table (x) VALUES (1)"],
            ]
            with self.assertRaises(sqlite3.OperationalError):
                await apply_migrations(connection, batches)
            self.assertEqual(await self._user_version(connection), 1)
            names = await self._table_names(connection)
            self.assertIn("alpha", names)
            self.assertNotIn("beta", names)
        finally:
            await connection.close()

    async def test_recovers_from_legacy_half_upgraded_database(self) -> None:
        batches = load_migrations()
        # 兼容目标必须仍然就是 schema.sql 里那条已确认的非幂等语句
        self.assertTrue(batches[2][0].startswith("ALTER TABLE usage ADD COLUMN purpose"))
        connection = await self._connect("legacy.db")
        try:
            for block in batches[:2]:
                for statement in block:
                    await connection.execute(statement)
            await connection.execute(batches[2][0])  # 结构已生效，随后中断，user_version 停在 2
            await connection.execute("PRAGMA user_version=2")
            await connection.commit()
            self.assertEqual((await self._column_names(connection, "usage")).count("purpose"), 1)
            self.assertNotIn("summaries", await self._table_names(connection))
            # 旧实现：这里会抛 duplicate column name: purpose，永远无法启动
            self.assertEqual(await apply_migrations(connection), 3)
            self.assertEqual(await self._user_version(connection), 3)
            self.assertEqual((await self._column_names(connection, "usage")).count("purpose"), 1)
            names = await self._table_names(connection)
            self.assertIn("summaries", names)
            self.assertIn("notes", names)
            # 恢复后重跑仍幂等，且不会重复加列
            self.assertEqual(await apply_migrations(connection), 3)
            self.assertEqual((await self._column_names(connection, "usage")).count("purpose"), 1)
        finally:
            await connection.close()

    async def test_other_duplicate_add_column_still_raises(self) -> None:
        connection = await self._connect("limited.db")
        try:
            batches = [["CREATE TABLE stickers (id INTEGER)"], ["ALTER TABLE stickers ADD COLUMN mood REAL"]]
            self.assertEqual(await apply_migrations(connection, batches), 2)
            await connection.execute("PRAGMA user_version=1")  # 同类的"结构已生效、版本未推进"
            await connection.commit()
            with self.assertRaises(sqlite3.OperationalError) as caught:
                await apply_migrations(connection, batches)
            self.assertIn("duplicate column name: mood", str(caught.exception))
            self.assertEqual(await self._user_version(connection), 1)
        finally:
            await connection.close()

    async def test_duplicate_create_table_still_raises(self) -> None:
        connection = await self._connect("ddl.db")
        try:
            batches = [["CREATE TABLE gadget (id INTEGER)", "CREATE TABLE gadget (id INTEGER)"]]
            with self.assertRaises(sqlite3.OperationalError) as caught:
                await apply_migrations(connection, batches)
            self.assertIn("already exists", str(caught.exception))
            self.assertEqual(await self._user_version(connection), 0)
            self.assertNotIn("gadget", await self._table_names(connection))
        finally:
            await connection.close()

    async def test_real_migrations_end_state(self) -> None:
        connection = await self._connect("end.db")
        try:
            self.assertEqual(await apply_migrations(connection), 3)
            self.assertEqual(await self._user_version(connection), 3)
            names = await self._table_names(connection)
            for table in ("updates", "messages", "chat_settings", "usage", "stickers", "summaries", "notes"):
                self.assertIn(table, names)
            self.assertIn("summaries_fts", names)
            self.assertIn("notes_fts", names)
            self.assertEqual((await self._column_names(connection, "usage")).count("purpose"), 1)
        finally:
            await connection.close()

if __name__ == "__main__":
    unittest.main()