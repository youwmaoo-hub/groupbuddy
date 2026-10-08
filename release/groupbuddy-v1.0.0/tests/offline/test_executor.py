"""executor：schema 校验 → 权限 → 执行 → 结构化结果，含熔断（F4.1、F4.8）。"""

from __future__ import annotations

import asyncio
import json
import unittest

from pydantic import BaseModel, ConfigDict

from app.tools.builtin.calc import CalcTool
from app.tools.builtin.search_web import FakeSearchBackend, SearchWebTool
from app.tools.executor import BreakerConfig, ToolExecutor
from app.tools.policy import Policy
from app.tools.registry import ToolContext, ToolError, ToolRegistry, ToolSpec
from tests.offline.helpers import FakeClock


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""


class _FailingTool:
    def __init__(self, name: str = "read_file", code: str = "execution_failed", message: str = "炸了") -> None:
        self.spec = ToolSpec(name=name, level="L0", description="总是失败", args_model=_Args, timeout_seconds=1.0)
        self._code = code
        self._message = message

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        raise ToolError(self._code, self._message)


class _SlowTool:
    spec = ToolSpec(name="read_file", level="L1", description="很慢", args_model=_Args, timeout_seconds=0.01)

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        await asyncio.sleep(0.05)
        return {}


class _CrashTool:
    spec = ToolSpec(name="read_file", level="L1", description="异常", args_model=_Args, timeout_seconds=1.0)

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        raise RuntimeError("内部细节不应外泄")


class _BigTool:
    spec = ToolSpec(name="read_file", level="L1", description="大输出", args_model=_Args, timeout_seconds=1.0)

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        return {"text": "x" * 5000}


def _build(*tools: object, config: BreakerConfig | None = None) -> tuple[ToolExecutor, FakeClock]:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)  # type: ignore[arg-type]
    clock = FakeClock()
    return ToolExecutor(registry, Policy(registry), config=config, clock=clock.monotonic), clock


def _ctx(chat_id: int = 1, **group: object) -> ToolContext:
    # 故障注入用文档里的 read_file：policy 对未登记名称一律拒绝
    values: dict[str, object] = {"allow_read": 1}
    values.update(group)
    return ToolContext(chat_id=chat_id, user_id=42, group=values)


class SpecTests(unittest.TestCase):
    def test_calc_schema_is_strict_and_title_free(self) -> None:
        executor, _ = _build(CalcTool())
        function = executor.specs_for(_ctx())[0]["function"]  # type: ignore[index]
        self.assertEqual(function["name"], "calc")
        parameters = function["parameters"]
        self.assertFalse(parameters["additionalProperties"])
        self.assertIn("expression", parameters["properties"])
        self.assertNotIn("title", json.dumps(parameters))

    def test_disabled_tool_is_not_exposed(self) -> None:
        executor, _ = _build(SearchWebTool(FakeSearchBackend()))
        self.assertEqual(executor.specs_for(_ctx(allow_search=0)), [])


class ArgumentTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_json(self) -> None:
        executor, _ = _build(CalcTool())
        payload = await executor.execute(_ctx(), "calc", "not json")
        self.assertEqual(payload["error"], "invalid_arguments")

    async def test_non_object_json(self) -> None:
        executor, _ = _build(CalcTool())
        payload = await executor.execute(_ctx(), "calc", "[1, 2]")
        self.assertEqual(payload["error"], "invalid_arguments")

    async def test_unknown_parameter_does_not_echo_value(self) -> None:
        executor, _ = _build(CalcTool())
        payload = await executor.execute(_ctx(), "calc", json.dumps({"expression": "1+1", "secret": "hunter2"}))
        self.assertEqual(payload["error"], "invalid_arguments")
        self.assertIn("secret", str(payload["message"]))
        self.assertNotIn("hunter2", str(payload["message"]))

    async def test_missing_required_parameter(self) -> None:
        executor, _ = _build(SearchWebTool(FakeSearchBackend()))
        payload = await executor.execute(_ctx(allow_search=1), "search_web", "{}")
        self.assertEqual(payload["error"], "invalid_arguments")

    async def test_wrong_type_is_invalid_arguments(self) -> None:
        executor, _ = _build(CalcTool())
        payload = await executor.execute(_ctx(), "calc", json.dumps({"expression": 123}))
        self.assertEqual(payload["error"], "invalid_arguments")

    async def test_permission_denied_for_disabled_group_switch(self) -> None:
        executor, _ = _build(SearchWebTool(FakeSearchBackend()))
        payload = await executor.execute(_ctx(allow_search=0), "search_web", json.dumps({"query": "q"}))
        self.assertEqual(payload["error"], "permission_denied")
        self.assertEqual(payload["tool"], "search_web")

    async def test_unregistered_tool_is_denied(self) -> None:
        executor, _ = _build(CalcTool())
        payload = await executor.execute(_ctx(), "run_code", "{}")
        self.assertEqual(payload["error"], "permission_denied")

    async def test_timeout(self) -> None:
        executor, _ = _build(_SlowTool())
        payload = await executor.execute(_ctx(), "read_file", "{}")
        self.assertEqual(payload["error"], "timeout")

    async def test_tool_error_code_passthrough(self) -> None:
        executor, _ = _build(_FailingTool(code="execution_failed"))
        payload = await executor.execute(_ctx(), "read_file", "{}")
        self.assertEqual(payload["error"], "execution_failed")

    async def test_unexpected_exception_is_internal_error(self) -> None:
        executor, _ = _build(_CrashTool())
        payload = await executor.execute(_ctx(), "read_file", "{}")
        self.assertEqual(payload["error"], "internal_error")
        self.assertEqual(payload["message"], "执行失败")
        self.assertNotIn("内部细节", json.dumps(payload, ensure_ascii=False))

    async def test_error_message_is_short(self) -> None:
        executor, _ = _build(_FailingTool(message="很长" * 300))
        payload = await executor.execute(_ctx(), "read_file", "{}")
        self.assertLessEqual(len(str(payload["message"])), 200)

    async def test_payload_too_large(self) -> None:
        executor, _ = _build(_BigTool())
        payload = await executor.execute(_ctx(), "read_file", "{}")
        self.assertEqual(payload["error"], "too_large")
        self.assertTrue(payload["truncated"])


class BreakerTests(unittest.IsolatedAsyncioTestCase):
    async def test_round_disable_after_two_failures(self) -> None:
        executor, _ = _build(_FailingTool())
        context = _ctx()
        first = await executor.execute(context, "read_file", "{}")
        second = await executor.execute(context, "read_file", "{}")
        third = await executor.execute(context, "read_file", "{}")
        self.assertEqual(first["error"], "execution_failed")
        self.assertEqual(second["error"], "execution_failed")
        self.assertEqual(third["error"], "cooldown")
        self.assertEqual(third["message"], "本轮该工具已失败 2 次，已禁用")
        self.assertEqual(executor.specs_for(context), [])

    async def test_round_disable_message_follows_the_configured_limit(self) -> None:
        executor, _ = _build(_FailingTool(), config=BreakerConfig(round_failures=1))
        context = _ctx()
        first = await executor.execute(context, "read_file", "{}")
        second = await executor.execute(context, "read_file", "{}")
        self.assertEqual(first["error"], "execution_failed")
        self.assertEqual(second["error"], "cooldown")
        self.assertEqual(second["message"], "本轮该工具已失败 1 次，已禁用")

    async def test_breaker_opens_after_eight_failures_then_recovers(self) -> None:
        executor, clock = _build(_FailingTool())
        for _ in range(8):
            await executor.execute(_ctx(), "read_file", "{}")  # 每轮新 context，绕开本轮禁用
        blocked = await executor.execute(_ctx(), "read_file", "{}")
        self.assertEqual(blocked["error"], "cooldown")
        clock.advance(31.0)
        recovered = await executor.execute(_ctx(), "read_file", "{}")
        self.assertEqual(recovered["error"], "execution_failed")

    async def test_breaker_window_expires(self) -> None:
        executor, clock = _build(_FailingTool())
        for _ in range(7):
            await executor.execute(_ctx(), "read_file", "{}")
        clock.advance(301.0)
        later = await executor.execute(_ctx(), "read_file", "{}")
        self.assertEqual(later["error"], "execution_failed")

    async def test_breaker_is_per_chat(self) -> None:
        executor, _ = _build(_FailingTool())
        for _ in range(8):
            await executor.execute(_ctx(chat_id=1), "read_file", "{}")
        other = await executor.execute(_ctx(chat_id=2), "read_file", "{}")
        self.assertEqual(other["error"], "execution_failed")


if __name__ == "__main__":
    unittest.main()
