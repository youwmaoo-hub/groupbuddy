"""FTS 检索与中文分词：只查摘要与笔记，按需注入（docs/memory.md §5）。

unicode61 会把整段中文当成一个 token，因此写入与查询两侧都用"中文双字 bigram + 拉丁词"。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

import aiosqlite

from app.storage.repo import notes as notes_repo
from app.storage.repo import summaries as summaries_repo
from app.storage.repo_models import SearchHit

CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
LATIN_WORD = re.compile(r"[a-z0-9_]{2,}")
LATIN_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "you", "are", "not", "but", "can", "how", "what", "why",
    }
)

RECALL_WORDS = (
    "之前", "上次", "刚才", "那个", "继续", "接着", "前面", "早先", "我们说过", "刚说", "前面说", "上回",
)
MAX_ITEMS = 3
MAX_CHARS = 800
MIN_QUERY_TERMS = 6
MAX_QUERY_TERMS = 40


def term_tokens(text: str) -> str:
    """中文双字 bigram + 拉丁词，去重后空格连接；写入与查询共用同一实现。"""
    lowered = (text or "").casefold()
    terms: list[str] = []
    for run in CJK_RUN.findall(lowered):
        if len(run) < 2:
            continue
        terms.extend(run[index : index + 2] for index in range(len(run) - 1))
    terms.extend(word for word in LATIN_WORD.findall(lowered) if word not in LATIN_STOPWORDS)

    unique: list[str] = []
    for term in terms:
        if term and term not in unique:
            unique.append(term)
    return " ".join(unique)


def build_match_query(text: str) -> str | None:
    """把当前消息变成 FTS 查询（OR 连接）；有效词太少则不检索。"""
    terms = term_tokens(text).split()
    if len(terms) < MIN_QUERY_TERMS:
        return None
    return " OR ".join(terms[:MAX_QUERY_TERMS])


def retrieval_wanted(texts: Iterable[str], *, trimmed: int = 0, has_unsummarized: bool = False) -> bool:
    """只在回溯/指代信号，或窗口被裁剪且仍有未摘要历史时才检索。"""
    joined = " ".join(texts).casefold()
    if any(word in joined for word in RECALL_WORDS):
        return True
    return trimmed > 0 and has_unsummarized


def select_snippets(
    hits: Sequence[SearchHit],
    *,
    max_items: int = MAX_ITEMS,
    max_chars: int = MAX_CHARS,
) -> list[str]:
    """去重、按 bm25 顺序累计到字符上限，每条带来源标记。"""
    picked: list[str] = []
    seen: set[str] = set()
    total = 0
    for hit in hits:
        if len(picked) >= max_items or total >= max_chars:
            break
        text = " ".join(str(hit.text).split())
        if not text or text in seen:
            continue
        line = f"[{hit.source}] {text}"
        budget = max_chars - total
        if len(line) > budget:
            line = line[:budget]
        if not line.strip():
            continue
        seen.add(text)
        picked.append(line)
        total += len(line)
    return picked


async def search_memory(
    connection: aiosqlite.Connection,
    *,
    chat_id: int,
    text: str,
    trimmed: int = 0,
    has_unsummarized: bool = False,
    limit: int = MAX_ITEMS,
) -> list[str]:
    """检索摘要与笔记；未命中或不需要检索时返回空列表（不注入、不报错）。"""
    if not retrieval_wanted([text], trimmed=trimmed, has_unsummarized=has_unsummarized):
        return []
    query = build_match_query(text)
    if query is None:
        return []
    hits = await summaries_repo.search(connection, chat_id=chat_id, match_query=query, limit=limit)
    if len(hits) < limit:
        hits = [
            *hits,
            *await notes_repo.search(connection, chat_id=chat_id, match_query=query, limit=limit - len(hits)),
        ]
    return select_snippets(hits, max_items=limit)
