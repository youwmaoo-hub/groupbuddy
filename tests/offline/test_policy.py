"""policy：等级 → 本群开关 → 可用清单（docs/security.md §2）。"""

from __future__ import annotations

import unittest

from pydantic import BaseModel, ConfigDict

from app.tools.builtin.calc import CalcTool
from app.tools.builtin.search_web import FakeSearchBackend, SearchWebTool
from app.tools.policy import POLICY_COLUMNS, Policy
from app.tools.registry import ToolContext, ToolRegistry, ToolSpec


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = ""


class _DummyTool:
    """只为验证等级映射；不会被真正执行。"""

    def __init__(self, name: str) -> None:
        self.spec = ToolSpec(name=name, level="L2", description="测试用", args_model=_Args, timeout_seconds=1.0)

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        return {}


def _registry(*names: str) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalcTool())
    registry.register(SearchWebTool(FakeSearchBackend()))
    for name in names:
        registry.register(_DummyTool(name))
    return registry


def _ctx(chat_id: int = 1, **group: object) -> ToolContext:
    return ToolContext(chat_id=chat_id, user_id=42, group=group)


class PolicyTests(unittest.TestCase):
    def test_calc_is_available_without_any_switch(self) -> None:
        policy = Policy(_registry())
        context = _ctx()
        self.assertIn("calc", policy.allowed_names(context))
        self.assertIsNone(policy.check("calc", context))

    def test_group_switch_controls_search_web(self) -> None:
        policy = Policy(_registry())
        self.assertIsNone(policy.check("search_web", _ctx(allow_search=1)))
        denied = _ctx(allow_search=0)
        self.assertEqual(policy.check("search_web", denied), "permission_denied")
        self.assertNotIn("search_web", policy.allowed_names(denied))

    def test_unregistered_tool_is_denied(self) -> None:
        policy = Policy(_registry())
        self.assertEqual(policy.check("run_code", _ctx(allow_code=1)), "permission_denied")

    def test_write_file_follows_allow_write(self) -> None:
        policy = Policy(_registry("write_file"))
        self.assertEqual(policy.check("write_file", _ctx(allow_write=0)), "permission_denied")
        self.assertIsNone(policy.check("write_file", _ctx(allow_write=1)))

    def test_unknown_registered_tool_defaults_to_denied(self) -> None:
        policy = Policy(_registry("weird_tool"))
        self.assertEqual(policy.check("weird_tool", _ctx()), "permission_denied")

    def test_allowed_names_are_sorted_and_per_chat(self) -> None:
        policy = Policy(_registry())
        self.assertEqual(policy.allowed_names(_ctx()), ("calc",))
        self.assertEqual(policy.allowed_names(_ctx(allow_search=1)), ("calc", "search_web"))
        self.assertEqual(policy.allowed_names(_ctx(chat_id=2, allow_search=0)), ("calc",))
        self.assertEqual(sorted(POLICY_COLUMNS), ["calc", "host_info", "read_file", "run_code", "search_web", "send_sticker", "write_file"])


if __name__ == "__main__":
    unittest.main()
