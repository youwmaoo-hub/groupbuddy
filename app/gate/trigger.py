"""发言闸门：程序侧判定 respond / wait / ignore，不调用模型（0 token）。

阶段 2（F2.2–F2.5）：强触发 → 可解释内容 → 上下文追问 → 冷却/窗口闸门。
判定顺序与原因码见 docs/requirements.md §2.1（本节唯一权威实现）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import Settings
from app.gate.limits import LIMIT_OK, ProactiveLimiter
from app.telegram.parse import IncomingMessage

Verdict = Literal["respond", "wait", "ignore"]

REASON_MENTION = "mention"
REASON_REPLY_TO_BOT = "reply_to_bot"
REASON_ALIAS = "alias"
REASON_QUESTION = "question"
REASON_TROUBLESHOOT = "troubleshoot"
REASON_RESOURCE = "resource"
REASON_FOLLOWUP = "followup"
REASON_NOT_ADDRESSED = "not_addressed"

# 弱触发：内容值得回应，但必须先过冷却/窗口闸门（强触发不受限）
WEAK_REASONS = frozenset({REASON_QUESTION, REASON_TROUBLESHOOT, REASON_RESOURCE, REASON_FOLLOWUP})

QUESTION_MARKS = ("?", "？")
QUESTION_WORDS = (
    "怎么", "如何", "为什么", "是什么", "什么是", "多少", "几点", "哪里", "哪个",
    "能不能", "可不可以", "有没有", "是不是", "吗", "呢",
)
TROUBLESHOOT_WORDS = (
    "报错", "错误", "异常", "失败", "崩溃", "跑不起来", "不起作用",
    "traceback", "error", "exception", "failed",
)
RESOURCE_WORDS = (
    "http://", "https://", "www.", "链接", "文件", "代码", "命令", "配置",
    "安装", "部署", "日志",
)
# 追问承接词：单字（那/再）会带来误判，靠冷却与窗口上限兜底（F2.4）
FOLLOWUP_WORDS = ("然后", "接着", "继续", "后来", "所以", "还有", "刚才", "上面", "那", "再")


def _contains(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


@dataclass(frozen=True, slots=True)
class TriggerDecision:
    verdict: Verdict
    reason: str
    proactive: bool = False  # 弱触发（未点名）为 True：回复要计入冷却与窗口上限

    @property
    def should_respond(self) -> bool:
        return self.verdict == "respond"


class TriggerDetector:
    """强触发不受冷却限制；弱触发（内容/追问）需要过闸门，被压住即 wait。"""

    def __init__(self, settings: Settings, limiter: ProactiveLimiter) -> None:
        self._aliases = tuple(alias.casefold() for alias in settings.aliases)
        self._followup_max = max(1, settings.followup_max_messages)
        self._limiter = limiter

    def decide(self, message: IncomingMessage, *, since_bot_reply: int | None = None) -> TriggerDecision:
        """since_bot_reply＝Bot 上一条发言之后（含本条）的消息条数；从未发言为 None。"""
        strong = self._strong(message)
        if strong is not None:
            return TriggerDecision("respond", strong)
        weak = self._weak(message, since_bot_reply=since_bot_reply)
        if weak is None:
            return TriggerDecision("ignore", REASON_NOT_ADDRESSED)
        limit = self._limiter.check(message.chat_id)
        if limit.reason != LIMIT_OK:
            return TriggerDecision("wait", limit.reason)  # 被冷却/窗口压住：0 token
        return TriggerDecision("respond", weak, proactive=True)

    def _strong(self, message: IncomingMessage) -> str | None:
        if message.mentions_bot:
            return REASON_MENTION
        if message.reply_to_bot:
            return REASON_REPLY_TO_BOT
        if self._matched_alias(message.text) is not None:
            return REASON_ALIAS
        return None

    def _weak(self, message: IncomingMessage, *, since_bot_reply: int | None) -> str | None:
        text = message.text.casefold()
        if _contains(text, QUESTION_MARKS) or _contains(text, QUESTION_WORDS):
            return REASON_QUESTION
        if _contains(text, TROUBLESHOOT_WORDS):
            return REASON_TROUBLESHOOT
        if _contains(text, RESOURCE_WORDS):
            return REASON_RESOURCE
        if self._is_followup(text, since_bot_reply):
            return REASON_FOLLOWUP
        return None

    def _is_followup(self, text: str, since_bot_reply: int | None) -> bool:
        if since_bot_reply is None or not 1 <= since_bot_reply <= self._followup_max:
            return False
        return _contains(text, FOLLOWUP_WORDS)

    def _matched_alias(self, text: str) -> str | None:
        lowered = text.casefold()
        for alias in self._aliases:
            if alias and alias in lowered:
                return alias
        return None
