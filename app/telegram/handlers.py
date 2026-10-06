"""aiogram 适配层：本模块与 app/telegram/parse.py 是唯一认识框架的地方。"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import Message, Update

from app.session.runner import SessionRunner
from app.telegram.parse import parse_update

logger = logging.getLogger(__name__)


def build_router(
    *,
    runner: SessionRunner,
    bot_id: int,
    bot_username: str,
    aliases: tuple[str, ...] = (),
) -> Router:
    """注册消息处理器；event_update 由 aiogram 自动注入（dispatcher.py:282）。"""
    router = Router(name="messages")

    @router.message()
    async def on_message(message: Message, event_update: Update) -> None:
        incoming = parse_update(
            event_update,
            bot_id=bot_id,
            bot_username=bot_username,
            aliases=aliases,
        )
        if incoming is None:
            return
        try:
            await runner.handle(incoming)
        except Exception:
            # 接收路径不允许把异常抛回 aiogram，否则会打断轮询
            logger.exception("消息处理失败 chat_id=%s update_id=%s", incoming.chat_id, incoming.update_id)

    return router
