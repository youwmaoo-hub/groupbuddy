"""aiogram 发送器：把 Telegram 异常翻译成出站层认识的错误（唯一真正调用 Telegram 的地方）。"""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from app.outbound.queue import RateLimited, SendFailed

logger = logging.getLogger(__name__)


class AiogramSender:
    """实现 outbound.queue 的 Sender 协议；只发送一段文本，分段由队列负责。"""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> int:
        # 不设置 parse_mode：模型输出里的 Markdown 符号不应该触发 Telegram 解析错误
        try:
            message = await self._bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
            )
        except TelegramRetryAfter as error:
            raise RateLimited(float(error.retry_after)) from error
        except TelegramAPIError as error:
            raise SendFailed(f"{type(error).__name__}: {error}") from error
        return int(message.message_id)
