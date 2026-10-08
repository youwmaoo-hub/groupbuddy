"""read_file：只读本群工作区内的 UTF-8 文本文件（F4.4、docs/tools.md §read_file）。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.tools.registry import ToolContext, ToolError, ToolSpec
from app.tools.workspace import MAX_READ_LINES, READ_MAX_BYTES, resolve_path, read_text_file

QUERY_NOT_SUPPORTED = "invalid_arguments"


class ReadFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    query: str | None = Field(default=None, description="本阶段不支持，传入会返回 invalid_arguments")


class ReadFileTool:
    spec = ToolSpec(
        name="read_file",
        level="L1",
        description="读取本群工作区里 UTF-8 文本文件的行区间（单次最多 200 行）。",
        args_model=ReadFileArgs,
        timeout_seconds=3.0,
        max_payload_bytes=READ_MAX_BYTES,
    )

    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        if args.query is not None:  # type: ignore[attr-defined]
            raise ToolError(QUERY_NOT_SUPPORTED, "本阶段 read_file 不支持 query 检索")
        path, relative = resolve_path(self._root, context.chat_id, args.path)  # type: ignore[attr-defined]
        lines = read_text_file(path).splitlines()
        total = len(lines)
        if total == 0:
            raise ToolError("invalid_arguments", "行区间为空")

        start = 1 if args.start_line is None else min(args.start_line, total)  # type: ignore[attr-defined]
        end = total if args.end_line is None else min(args.end_line, total)  # type: ignore[attr-defined]
        if start > end:
            raise ToolError("invalid_arguments", "行区间为空")
        end = min(end, start + MAX_READ_LINES - 1)
        return {
            "path": relative,
            "start_line": start,
            "end_line": end,
            "text": "\n".join(lines[start - 1 : end]),
            "total_lines": total,
        }
