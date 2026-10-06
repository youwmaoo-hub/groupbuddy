"""write_file：写入本群工作区文件，覆盖前备份 + 原子替换（F4.4）。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.tools.registry import ToolContext, ToolSpec
from app.tools.workspace import atomic_write_text, resolve_path


class WriteFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=300)
    content: str = ""


class WriteFileTool:
    spec = ToolSpec(
        name="write_file",
        level="L2",
        description="把文本写入本群工作区文件（覆盖已存在文件前先备份为 .bak，原子替换，单次 ≤1 MB）。",
        args_model=WriteFileArgs,
        timeout_seconds=5.0,
    )

    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        path, relative = resolve_path(self._root, context.chat_id, args.path)  # type: ignore[attr-defined]
        written, backup = atomic_write_text(path, args.content)  # type: ignore[attr-defined]
        payload: dict[str, object] = {"path": relative, "bytes": written}
        if backup is not None:
            payload["backup"] = backup
        return payload
