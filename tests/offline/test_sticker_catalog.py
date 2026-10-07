"""贴纸 catalog / manifest 与批量导入的离线测试（阶段 8）。

覆盖：manifest 读取与校验（fail-closed）、素材名路径穿越防护、
按 emoji 匹配贴纸包、以及 `register_entries` 的幂等 / dry-run / 拒绝未绑定条目。
不联网：`scripts/import_sticker_set.py` 的 HTTP 调用不在单测范围内（手工运维步骤）。
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.ops.sticker_catalog import (
    CatalogEntry,
    CatalogError,
    load_manifest,
    match_sticker_set,
    register_entries,
    resolve_asset,
    validate_asset_name,
)
from app.storage import db
from app.storage.repo.stickers import decode_tags


def _raw(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "key": "happy",
        "emotion": "开心",
        "emoji": "😄",
        "tags": ["开心", "笑"],
        "valence": 0.8,
        "arousal": 0.6,
    }
    data.update(overrides)
    return data


def _entry(**overrides: object) -> CatalogEntry:
    data = {
        "key": "happy",
        "emotion": "开心",
        "emoji": "😄",
        "tags": ("开心",),
        "valence": 0.8,
        "arousal": 0.6,
        "file_id": "F1",
        "file_unique_id": "U1",
    }
    data.update(overrides)
    return CatalogEntry(**data)  # type: ignore[arg-type]


class CatalogTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, name: str, data: object) -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def make_db(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.tmp / "bot.db")
        self.addCleanup(connection.close)
        for batch in db.load_migrations():
            for statement in batch:
                connection.execute(statement)
        connection.commit()
        return connection


class ManifestTests(CatalogTestCase):
    def test_object_and_array_forms_are_both_accepted(self) -> None:
        wrapped = load_manifest(self.write("a.json", {"version": 1, "stickers": [_raw()]}))
        plain = load_manifest(self.write("b.json", [_raw(key="laugh", emotion="笑", emoji="😆")]))
        self.assertEqual([entry.key for entry in wrapped], ["happy"])
        self.assertEqual([entry.emotion for entry in plain], ["笑"])

    def test_directory_merges_json_files_in_name_order(self) -> None:
        self.write("02-second.json", [_raw(key="laugh", emotion="笑", emoji="😆")])
        self.write("01-first.json", [_raw()])
        entries = load_manifest(self.tmp)
        self.assertEqual([entry.key for entry in entries], ["happy", "laugh"])

    def test_duplicate_key_across_files_is_rejected(self) -> None:
        self.write("01.json", [_raw()])
        self.write("02.json", [_raw(emotion="开心2")])
        with self.assertRaises(CatalogError):
            load_manifest(self.tmp)

    def test_empty_directory_and_missing_file_are_rejected(self) -> None:
        with self.assertRaises(CatalogError):
            load_manifest(self.tmp)
        with self.assertRaises(CatalogError):
            load_manifest(self.tmp / "nope.json")

    def test_invalid_json_and_plain_object_are_rejected(self) -> None:
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaises(CatalogError):
            load_manifest(bad)
        with self.assertRaises(CatalogError):
            load_manifest(self.write("object.json", {"stickers": {"key": "happy"}}))


class EntryValidationTests(CatalogTestCase):
    def test_missing_required_field_is_rejected(self) -> None:
        with self.assertRaises(CatalogError) as caught:
            load_manifest(self.write("a.json", [_raw(emoji="")]))
        self.assertIn("缺少字段", str(caught.exception))

    def test_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(CatalogError) as caught:
            load_manifest(self.write("a.json", [_raw(valencee=1.0)]))
        self.assertIn("未知字段", str(caught.exception))

    def test_tags_must_be_a_non_empty_string_array(self) -> None:
        for broken in ([], "开心", ["开心", "  "], None):
            with self.subTest(tags=broken), self.assertRaises(CatalogError):
                load_manifest(self.write("a.json", [_raw(tags=broken)]))

    def test_valence_and_arousal_must_be_numbers_in_range(self) -> None:
        for broken in (1.5, -1.2, "甜"):
            with self.subTest(valence=broken), self.assertRaises(CatalogError):
                load_manifest(self.write("a.json", [_raw(valence=broken)]))

    def test_sha256_must_be_hexadecimal_when_given(self) -> None:
        with self.assertRaises(CatalogError):
            load_manifest(self.write("a.json", [_raw(sha256="zz")]))
        entry = load_manifest(self.write("b.json", [_raw(sha256="A" * 64)]))[0]
        self.assertEqual(entry.sha256, "a" * 64)

    def test_asset_must_be_a_bare_file_name(self) -> None:
        for broken in ("", ".", "..", "../x.webp", "a/b.webp", "C:\\x.webp", "..\\x.webp", "x\x00.webp"):
            with self.subTest(asset=broken), self.assertRaises(CatalogError):
                validate_asset_name(broken)
        self.assertEqual(validate_asset_name(" happy.webm "), "happy.webm")
        # 完全没有 asset 字段也是合法的（只有 catalog 槽位、素材后补）
        self.assertEqual(load_manifest(self.write("a.json", [_raw()]))[0].asset, "")

    def test_resolve_asset_stays_inside_the_asset_directory(self) -> None:
        assets = self.tmp / "assets"
        assets.mkdir()
        self.assertEqual(resolve_asset(assets, "happy.webm"), (assets / "happy.webm").resolve())
        for broken in ("../outside.webm", "sub/inner.webm"):
            with self.subTest(asset=broken), self.assertRaises(CatalogError):
                resolve_asset(assets, broken)


class MatchTests(CatalogTestCase):
    def test_matches_by_emoji_and_backfills_file_id(self) -> None:
        catalog = load_manifest(self.write("a.json", [_raw()]))
        stickers = [
            {"emoji": "😆", "file_id": "F2", "file_unique_id": "U2"},
            {"emoji": "😄", "file_id": "F1", "file_unique_id": "U1"},
        ]
        result = match_sticker_set(stickers, catalog)
        self.assertEqual(len(result.matched), 1)
        entry, sticker = result.matched[0]
        self.assertEqual((entry.file_id, entry.file_unique_id), ("F1", "U1"))
        self.assertEqual(sticker["file_unique_id"], "U1")
        self.assertTrue(entry.bound)
        self.assertEqual(len(result.unused_in_set), 1)

    def test_reports_missing_slots_and_unused_stickers(self) -> None:
        catalog = load_manifest(
            self.write("a.json", [_raw(), _raw(key="laugh", emotion="笑", emoji="😆")])
        )
        result = match_sticker_set([{"emoji": "😄", "file_id": "F1", "file_unique_id": "U1"}], catalog)
        self.assertEqual([entry.key for entry, _ in result.matched], ["happy"])
        self.assertEqual([entry.key for entry in result.missing_in_set], ["laugh"])

    def test_two_slots_with_the_same_emoji_need_two_stickers(self) -> None:
        catalog = load_manifest(
            self.write("a.json", [_raw(), _raw(key="laugh", emotion="笑", emoji="😄")])
        )
        one = match_sticker_set([{"emoji": "😄", "file_id": "F1", "file_unique_id": "U1"}], catalog)
        self.assertEqual([entry.key for entry in one.missing_in_set], ["laugh"])
        two = match_sticker_set(
            [
                {"emoji": "😄", "file_id": "F1", "file_unique_id": "U1"},
                {"emoji": "😄", "file_id": "F2", "file_unique_id": "U2"},
            ],
            catalog,
        )
        self.assertEqual({entry.file_unique_id for entry, _ in two.matched}, {"U1", "U2"})


class RegisterTests(CatalogTestCase):
    def test_insert_then_update_is_idempotent(self) -> None:
        connection = self.make_db()
        first = register_entries(connection, chat_id=1, entries=[_entry()], now=100)
        self.assertEqual((first.inserted, first.updated), (1, 0))
        second = register_entries(
            connection,
            chat_id=1,
            entries=[_entry(file_id="F9", valence=0.5, tags=("摸鱼",))],
            now=200,
        )
        self.assertEqual((second.inserted, second.updated), (0, 1))
        self.assertEqual(first.ids, second.ids)
        rows = connection.execute(
            "SELECT file_id, valence, arousal, tags, created_at FROM stickers WHERE chat_id = 1"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "F9")
        self.assertEqual(rows[0][1], 0.5)
        self.assertEqual(decode_tags(rows[0][3]), ("摸鱼",))
        # 唯一键冲突时 created_at 不被 UPDATE 覆盖，仍是最初写入的时间
        self.assertEqual(rows[0][4], 100)

    def test_dry_run_reports_without_writing(self) -> None:
        connection = self.make_db()
        report = register_entries(connection, chat_id=1, entries=[_entry()], dry_run=True)
        self.assertEqual((report.inserted, report.updated, report.total), (1, 0, 1))
        self.assertTrue(report.dry_run)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM stickers").fetchone()[0], 0)

    def test_chat_id_zero_and_unbound_entries_are_rejected(self) -> None:
        connection = self.make_db()
        with self.assertRaises(CatalogError):
            register_entries(connection, chat_id=0, entries=[_entry()])
        with self.assertRaises(CatalogError) as caught:
            register_entries(connection, chat_id=1, entries=[_entry(file_id="", file_unique_id="")])
        self.assertIn("happy", str(caught.exception))
        self.assertFalse(_entry(file_id="", file_unique_id="").bound)

    def test_same_sticker_in_two_chats_is_allowed(self) -> None:
        connection = self.make_db()
        register_entries(connection, chat_id=1, entries=[_entry()])
        register_entries(connection, chat_id=2, entries=[_entry()])
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM stickers").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
