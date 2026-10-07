"""群级人设（Persona）的读取与清洗规则（docs/persona.md §2、docs/security.md §2.1）。"""

from __future__ import annotations

import unittest

from app.ops import persona


class SanitizeTests(unittest.TestCase):
    def test_plain_text_is_trimmed(self) -> None:
        self.assertEqual(persona.sanitize("  温柔一点  "), "温柔一点")

    def test_control_characters_become_single_spaces(self) -> None:
        self.assertEqual(persona.sanitize("甲\n乙\t丙\r\n丁"), "甲 乙 丙 丁")
        self.assertEqual(persona.sanitize("甲\x00乙\x1b丙"), "甲 乙 丙")
        self.assertEqual(persona.sanitize("甲\x85乙"), "甲 乙")  # C1 控制字符

    def test_blank_variants_collapse_to_empty(self) -> None:
        for text in ("", "   ", "\n\n", "\t \r"):
            with self.subTest(text=text):
                self.assertEqual(persona.sanitize(text), "")

    def test_is_clear_accepts_off_and_off_aliases_only(self) -> None:
        self.assertTrue(persona.is_clear("off"))
        self.assertTrue(persona.is_clear("OFF"))
        self.assertTrue(persona.is_clear("关"))
        self.assertFalse(persona.is_clear("关闭"))
        self.assertFalse(persona.is_clear("off topic"))


class ResolveTests(unittest.TestCase):
    def test_group_override_wins_over_deploy_persona(self) -> None:
        group = {"persona_override": "本群用短句"}
        self.assertEqual(persona.resolve(group, "部署侧人格"), "本群用短句")

    def test_deploy_persona_is_used_when_group_has_none(self) -> None:
        self.assertEqual(persona.resolve({"persona_override": None}, "部署侧人格"), "部署侧人格")
        self.assertEqual(persona.resolve(None, "部署侧人格"), "部署侧人格")

    def test_blank_override_falls_back_instead_of_blanking_the_bot(self) -> None:
        for override in ("", "   ", "\n", None):
            with self.subTest(override=override):
                self.assertEqual(
                    persona.resolve({"persona_override": override}, "部署侧人格"), "部署侧人格"
                )

    def test_empty_result_means_builtin_persona(self) -> None:
        # 空串由 `app/llm/prompts.py` 回退到内置 GLOBAL_PERSONA。
        self.assertEqual(persona.resolve(None, ""), "")
        self.assertEqual(persona.resolve({"persona_override": "   "}, "  "), "")

    def test_group_override_is_sanitized_on_read(self) -> None:
        # 即使历史行里存了多行文本（例如早期写入），读取侧也保证只进一段。
        self.assertEqual(
            persona.resolve({"persona_override": "甲\n乙"}, "部署侧人格"), "甲 乙"
        )

    def test_max_chars_is_the_documented_limit(self) -> None:
        self.assertEqual(persona.MAX_CHARS, 500)


if __name__ == "__main__":
    unittest.main()
