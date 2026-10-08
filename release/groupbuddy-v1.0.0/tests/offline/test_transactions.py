"""写入事务边界（技术债 T9）：repo 不再自己 commit，多语句写入整体成功或整体回滚。

契约见 `docs/database.md` §6；实现见 `app/storage/tx.py`。
"""

from __future__ import annotations

from unittest import mock

import aiosqlite

from app.session.retrieval import build_match_query, term_tokens
from app.storage.repo import (
    chat_settings,
    messages,
    notes,
    stickers,
    summaries,
    tool_failures,
    updates,
    usage,
)
from app.storage.tx import transaction
from tests.offline.helpers import DbTestCase

EXISTING = "部署用 systemd"
REPLACEMENT = "部署改用 docker"
BAD_SQL = "INSERT INTO missing_table (a) VALUES (?)"
BAD_DELETE_SQL = "DELETE FROM missing_table WHERE id = ?"


async def _scalar(connection: aiosqlite.Connection, sql: str, params: tuple[object, ...] = ()) -> object:
    cursor = await connection.execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    return None if row is None else row[0]


class TransactionTests(DbTestCase):
    """`transaction()` 自身的提交/回滚语义（SAVEPOINT 嵌套）。"""

    async def test_outermost_savepoint_commits_for_other_connections(self) -> None:
        async with transaction(self.connection):
            await self.connection.execute(
                "INSERT INTO updates (update_id, chat_id, received_at) VALUES (1, -100, 1)"
            )
        other = await aiosqlite.connect(self.settings.db_path)
        try:
            self.assertEqual(await _scalar(other, "SELECT COUNT(*) FROM updates"), 1)
        finally:
            await other.close()

    async def test_failure_rolls_back_and_a_later_write_does_not_commit_leftovers(self) -> None:
        with self.assertRaises(RuntimeError):
            async with transaction(self.connection):
                await self.connection.execute(
                    "INSERT INTO updates (update_id, chat_id, received_at) VALUES (2, -100, 1)"
                )
                raise RuntimeError("模拟写入中途失败")
        # 另一个任务的正常写入（原先的 commit 会把半成品顺带提交）
        await messages.insert(self.connection, chat_id=1, message_id=1, user_id=42, role="user", text="hi")
        self.assertEqual(await _scalar(self.connection, "SELECT COUNT(*) FROM updates"), 0)
        self.assertEqual(await _scalar(self.connection, "SELECT COUNT(*) FROM messages"), 1)

    async def test_inner_failure_rolls_back_only_inner_segment(self) -> None:
        async with transaction(self.connection):
            await self.connection.execute(
                "INSERT INTO updates (update_id, chat_id, received_at) VALUES (10, -100, 1)"
            )
            with self.assertRaises(RuntimeError):
                async with transaction(self.connection):
                    await self.connection.execute(
                        "INSERT INTO updates (update_id, chat_id, received_at) VALUES (11, -100, 1)"
                    )
                    raise RuntimeError("内层失败")
            await self.connection.execute(
                "INSERT INTO updates (update_id, chat_id, received_at) VALUES (12, -100, 1)"
            )
        self.assertEqual(
            await _scalar(self.connection, "SELECT GROUP_CONCAT(update_id) FROM updates"), "10,12"
        )

    async def test_nested_transactions_commit_together(self) -> None:
        async with transaction(self.connection):
            await self.connection.execute(
                "INSERT INTO updates (update_id, chat_id, received_at) VALUES (20, -100, 1)"
            )
            async with transaction(self.connection):
                await self.connection.execute(
                    "INSERT INTO updates (update_id, chat_id, received_at) VALUES (21, -100, 1)"
                )
        other = await aiosqlite.connect(self.settings.db_path)
        try:
            self.assertEqual(await _scalar(other, "SELECT COUNT(*) FROM updates"), 2)
        finally:
            await other.close()


