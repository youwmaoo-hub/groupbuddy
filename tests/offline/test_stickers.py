"""贴纸：表结构、repo、匹配与工具（F4.5）。"""

from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from app.storage.repo import stickers
from app.storage.repo.stickers import DbStickerStore
from app.storage.repo_models import StickerRow
from app.tools.builtin.send_sticker import (
    MIN_SCORE,
    SendStickerArgs,
    SendStickerTool,
    match_sticker,
    sticker_score,
)
from app.tools.registry import ToolContext, ToolError
from tests.offline.helpers import DbTestCase, FakeClock

FILE_ID = "CAACAgIAAxkBAAEtestfileid"


def row(
    sticker_id: int,
    valence: float | None,
    arousal: float | None,
    *,
    tags: list[str] | None = None,
    used: int | None = None,
) -> StickerRow:
    return StickerRow(
        id=sticker_id,
        chat_id=1,
        file_id=f"{FILE_ID}{sticker_id}",
        file_unique_id=f"U{sticker_id}",
        valence=valence,
        arousal=arousal,
        tags=None if tags is None else json.dumps(tags, ensure_ascii=False),
        last_used_at=used,
    )


class StickerRepoTests(DbTestCase):
    async def test_table_columns_match_document(self) -> None:
        cursor = await self.connection.execute("PRAGMA table_info(stickers)")
        columns = [item[1] for item in await cursor.fetchall()]
        await cursor.close()
        self.assertEqual(
            columns,
            [
                "id",
                "chat_id",
                "file_id",
                "file_unique_id",
                "valence",
                "arousal",
                "tags",
                "last_used_at",
                "created_at",
            ],
        )

    async def test_register_is_idempotent_per_chat(self) -> None:
        first = await stickers.register(
            self.connection, chat_id=1, file_id="F1", file_unique_id="U1", valence=0.5, arousal=0.5, tags=["开心"]
        )
        second = await stickers.register(
            self.connection, chat_id=1, file_id="F2", file_unique_id="U1", valence=0.1, arousal=0.2, tags=[]
        )
        self.assertEqual(first, second)
        rows = await stickers.candidates(self.connection, chat_id=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].file_id, "F2")
        self.assertEqual(stickers.decode_tags(rows[0].tags), ())

    async def test_candidates_are_isolated_per_chat(self) -> None:
        await stickers.register(self.connection, chat_id=1, file_id="F1", file_unique_id="U1", valence=1.0, arousal=1.0)
        await stickers.register(self.connection, chat_id=2, file_id="F2", file_unique_id="U2", valence=1.0, arousal=1.0)
        self.assertEqual([item.file_id for item in await stickers.candidates(self.connection, chat_id=1)], ["F1"])
        self.assertEqual([item.file_id for item in await stickers.candidates(self.connection, chat_id=2)], ["F2"])

    async def test_mark_used_stores_timestamp(self) -> None:
        sticker_id = await stickers.register(
            self.connection, chat_id=1, file_id="F1", file_unique_id="U1", valence=1.0, arousal=1.0
        )
        await stickers.mark_used(self.connection, sticker_id=sticker_id, used_at=1234)
        rows = await stickers.candidates(self.connection, chat_id=1)
        self.assertEqual(rows[0].last_used_at, 1234)

    async def test_store_adapter(self) -> None:
        store = DbStickerStore(self.connection)
        await stickers.register(self.connection, chat_id=1, file_id="F1", file_unique_id="U1", valence=1.0, arousal=1.0)
        rows = await store.candidates(1)
        self.assertEqual(len(rows), 1)
        await store.mark_used(rows[0].id, 99)
        self.assertEqual((await store.candidates(1))[0].last_used_at, 99)

    def test_decode_tags_tolerates_garbage(self) -> None:
        self.assertEqual(stickers.decode_tags(None), ())
        self.assertEqual(stickers.decode_tags("not json"), ())
        self.assertEqual(stickers.decode_tags('{"a": 1}'), ())
        self.assertEqual(stickers.decode_tags('["开心", "摸鱼"]'), ("开心", "摸鱼"))


class MatcherTests(unittest.TestCase):
    def test_cosine_prefers_same_direction(self) -> None:
        rows = [row(1, 1.0, 0.0), row(2, 0.0, 1.0)]
        matched = match_sticker(rows, valence=1.0, arousal=0.0, tags=())
        self.assertIsNotNone(matched)
        self.assertEqual(matched.id, 1)  # type: ignore[union-attr]

    def test_below_threshold_returns_none(self) -> None:
        rows = [row(1, 1.0, 0.0)]
        self.assertIsNone(match_sticker(rows, valence=0.0, arousal=1.0, tags=()))

    def test_tags_add_light_bonus(self) -> None:
        rows = [row(1, 1.0, 0.0, tags=["开心"]), row(2, 1.0, 0.0)]
        matched = match_sticker(rows, valence=1.0, arousal=0.0, tags=("开心",))
        self.assertEqual(matched.id, 1)  # type: ignore[union-attr]
        bonus = sticker_score(rows[0], 1.0, 0.0, ("开心",)) - sticker_score(rows[1], 1.0, 0.0, ("开心",))
        self.assertAlmostEqual(bonus, 0.1, places=6)

    def test_tie_prefers_older_last_used(self) -> None:
        rows = [row(1, 1.0, 0.0, used=100), row(2, 1.0, 0.0, used=50)]
        matched = match_sticker(rows, valence=1.0, arousal=0.0, tags=())
        self.assertEqual(matched.id, 2)  # type: ignore[union-attr]

    def test_missing_or_zero_vectors_are_skipped(self) -> None:
        self.assertIsNone(match_sticker([row(1, None, None)], valence=1.0, arousal=1.0, tags=()))
        self.assertIsNone(match_sticker([row(1, 1.0, 1.0)], valence=0.0, arousal=0.0, tags=()))
        self.assertGreaterEqual(MIN_SCORE, 0.5)


