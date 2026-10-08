"""本群角色判定：管理员集合 + 群主身份 + 进程内缓存（docs/security.md §2 第 3 步）。

判定只认程序侧事实：角色来自 Telegram `getChatAdministrators`（同时返回 creator 与普通管理员）——
**只有 creator 算群主**，普通 `administrator` 不算（Persona 等最高级设置的写入只认群主）。
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


@dataclass(frozen=True, slots=True)
class ChatRoles:
    """一次 Telegram 查询的结果：管理员集合 + 群主（creator）id；没有 creator 时为 None。"""

    admins: frozenset[int]
    owner_id: int | None


RolesFetcher = Callable[[int], Awaitable[ChatRoles]]


@dataclass(frozen=True, slots=True)
class _Entry:
    expires_at: float
    roles: ChatRoles
    ok: bool


class AdminRegistry:
    """角色判定的唯一入口；状态在进程内存，重启归零。

    `is_admin`（管理员，含群主）与 `is_owner`（仅群主）读同一份缓存，因此一次查询同时服务两者。
    """

    def __init__(
        self,
        fetch: RolesFetcher,
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
        """群主与普通管理员都算；缓存过期时刷新一次，刷新失败返回 False（拒绝而不是放行）。"""
        entry = await self._entry(chat_id)
        return entry.ok and user_id in entry.roles.admins

    async def is_owner(self, chat_id: int, user_id: int) -> bool:
        """只有 Telegram `creator` 算群主；没有 creator、或查询失败一律 False（fail-closed）。"""
        entry = await self._entry(chat_id)
        return entry.ok and entry.roles.owner_id is not None and user_id == entry.roles.owner_id

    def invalidate(self, chat_id: int | None = None) -> None:
        """权限变动后主动失效；不传 chat_id 表示整表失效。"""
        if chat_id is None:
            self._cache.clear()
        else:
            self._cache.pop(chat_id, None)

    async def _entry(self, chat_id: int) -> _Entry:
        entry = self._cache.get(chat_id)
        if entry is None or entry.expires_at <= self._clock():
            entry = await self._refresh(chat_id)
        return entry

    async def _refresh(self, chat_id: int) -> _Entry:
        try:
            roles = await self._fetch(chat_id)
        except Exception:
            logger.warning("角色查询失败，按拒绝处理 chat_id=%s", chat_id, exc_info=True)
            entry = _Entry(
                self._clock() + self._failure_cache_seconds,
                ChatRoles(admins=frozenset(), owner_id=None),
                False,
            )
        else:
            entry = _Entry(
                self._clock() + self._cache_seconds,
                ChatRoles(admins=frozenset(roles.admins), owner_id=roles.owner_id),
                True,
            )
        self._cache[chat_id] = entry
        return entry
