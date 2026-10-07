"""本群管理员判定：Telegram 管理员集合 + 进程内缓存（docs/security.md §2 第 3 步）。

判定只认程序侧事实：管理员集合来自 Telegram `getChatAdministrators`（含 creator）。
查询失败一律按**拒绝**处理（fail-closed），不做任何 owner 自举。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: 成功结果的缓存秒数；失败结果缓存更短，避免群里反复发命令时打爆 Telegram API。
CACHE_SECONDS = 300.0
FAILURE_CACHE_SECONDS = 30.0

AdminFetcher = Callable[[int], Awaitable[set[int]]]


@dataclass(frozen=True, slots=True)
class _Entry:
    expires_at: float
    admins: frozenset[int]
    ok: bool


class AdminRegistry:
    """管理员集合的唯一判定入口；状态在进程内存，重启归零。"""

    def __init__(
        self,
        fetch: AdminFetcher,
        *,
        cache_seconds: float = CACHE_SECONDS,
        failure_cache_seconds: float = FAILURE_CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._cache_seconds = max(0.0, cache_seconds)
        self._failure_cache_seconds = max(0.0, failure_cache_seconds)
        self._clock = clock
        self._cache: dict[int, _Entry] = {}

    async def is_admin(self, chat_id: int, user_id: int) -> bool:
        """缓存过期时刷新一次；刷新失败返回 False（拒绝而不是放行）。"""
        entry = self._cache.get(chat_id)
        if entry is None or entry.expires_at <= self._clock():
            entry = await self._refresh(chat_id)
        return entry.ok and user_id in entry.admins

    def invalidate(self, chat_id: int | None = None) -> None:
        """权限变动后主动失效；不传 chat_id 表示整表失效。"""
        if chat_id is None:
            self._cache.clear()
        else:
            self._cache.pop(chat_id, None)

    async def _refresh(self, chat_id: int) -> _Entry:
        try:
            admins = frozenset(int(member_id) for member_id in await self._fetch(chat_id))
        except Exception:
            logger.warning("管理员查询失败，按拒绝处理 chat_id=%s", chat_id, exc_info=True)
            entry = _Entry(self._clock() + self._failure_cache_seconds, frozenset(), False)
        else:
            entry = _Entry(self._clock() + self._cache_seconds, admins, True)
        self._cache[chat_id] = entry
        return entry