class RepoTransactionTests(DbTestCase):
    """repo 层的实际写入路径：失败必须整体回滚，成功无需自己 commit。"""

    async def test_notes_upsert_rolls_back_when_fts_sync_fails(self) -> None:
        await notes.upsert(
            self.connection, chat_id=1, name="部署", text=EXISTING, tokens=term_tokens(EXISTING)
        )
        with mock.patch.object(notes, "FTS_INSERT_SQL", BAD_SQL):
            with self.assertRaises(aiosqlite.OperationalError):
                await notes.upsert(
                    self.connection,
                    chat_id=1,
                    name="部署",
                    text=REPLACEMENT,
                    tokens=term_tokens(REPLACEMENT),
                )
        row = await notes.get(self.connection, chat_id=1, name="部署")
        assert row is not None
        self.assertEqual(row.text, EXISTING)
        self.assertEqual(row.version, 1)
        hits = await notes.search(self.connection, chat_id=1, match_query=build_match_query("部署") or "部署")
        self.assertEqual([hit.text for hit in hits], [EXISTING])
        # 失败事务的残留不得被后续别的写入顺带提交
        await messages.insert(self.connection, chat_id=1, message_id=1, user_id=42, role="user", text="hi")
        row = await notes.get(self.connection, chat_id=1, name="部署")
        assert row is not None
        self.assertEqual((row.text, row.version), (EXISTING, 1))

    async def test_notes_delete_rolls_back_when_row_delete_fails(self) -> None:
        await notes.upsert(
            self.connection, chat_id=1, name="部署", text=EXISTING, tokens=term_tokens(EXISTING)
        )
        with mock.patch.object(notes, "DELETE_SQL", BAD_DELETE_SQL):
            with self.assertRaises(aiosqlite.OperationalError):
                await notes.delete(self.connection, chat_id=1, name="部署")
        row = await notes.get(self.connection, chat_id=1, name="部署")
        self.assertIsNotNone(row)
        hits = await notes.search(self.connection, chat_id=1, match_query=build_match_query("部署") or "部署")
        self.assertEqual([hit.text for hit in hits], [EXISTING])

    async def test_summaries_insert_rolls_back_when_fts_sync_fails(self) -> None:
        with mock.patch.object(summaries, "FTS_INSERT_SQL", BAD_SQL):
            with self.assertRaises(aiosqlite.OperationalError):
                await summaries.insert(
                    self.connection, chat_id=1, text="在改部署脚本", tokens=term_tokens("在改部署脚本")
                )
        self.assertIsNone(await summaries.latest(self.connection, chat_id=1))
        self.assertEqual(await _scalar(self.connection, "SELECT COUNT(*) FROM summaries"), 0)

    async def test_summaries_prune_rolls_back_all_deletions_when_one_fails(self) -> None:
        for index in range(3):
            await summaries.insert(
                self.connection,
                chat_id=1,
                text=f"在改部署脚本 {index}",
                tokens=term_tokens(f"在改部署脚本 {index}"),
                created_at=100 + index,
            )
        with mock.patch.object(summaries, "DELETE_SQL", BAD_DELETE_SQL):
            with self.assertRaises(aiosqlite.OperationalError):
                await summaries.prune(self.connection, chat_id=1, keep=1)
        self.assertEqual(await _scalar(self.connection, "SELECT COUNT(*) FROM summaries"), 3)
        hits = await summaries.search(
            self.connection,
            chat_id=1,
            match_query=build_match_query("部署脚本") or "部署",
            limit=10,
        )
        self.assertEqual(len(hits), 3)

    async def test_repo_write_is_committed_without_explicit_commit(self) -> None:
        await messages.insert(self.connection, chat_id=1, message_id=7, user_id=42, role="user", text="hi")
        other = await aiosqlite.connect(self.settings.db_path)
        try:
            self.assertEqual(await _scalar(other, "SELECT COUNT(*) FROM messages"), 1)
        finally:
            await other.close()

    async def test_repos_never_call_connection_commit(self) -> None:
        async def forbidden(self: aiosqlite.Connection) -> None:
            raise AssertionError("repo 不应自己 commit()（契约见 docs/database.md §6）")

        with mock.patch.object(aiosqlite.Connection, "commit", forbidden):
            await messages.insert(
                self.connection, chat_id=1, message_id=1, user_id=42, role="user", text="hi"
            )
            await messages.clear_chat(self.connection, 1)
            await notes.upsert(
                self.connection, chat_id=1, name="部署", text=EXISTING, tokens=term_tokens(EXISTING)
            )
            await notes.delete(self.connection, chat_id=1, name="部署")
            await summaries.insert(
                self.connection, chat_id=1, text="在改部署脚本", tokens=term_tokens("在改部署脚本")
            )
            await summaries.prune(self.connection, chat_id=1, keep=5)
            await stickers.register(self.connection, chat_id=1, file_id="f1", file_unique_id="u1")
            await stickers.mark_used(self.connection, sticker_id=1, used_at=1)
            await chat_settings.upsert(self.connection, 1, mode="smart")
            await usage.record(self.connection, chat_id=1, user_id=42, day="2026-10-07", model="m")
            await updates.mark_seen(self.connection, 1, 1)
            await updates.purge_old(self.connection, older_than_seconds=0)
            await tool_failures.record(self.connection, tool="calc", chat_id=1, error_code="timeout")
            await tool_failures.purge_old(self.connection, days=0)
