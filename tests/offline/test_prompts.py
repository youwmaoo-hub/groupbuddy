"""Prompt 结构：固定段顺序与字节稳定、情绪槽位、运行人设与文档一致。"""

from __future__ import annotations

import unittest
from pathlib import Path

from app.llm.prompts import GLOBAL_PERSONA, build_messages, build_system_prompt

PERSONA_DOC = Path(__file__).resolve().parents[2] / "docs" / "persona.md"
FENCE = chr(96) * 3


def persona_text_from_doc() -> str:
    """取 docs/persona.md §4 围栏代码块里的运行文本。"""
    text = PERSONA_DOC.read_text(encoding="utf-8")
    heading = text.index("## 4.")
    start = text.index(FENCE, heading) + len(FENCE)
    end = text.index(FENCE, start)
    return text[start:end].strip("\n")


class SystemPromptTests(unittest.TestCase):
    def test_section_order_is_fixed(self) -> None:
        prompt = build_system_prompt()
        self.assertTrue(prompt.startswith("## 全局人格\n"))
        self.assertLess(prompt.index("## 全局人格"), prompt.index("## 群设定"))
        self.assertLess(prompt.index("## 群设定"), prompt.index("## 输出规则"))

    def test_prompt_is_byte_stable(self) -> None:
        # 固定段必须字节一致，否则吃不到提示词缓存（docs/token.md 一杠杆）
        self.assertEqual(build_system_prompt(), build_system_prompt())

    def test_persona_override_replaces_global_persona(self) -> None:
        prompt = build_system_prompt(persona="临时人设")
        self.assertIn("临时人设", prompt)
        self.assertNotIn(GLOBAL_PERSONA, prompt)

    def test_mode_is_rendered_in_group_section(self) -> None:
        self.assertIn("模式：smart", build_system_prompt(mode="smart"))

    def test_tool_policy_section_renders_allowed_tools(self) -> None:
        prompt = build_system_prompt(allowed_tools=("calc", "search_web"))
        self.assertIn("## 工具策略", prompt)
        self.assertIn('{"allowed_tools": ["calc", "search_web"]}', prompt)
        self.assertLess(prompt.index("## 群设定"), prompt.index("## 工具策略"))
        self.assertLess(prompt.index("## 工具策略"), prompt.index("## 输出规则"))

    def test_empty_tool_list_is_rendered(self) -> None:
        self.assertIn('{"allowed_tools": []}', build_system_prompt())


class MoodTests(unittest.TestCase):
    def test_no_mood_by_default(self) -> None:
        self.assertEqual(len(build_messages(build_system_prompt(), [])), 1)

    def test_mood_is_appended_after_fixed_sections(self) -> None:
        fixed = build_system_prompt()
        messages = build_messages(fixed, [], mood="有点得意")
        self.assertEqual(messages[0]["content"], fixed)
        self.assertEqual(messages[-1], {"role": "system", "content": "当前情绪：有点得意"})

    def test_blank_mood_is_ignored(self) -> None:
        self.assertEqual(len(build_messages(build_system_prompt(), [], mood="   ")), 1)


class PersonaDocTests(unittest.TestCase):
    def test_runtime_persona_matches_document(self) -> None:
        # 文档是唯一事实来源：改人设先改 docs/persona.md §4
        self.assertEqual(persona_text_from_doc(), GLOBAL_PERSONA)


if __name__ == "__main__":
    unittest.main()
