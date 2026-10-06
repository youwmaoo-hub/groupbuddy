"""内置工具装配：settings → ToolRegistry（唯一注册点）。"""

from __future__ import annotations

from app.config import Settings
from app.tools.builtin.calc import CalcTool
from app.tools.builtin.read_file import ReadFileTool
from app.tools.builtin.run_code import RunCodeTool, SandboxRunnerLike
from app.tools.builtin.search_web import FakeSearchBackend, SearchWebTool
from app.tools.builtin.send_sticker import (
    MoodSinkLike,
    SendStickerTool,
    StickerOutboundLike,
    StickerStoreLike,
)
from app.tools.builtin.write_file import WriteFileTool
from app.tools.registry import ToolRegistry


def build_registry(
    settings: Settings,
    *,
    store: StickerStoreLike,
    outbound: StickerOutboundLike,
    mood: MoodSinkLike,
    sandbox: SandboxRunnerLike | None = None,
) -> ToolRegistry:
    """注册所有已实现工具；能不能用由群开关决定（docs/security.md §2）。

    search_web 后端未定，只有显式选择假后端时才注册（fail-closed）。
    run_code 需要可用的沙箱运行时（阶段 7）；没有运行时就不注册该工具。
    """
    registry = ToolRegistry()
    registry.register(CalcTool())
    registry.register(ReadFileTool(settings.workspace_root))
    registry.register(WriteFileTool(settings.workspace_root))
    registry.register(SendStickerTool(store, outbound, mood))
    if settings.search_backend == "fake":
        registry.register(SearchWebTool(FakeSearchBackend()))
    if sandbox is not None:
        registry.register(RunCodeTool(sandbox))
    return registry
