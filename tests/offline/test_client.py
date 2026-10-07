"""LLM 客户端离线测试：请求组装、usage/tool_calls 提取与错误翻译（app/llm/client.py、T25）。

不联网：注入假的 AsyncOpenAI 形状对象（只实现 chat.completions.create 与 close）。
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from openai import AsyncOpenAI

from app.domain.bot_instance import LLMCredentials
from app.llm.client import LLMError, DeepSeekClient, ToolCall


class _FakeCompletions:
    def __init__(self, response: object, error: Exception | None) -> None:
        self.payloads: list[dict[str, object]] = []
        self._response = response
        self._error = error

    async def create(self, **payload: object) -> object:
        self.payloads.append(payload)
        if self._error is not None:
            raise self._error
        return self._response


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeOpenAI:
    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.completions = _FakeCompletions(response, error)
        self.chat = _FakeChat(self.completions)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _credentials(**overrides: object) -> LLMCredentials:
    values: dict[str, object] = {
        "base_url": "http://127.0.0.1:9",
        "api_key": "test-key",
        "timeout_seconds": 1.0,
        "model": "model-x",
        "temperature": 0.3,
        "max_output_tokens": 77,
    }
    values.update(overrides)
    return LLMCredentials(**values)  # type: ignore[arg-type]


def _response(
    *,
    content: str | None = "你好",
    tool_calls: tuple[object, ...] = (),
    model: str = "model-x",
    usage: object | None = None,
    choices: bool = True,
) -> object:
    message = SimpleNamespace(content=content, tool_calls=list(tool_calls) or None)
    if usage is None:
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=4, prompt_tokens_details=None)
    if not choices:
        return SimpleNamespace(choices=[], usage=usage, model=model)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage, model=model)


def _client(response: object = None, *, error: Exception | None = None, **overrides: object):
    fake = _FakeOpenAI(response, error)
    return DeepSeekClient(_credentials(**overrides), client=fake), fake  # type: ignore[arg-type]


class PayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_credentials_fill_the_default_payload(self) -> None:
        client, fake = _client(_response())
        messages = [{"role": "user", "content": "hi"}]

        await client.complete(messages)

        payload = fake.completions.payloads[0]
        self.assertEqual("model-x", payload["model"])
        self.assertIs(messages, payload["messages"])
        self.assertEqual(0.3, payload["temperature"])
        self.assertEqual(77, payload["max_tokens"])
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)

    async def test_overrides_and_unrestricted_output(self) -> None:
        client, fake = _client(_response())

        await client.complete([], model="model-y", temperature=0.9, max_tokens=None)
        await client.complete([], max_tokens=5)

        first, second = fake.completions.payloads
        self.assertEqual("model-y", first["model"])
        self.assertEqual(0.9, first["temperature"])
        # 显式 None 表示不发送该字段（不限输出，docs/token.md §5 unrestricted）
        self.assertNotIn("max_tokens", first)
        self.assertEqual(5, second["max_tokens"])

    async def test_tools_are_passed_with_automatic_choice(self) -> None:
        client, fake = _client(_response())
        tools = [{"type": "function", "function": {"name": "calc"}}]

        await client.complete([], tools=tools)
        await client.complete([], tools=[])

        first, second = fake.completions.payloads
        self.assertIs(tools, first["tools"])
        self.assertEqual("auto", first["tool_choice"])
        self.assertNotIn("tools", second)


class ReplyParsingTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_fields_and_tool_calls_are_extracted(self) -> None:
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=4,
            prompt_tokens_details=SimpleNamespace(cached_tokens=6),
        )
        tool_calls = (
            SimpleNamespace(id="call-1", function=SimpleNamespace(name="calc", arguments='{"x": 1}')),
        )
        client, _ = _client(_response(content=None, tool_calls=tool_calls, model="model-y", usage=usage))

        reply = await client.complete([])

        self.assertEqual("", reply.text)
        self.assertEqual("model-y", reply.model)
        self.assertEqual(10, reply.input_tokens)
        self.assertEqual(6, reply.cached_tokens)
        self.assertEqual(4, reply.output_tokens)
        self.assertEqual((ToolCall(id="call-1", name="calc", arguments='{"x": 1}'),), reply.tool_calls)

    async def test_cached_tokens_fall_back_to_the_deepseek_field(self) -> None:
        usage = SimpleNamespace(prompt_tokens=3, completion_tokens=1, prompt_cache_hit_tokens=2)
        client, _ = _client(_response(usage=usage))

        reply = await client.complete([])

        self.assertEqual(2, reply.cached_tokens)

    async def test_missing_usage_fields_become_zero(self) -> None:
        client, _ = _client(_response(usage=SimpleNamespace()))

        reply = await client.complete([])

        self.assertEqual((0, 0, 0), (reply.input_tokens, reply.cached_tokens, reply.output_tokens))

    async def test_missing_reply_fields_get_safe_defaults(self) -> None:
        tool_calls = (SimpleNamespace(id=None, function=SimpleNamespace(name="calc", arguments="")),)
        client, _ = _client(_response(tool_calls=tool_calls))

        reply = await client.complete([])

        self.assertEqual((ToolCall(id="", name="calc", arguments="{}"),), reply.tool_calls)

    async def test_text_without_tool_calls(self) -> None:
        client, _ = _client(_response(content="好的"))

        reply = await client.complete([])

        self.assertEqual("好的", reply.text)
        self.assertEqual((), reply.tool_calls)

    async def test_empty_model_field_falls_back_to_credentials(self) -> None:
        client, _ = _client(_response(model=""))

        reply = await client.complete([])

        self.assertEqual("model-x", reply.model)


class ErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_choices_raise_llm_error(self) -> None:
        client, _ = _client(_response(choices=False))

        with self.assertRaises(LLMError) as caught:
            await client.complete([])

        self.assertEqual("模型返回空 choices", str(caught.exception))

    async def test_client_exception_is_wrapped_with_its_type_name(self) -> None:
        error = ValueError("boom")
        client, _ = _client(error=error)

        with self.assertRaises(LLMError) as caught:
            await client.complete([])

        self.assertEqual("ValueError: boom", str(caught.exception))
        self.assertIs(error, caught.exception.__cause__)


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_aclose_delegates_to_the_injected_client(self) -> None:
        client, fake = _client(_response())

        await client.aclose()

        self.assertTrue(fake.closed)

    async def test_a_real_client_is_created_when_none_is_injected(self) -> None:
        instance = DeepSeekClient(_credentials())
        try:
            self.assertIsInstance(instance._client, AsyncOpenAI)
        finally:
            await instance.aclose()
