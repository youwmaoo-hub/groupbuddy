"""内置工具装配：settings → ToolRegistry（唯一注册点）。"""

from __future__ import annotations

from app.config import Settings
from app.tools.builtin.calc import CalcTool
from app.tools.builtin.search_web import FakeSearchBackend, SearchWebTool
from app.tools.registry import ToolRegistry


def build_registry(settings: Settings) -> ToolRegistry:
    """默认只带 calc；search_web 后端未定，只有显式选择假后端时才注册（fail-closed）。"""
    registry = ToolRegistry()
    registry.register(CalcTool())
    if settings.search_backend == "fake":
        registry.register(SearchWebTool(FakeSearchBackend()))
    return registry
