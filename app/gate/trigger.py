"""发言闸门：只输出 respond / ignore，不调用模型（0 token）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import Settings
from app.telegram.parse import IncomingMessage

Verdict = Literal["respond", "ignore"]

REASON_MENTION = "mention"
REASON_REPLY_TO_BOT = "reply_to_bot"
REASON_ALIAS = "alias"
REASON_NOT_ADDRESSED = "not_addressed"


@dataclass(frozen=True, slots=True)
class TriggerDecision:
    verdict: Verdict
    reason: str

    @property
    def should_respond(self) -> bool:
        return self.verdict == "respond"


class TriggerDetector:
    """阶段 1 只实现强触发：@Bot、回复 Bot、Bot 别名/昵称。"""

    def __init__(self, settings: Settings) -> None:
        self._aliases = tuple(alias.casefold() for alias in settings.aliases)

    def decide(self, message: IncomingMessage) -> TriggerDecision:
        if message.mentions_bot:
            return TriggerDecision("respond", REASON_MENTION)
        if message.reply_to_bot:
            return TriggerDecision("respond", REASON_REPLY_TO_BOT)
        if self._matched_alias(message.text) is not None:
            return TriggerDecision("respond", REASON_ALIAS)
        return TriggerDecision("ignore", REASON_NOT_ADDRESSED)

    def _matched_alias(self, text: str) -> str | None:
        lowered = text.casefold()
        for alias in self._aliases:
            if alias and alias in lowered:
                return alias
        return None
