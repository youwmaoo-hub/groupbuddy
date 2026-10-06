"""工作区文件工具：路径安全、行区间、原子写与 .bak（F4.4、docs/security.md §3/§11）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.tools.builtin.read_file import ReadFileArgs, ReadFileTool
from app.tools.builtin.write_file import WriteFileArgs, WriteFileTool
from app.tools.registry import ToolContext, ToolError
from app.tools.workspace import (
    MAX_FILE_BYTES,
    MAX_READ_LINES,
    atomic_write_text,
    read_text_file,
    resolve_path,
)

ESCAPE_PATHS = (
    "../../.env",
    "..\\..\\x",
    "../1/secret.txt",
    "a/../../x",
    "/etc/passwd",
    "C:\\Windows\\win.ini",
    "\\\\server\\share\\x",
    "sub\\file.txt",
    "file\x00name",
    "",
    "   ",
    ".",
    "..",
)


class _Base:
    def setUp_workspace(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "workspaces"

    def tearDown_workspace(self) -> None:
        self._tmp.cleanup()

    def workspace(self, chat_id: int = 1) -> Path:
        path = self.root / str(chat_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ctx(self, chat_id: int = 1) -> ToolContext:
        return ToolContext(chat_id=chat_id, user_id=42, group={"allow_read": 1, "allow_write": 1})


class PathSafetyTests(_Base, unittest.TestCase):
    def setUp(self) -> None:
        self.setUp_workspace()

    def tearDown(self) -> None:
        self.tearDown_workspace()

    def test_resolves_relative_path_inside_workspace(self) -> None:
        target, relative = resolve_path(self.root, 7, "sub/note.txt")
        self.assertEqual(relative, "sub/note.txt")
        self.assertTrue(target.is_relative_to((self.root / "7").resolve()))

    def test_rejects_escape_paths(self) -> None:
        for raw in ESCAPE_PATHS:
            with self.subTest(path=raw):
                with self.assertRaises(ToolError) as caught:
                    resolve_path(self.root, 1, raw)
                self.assertEqual(caught.exception.code, "path_outside_workspace")
                self.assertNotIn(str(self.root), caught.exception.message)

    def test_chat_directories_are_isolated(self) -> None:
        (self.workspace(1) / "note.txt").write_text("chat1", encoding="utf-8")
        target, relative = resolve_path(self.root, 2, "note.txt")
        self.assertEqual(relative, "note.txt")
        self.assertFalse(target.exists())

    def test_rejects_symlink(self) -> None:
        outside = Path(self._tmp.name) / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        link = self.workspace(1) / "link.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("当前环境不允许创建符号链接")
        with self.assertRaises(ToolError) as caught:
            resolve_path(self.root, 1, "link.txt")
        self.assertEqual(caught.exception.code, "path_outside_workspace")

    def test_rejects_symlinked_directory(self) -> None:
        outside_dir = Path(self._tmp.name) / "outside"
        outside_dir.mkdir()
        (outside_dir / "x.txt").write_text("secret", encoding="utf-8")
        link = self.workspace(1) / "linkdir"
        try:
            link.symlink_to(outside_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("当前环境不允许创建符号链接")
        with self.assertRaises(ToolError):
            resolve_path(self.root, 1, "linkdir/x.txt")

    def test_symlink_branch_rejects_even_without_privilege(self) -> None:
        from unittest import mock

        real = Path.is_symlink

        def fake(self: Path) -> bool:
            return True if self.name == "link.txt" else real(self)

        with mock.patch.object(Path, "is_symlink", fake):
            with self.assertRaises(ToolError) as caught:
                resolve_path(self.root, 1, "link.txt")
        self.assertEqual(caught.exception.code, "path_outside_workspace")

    def test_rejects_hardlink(self) -> None:
        outside = Path(self._tmp.name) / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        link = self.workspace(1) / "hard.txt"
        try:
            os.link(outside, link)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("当前环境不允许创建硬链接")
        _, relative = resolve_path(self.root, 1, "hard.txt")
        self.assertEqual(relative, "hard.txt")
        with self.assertRaises(ToolError) as caught:
            read_text_file(link)
        self.assertEqual(caught.exception.code, "path_outside_workspace")
        with self.assertRaises(ToolError):
            atomic_write_text(link, "overwrite")
        self.assertEqual(outside.read_text(encoding="utf-8"), "secret")


class ReadFileTests(_Base, unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.setUp_workspace()
        self.tool = ReadFileTool(self.root)

    def tearDown(self) -> None:
        self.tearDown_workspace()

    def write(self, text: str, name: str = "note.txt", *, chat_id: int = 1) -> None:
        (self.workspace(chat_id) / name).write_text(text, encoding="utf-8")

    async def read(self, **kwargs: object) -> dict:
        return await self.tool.run(ReadFileArgs(**kwargs), self.ctx())

    async def test_default_read_returns_all_lines(self) -> None:
        self.write("a\nb\nc\n")
        payload = await self.read(path="note.txt")
        self.assertEqual(payload["path"], "note.txt")
        self.assertEqual((payload["start_line"], payload["end_line"]), (1, 3))
        self.assertEqual(payload["text"], "a\nb\nc")
        self.assertEqual(payload["total_lines"], 3)

    async def test_range_is_inclusive_on_both_ends(self) -> None:
        self.write("\n".join(str(index) for index in range(1, 11)))
        payload = await self.read(path="note.txt", start_line=3, end_line=5)
        self.assertEqual((payload["start_line"], payload["end_line"]), (3, 5))
        self.assertEqual(payload["text"], "3\n4\n5")
        self.assertEqual(payload["total_lines"], 10)

    async def test_omitted_end_reads_to_end(self) -> None:
        self.write("\n".join(str(index) for index in range(1, 11)))
        payload = await self.read(path="note.txt", start_line=8)
        self.assertEqual(payload["text"], "8\n9\n10")
        self.assertEqual(payload["end_line"], 10)

    async def test_out_of_range_is_clamped(self) -> None:
        self.write("\n".join(str(index) for index in range(1, 11)))
        payload = await self.read(path="note.txt", start_line=999)
        self.assertEqual((payload["start_line"], payload["end_line"]), (10, 10))
        payload = await self.read(path="note.txt", end_line=999)
        self.assertEqual(payload["end_line"], 10)

    async def test_empty_range_is_rejected(self) -> None:
        self.write("\n".join(str(index) for index in range(1, 11)))
        with self.assertRaises(ToolError) as caught:
            await self.read(path="note.txt", start_line=5, end_line=3)
        self.assertEqual(caught.exception.code, "invalid_arguments")

    async def test_empty_file_is_rejected(self) -> None:
        self.write("")
        with self.assertRaises(ToolError) as caught:
            await self.read(path="note.txt")
        self.assertEqual(caught.exception.code, "invalid_arguments")

    async def test_long_file_is_windowed(self) -> None:
        self.write("\n".join(str(index) for index in range(1, 251)))
        payload = await self.read(path="note.txt")
        self.assertEqual(payload["end_line"], MAX_READ_LINES)
        self.assertEqual(payload["total_lines"], 250)
        self.assertEqual(len(str(payload["text"]).splitlines()), MAX_READ_LINES)

    async def test_query_is_not_supported(self) -> None:
        self.write("hello")
        with self.assertRaises(ToolError) as caught:
            await self.read(path="note.txt", query="hello")
        self.assertEqual(caught.exception.code, "invalid_arguments")

    async def test_missing_file(self) -> None:
        with self.assertRaises(ToolError) as caught:
            await self.read(path="missing.txt")
        self.assertEqual(caught.exception.code, "not_found")

    async def test_directory_is_not_readable(self) -> None:
        (self.workspace() / "sub").mkdir()
        with self.assertRaises(ToolError) as caught:
            await self.read(path="sub")
        self.assertEqual(caught.exception.code, "not_found")

    async def test_oversized_file_is_rejected(self) -> None:
        (self.workspace() / "big.txt").write_bytes(b"a" * (MAX_FILE_BYTES + 1))
        with self.assertRaises(ToolError) as caught:
            await self.read(path="big.txt")
        self.assertEqual(caught.exception.code, "too_large")

    async def test_non_utf8_file_is_rejected(self) -> None:
        (self.workspace() / "bin.dat").write_bytes(b"\xff\xfe\x00\x01")
        with self.assertRaises(ToolError) as caught:
            await self.read(path="bin.dat")
        self.assertEqual(caught.exception.code, "invalid_arguments")

    async def test_output_contains_no_host_path(self) -> None:
        self.write("a")
        payload = await self.read(path="note.txt")
        self.assertNotIn(str(self.root), str(payload))

    def test_extra_argument_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ReadFileArgs(path="note.txt", encoding="utf-16")


class WriteFileTests(_Base, unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.setUp_workspace()
        self.tool = WriteFileTool(self.root)

    def tearDown(self) -> None:
        self.tearDown_workspace()

    async def write(self, content: str, name: str = "note.txt") -> dict:
        return await self.tool.run(WriteFileArgs(path=name, content=content), self.ctx())

    async def test_creates_file_without_backup(self) -> None:
        payload = await self.write("hello")
        self.assertEqual(payload["path"], "note.txt")
        self.assertEqual(payload["bytes"], 5)
        self.assertNotIn("backup", payload)
        self.assertEqual((self.workspace() / "note.txt").read_text(encoding="utf-8"), "hello")

    async def test_overwrite_creates_single_level_backup(self) -> None:
        await self.write("v1")
        payload = await self.write("v2")
        self.assertEqual(payload["backup"], "note.txt.bak")
        self.assertEqual((self.workspace() / "note.txt.bak").read_text(encoding="utf-8"), "v1")
        self.assertEqual((self.workspace() / "note.txt").read_text(encoding="utf-8"), "v2")

    async def test_second_overwrite_updates_the_same_backup(self) -> None:
        await self.write("v1")
        await self.write("v2")
        await self.write("v3")
        self.assertEqual((self.workspace() / "note.txt.bak").read_text(encoding="utf-8"), "v2")
        self.assertEqual((self.workspace() / "note.txt").read_text(encoding="utf-8"), "v3")
        self.assertEqual([item.name for item in self.workspace().glob("*.bak")], ["note.txt.bak"])

    async def test_no_temp_files_left_behind(self) -> None:
        await self.write("v1")
        await self.write("v2")
        leftovers = [item.name for item in self.workspace().iterdir() if item.name.startswith(".write-")]
        self.assertEqual(leftovers, [])

    async def test_utf8_round_trip(self) -> None:
        await self.write("群里的话：你好\n第二行")
        reader = ReadFileTool(self.root)
        payload = await reader.run(ReadFileArgs(path="note.txt"), self.ctx())
        self.assertEqual(payload["text"], "群里的话：你好\n第二行")

    async def test_oversized_content_is_rejected(self) -> None:
        with self.assertRaises(ToolError) as caught:
            await self.write("x" * (MAX_FILE_BYTES + 1))
        self.assertEqual(caught.exception.code, "too_large")

    async def test_missing_parent_directory(self) -> None:
        with self.assertRaises(ToolError) as caught:
            await self.write("hi", "sub/note.txt")
        self.assertEqual(caught.exception.code, "not_found")

    async def test_directory_target_is_rejected(self) -> None:
        (self.workspace() / "sub").mkdir()
        with self.assertRaises(ToolError) as caught:
            await self.write("hi", "sub")
        self.assertEqual(caught.exception.code, "not_found")

    async def test_escape_is_rejected_and_nothing_written(self) -> None:
        with self.assertRaises(ToolError) as caught:
            await self.write("evil", "../evil.txt")
        self.assertEqual(caught.exception.code, "path_outside_workspace")
        self.assertFalse((Path(self._tmp.name) / "evil.txt").exists())

    def test_extra_argument_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            WriteFileArgs(path="note.txt", content="a", mode="append")


if __name__ == "__main__":
    unittest.main()
