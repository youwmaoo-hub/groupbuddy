"""search_web：只把查询词上行，结果短且结构化（docs/tools.md §search_web、F4.3）。

后端未定（docs/requirements.md §4 #1）：本阶段冻结接口，默认不注册（fail-closed），
需要时用假后端离线验证；接真实后端只需实现 SearchBackend。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.tools.registry import ToolContext, ToolSpec

MAX_RESULTS = 5
SNIPPET_LIMIT = 500
TITLE_LIMIT = 120
URL_LIMIT = 300


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchBackend(Protocol):
    """唯一上行面：只有查询词与条数；不带 chat/群设置/文件/环境变量。"""

    async def search(self, query: str, *, top_k: int) -> list[SearchResult]: ...


class FakeSearchBackend:
    """离线/演示用假后端；结果明确标注为示例，不用于生产。"""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.queries: list[str] = []
        self._results = results if results is not None else [
            SearchResult(
                title="示例结果（假后端）",
                url="https://example.invalid/sample",
                snippet="这是离线假后端返回的示例数据，用于验证接口与截断规则。",
            )
        ]

    async def search(self, query: str, *, top_k: int) -> list[SearchResult]:
        self.queries.append(query)
        return self._results


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=300)
    top_k: int = Field(default=3, ge=1, le=MAX_RESULTS)


class SearchWebTool:
    spec = ToolSpec(
        name="search_web",
        level="L0",
        description="查询公开资料，返回少量结果（标题、链接、摘要）。",
        args_model=SearchArgs,
        timeout_seconds=10.0,
    )

    def __init__(self, backend: SearchBackend) -> None:
        self._backend = backend

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        query = args.query  # type: ignore[attr-defined]
        top_k = args.top_k  # type: ignore[attr-defined]
        results = await self._backend.search(query, top_k=top_k)
        trimmed = [_render(item) for item in results[:MAX_RESULTS]]
        return {"results": trimmed, "truncated": len(results) > len(trimmed)}


def _render(result: SearchResult) -> dict[str, str]:
    return {
        "title": _clip(str(result.title), TITLE_LIMIT),
        "url": _clip(str(result.url), URL_LIMIT),
        "snippet": _clip(str(result.snippet), SNIPPET_LIMIT),
    }


def _clip(text: str, limit: int) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= limit else clean[:limit]
