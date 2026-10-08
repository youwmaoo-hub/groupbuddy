"""群主命令通道：解析 → 管理员判定 → 读写设置 / 运行指标（docs/security.md §2.1、F5.1/F5.2/F5.4）。

命令不走模型、不写 `messages`、0 token；出站仍由调用方交给 `app/outbound/queue.py`。
未知命令静默丢弃（与历史行为一致），不做"未知命令"提示。
`/settings <字段> <值>` 只允许 F5.1 列出的字段（模式、工具开关、贴纸冷却），
非法字段/非法值一律只回一条提示且**不写库**（docs/requirements.md F5.1）。
`/stats` 与 `/health` 只读：文案由 `app/ops/metrics.py` 渲染，不含路径、堆栈与凭据。
`/clear` 只删本群 `messages` 原文（`docs/database.md` §4）：摘要、用量与统计数据保留，其他群不受影响。
`/settings persona_override <文本>` 是本群的人设覆盖（docs/persona.md §2），**只有群主（creator）能写**：
普通管理员与成员都按 `DENIED_TEXT` 拒绝；文本清洗与长度校验见 `app/ops/persona.py`。
`/note` 是本群长期记忆（docs/memory.md §6），同样**只有群主**能用：列出、查看、记住、删除，
解析与文案见 `app/ops/notes.py`，写库与 FTS 同步见 `app/storage/repo/notes.py`。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiosqlite

from app import modes
from app.config import Settings
from app.ops import notes as notes_ops
from app.ops import persona
from app.ops.admin import AdminRegistry
from app.ops.health import HealthState
from app.ops.metrics import render_health, render_stats
from app.session.retrieval import term_tokens
from app.storage.repo import chat_settings, messages, notes

logger = logging.getLogger(__name__)

PREFIX = "/"
SETTINGS = "settings"
STATS = "stats"
HEALTH = "health"
CLEAR = "clear"
NOTE = "note"
HELP = "help"

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

#: 四种模式（唯一来源 `app/modes.py`，docs/token.md §5）；模式的实际影响也在那里。
MODES = modes.MODES
MODE = "mode"
STICKER_COOLDOWN = "sticker_cooldown"

#: 贴纸冷却合法区间（秒）：0 表示不额外冷却；上限避免把贴纸钉死。
COOLDOWN_MAX_SECONDS = 3600

BOOL_TRUE = frozenset({"on", "开"})
BOOL_FALSE = frozenset({"off", "关"})

#: 写入失败只回这一句：不把 SQLite 细节暴露到聊天里。
WRITE_FAILED_TEXT = "写入失败，请稍后重试。"

#: `/clear` 的用法与失败文案（同样不泄露数据库细节）。
CLEAR_USAGE = "用法：/clear"
CLEAR_FAILED_TEXT = "清理失败，请稍后重试。"

#: `/note` 的失败文案来自这里（用法文案在 `app/ops/notes.py`，由 `parse` 直接返回）。
NOTE_FAILED_TEXT = "笔记操作失败，请稍后重试。"


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

#: 群级人设：只认群主写入，因此单独成字段、不进 `SETTING_FIELDS` 的通用两参数路径。
PERSONA = "persona_override"
PERSONA_FIELD = SettingField(name=PERSONA, column=PERSONA, kind="text")
OWNER_FIELD_NAMES = f"{FIELD_NAMES}、{PERSONA}"


def usage_text(field_names: str = FIELD_NAMES) -> str:
    """`/settings` 用法；群主能多看到一个只属于他的字段。"""
    return f"用法：/settings 或 /settings <字段> <值>\n可用字段：{field_names}"


USAGE_TEXT = usage_text()


def help_text() -> str:
    """`/help`：把所有指令和该找谁用写清楚（指令可发现性；命令本身各自鉴权）。"""
    return "\n".join(
        (
            "我是本群的群宠助手，指令都在群里直接发给我：",
            f"/{HELP} —— 看这份指令表",
            f"/{SETTINGS} —— 看本群设置（模式、工具开关、贴纸冷却）",
            f"/{SETTINGS} <字段> <值> —— 改设置，例如 /{SETTINGS} search_web on、/{SETTINGS} mode smart",
            f"    可用字段：{OWNER_FIELD_NAMES}",
            f"/{NOTE} —— 记笔记：/{NOTE} 列表、/{NOTE} <名称> 查看、/{NOTE} <名称> <内容> 记住、/{NOTE} del <名称> 删除",
            f"/{STATS} —— 本群运行统计",
            f"/{HEALTH} —— 运行健康状态",
            f"/{CLEAR} —— 清空本群已存的消息原文（摘要与统计保留）",
            f"权限：/{SETTINGS}、/{STATS}、/{HEALTH}、/{CLEAR}、/{NOTE} 只认本群管理员，人设覆盖只认群主；",
            f"/{HELP} 所有人都能用。",
            "不点我也能聊：@我、回复我、或者叫我「大肥鱼 / 鲸鱼娘」我必应；平时我会看情绪和话题偶尔插一句。",
        )
    )


#: Telegram 指令菜单（`bot.set_my_commands`）：名称小写，描述越短越好（手机上会截断）。
BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    (HELP, "看全部指令怎么用"),
    (SETTINGS, "查看或修改本群设置（管理员）"),
    (NOTE, "记笔记（管理员）"),
    (STATS, "本群运行统计（管理员）"),
    (HEALTH, "运行健康状态（管理员）"),
    (CLEAR, "清空本群已存消息原文（管理员）"),
)


@dataclass(frozen=True, slots=True)
class Command:
    """已解析的命令；`name` 为小写、不含 `/` 与 `@Bot` 后缀。"""

    name: str
    args: tuple[str, ...] = ()
    mention: str = ""
    rest: str = ""  # 命令名之后的原文（人设文本可含空格，不能只按空白切分）


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
    return Command(
        name=name,
        args=tuple(parts[1:]),
        mention=mention,
        rest=stripped[len(parts[0]) :].strip(),
    )


def render_settings(group: dict[str, object], *, can_set_persona: bool = False) -> str:
    """只回显设置本身：模式、工具开关、贴纸冷却；群主额外看到人设覆盖状态（不回显全文）。"""
    lines = ["当前群设置", f"模式：{group.get('mode', 'normal')}"]
    for tool, column in TOOL_SWITCHES:
        lines.append(f"{tool}：{'开' if group.get(column) else '关'}")
    lines.append(f"贴纸冷却：{int(group.get('sticker_cooldown') or 0)} 秒")
    if can_set_persona:
        override = persona.sanitize(str(group.get(PERSONA) or ""))
        lines.append(f"人设覆盖：{f'已设置（{len(override)} 字）' if override else '未设置'}")
    lines.append(f"指令：/{HELP} 查看全部指令")
    return "\n".join(lines)


def resolve_setting(
    args: tuple[str, ...], *, field_names: str = FIELD_NAMES
) -> tuple[SettingField, object] | str:
    """解析 `<字段> <值>`：成功返回 (字段, 值)，失败返回一条可直接回复的文案（不写库）。"""
    if len(args) != 2:
        return usage_text(field_names)
    field = SETTING_FIELDS.get(args[0].casefold())
    if field is None:
        return f"未知字段：{args[0]}\n可用字段：{field_names}"
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


def resolve_persona_setting(rest: str) -> tuple[SettingField, str] | str:
    """解析 `/settings persona_override <文本>`；文本取命令名之后的原文（可含空格）。

    返回 (字段, 清洗后文本)：文本为 `off`/`关` 时值为空串，表示清除本群覆盖、回退部署侧人格。
    """
    parts = rest.split(None, 1)
    if len(parts) < 2:
        return f"用法：/settings {PERSONA} <文本>（用 off 清除）"
    text = persona.sanitize(parts[1])
    if not text:
        return f"用法：/settings {PERSONA} <文本>（用 off 清除）"
    if persona.is_clear(text):
        return PERSONA_FIELD, ""
    if len(text) > persona.MAX_CHARS:
        return f"人设文本过长：上限 {persona.MAX_CHARS} 字符（当前 {len(text)}）"
    return PERSONA_FIELD, text


def render_value(field: SettingField, value: object) -> str:
    """把写入的值渲染成确认文案里的样子（与 render_settings 措辞一致）。"""
    if field.kind == "bool":
        return "开" if value else "关"
    if field.kind == "int":
        return f"{int(value)} 秒"
    if field.kind == "text":
        # 人设正文不回显到群里（群主自己刚发的，无需复读，也少一份被转发的文本）。
        return f"{len(str(value))} 字" if value else "已清除（回退到部署侧 PERSONA / 内置人格）"
    return str(value)


class CommandService:
    """命令的唯一业务入口：授权判定、参数校验与回复文本；不依赖 aiogram。"""

    def __init__(
        self,
        connection: aiosqlite.Connection,
        admins: AdminRegistry,
        *,
        settings: Settings | None = None,
        health: HealthState | None = None,
    ) -> None:
        self._connection = connection
        self._admins = admins
        self._settings = settings
        self._health = health

    async def reply_text(self, *, chat_id: int, user_id: int, command: Command) -> str | None:
        """返回要发送的文本；None 表示静默丢弃（未知命令或未装配的数据源）。"""
        if command.name == HELP:
            # 指令表公开：不知道命令怎么用是可用性问题，不设管理员门槛
            logger.info("查看指令表 chat_id=%s user_id=%s", chat_id, user_id)
            return help_text()
        if command.name not in (SETTINGS, STATS, HEALTH, CLEAR, NOTE):
            logger.debug("未实现的命令 chat_id=%s name=%s", chat_id, command.name)
            return None
        if not await self._admins.is_admin(chat_id, user_id):
            logger.info(
                "命令被拒 chat_id=%s user_id=%s name=%s 原因=not_admin", chat_id, user_id, command.name
            )
            return DENIED_TEXT
        if command.name == NOTE:
            return await self._note(chat_id=chat_id, user_id=user_id, command=command)
        if command.name == CLEAR:
            return await self._clear(chat_id=chat_id, user_id=user_id, args=command.args)
        if command.name == STATS:
            if self._settings is None:
                logger.warning("未装配配置，/stats 不可用 chat_id=%s", chat_id)
                return None
            logger.info("查看运行统计 chat_id=%s user_id=%s", chat_id, user_id)
            return await render_stats(self._connection, self._settings, chat_id=chat_id)
        if command.name == HEALTH:
            if self._health is None:
                logger.warning("未装配健康状态，/health 不可用 chat_id=%s", chat_id)
                return None
            logger.info("查看健康状态 chat_id=%s user_id=%s", chat_id, user_id)
            return render_health(await self._health.snapshot())
        # 以下都是 `/settings`：人设覆盖只认群主，其余字段仍只认管理员。
        is_owner = await self._admins.is_owner(chat_id, user_id)
        if command.args and command.args[0].casefold() == PERSONA and not is_owner:
            logger.info(
                "命令被拒 chat_id=%s user_id=%s name=%s 原因=not_owner", chat_id, user_id, command.name
            )
            return DENIED_TEXT
        if not command.args:
            group = await chat_settings.get(self._connection, chat_id)
            return render_settings(group, can_set_persona=is_owner)
        if command.args[0].casefold() == PERSONA:
            resolved = resolve_persona_setting(command.rest)
        else:
            field_names = OWNER_FIELD_NAMES if is_owner else FIELD_NAMES
            resolved = resolve_setting(command.args, field_names=field_names)
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

    async def _clear(self, *, chat_id: int, user_id: int, args: tuple[str, ...]) -> str:
        """`/clear`：只删本群消息原文（`docs/database.md` §4）；摘要、用量与统计保留。"""
        if args:
            return CLEAR_USAGE
        try:
            deleted = await messages.clear_chat(self._connection, chat_id)
        except aiosqlite.Error:
            logger.exception("群消息清理失败 chat_id=%s", chat_id)
            return CLEAR_FAILED_TEXT
        logger.info("群消息已清理 chat_id=%s user_id=%s rows=%s", chat_id, user_id, deleted)
        return f"已清理本群消息原文 {deleted} 条；群摘要保留。"

    async def _note(self, *, chat_id: int, user_id: int, command: Command) -> str:
        """`/note`：只有群主能读写本群长期记忆（docs/memory.md §6）。

        列出/查看/记住/删除都走同一条授权判定；正文经 `app/ops/notes.py` 清洗并限长，
        写入复用 `notes.upsert`（同名覆盖 version+1，FTS 同步）；失败只回固定短句。
        """
        if not await self._admins.is_owner(chat_id, user_id):
            logger.info("命令被拒 chat_id=%s user_id=%s name=note 原因=not_owner", chat_id, user_id)
            return DENIED_TEXT
        request = notes_ops.parse(command.args, command.rest)
        if isinstance(request, str):
            logger.info("笔记参数被拒 chat_id=%s user_id=%s", chat_id, user_id)
            return request
        try:
            if request.action == "list":
                rows = await notes.list_for_chat(
                    self._connection, chat_id=chat_id, limit=notes_ops.LIST_LIMIT
                )
                return notes_ops.render_list(rows)
            if request.action == "show":
                row = await notes.get(self._connection, chat_id=chat_id, name=request.name)
                return notes_ops.render_show(row) if row is not None else notes_ops.missing(request.name)
            if request.action == "delete":
                deleted = await notes.delete(self._connection, chat_id=chat_id, name=request.name)
                if not deleted:
                    return notes_ops.missing(request.name)
                logger.info("笔记已删除 chat_id=%s user_id=%s name=%s", chat_id, user_id, request.name)
                return notes_ops.render_deleted(request.name)
            # save：写入后回读一次拿权威版本号（新建 v1 / 同名覆盖 +1）。
            await notes.upsert(
                self._connection,
                chat_id=chat_id,
                name=request.name,
                text=request.text,
                tokens=term_tokens(request.text),
            )
            stored = await notes.get(self._connection, chat_id=chat_id, name=request.name)
        except aiosqlite.Error:
            logger.exception("笔记读写失败 chat_id=%s action=%s", chat_id, request.action)
            return NOTE_FAILED_TEXT
        if stored is None:
            logger.warning("笔记写入后读不到 chat_id=%s name=%s", chat_id, request.name)
            return NOTE_FAILED_TEXT
        logger.info(
            "笔记已写入 chat_id=%s user_id=%s name=%s version=%s",
            chat_id,
            user_id,
            request.name,
            stored.version,
        )
        return notes_ops.render_saved(stored)
