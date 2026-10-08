"""calc：AST 白名单，零文件零网络零 shell（F4.2）。"""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.tools.builtin.calc import CalcArgs, CalcTool, evaluate
from app.tools.registry import ToolContext, ToolError


def _ctx() -> ToolContext:
    return ToolContext(chat_id=1, user_id=42, group={})


class EvaluateTests(unittest.TestCase):
    def test_arithmetic_and_precedence(self) -> None:
        self.assertEqual(evaluate("1+2*3"), 7)
        self.assertEqual(evaluate("(1+2)*3"), 9)
        self.assertEqual(evaluate("2**10"), 1024)
        self.assertEqual(evaluate("7%3"), 1)
        self.assertEqual(evaluate("-3+1"), -2)
        self.assertEqual(evaluate("1/4"), 0.25)

    def test_rejects_code_constructs(self) -> None:
        bad = (
            "__import__('os')",
            "os.system('ls')",
            "().__class__",
            "len('x')",
            "a+1",
            "[1][0]",
            "True",
            "'x'",
            "1 if 2 else 3",
            "{1: 2}",
            "[x for x in (1,)]",
            "lambda: 1",
        )
        for expression in bad:
            with self.subTest(expression=expression):
                with self.assertRaises(ToolError) as caught:
                    evaluate(expression)
                self.assertEqual(caught.exception.code, "invalid_expression")

    def test_division_by_zero(self) -> None:
        with self.assertRaises(ToolError) as caught:
            evaluate("1/0")
        self.assertEqual(caught.exception.code, "invalid_expression")

    def test_huge_exponent_and_result_rejected(self) -> None:
        for expression in ("2**101", "9**9**9", "10**100*10"):
            with self.subTest(expression=expression):
                with self.assertRaises(ToolError) as caught:
                    evaluate(expression)
                self.assertEqual(caught.exception.code, "invalid_expression")

    def test_syntax_error(self) -> None:
        with self.assertRaises(ToolError) as caught:
            evaluate("1+")
        self.assertEqual(caught.exception.code, "invalid_expression")


class CalcSchemaTests(unittest.TestCase):
    def test_expression_length_is_schema_error(self) -> None:
        with self.assertRaises(ValidationError):
            CalcArgs(expression="1" * 201)

    def test_extra_arguments_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            CalcArgs(expression="1+1", precision=2)


class CalcToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_string_value(self) -> None:
        payload = await CalcTool().run(CalcArgs(expression="1/3"), _ctx())
        self.assertEqual(payload, {"value": "0.333333333333"})

    async def test_spec_is_l0_with_two_second_timeout(self) -> None:
        spec = CalcTool().spec
        self.assertEqual((spec.name, spec.level, spec.timeout_seconds), ("calc", "L0", 2.0))


if __name__ == "__main__":
    unittest.main()
