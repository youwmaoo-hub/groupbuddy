"""aiogram 管理员来源：唯一真正请求 Telegram 管理员列表的地方。

`getChatAdministrators` 同时返回 creator 与管理员（docs/security.md §2 第 3 步）；
异常不在这里吞掉，交给 `app/ops/admin.py` 统一按拒绝处理（fail-closed）。
"""

from __future__ import annotations

from aiogram import Bot


class AiogramAdminSource:
    """实现 `app/ops/admin.py` 需要的取值函数。"""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def __call__(self, chat_id: int) -> set[int]:
        members = await self._bot.get_chat_administrators(chat_id)
        return {int(member.user.id) for member in members}
