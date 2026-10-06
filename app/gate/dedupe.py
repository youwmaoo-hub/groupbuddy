"""批次级去重：update_id 只处理一次（Telegram 重放安全）。"""

from __future__ import annotations

import aiosqlite

from app.storage.repo import updates


class UpdateDeduplicator:
    """包装 updates 表；重复的 update_id 一律丢弃。"""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection

    async def first_seen(self, update_id: int, chat_id: int | None) -> bool:
        """首次见到返回 True；重放返回 False。"""
        return await updates.mark_seen(self._connection, update_id, chat_id)

    async def purge(self, older_than_seconds: int = 48 * 3600) -> int:
        return await updates.purge_old(self._connection, older_than_seconds)
