"""工具契约：错误、规格、上下文与注册表（唯一权威说明见 docs/tools.md）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel

ToolLevel = Literal["L0", "L1", "L2", "L3", "L4"]

# docs/tools.md §3 的 11 个错误码
ERROR_CODES = frozenset(
    {
        "permission_denied",
        "invalid_arguments",
        "invalid_expression",
        "not_found",
        "path_outside_workspace",
        "too_large",
        "timeout",
        "sandbox_unavailable",
        "execution_failed",
        "cooldown",
        "internal_error",
    }
)

MAX_ERROR_MESSAGE_CHARS = 200


class ToolError(Exception):
    """工具执行失败：只带错误码与不超过 200 字符的短句（docs/tools.md §3）。"""

    def __init__(self, code: str, message: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"未知错误码: {code}")
        short = " ".join(str(message).split())[:MAX_ERROR_MESSAGE_CHARS]
        super().__init__(short)
        self.code = code
        self.message = short


@dataclass(slots=True)
class ToolContext:
    """一次回复轮次的工具执行上下文；每轮新建，因此天然按 chat_id 隔离。"""

    chat_id: int
    user_id: int
    group: dict[str, object]
    # 本轮每个工具的失败次数与本轮已被禁用（失败 2 次）的工具名
    failures_this_round: dict[str, int] = field(default_factory=dict)
    failed_this_round: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """工具规格；name/输入输出/等级/超时以 docs/tools.md §2 冻结表为准。"""

    name: str
    level: ToolLevel
    description: str
    args_model: type[BaseModel]
    timeout_seconds: float

    @property
    def parameters(self) -> dict[str, object]:
        """给模型的 JSON Schema（去掉 title，禁止额外字段）。"""
        schema = _strip_titles(self.args_model.model_json_schema())
        schema["additionalProperties"] = False
        return schema

    def api_schema(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Tool(Protocol):
    spec: ToolSpec

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]: ...


class ToolRegistry:
    """name → Tool；只把已注册的工具暴露给模型（docs/security.md §2 判定第 1 步）。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.spec.name
        if name in self._tools:
            raise ValueError(f"工具重复注册: {name}")
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def tools(self) -> tuple[Tool, ...]:
        return tuple(self._tools[name] for name in self.names())


def _strip_titles(value: object) -> object:
    if isinstance(value, dict):
        return {key: _strip_titles(item) for key, item in value.items() if key != "title"}
    if isinstance(value, list):
        return [_strip_titles(item) for item in value]
    return value
