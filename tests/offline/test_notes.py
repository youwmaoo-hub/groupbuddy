"""长期笔记（notes）：解析、清洗、回显与 FTS 同步（docs/memory.md §6、F3.4）。"""

from __future__ import annotations

import unittest

from app.ops import notes as notes_ops
from app.ops.notes import MAX_CHARS, MAX_NAME_CHARS, Request
from app.ops.text import single_line
from app.session.retrieval import term_tokens
from app.storage.repo import notes as notes_repo
from app.storage.repo_models import NoteRow
from tests.offline.helpers import DbTestCase

UPDATED_AT = 1_700_000_000


def make_row(**overrides: object) -> NoteRow:
    values: dict[str, object] = {
        "id": 1,
        "chat_id": -100,
        "name": "部署",
        "text": "生产用 systemd 托管",
        "tokens": "生产 产用 systemd 托管",
        "version": 1,
        "created_at": UPDATED_AT,
        "updated_at": UPDATED_AT,
    }
    values.update(overrides)
    return NoteRow(**values)  # type: ignore[arg-type]


class SingleLineTests(unittest.TestCase):
    def test_control_characters_collapse_to_one_line(self) -> None:
        self.assertEqual(single_line("甲\n乙\t丙"), "甲 乙 丙")
        self.assertEqual(single_line("  a   b  "), "a b")
        self.assertEqual(single_line("\x00\x1f\x7f\x85"), "")
        self.assertEqual(single_line("正常"), "正常")


class ParseTests(unittest.TestCase):
    def test_list_forms(self) -> None:
        self.assertEqual(notes_ops.parse((), ""), Request("list"))
        self.assertEqual(notes_ops.parse(("list",), "list"), Request("list"))
        self.assertEqual(notes_ops.parse(("列表",), "列表"), Request("list"))

    def test_list_rejects_extra_arguments(self) -> None:
        self.assertEqual(notes_ops.parse(("list", "x"), "list x"), notes_ops.USAGE_TEXT)

    def test_name_only_means_show(self) -> None:
        self.assertEqual(notes_ops.parse(("部署",), "部署"), Request("show", name="部署"))

    def test_save_keeps_the_rest_of_the_line(self) -> None:
        request = notes_ops.parse(("部署", "生产", "用", "systemd"), "部署 生产 用 systemd")
        self.assertEqual(request, Request("save", name="部署", text="生产 用 systemd"))

    def test_save_flattens_multiline_text(self) -> None:
        request = notes_ops.parse(("部署", "甲"), "部署 甲\n乙")
        self.assertEqual(request, Request("save", name="部署", text="甲 乙"))

    def test_delete_aliases(self) -> None:
        for word in ("del", "delete", "删除", "忘掉"):
            with self.subTest(word=word):
                self.assertEqual(
                    notes_ops.parse((word, "部署"), f"{word} 部署"), Request("delete", name="部署")
                )

    def test_delete_needs_exactly_one_name(self) -> None:
        self.assertEqual(notes_ops.parse(("del",), "del"), notes_ops.USAGE_TEXT)
        self.assertEqual(notes_ops.parse(("del", "a", "b"), "del a b"), notes_ops.USAGE_TEXT)

    def test_reserved_words_are_not_names(self) -> None:
        # 保留字优先当子命令：既不能当笔记名，也不能被删除
        self.assertEqual(notes_ops.parse(("list", "内容"), "list 内容"), notes_ops.USAGE_TEXT)
        self.assertEqual(notes_ops.parse(("del", "list"), "del list"), notes_ops.USAGE_TEXT)

    def test_name_and_text_limits(self) -> None:
        self.assertEqual(
            notes_ops.parse(("好" * (MAX_NAME_CHARS + 1),), "好" * (MAX_NAME_CHARS + 1)),
            f"笔记名过长：上限 {MAX_NAME_CHARS} 字符（当前 {MAX_NAME_CHARS + 1}）",
        )
        self.assertEqual(
            notes_ops.parse(("部署", "好" * (MAX_CHARS + 1)), "部署 " + "好" * (MAX_CHARS + 1)),
            f"笔记内容过长：上限 {MAX_CHARS} 字符（当前 {MAX_CHARS + 1}）",
        )
        self.assertEqual(
            notes_ops.parse(("部署", "好" * MAX_CHARS), "部署 " + "好" * MAX_CHARS),
            Request("save", name="部署", text="好" * MAX_CHARS),
        )


