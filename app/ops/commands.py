"""群主命令通道：解析 → 管理员判定 → 简短回复（docs/security.md §2 第 3 步、F5.2）。

命令不走模型、不写 `messages`、0 token；出站仍由调用方交给 `app/outbound/queue.py`。
未知命令静默丢弃（与历史行为一致），不做"未知命令"提示。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiosqlite

from app.ops.admin import AdminRegistry
from app.storage.repo import chat_settings

logger = logging.getLogger(__name__)

PREFIX = "/"
SETTINGS = "settings"

#: 非管理员只看到这一句：不泄露设置内容，也不透露内部判定原因。
DENIED_TEXT = "这个命令只有群管理员能用。"

#: 工具名 → chat_settings 开关列（docs/security.md §2 等级表）
TOOL_SWITCHES: tuple[tuple[str, str], ...] = (
    ("search_web", "allow_search"),
    ("read_file", "allow_read"),
    ("write_file", "allow_write"),
    ("run_code", "allow_code"),
    ("send_sticker", "allow_sticker"),
    ("host_info", "allow_host_info"),
)


@dataclass(frozen=True, slots=True)
class Command:
    """已解析的命令；`name` 为小写、不含 `/` 与 `@Bot` 后缀。"""

    name: str
    args: tuple[str, ...] = ()
    mention: str = ""


def parse_command(text: str, *, bot_username: str = "") -> Command | None:
    """解析 `/name[@bot] [args]`；不是命令、或明确指向别的 Bot 时返回 None。"""
    stripped = text.lstrip()
    if not stripped.startswith(PREFIX):
        return None
    parts = stripped.split()
    name, _, mention = parts[0][len(PREFIX) :].partition("@")
    name = name.casefold()
    mention = mention.casefold()
    if not name or not name.replace("_", "").isalnum():
        return None
    if mention and bot_username and mention != bot_username.casefold():
        # 命令是发给别的 Bot 的：交给入口过滤器按普通命令丢弃
        return None
    return Command(name=name, args=tuple(parts[1:]), mention=mention)


def render_settings(group: dict[str, object]) -> str:
    """只回显设置本身：模式、工具开关、贴纸冷却；不含凭据与路径。"""
    lines = ["当前群设置", f"模式：{group.get('mode', 'normal')}"]
    for tool, column in TOOL_SWITCHES:
        lines.append(f"{tool}：{'开' if group.get(column) else '关'}")
    lines.append(f"贴纸冷却：{int(group.get('sticker_cooldown') or 0)} 秒")
    return "\n".join(lines)


class CommandService:
    """命令的唯一业务入口：授权判定与回复文本；不依赖 aiogram。"""

    def __init__(self, connection: aiosqlite.Connection, admins: AdminRegistry) -> None:
        self._connection = connection
        self._admins = admins

    async def reply_text(self, *, chat_id: int, user_id: int, command: Command) -> str | None:
        """返回要发送的文本；None 表示静默丢弃（未知命令）。"""
        if command.name != SETTINGS:
            logger.debug("未实现的命令 chat_id=%s name=%s", chat_id, command.name)
            return None
        if not await self._admins.is_admin(chat_id, user_id):
            logger.info(
                "命令被拒 chat_id=%s user_id=%s name=%s 原因=not_admin", chat_id, user_id, command.name
            )
            return DENIED_TEXT
        group = await chat_settings.get(self._connection, chat_id)
        return render_settings(group)
