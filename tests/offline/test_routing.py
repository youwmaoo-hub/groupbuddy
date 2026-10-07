"""模型档位路由：默认档、复杂任务升级、fail-safe，以及意图分档规则（docs/token.md §5）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.gate.debounce import Batch
from app.llm.routing import (
    INTENT_CHITCHAT,
    INTENT_COMPLEX,
    INTENT_DEFAULT,
    PURPOSE_CHAT,
    PURPOSE_SUMMARY,
    ModelRouter,
)
from app.session.context import ContextBuilder
from tests.offline.helpers import DbTestCase, make_incoming, make_settings

FENCE = "```"
STRONG = "deepseek-v4-pro"


class RouterTests(unittest.TestCase):
    """选模型名本身：纯规则、不需要数据库、不产生任何模型调用。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _router(self, **overrides: object) -> ModelRouter:
        return ModelRouter(make_settings(self.tmp, **overrides))

    def test_plain_and_chitchat_tasks_use_the_default_model(self) -> None:
        router = self._router(LLM_MODEL_STRONG=STRONG)
        self.assertEqual(router.choose(intent=INTENT_DEFAULT), "deepseek-flash")
        self.assertEqual(router.choose(intent=INTENT_CHITCHAT), "deepseek-flash")

    def test_complex_task_routes_to_the_configured_strong_model(self) -> None:
        router = self._router(LLM_MODEL_STRONG=STRONG)
        self.assertEqual(router.default_model, "deepseek-flash")
        self.assertEqual(router.strong_model, STRONG)
        self.assertEqual(router.choose(intent=INTENT_COMPLEX), STRONG)

    def test_complex_task_falls_back_to_the_default_model_without_a_strong_model(self) -> None:
        router = self._router()  # 未配置 LLM_MODEL_STRONG
        self.assertIsNone(router.strong_model)
        self.assertEqual(router.choose(intent=INTENT_COMPLEX), "deepseek-flash")

    def test_unknown_intent_uses_the_default_model(self) -> None:
        router = self._router(LLM_MODEL_STRONG=STRONG)
        self.assertEqual(router.choose(intent="whatever"), "deepseek-flash")

    def test_summary_purpose_stays_on_the_default_model(self) -> None:
        """summary / 后台任务永远是默认档（docs/token.md §5）。"""
        router = self._router(LLM_MODEL_STRONG=STRONG)
        self.assertEqual(router.choose(intent=INTENT_COMPLEX, purpose=PURPOSE_SUMMARY), "deepseek-flash")
        self.assertEqual(router.choose(intent=INTENT_COMPLEX, purpose=PURPOSE_CHAT), STRONG)

    def test_strong_model_same_as_the_default_is_ignored(self) -> None:
        router = self._router(LLM_MODEL="deepseek-flash", LLM_MODEL_STRONG=" deepseek-flash ")
        self.assertIsNone(router.strong_model)
        self.assertEqual(router.choose(intent=INTENT_COMPLEX), "deepseek-flash")

    def test_strong_model_name_is_trimmed(self) -> None:
        router = self._router(LLM_MODEL_STRONG=f" {STRONG} ")
        self.assertEqual(router.choose(intent=INTENT_COMPLEX), STRONG)

    def test_both_tiers_follow_the_configuration(self) -> None:
        router = self._router(LLM_MODEL="my-model", LLM_MODEL_STRONG="strong-model")
        self.assertEqual(router.choose(intent=INTENT_DEFAULT), "my-model")
        self.assertEqual(router.choose(intent=INTENT_COMPLEX), "strong-model")

    def test_selection_failure_falls_back_to_the_default_model(self) -> None:
        """规则 10：选择过程出错时 fail-safe 回默认模型，不抛给调用方。"""
        router = self._router(LLM_MODEL_STRONG=STRONG)
        with self.assertLogs("app.llm.routing", level="ERROR"):
            with mock.patch.object(ModelRouter, "_decide", side_effect=RuntimeError("坏配置")):
                self.assertEqual(router.choose(intent=INTENT_COMPLEX), "deepseek-flash")


class IntentTests(DbTestCase):
    """`ContextBuilder.intent`：复杂度只由规则给出，无法判断时归 default（路由据此保持默认档）。"""

    @staticmethod
    def _batch(*texts: str) -> Batch:
        items = [
            make_incoming(update_id=700 + index, chat_id=1, message_id=700 + index, text=text)
            for index, text in enumerate(texts)
        ]
        return Batch(chat_id=1, items=items, last_at=0.0, full=False)

    def _builder(self) -> ContextBuilder:
        return ContextBuilder(self.connection, self.settings)

    def test_code_long_text_links_and_recall_are_complex(self) -> None:
        builder = self._builder()
        self.assertEqual(builder.intent(self._batch(f"看代码 {FENCE}x{FENCE}")), INTENT_COMPLEX)
        self.assertEqual(builder.intent(self._batch("长" * 400)), INTENT_COMPLEX)
        self.assertEqual(builder.intent(self._batch("看这个 https://example.com/a")), INTENT_COMPLEX)
        self.assertEqual(builder.intent(self._batch("之前那个怎么搞的")), INTENT_COMPLEX)  # 检索类措辞

    def test_short_chatter_and_ordinary_talk_are_not_complex(self) -> None:
        builder = self._builder()
        self.assertEqual(builder.intent(self._batch("哈哈")), INTENT_CHITCHAT)
        self.assertEqual(builder.intent(self._batch("这是一句普通的日常对话内容")), INTENT_DEFAULT)
        self.assertEqual(builder.intent(self._batch("这个怎么弄？")), INTENT_DEFAULT)  # 短但有问号

    def test_unjudgeable_batch_is_default(self) -> None:
        """规则 5：没有可靠信号（含空批）一律 default → 默认模型。"""
        self.assertEqual(self._builder().intent(self._batch()), INTENT_DEFAULT)


if __name__ == "__main__":
    unittest.main()
