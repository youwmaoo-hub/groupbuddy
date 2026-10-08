"""Telegram 角色来源（`app/telegram/admins.py`）：一次查询同时给出管理员集合与群主 id。"""

from __future__ import annotations

import unittest

from aiogram.types import ChatMemberOwner, User

from app.telegram.admins import AiogramAdminSource


class _FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class _FakeMember:
    def __init__(self, user_id: int, status: str) -> None:
        self.user = _FakeUser(user_id)
        self.status = status


class _FakeBot:
    def __init__(self, members: list[object], *, error: Exception | None = None) -> None:
        self._members = members
        self._error = error
        self.calls: list[int] = []

    async def get_chat_administrators(self, chat_id: int) -> list[object]:
        self.calls.append(chat_id)
        if self._error is not None:
            raise self._error
        return self._members


class AiogramAdminSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_creator_is_reported_separately_from_administrators(self) -> None:
        bot = _FakeBot([_FakeMember(7, "creator"), _FakeMember(8, "administrator")])
        roles = await AiogramAdminSource(bot)(-100)
        self.assertEqual(roles.admins, frozenset({7, 8}))
        self.assertEqual(roles.owner_id, 7)
        self.assertEqual(bot.calls, [-100])

    async def test_order_does_not_matter(self) -> None:
        bot = _FakeBot([_FakeMember(8, "administrator"), _FakeMember(7, "creator")])
        self.assertEqual((await AiogramAdminSource(bot)(-100)).owner_id, 7)

    async def test_group_without_creator_has_no_owner(self) -> None:
        bot = _FakeBot([_FakeMember(8, "administrator")])
        roles = await AiogramAdminSource(bot)(-100)
        self.assertEqual(roles.admins, frozenset({8}))
        self.assertIsNone(roles.owner_id)

    async def test_real_aiogram_creator_object_is_recognized(self) -> None:
        owner = ChatMemberOwner(user=User(id=7, is_bot=False, first_name="群主"), is_anonymous=False)
        roles = await AiogramAdminSource(_FakeBot([owner]))(-100)
        self.assertEqual(roles.owner_id, 7)

    async def test_errors_propagate_to_the_registry(self) -> None:
        # 来源不吞异常：fail-closed 统一由 `app/ops/admin.py` 决定。
        bot = _FakeBot([], error=RuntimeError("telegram 不可用"))
        with self.assertRaises(RuntimeError):
            await AiogramAdminSource(bot)(-100)


if __name__ == "__main__":
    unittest.main()
