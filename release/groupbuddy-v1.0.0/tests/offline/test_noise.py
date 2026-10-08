"""噪声判定：不进触发、不进上下文、不进摘要输入（F3.2、docs/memory.md §3）。"""

from __future__ import annotations

import unittest

from app.session.noise import is_noise


class NoiseRuleTests(unittest.TestCase):
    def test_empty_is_noise(self) -> None:
        self.assertTrue(is_noise(""))
        self.assertTrue(is_noise("   "))

    def test_pure_emoji_and_punctuation_is_noise(self) -> None:
        self.assertTrue(is_noise("😀😀😀"))
        self.assertTrue(is_noise("。。。"))
        self.assertTrue(is_noise("！！！"))

    def test_short_without_question_is_noise(self) -> None:
        self.assertTrue(is_noise("嗯"))
        self.assertTrue(is_noise("好的"))
        self.assertTrue(is_noise("收到"))

    def test_short_question_is_not_noise(self) -> None:
        self.assertFalse(is_noise("在吗"))
        self.assertFalse(is_noise("啥呢"))

    def test_common_phrases_are_noise(self) -> None:
        for text in ("哈哈", "哈哈哈哈", "笑死", "确实", "晚安", "666", "xswl"):
            with self.subTest(text=text):
                self.assertTrue(is_noise(text))

    def test_mention_is_never_noise(self) -> None:
        self.assertFalse(is_noise("哈哈", mentions_bot=True))
        self.assertFalse(is_noise("@bot"))

    def test_reply_to_bot_is_never_noise(self) -> None:
        self.assertFalse(is_noise("嗯", reply_to_bot=True))

    def test_question_mark_is_never_noise(self) -> None:
        self.assertFalse(is_noise("哈?"))
        self.assertFalse(is_noise("哈？"))

    def test_links_and_code_are_never_noise(self) -> None:
        self.assertFalse(is_noise("https://example.com"))
        self.assertFalse(is_noise("看这个 " + chr(96) * 3 + "x" + chr(96) * 3))

    def test_error_words_are_never_noise(self) -> None:
        for text in ("报错", "error", "失败了"):
            with self.subTest(text=text):
                self.assertFalse(is_noise(text))

    def test_normal_sentence_is_not_noise(self) -> None:
        self.assertFalse(is_noise("我们明天把部署脚本改一下"))
        self.assertFalse(is_noise("这个方案的取舍是什么"))


if __name__ == "__main__":
    unittest.main()
