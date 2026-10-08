"""Prompt 结构：固定段顺序与字节稳定、情绪槽位、运行人设与文档一致。"""

from __future__ import annotations

import unittest
from pathlib import Path

from app.llm.prompts import (
    GLOBAL_PERSONA,
    NO_REPLY,
    NO_REPLY_NUDGE,
    build_messages,
    build_system_prompt,
    fit_reply,
)

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


class ReplyLengthTests(unittest.TestCase):
    """回复字数上限：提示词里加约束，超长由 fit_reply 兜底（docs/token.md §5）。"""

    def test_length_rule_is_included_when_limited(self) -> None:
        prompt = build_system_prompt(reply_limit=280)
        self.assertIn("280 字以内", prompt)
        self.assertLess(prompt.index("280 字以内"), prompt.index("不需要回应时只输出"))

    def test_no_length_rule_when_unlimited(self) -> None:
        self.assertNotIn("字以内", build_system_prompt())
        self.assertNotIn("字以内", build_system_prompt(reply_limit=0))

    def test_zero_limit_keeps_the_reply(self) -> None:
        text = "字" * 500
        self.assertEqual(fit_reply(text, 0), text)

    def test_short_reply_is_untouched(self) -> None:
        self.assertEqual(fit_reply("在的，咋了", 280), "在的，咋了")

    def test_long_reply_is_cut_at_the_last_sentence_end(self) -> None:
        text = "甲" * 200 + "。" + "乙" * 200
        cut = fit_reply(text, 280)
        self.assertEqual(cut, "甲" * 200 + "。")
        self.assertLessEqual(len(cut), 280)

    def test_long_reply_without_sentence_end_is_hard_cut(self) -> None:
        cut = fit_reply("字" * 400, 280)
        self.assertEqual(cut, "字" * 279 + "…")
        self.assertLessEqual(len(cut), 280)

    def test_early_sentence_end_is_not_used(self) -> None:
        # 句末太靠前（不到一半）时不采用，否则会砍掉大半条有用回复
        text = "嗯。" + "字" * 400
        cut = fit_reply(text, 280)
        self.assertEqual(cut, "嗯。" + "字" * 277 + "…")


class DefaultReplyStanceTests(unittest.TestCase):
    """默认接话（2026-10-08 用户要求）：通过了筛选就别沉默，NO_REPLY 只留「完全接不上」。"""

    def test_default_stance_is_to_speak_up(self) -> None:
        prompt = build_system_prompt()
        self.assertIn("已经通过筛选、轮到你了", prompt)
        self.assertIn("不要因为「没点名我」", prompt)
        self.assertLess(prompt.index("已经通过筛选、轮到你了"), prompt.index(NO_REPLY))

    def test_no_reply_is_narrowed_to_unanswerable_messages(self) -> None:
        prompt = build_system_prompt()
        self.assertIn("确实接不上时", prompt)
        self.assertIn(NO_REPLY, prompt)

    def test_no_reply_nudge_asks_for_a_second_try(self) -> None:
        # runner 在模型首轮回 NO_REPLY 时用它追问一次：追问里必须明确「不要再输出 NO_REPLY」
        self.assertIn(NO_REPLY, NO_REPLY_NUDGE)
        self.assertIn("不要再输出", NO_REPLY_NUDGE)


class ReplyTargetTests(unittest.TestCase):
    """回复目标唯一：历史只用于理解，被跳过的消息不补答（docs/requirements.md §2.1 第 9–13 条）。"""

    def test_single_reply_target_rule_is_included(self) -> None:
        prompt = build_system_prompt()
        self.assertIn("当前触发你的那条消息", prompt)
        self.assertIn("视为已经跳过", prompt)

    def test_rule_precedes_no_reply_instruction(self) -> None:
        prompt = build_system_prompt(reply_limit=280)
        self.assertLess(prompt.index("当前触发你的那条消息"), prompt.index("不需要回应时只输出"))

    def test_persona_override_does_not_remove_the_rule(self) -> None:
        # 人设覆盖只换「全局人格」段，回复目标规则在「输出规则」段，不受影响（docs/persona.md §2）
        prompt = build_system_prompt(persona="临时人设")
        self.assertIn("当前触发你的那条消息", prompt)


class PersonaDocTests(unittest.TestCase):
    def test_runtime_persona_matches_document(self) -> None:
        # 文档是唯一事实来源：改人设先改 docs/persona.md §4
        self.assertEqual(persona_text_from_doc(), GLOBAL_PERSONA)


if __name__ == "__main__":
    unittest.main()
