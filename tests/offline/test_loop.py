"""工具循环：轮次上限、用量聚合与工具结果回填（docs/token.md 链 3）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.llm.loop import Outcome, Responder
from app.tools.registry import ToolContext
from tests.offline.helpers import FakeLLMClient, make_settings, tool_reply

SPECS: list[dict[str, object]] = [
    {
        "type": "function",
        "function": {"name": "calc", "description": "算", "parameters": {"type": "object", "properties": {}}},
    }
]


class FakeTools:
    """按协议实现的最小执行器：记录调用并返回固定结果。"""

    def __init__(self, payload: dict[str, object] | None = None, specs: list[dict[str, object]] | None = None) -> None:
        self._payload = payload if payload is not None else {"value": "2"}
        self._specs = SPECS if specs is None else specs
        self.executed: list[tuple[str, str]] = []

    def specs_for(self, context: object) -> list[dict[str, object]]:
        return self._specs

    async def execute(self, context: object, name: str, arguments: str) -> dict[str, object]:
        self.executed.append((name, arguments))
        return self._payload


def _settings(**overrides: object):
    return make_settings(Path(tempfile.mkdtemp()), **overrides)


def _ctx() -> ToolContext:
    return ToolContext(chat_id=1, user_id=42, group={"allow_search": 1})


class ResponderTests(unittest.IsolatedAsyncioTestCase):
    async def test_without_tools_single_call(self) -> None:
        client = FakeLLMClient("好的")
        outcome = await Responder(client, _settings()).reply([{"role": "user", "content": "hi"}])
        self.assertEqual(outcome.text, "好的")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.tools, [None])
        self.assertEqual(outcome.tool_calls, 0)

    async def test_no_context_means_no_tools(self) -> None:
        client = FakeLLMClient("好的")
        outcome = await Responder(client, _settings(), FakeTools()).reply([{"role": "user", "content": "hi"}])
        self.assertEqual(outcome.text, "好的")
        self.assertEqual(client.tools, [None])

    async def test_empty_specs_means_single_call(self) -> None:
        client = FakeLLMClient("好的")
        tools = FakeTools(specs=[])
        outcome = await Responder(client, _settings(), tools).reply([{"role": "user", "content": "hi"}], context=_ctx())
        self.assertEqual(outcome.text, "好的")
        self.assertEqual(len(client.calls), 1)

    async def test_tool_round_executes_and_aggregates_usage(self) -> None:
        client = FakeLLMClient(tool_reply("calc", {"expression": "1+1"}), "等于 2")
        tools = FakeTools()
        outcome = await Responder(client, _settings(), tools).reply(
            [{"role": "user", "content": "1+1"}], context=_ctx()
        )
        self.assertEqual(outcome.text, "等于 2")
        self.assertEqual(outcome.tool_calls, 1)
        self.assertEqual(tools.executed, [("calc", json.dumps({"expression": "1+1"}, ensure_ascii=False))])
        self.assertEqual(client.tool_names, [["calc"], ["calc"]])
        self.assertEqual(outcome.reply.input_tokens, 20)
        tool_messages = [item for item in client.calls[1] if item.get("role") == "tool"]
        self.assertEqual(json.loads(str(tool_messages[0]["content"])), {"value": "2"})

    async def test_tool_error_payload_reaches_model(self) -> None:
        error = {"error": "permission_denied", "tool": "calc", "message": "该工具在本群不可用"}
        client = FakeLLMClient(tool_reply("calc", "{}"), "这个我做不了")
        outcome = await Responder(client, _settings(), FakeTools(payload=error)).reply(
            [{"role": "user", "content": "?"}], context=_ctx()
        )
        self.assertEqual(outcome.text, "这个我做不了")
        tool_messages = [item for item in client.calls[1] if item.get("role") == "tool"]
        self.assertIn("permission_denied", str(tool_messages[0]["content"]))

    async def test_round_cap_keeps_calls_bounded(self) -> None:
        client = FakeLLMClient(tool_reply("calc", "{}"), "最终答案")
        settings = _settings(TOOL_MAX_ROUNDS=1)
        outcome = await Responder(client, settings, FakeTools()).reply(
            [{"role": "user", "content": "?"}], context=_ctx()
        )
        self.assertEqual(outcome.text, "最终答案")
        self.assertEqual(client.tool_names, [["calc"], None])
        self.assertEqual(outcome.tool_calls, 1)

    async def test_tools_stop_when_round_cap_reached(self) -> None:
        client = FakeLLMClient(tool_reply("calc", "{}"), tool_reply("calc", "{}", call_id="call-2"))
        settings = _settings(TOOL_MAX_ROUNDS=1)
        tools = FakeTools()
        outcome = await Responder(client, settings, tools).reply(
            [{"role": "user", "content": "?"}], context=_ctx()
        )
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(tools.executed), 1)  # 最后一轮不再执行工具
        self.assertIsNone(outcome.text)

    def test_outcome_defaults(self) -> None:
        outcome = Outcome("x")
        self.assertEqual((outcome.tool_calls, outcome.tool_ms), (0, 0))


if __name__ == "__main__":
    unittest.main()
