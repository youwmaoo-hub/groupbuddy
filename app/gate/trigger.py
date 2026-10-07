"""发言闸门：程序侧判定 respond / wait / ignore，不调用模型（0 token）。

阶段 2（F2.2–F2.5）：强触发 → 可解释内容 → 上下文追问 → 冷却/窗口闸门。
阶段 8（群宠体验升级）：人类中心——Bot 作者直接 ignore；普通消息增加
「同话题 / 情绪反应 / 久静后开口」三条弱触发以提高合理活跃度，冷却与窗口
上限不变；回复「其他 Bot」的消息只在强触发时回应（见 docs/requirements.md §2.1，
本节唯一权威实现）。
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
REASON_TOPIC = "topic"
REASON_EMOTION = "emotion"
REASON_QUIET_OPEN = "quiet_open"
REASON_BOT_AUTHOR = "bot_author"
REASON_OTHER_BOT_REPLY = "other_bot_reply"
REASON_NOT_ADDRESSED = "not_addressed"

# 弱触发：内容值得回应，但必须先过冷却/窗口闸门（强触发不受限）
WEAK_REASONS = frozenset({
    REASON_QUESTION, REASON_TROUBLESHOOT, REASON_RESOURCE, REASON_FOLLOWUP,
    REASON_TOPIC, REASON_EMOTION, REASON_QUIET_OPEN,
})

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
# 情绪/反应词（多字词，避免单字误判）：明显带情绪的消息更容易被接住
EMOTION_WORDS = (
    "笑死", "笑不活", "绷不住", "破防", "泪目", "呜呜", "好耶", "太棒", "绝了", "离谱",
    "震惊", "无语", "生气", "难过", "开心", "好烦", "好累", "awsl", "爱了",
    "喜欢", "讨厌", "害怕", "恐怖", "牛逼", "太强", "好强", "厉害", "救命", "寄了",
    "完了", "崩溃", "摸鱼", "加班", "饿了", "好困", "吓人", "尴尬", "害羞", "得意",
    "委屈", "求求", "拜托", "恭喜", "抱抱", "贴贴",
)
# 「同话题」判定用的 2 字组停用表：跨话题高频词，单独命中不算同一话题
STOP_BIGRAMS = frozenset({
    "什么", "这个", "那个", "可以", "我们", "你们", "他们", "一个", "就是", "不是",
    "没有", "已经", "还是", "因为", "所以", "但是", "如果", "现在", "今天", "明天",
    "然后", "这样", "那样", "怎么", "为什么", "自己", "东西", "时候", "感觉", "应该",
})
# 久静后开口的门槛：太短的消息不值得主动开口（噪声消息在 runner 已拦下）
QUIET_OPEN_MIN_CHARS = 6


def _contains(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _bigrams(text: str) -> set[str]:
    """取内容 2 字组（去掉空白与标点），用于低成本「同话题」判定。"""
    cleaned = "".join(char for char in text.casefold() if char.isalnum())
    return {cleaned[index:index + 2] for index in range(len(cleaned) - 1)}


@dataclass(frozen=True, slots=True)
class TriggerDecision:
    verdict: Verdict
    reason: str
    proactive: bool = False  # 弱触发（未点名）为 True：回复要计入冷却与窗口上限

    @property
    def should_respond(self) -> bool:
        return self.verdict == "respond"


class TriggerDetector:
    """强触发不受冷却限制；弱触发（内容/追问/同话题/情绪/久静）需要过闸门，被压住即 wait。"""

    def __init__(self, settings: Settings, limiter: ProactiveLimiter) -> None:
        self._aliases = tuple(alias.casefold() for alias in settings.aliases)
        self._followup_max = max(1, settings.followup_max_messages)
        self._topic_max = max(1, settings.proactive_topic_max_messages)
        self._quiet_messages = max(1, settings.proactive_quiet_messages)
        self._limiter = limiter

    def decide(
        self,
        message: IncomingMessage,
        *,
        since_bot_reply: int | None = None,
        bot_last_text: str | None = None,
    ) -> TriggerDecision:
        """since_bot_reply＝Bot 上一条发言之后（含本条）的消息条数；从未发言为 None。

        bot_last_text＝Bot 上一条发言的文本，仅用于「同话题」弱触发。
        其他 Bot 的消息在 `app/gate/filters.py` 已被丢弃（不入库、不进冷却），
        这里再挡一次：Bot 作者永远 ignore，避免 Bot↔Bot 循环（人类中心）。
        群友回复「另一个 Bot」的消息同理只当背景：除非明确点名/叫别名（强触发），
        否则不插嘴——否则用户跟别的 Bot 对话时本 Bot 会莫名其妙接话。
        """
        if message.is_bot_author:
            return TriggerDecision("ignore", REASON_BOT_AUTHOR)
        if message.reply_to_other_bot:
            strong = self._strong(message)
            if strong is None:
                return TriggerDecision("ignore", REASON_OTHER_BOT_REPLY)
            return TriggerDecision("respond", strong)
        strong = self._strong(message)
        if strong is not None:
            return TriggerDecision("respond", strong)
        weak = self._weak(message, since_bot_reply=since_bot_reply, bot_last_text=bot_last_text)
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

    def _weak(
        self,
        message: IncomingMessage,
        *,
        since_bot_reply: int | None,
        bot_last_text: str | None,
    ) -> str | None:
        text = message.text.casefold()
        if _contains(text, QUESTION_MARKS) or _contains(text, QUESTION_WORDS):
            return REASON_QUESTION
        if _contains(text, TROUBLESHOOT_WORDS):
            return REASON_TROUBLESHOOT
        if _contains(text, RESOURCE_WORDS):
            return REASON_RESOURCE
        if self._is_followup(text, since_bot_reply):
            return REASON_FOLLOWUP
        if self._is_topic(message.text, since_bot_reply, bot_last_text):
            return REASON_TOPIC
        if _contains(text, EMOTION_WORDS):
            return REASON_EMOTION
        if self._is_quiet_open(message.text, since_bot_reply):
            return REASON_QUIET_OPEN
        return None

    def _is_followup(self, text: str, since_bot_reply: int | None) -> bool:
        if since_bot_reply is None or not 1 <= since_bot_reply <= self._followup_max:
            return False
        return _contains(text, FOLLOWUP_WORDS)

    def _is_topic(self, text: str, since_bot_reply: int | None, bot_last_text: str | None) -> bool:
        """与 Bot 上一条发言共享内容词，且还在话题窗口内：接着聊自己的话题。"""
        if not bot_last_text:
            return False
        if since_bot_reply is None or not 1 <= since_bot_reply <= self._topic_max:
            return False
        return bool((_bigrams(text) & _bigrams(bot_last_text)) - STOP_BIGRAMS)

    def _is_quiet_open(self, text: str, since_bot_reply: int | None) -> bool:
        """安静够久（Bot 从未说过话，或已经过去 N 条消息）后的第一条有内容的消息。"""
        quiet = since_bot_reply is None or since_bot_reply >= self._quiet_messages
        return quiet and len(text.strip()) >= QUIET_OPEN_MIN_CHARS

    def _matched_alias(self, text: str) -> str | None:
        lowered = text.casefold()
        for alias in self._aliases:
            if alias and alias in lowered:
                return alias
        return None
