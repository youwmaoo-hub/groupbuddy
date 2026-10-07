"""群主命令通道：解析 → 管理员判定 → 读写本群设置（docs/security.md §2.1、F5.1/F5.2）。

命令不走模型、不写 `messages`、0 token；出站仍由调用方交给 `app/outbound/queue.py`。
未知命令静默丢弃（与历史行为一致），不做"未知命令"提示。
`/settings <字段> <值>` 只允许 F5.1 列出的字段（模式、工具开关、贴纸冷却），
非法字段/非法值一律只回一条提示且**不写库**（docs/requirements.md F5.1）。
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

#: 四种模式（docs/token.md §5）；本项只负责写入，模式对窗口/输出上限的影响见阶段 8 后续项。
MODES: tuple[str, ...] = ("economy", "normal", "smart", "unrestricted")
MODE = "mode"
STICKER_COOLDOWN = "sticker_cooldown"

#: 贴纸冷却合法区间（秒）：0 表示不额外冷却；上限避免把贴纸钉死。
COOLDOWN_MAX_SECONDS = 3600

BOOL_TRUE = frozenset({"on", "开"})
BOOL_FALSE = frozenset({"off", "关"})

#: 写入失败只回这一句：不把 SQLite 细节暴露到聊天里。
WRITE_FAILED_TEXT = "写入失败，请稍后重试。"


@dataclass(frozen=True, slots=True)
class SettingField:
    """一个允许群主修改的设置字段。"""

    name: str  # 回显与确认文案里的规范名
    column: str  # chat_settings 列名
    kind: str  # "bool" | "mode" | "int"


def _build_fields() -> dict[str, SettingField]:
    """别名 → 字段：工具开关同时接受工具名（`search_web`）与列名（`allow_search`）。"""
    fields: dict[str, SettingField] = {MODE: SettingField(name=MODE, column=MODE, kind="mode")}
    for tool, column in TOOL_SWITCHES:
        field = SettingField(name=tool, column=column, kind="bool")
        fields[tool] = field
        fields[column] = field
    fields[STICKER_COOLDOWN] = SettingField(
        name=STICKER_COOLDOWN, column=STICKER_COOLDOWN, kind="int"
    )
    return fields


SETTING_FIELDS = _build_fields()

#: 可用字段（规范名，按 render_settings 的回显顺序）。
FIELD_NAMES = "、".join((MODE, *(tool for tool, _ in TOOL_SWITCHES), STICKER_COOLDOWN))
USAGE_TEXT = f"用法：/settings 或 /settings <字段> <值>\n可用字段：{FIELD_NAMES}"


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


def resolve_setting(args: tuple[str, ...]) -> tuple[SettingField, object] | str:
    """解析 `<字段> <值>`：成功返回 (字段, 值)，失败返回一条可直接回复的文案（不写库）。"""
    if len(args) != 2:
        return USAGE_TEXT
    field = SETTING_FIELDS.get(args[0].casefold())
    if field is None:
        return f"未知字段：{args[0]}\n可用字段：{FIELD_NAMES}"
    value = args[1].strip().casefold()
    if field.kind == "bool":
        if value in BOOL_TRUE:
            return field, 1
        if value in BOOL_FALSE:
            return field, 0
        return f"值不合法：{field.name} 只能是 on/off（开/关）"
    if field.kind == "mode":
        if value in MODES:
            return field, value
        return f"值不合法：{field.name} 只能是 {'、'.join(MODES)}"
    if not (value.isascii() and value.isdigit()) or int(value) > COOLDOWN_MAX_SECONDS:
        return f"值不合法：{field.name} 只能是 0–{COOLDOWN_MAX_SECONDS} 之间的整数秒"
    return field, int(value)


def render_value(field: SettingField, value: object) -> str:
    """把写入的值渲染成确认文案里的样子（与 render_settings 措辞一致）。"""
    if field.kind == "bool":
        return "开" if value else "关"
    if field.kind == "int":
        return f"{int(value)} 秒"
    return str(value)


class CommandService:
    """命令的唯一业务入口：授权判定、参数校验与回复文本；不依赖 aiogram。"""

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
        if not command.args:
            return render_settings(await chat_settings.get(self._connection, chat_id))
        resolved = resolve_setting(command.args)
        if isinstance(resolved, str):
            logger.info("命令参数被拒 chat_id=%s user_id=%s 字段=%s", chat_id, user_id, command.args[0])
            return resolved
        field, value = resolved
        try:
            # 单条原子 upsert（T12）：只写这一列，绝不整行覆盖。
            await chat_settings.upsert(self._connection, chat_id, **{field.column: value})
        except aiosqlite.Error:
            logger.exception("群设置写入失败 chat_id=%s 字段=%s", chat_id, field.column)
            return WRITE_FAILED_TEXT
        logger.info("群设置已更新 chat_id=%s user_id=%s 字段=%s", chat_id, user_id, field.column)
        return f"已更新：{field.name} = {render_value(field, value)}"