class RenderTests(unittest.TestCase):
    def test_empty_list_shows_usage(self) -> None:
        text = notes_ops.render_list([])
        self.assertIn("本群还没有笔记", text)
        self.assertIn("/note <名称> <内容>", text)

    def test_list_shows_metadata_but_not_the_body(self) -> None:
        text = notes_ops.render_list([make_row()])
        self.assertIn("本群笔记（1 条）", text)
        self.assertIn(f"部署（v1，{len('生产用 systemd 托管')} 字，{notes_ops.stamp(UPDATED_AT)}）", text)
        self.assertNotIn("systemd", text)  # 正文要靠 /note <名称> 查看

    def test_show_returns_the_body(self) -> None:
        text = notes_ops.render_show(make_row(version=2))
        self.assertIn("笔记「部署」（v2", text)
        self.assertIn("生产用 systemd 托管", text)

    def test_saved_says_created_or_updated(self) -> None:
        self.assertIn("已记住笔记「部署」（v1", notes_ops.render_saved(make_row()))
        self.assertIn("已更新笔记「部署」（v2", notes_ops.render_saved(make_row(version=2)))

    def test_delete_and_missing_texts(self) -> None:
        self.assertEqual(notes_ops.render_deleted("部署"), "已删除笔记「部署」。")
        self.assertEqual(notes_ops.missing("部署"), "没有这条笔记：部署")

    def test_stamp_tolerates_bad_values(self) -> None:
        self.assertEqual(notes_ops.stamp(10**18), "时间未知")


class NoteRepoTests(DbTestCase):
    async def test_upsert_list_and_per_chat_isolation(self) -> None:
        await notes_repo.upsert(
            self.connection, chat_id=-100, name="部署", text="生产用 systemd", tokens=term_tokens("生产用 systemd")
        )
        await notes_repo.upsert(
            self.connection, chat_id=-200, name="别的", text="另一个群", tokens=term_tokens("另一个群")
        )
        rows = await notes_repo.list_for_chat(self.connection, chat_id=-100)
        self.assertEqual([row.name for row in rows], ["部署"])
        self.assertEqual(rows[0].version, 1)
        self.assertEqual((await notes_repo.list_for_chat(self.connection, chat_id=-200))[0].name, "别的")

    async def test_same_name_overwrites_and_replaces_fts_tokens(self) -> None:
        await notes_repo.upsert(self.connection, chat_id=-100, name="部署", text="用 systemd", tokens=term_tokens("用 systemd"))
        await notes_repo.upsert(self.connection, chat_id=-100, name="部署", text="改用 docker", tokens=term_tokens("改用 docker"))

        rows = await notes_repo.list_for_chat(self.connection, chat_id=-100)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].version, 2)
        self.assertEqual(rows[0].text, "改用 docker")
        self.assertEqual(await notes_repo.search(self.connection, chat_id=-100, match_query="systemd"), [])
        hits = await notes_repo.search(self.connection, chat_id=-100, match_query="docker")
        self.assertEqual([hit.source for hit in hits], ["笔记:部署"])

    async def test_delete_removes_the_row_and_the_fts_entry(self) -> None:
        await notes_repo.upsert(self.connection, chat_id=-100, name="部署", text="用 systemd", tokens=term_tokens("用 systemd"))
        self.assertTrue(await notes_repo.delete(self.connection, chat_id=-100, name="部署"))
        self.assertIsNone(await notes_repo.get(self.connection, chat_id=-100, name="部署"))
        self.assertEqual(await notes_repo.search(self.connection, chat_id=-100, match_query="systemd"), [])

    async def test_delete_missing_returns_false(self) -> None:
        self.assertFalse(await notes_repo.delete(self.connection, chat_id=-100, name="没有"))

    async def test_list_is_ordered_by_update_time(self) -> None:
        await notes_repo.upsert(self.connection, chat_id=-100, name="old", text="first", tokens="first", updated_at=1_000)
        await notes_repo.upsert(self.connection, chat_id=-100, name="new", text="second", tokens="second", updated_at=2_000)
        rows = await notes_repo.list_for_chat(self.connection, chat_id=-100)
        self.assertEqual([row.name for row in rows], ["new", "old"])


if __name__ == "__main__":
    unittest.main()
