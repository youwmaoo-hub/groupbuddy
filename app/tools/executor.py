"""工具执行器：注册表 → 权限 → schema 校验 → 执行 → 结构化结果，含熔断（F4.8）。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass

from pydantic import ValidationError

from app.tools.policy import Policy
from app.tools.registry import ToolContext, ToolError, ToolRegistry

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 4096
ROUND_FAILURE_LIMIT = 2
BREAKER_WINDOW_SECONDS = 300.0
BREAKER_FAILURES = 8
BREAKER_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class BreakerConfig:
    round_failures: int = ROUND_FAILURE_LIMIT
    window_seconds: float = BREAKER_WINDOW_SECONDS
    window_failures: int = BREAKER_FAILURES
    breaker_seconds: float = BREAKER_SECONDS


class ToolExecutor:
    """工具调用的唯一执行入口；错误一律以结构化对象返回给模型。"""

    def __init__(
        self,
        registry: ToolRegistry,
        policy: Policy,
        *,
        config: BreakerConfig | None = None,
        max_payload_bytes: int = MAX_PAYLOAD_BYTES,
        clock=None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._config = config or BreakerConfig()
        self._max_payload_bytes = max_payload_bytes
        self._clock = clock or time.monotonic
        self._failures: dict[tuple[int, str], deque[float]] = {}
        self._breaker_until: dict[tuple[int, str], float] = {}

    def allowed_names(self, context: ToolContext) -> tuple[str, ...]:
        return self._policy.allowed_names(context)

    def specs_for(self, context: ToolContext) -> list[dict[str, object]]:
        """本轮可下发给模型的工具定义；被熔断/本轮禁用的工具不出现。"""
        now = self._clock()
        specs: list[dict[str, object]] = []
        for name in self.allowed_names(context):
            if name in context.failed_this_round or self._breaker_until.get((context.chat_id, name), 0.0) > now:
                continue
            tool = self._registry.get(name)
            if tool is not None:
                specs.append(tool.spec.api_schema())
        return specs

    async def execute(self, context: ToolContext, name: str, arguments: str) -> dict[str, object]:
        blocked = self._blocked_reason(context, name)
        if blocked is not None:
            return _error(name, "cooldown", blocked)

        tool = self._registry.get(name)
        if tool is None:
            return _error(name, "permission_denied", "该工具不可用")
        code = self._policy.check(name, context)
        if code is not None:
            return _error(name, code, "该工具在本群不可用")

        raw = _parse_arguments(arguments)
        if raw is None:
            return _error(name, "invalid_arguments", "参数不是合法的 JSON 对象")
        try:
            args = tool.spec.args_model.model_validate(raw)
        except ValidationError as error:
            return _error(name, "invalid_arguments", _validation_hint(error))

        try:
            payload = await asyncio.wait_for(tool.run(args, context), timeout=tool.spec.timeout_seconds)
        except asyncio.TimeoutError:
            self._note_failure(context, name)
            return _error(name, "timeout", f"执行超过 {tool.spec.timeout_seconds:g} 秒")
        except ToolError as error:
            self._note_failure(context, name)
            return _error(name, error.code, error.message)
        except Exception:  # 未预期错误只记日志，不把细节给模型
            logger.exception("工具执行失败 tool=%s chat_id=%s", name, context.chat_id)
            self._note_failure(context, name)
            return _error(name, "internal_error", "执行失败")

        return self._fit_payload(name, payload, tool.spec.max_payload_bytes)

    def _blocked_reason(self, context: ToolContext, name: str) -> str | None:
        now = self._clock()
        if name in context.failed_this_round:
            return "本轮该工具已失败 2 次，已禁用"
        if self._breaker_until.get((context.chat_id, name), 0.0) > now:
            return "该工具暂时熔断，稍后再试"
        return None

    def _note_failure(self, context: ToolContext, name: str) -> None:
        count = context.failures_this_round.get(name, 0) + 1
        context.failures_this_round[name] = count
        if count >= self._config.round_failures:
            context.failed_this_round.add(name)

        now = self._clock()
        history = self._failures.setdefault((context.chat_id, name), deque())
        history.append(now)
        while history and now - history[0] > self._config.window_seconds:
            history.popleft()
        if len(history) >= self._config.window_failures:
            self._breaker_until[(context.chat_id, name)] = now + self._config.breaker_seconds
            logger.warning("工具熔断 tool=%s chat_id=%s", name, context.chat_id)

    def _fit_payload(self, name: str, payload: dict[str, object], limit: int | None = None) -> dict[str, object]:
        budget = self._max_payload_bytes if limit is None else limit
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded.encode("utf-8")) <= budget:
            return payload
        logger.warning("工具输出超过上限 tool=%s bytes=%s", name, len(encoded.encode("utf-8")))
        return {
            "error": "too_large",
            "tool": name,
            "message": "结果超过上限，已丢弃",
            "truncated": True,
        }


def _error(name: str, code: str, message: str) -> dict[str, object]:
    return {"error": code, "tool": name, "message": " ".join(str(message).split())[:200]}


def _parse_arguments(arguments: str) -> dict[str, object] | None:
    text = (arguments or "").strip() or "{}"
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _validation_hint(error: ValidationError) -> str:
    """只回字段名与错误类型，不回传入的值（不泄露隐私）。"""
    parts = [f"{'.'.join(str(item) for item in err['loc']) or '参数'}:{err['type']}" for err in error.errors()]
    return "参数不符合 schema → " + ", ".join(sorted(parts))
