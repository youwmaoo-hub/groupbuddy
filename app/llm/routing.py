"""模型档位路由：最小规则型入口（docs/token.md §5）。

口径（已确认的产品规则）：

- 默认模型 = `LLM_MODEL`（当前 `deepseek-flash`）：普通聊天、summary/后台任务、无法判断
  复杂度、未配置更强模型、选择过程出错，一律用默认模型。
- 只有规则判定为"明显复杂"（代码 / 长文 / 多步骤 / 链接与检索类，由
  `app/session/context.py` 的纯规则给出）且配置里确实存在另一个更强模型
  （`LLM_MODEL_STRONG`）时才升级。
- 不做额外模型调用、不做独立 AI 分类器、不引入新依赖；路由只决定"用哪个模型名"，
  不触碰 quota、工具策略、沙箱与权限——那些仍是硬约束。

调用方（当前只有 `app/session/runner.py`，以后 Web / Service Layer 复用同一入口）：

    model = router.choose(intent=context.intent(batch), purpose=routing.PURPOSE_CHAT)
"""

from __future__ import annotations

import logging

from app.config import Settings

logger = logging.getLogger(__name__)

#: 用途：chat = 群聊回复；summary = 后台摘要（docs/token.md §4）。
PURPOSE_CHAT = "chat"
PURPOSE_SUMMARY = "summary"

#: 意图分档（由 `app/session/context.py::ContextBuilder.intent` 的纯规则给出）。
INTENT_COMPLEX = "complex"
INTENT_CHITCHAT = "chitchat"
INTENT_DEFAULT = "default"


class ModelRouter:
    """按用途 + 意图给出模型名；任何不确定都回退默认模型（fail-safe）。"""

    def __init__(self, settings: Settings) -> None:
        self._default = settings.llm_model
        strong = (settings.llm_model_strong or "").strip()
        # 与默认同名等于没配：只在真的存在"另一个更强模型"时才参与路由。
        self._strong = strong if strong and strong != self._default else None

    @property
    def default_model(self) -> str:
        return self._default

    @property
    def strong_model(self) -> str | None:
        """配置的更强模型名；未配置 / 与默认同名时为 None。"""
        return self._strong

    def choose(self, *, intent: str, purpose: str = PURPOSE_CHAT) -> str:
        """summary 与后台任务 → 默认；复杂任务且配置了强模型 → 强模型；其余 → 默认。"""
        try:
            return self._decide(intent=intent, purpose=purpose)
        except Exception:
            logger.exception("模型选择失败，回退默认模型 %s", self._default)
            return self._default

    def _decide(self, *, intent: str, purpose: str) -> str:
        if purpose != PURPOSE_CHAT or intent != INTENT_COMPLEX:
            return self._default
        if self._strong is None:
            return self._default
        if not isinstance(self._strong, str) or not self._strong.strip():
            raise ValueError("配置的更强模型名无效")
        return self._strong.strip()