class _Store:
    def __init__(self, rows: list[StickerRow]) -> None:
        self.rows = rows
        self.used: list[tuple[int, int]] = []

    async def candidates(self, chat_id: int) -> list[StickerRow]:
        return self.rows

    async def mark_used(self, sticker_id: int, used_at: int) -> None:
        self.used.append((sticker_id, used_at))


class _Outbound:
    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[tuple[int, str, str]] = []

    async def send_sticker(self, *, chat_id: int, chat_type: str, file_id: str) -> bool:
        self.calls.append((chat_id, chat_type, file_id))
        return self.ok


class _Mood:
    def __init__(self) -> None:
        self.records: list[tuple[int, float, float]] = []

    def record(self, chat_id: int, valence: float, arousal: float) -> None:
        self.records.append((chat_id, valence, arousal))


def context(**overrides: object) -> ToolContext:
    values: dict[str, object] = {"chat_id": 5, "user_id": 42, "group": {"sticker_cooldown": 30}, "chat_type": "supergroup"}
    values.update(overrides)
    return ToolContext(**values)  # type: ignore[arg-type]


class SendStickerToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.store = _Store([row(7, 1.0, 1.0, used=1)])
        self.outbound = _Outbound()
        self.mood = _Mood()
        self.tool = SendStickerTool(self.store, self.outbound, self.mood, clock=self.clock.monotonic)

    def args(self, **overrides: object) -> SendStickerArgs:
        values: dict[str, object] = {"valence": 1.0, "arousal": 1.0}
        values.update(overrides)
        return SendStickerArgs(**values)  # type: ignore[arg-type]

    async def test_success_returns_internal_id_only(self) -> None:
        payload = await self.tool.run(self.args(), context())
        self.assertEqual(payload, {"sent": True, "sticker_id": 7})
        self.assertNotIn("file_id", payload)
        self.assertNotIn(FILE_ID, str(payload))
        self.assertEqual(self.store.used, [(7, 1000)])
        self.assertEqual(self.mood.records, [(5, 1.0, 1.0)])
        self.assertEqual(self.outbound.calls, [(5, "supergroup", f"{FILE_ID}7")])

    async def test_cooldown_is_a_state_not_an_error(self) -> None:
        await self.tool.run(self.args(), context())
        payload = await self.tool.run(self.args(), context())
        self.assertEqual(payload, {"sent": False, "state": "cooldown", "retry_after": 30})
        self.assertEqual(len(self.outbound.calls), 1)

    async def test_cooldown_expires(self) -> None:
        await self.tool.run(self.args(), context())
        self.clock.advance(30.0)
        payload = await self.tool.run(self.args(), context())
        self.assertEqual(payload["sent"], True)

    async def test_no_match_raises_not_found(self) -> None:
        tool = SendStickerTool(_Store([row(1, -1.0, -1.0)]), self.outbound, self.mood, clock=self.clock.monotonic)
        with self.assertRaises(ToolError) as caught:
            await tool.run(self.args(), context())
        self.assertEqual(caught.exception.code, "not_found")
        self.assertEqual(self.outbound.calls, [])

    async def test_send_failure_raises_internal_error_without_file_id(self) -> None:
        tool = SendStickerTool(self.store, _Outbound(ok=False), self.mood, clock=self.clock.monotonic)
        with self.assertRaises(ToolError) as caught:
            await tool.run(self.args(), context())
        self.assertEqual(caught.exception.code, "internal_error")
        self.assertNotIn(FILE_ID, caught.exception.message)
        self.assertEqual(self.store.used, [])

    async def test_cooldown_falls_back_when_group_value_invalid(self) -> None:
        tool = SendStickerTool(self.store, self.outbound, self.mood, clock=self.clock.monotonic)
        await tool.run(self.args(), context(group={"sticker_cooldown": "bad"}))
        payload = await tool.run(self.args(), context(group={"sticker_cooldown": "bad"}))
        self.assertEqual(payload["state"], "cooldown")
        self.assertEqual(payload["retry_after"], 30)

    def test_argument_bounds(self) -> None:
        for overrides in ({"valence": 1.1}, {"arousal": -1.1}, {"tags": ["x" * 33]}, {"tags": ["t"] * 9}, {"extra": 1}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValidationError):
                    self.args(**overrides)


if __name__ == "__main__":
    unittest.main()
