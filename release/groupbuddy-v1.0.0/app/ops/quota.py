"""Token 配额（阶段 8 F5.3）：调用模型之前按 `chat_id` 检查日/月用量（docs/token.md §4.1）。

只读 `usage` 表，不写库、不缓存；判定的唯一入口是本模块，业务侧只问"能不能调用"。
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import aiosqlite

from app.config import Settings, today_in_timezone
from app.storage.repo import usage

logger = logging.getLogger(__name__)

# 提示面向群里的人：明确说清"哪种配额用完了"，不含任何数据库/实现细节
DAILY_EXHAUSTED_TEXT = "本群今天的 Token 配额已用完，暂时不能回复，明天恢复。"
MONTHLY_EXHAUSTED_TEXT = "本群本月的 Token 配额已用完，暂时不能回复，下月恢复。"


class QuotaGuard:
    """按群检查日/月 token 配额；`0` 或未配置 = 不限额。"""

    def __init__(
        self,
        connection: aiosqlite.Connection,
        settings: Settings,
        *,
        today: Callable[[], str] | None = None,
    ) -> None:
        self._connection = connection
        self._daily = max(0, int(settings.quota_daily_tokens))
        self._monthly = max(0, int(settings.quota_monthly_tokens))
        self._today = today if today is not None else (lambda: today_in_timezone(settings))

    @property
    def enabled(self) -> bool:
        """两个键都为 0（未配置）时关闭配额，行为与不配完全一致。"""
        return self._daily > 0 or self._monthly > 0

    async def check(self, chat_id: int) -> str | None:
        """达到或超过上限时返回提示文案（本轮不得调用模型）；否则返回 None。"""
        if not self.enabled:
            return None
        day = self._today()
        if self._daily > 0:
            used = await usage.tokens_used(self._connection, chat_id=chat_id, day_prefix=day)
            if used >= self._daily:
                logger.info("日配额已满 chat_id=%s 上限=%s 已用=%s", chat_id, self._daily, used)
                return DAILY_EXHAUSTED_TEXT
        if self._monthly > 0:
            used = await usage.tokens_used(self._connection, chat_id=chat_id, day_prefix=day[:7])
            if used >= self._monthly:
                logger.info("月配额已满 chat_id=%s 上限=%s 已用=%s", chat_id, self._monthly, used)
                return MONTHLY_EXHAUSTED_TEXT
        return None
