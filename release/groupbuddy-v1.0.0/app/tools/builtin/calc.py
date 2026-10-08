"""calc：只解析纯数学表达式，零文件、零网络、零 shell（docs/tools.md §calc）。"""

from __future__ import annotations

import ast
import math
import operator

from pydantic import BaseModel, ConfigDict, Field

from app.tools.registry import ToolContext, ToolError, ToolSpec

MAX_EXPONENT = 100
MAX_EXPRESSION_CHARS = 200

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class CalcArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str = Field(min_length=1, max_length=MAX_EXPRESSION_CHARS)


class CalcTool:
    spec = ToolSpec(
        name="calc",
        level="L0",
        description="计算一个纯数学表达式：数字与 + - * / % ** 和括号。",
        args_model=CalcArgs,
        timeout_seconds=2.0,
    )

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        value = evaluate(args.expression)  # type: ignore[attr-defined]
        return {"value": _format(value)}


def evaluate(expression: str) -> int | float:
    """AST 白名单求值；任何其他构造都视为 invalid_expression。"""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        raise ToolError("invalid_expression", "表达式无法解析") from None

    try:
        return _eval(tree.body)
    except ZeroDivisionError:
        raise ToolError("invalid_expression", "除数为零") from None
    except OverflowError:
        raise ToolError("invalid_expression", "结果超出可计算范围") from None


def _eval(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ToolError("invalid_expression", "只允许数字常量")
        return node.value
    if isinstance(node, ast.BinOp):
        handler = _BINOPS.get(type(node.op))
        if handler is None:
            raise ToolError("invalid_expression", "不允许的运算符")
        left = _eval(node.left)
        right = _eval(node.right)
        if isinstance(node.op, ast.Pow):
            _check_exponent(right)
        result = handler(left, right)
        return _check_result(result)
    if isinstance(node, ast.UnaryOp):
        handler = _UNARY.get(type(node.op))
        if handler is None:
            raise ToolError("invalid_expression", "不允许的一元运算符")
        return _check_result(handler(_eval(node.operand)))
    raise ToolError("invalid_expression", "表达式含不允许的构造")


def _check_exponent(exponent: int | float) -> None:
    if abs(exponent) > MAX_EXPONENT:
        raise ToolError("invalid_expression", f"指数绝对值不能超过 {MAX_EXPONENT}")


def _check_result(value: int | float) -> int | float:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ToolError("invalid_expression", "结果不是有限数值")
        return value
    if abs(value) > 10**MAX_EXPONENT:
        raise ToolError("invalid_expression", f"结果绝对值不能超过 10^{MAX_EXPONENT}")
    return value


def _format(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{value:.12g}"
