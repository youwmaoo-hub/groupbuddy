"""存储层：迁移幂等、消息去重与排序、设置默认值、记账。"""

from __future__ import annotations

import unittest

from app.storage.db import apply_migrations, load_migrations
from app.storage.repo import chat_settings, messages, updates, usage
from tests.offline.helpers import DbTestCase


class MigrationTests(DbTestCase):
    async def test_load_migrations(self) -> None:
        versions = load_migrations()
        self.assertEqual(len(versions), 1)
        self.assertEqual(len(versions[0]), 6)

    async def test_apply_is_idempotent(self) -> None:
        self.assertEqual(await apply_migrations(self.connection), 1)


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


if __name__ == "__main__":
    unittest.main()