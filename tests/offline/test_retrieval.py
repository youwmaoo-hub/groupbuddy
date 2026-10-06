"""检索：分词、触发条件、预算与同群隔离（F3.4）。"""

from __future__ import annotations

import unittest

from app.session.retrieval import (
    MAX_CHARS,
    build_match_query,
    retrieval_wanted,
    search_memory,
    select_snippets,
    term_tokens,
)
from app.storage.repo import notes as notes_repo
from app.storage.repo import summaries as summaries_repo
from app.storage.repo_models import SearchHit
from tests.offline.helpers import DbTestCase


class TokenizerTests(unittest.TestCase):
    def test_chinese_bigrams(self) -> None:
        tokens = term_tokens("部署脚本").split()
        self.assertIn("部署", tokens)
        self.assertIn("署脚", tokens)
        self.assertIn("脚本", tokens)

    def test_latin_words_and_dedup(self) -> None:
        tokens = term_tokens("deploy deploy 脚本").split()
        self.assertEqual(tokens.count("deploy"), 1)
        self.assertIn("脚本", tokens)

    def test_empty_text(self) -> None:
        self.assertEqual(term_tokens(""), "")
        self.assertEqual(term_tokens("123"), "123")


class QueryTests(unittest.TestCase):
    def test_too_few_terms_returns_none(self) -> None:
        self.assertIsNone(build_match_query(""))
        self.assertIsNone(build_match_query("嗯"))

    def test_query_is_or_joined(self) -> None:
        query = build_match_query("之前那个部署脚本怎么搞的")
        self.assertIsNotNone(query)
        assert query is not None
        self.assertIn(" OR ", query)
        self.assertIn("部署", query)


class TriggerTests(unittest.TestCase):
    def test_recall_words_trigger(self) -> None:
        self.assertTrue(retrieval_wanted(["之前那个怎么搞的"]))
        self.assertTrue(retrieval_wanted(["继续刚才的话题"]))

    def test_plain_message_does_not_trigger(self) -> None:
        self.assertFalse(retrieval_wanted(["今天天气不错"]))

    def test_trimmed_with_unsummarized_triggers(self) -> None:
        self.assertTrue(retrieval_wanted(["随便说说"], trimmed=5, has_unsummarized=True))
        self.assertFalse(retrieval_wanted(["随便说说"], trimmed=5, has_unsummarized=False))
        self.assertFalse(retrieval_wanted(["随便说说"], trimmed=0, has_unsummarized=True))


class SnippetTests(unittest.TestCase):
    def test_limits_and_labels(self) -> None:
        hits = [SearchHit(source=f"摘要#{index}", text="内容" * 100) for index in range(5)]
        picked = select_snippets(hits)
        self.assertLessEqual(len(picked), 3)
        self.assertLessEqual(sum(len(item) for item in picked), MAX_CHARS)
        self.assertTrue(picked[0].startswith("[摘要#0]"))

    def test_duplicates_are_dropped(self) -> None:
        hits = [SearchHit(source="摘要#1", text="同一段"), SearchHit(source="摘要#2", text="同一段")]
        self.assertEqual(len(select_snippets(hits)), 1)


class MemorySearchTests(DbTestCase):
    async def test_summaries_search_is_per_chat(self) -> None:
        await summaries_repo.insert(self.connection, chat_id=1, text="我们在改部署脚本", tokens=term_tokens("我们在改部署脚本"))
        await summaries_repo.insert(self.connection, chat_id=2, text="另一个群的部署脚本", tokens=term_tokens("另一个群的部署脚本"))
        hits = await summaries_repo.search(
            self.connection, chat_id=1, match_query=build_match_query("部署脚本") or "部署", limit=3
        )
        self.assertEqual(len(hits), 1)
        self.assertIn("我们在改部署脚本", hits[0].text)

    async def test_notes_search_is_per_chat(self) -> None:
        await notes_repo.upsert(self.connection, chat_id=1, name="部署", text="部署用 systemd", tokens=term_tokens("部署用 systemd"))
        hits = await notes_repo.search(self.connection, chat_id=2, match_query="部署", limit=3)
        self.assertEqual(hits, [])
        hits = await notes_repo.search(self.connection, chat_id=1, match_query="部署", limit=3)
        self.assertEqual(hits[0].source, "笔记:部署")

    async def test_search_memory_returns_nothing_without_signal(self) -> None:
        await summaries_repo.insert(self.connection, chat_id=1, text="我们在改部署脚本", tokens=term_tokens("我们在改部署脚本"))
        self.assertEqual(await search_memory(self.connection, chat_id=1, text="今天天气不错"), [])

    async def test_search_memory_returns_snippets_with_signal(self) -> None:
        await summaries_repo.insert(self.connection, chat_id=1, text="之前讨论过部署脚本", tokens=term_tokens("之前讨论过部署脚本"))
        picked = await search_memory(self.connection, chat_id=1, text="之前那个部署脚本怎么搞的")
        self.assertTrue(picked)
        self.assertTrue(picked[0].startswith("[摘要#"))


if __name__ == "__main__":
    unittest.main()
