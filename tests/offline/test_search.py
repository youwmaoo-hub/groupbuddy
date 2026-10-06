"""search_web：只上行查询词，结果短且结构化（F4.3）。"""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.tools.builtin.search_web import (
    FakeSearchBackend,
    SearchArgs,
    SearchResult,
    SearchWebTool,
)
from app.tools.registry import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(chat_id=7, user_id=42, group={"allow_search": 1})


class RecordingBackend:
    """记录上行参数；证明只有 query 与 top_k 会被传出去。"""

    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, *, top_k: int) -> list[SearchResult]:
        self.calls.append((query, top_k))
        return self.results


class SearchWebTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_query_and_top_k_go_upstream(self) -> None:
        backend = RecordingBackend([SearchResult(title="t", url="https://x/1", snippet="s")])
        payload = await SearchWebTool(backend).run(SearchArgs(query="天气"), _ctx())
        self.assertEqual(backend.calls, [("天气", 3)])
        self.assertEqual(payload["truncated"], False)
        self.assertEqual(payload["results"][0]["url"], "https://x/1")

    async def test_results_capped_at_five(self) -> None:
        many = [SearchResult(title=f"t{index}", url=f"https://x/{index}", snippet="s") for index in range(7)]
        payload = await SearchWebTool(RecordingBackend(many)).run(SearchArgs(query="q", top_k=5), _ctx())
        self.assertEqual(len(payload["results"]), 5)
        self.assertTrue(payload["truncated"])

    async def test_snippet_and_title_are_clipped(self) -> None:
        long = SearchResult(title="t" * 500, url="https://x", snippet="字" * 900)
        payload = await SearchWebTool(RecordingBackend([long])).run(SearchArgs(query="q"), _ctx())
        item = payload["results"][0]
        self.assertEqual(len(item["snippet"]), 500)
        self.assertEqual(len(item["title"]), 120)

    async def test_fake_backend_marks_sample_data(self) -> None:
        payload = await SearchWebTool(FakeSearchBackend()).run(SearchArgs(query="q"), _ctx())
        self.assertIn("示例", payload["results"][0]["title"])

    def test_top_k_bounds(self) -> None:
        for value in (0, 6):
            with self.subTest(top_k=value):
                with self.assertRaises(ValidationError):
                    SearchArgs(query="q", top_k=value)

    def test_extra_arguments_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SearchArgs(query="q", engine="google")


if __name__ == "__main__":
    unittest.main()
