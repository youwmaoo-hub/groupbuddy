"""群设置服务：面板与 Telegram 命令通道共享的唯一读写入口（docs/architecture.md §10）。

关键约束（避免"两个入口两套规则"这类最典型的面板漏洞）：
- 字段白名单、取值解析、确认文案**直接复用** `app/ops/commands.py` 的解析函数，
  面板不会因为多写一套校验而放宽 `/settings` 的规则；
- 写库只走 `chat_settings.upsert`（单字段原子 upsert，T12），绝不做整行覆盖；
- 人设覆盖（`persona_override`）在 Telegram 侧只认群主，面板侧对应独立的
  `write:persona` 授权，由调用方显式传入 `allow_persona`，本函数只做兜底拒绝。

本模块不 import Web 框架、不读环境变量，也不返回任何凭据。
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass

import aiosqlite

from app.ops import commands, persona
from app.storage.repo import chat_settings, messages

logger = logging.getLogger(__name__)

#: 群列表默认上限：面板是运维视图，不做分页，超出部分按最近活动截断。
DEFAULT_GROUP_LIMIT = 200

#: 单字段取值的字符上限：只用于拦住异常大的请求体，合法取值另有更严格的校验。
MAX_VALUE_CHARS = 2000


class SettingError(ValueError):
    """字段或取值不合法；`str(exc)` 是可直接展示给操作者的中文说明（与 `/settings` 同源）。"""


@dataclass(frozen=True, slots=True)
class FieldInfo:
    """面板要展示的一个可写字段：含取值约束，供前端生成控件（不在前端硬编码白名单）。"""

    name: str
    column: str
    kind: str  # "bool" | "mode" | "int" | "text"
    owner_only: bool = False
    choices: tuple[str, ...] = ()
    maximum: int | None = None


@dataclass(frozen=True, slots=True)
class GroupSettings:
    """一个群的当前设置；`persona_override` 是群内人设文本（不是凭据，面板可读）。"""

    chat_id: int
    mode: str
    toggles: dict[str, bool]
    sticker_cooldown: int
    persona_override: str
    persona_chars: int
    owner_user_id: int | None
    updated_at: int | None


@dataclass(frozen=True, slots=True)
class GroupSummary:
    """群列表里的一行：设置摘要 + 该群的消息量（不给出原文，面板不做聊天记录浏览）。"""

    chat_id: int
    mode: str
    enabled_tools: tuple[str, ...]
    sticker_cooldown: int
    persona_set: bool
    messages: int
    last_message_at: int | None
    updated_at: int | None


def fields() -> tuple[FieldInfo, ...]:
    """可写字段的完整清单（顺序即面板的展示顺序）。"""
    infos = [
        FieldInfo(
            name=commands.MODE,
            column=commands.MODE,
            kind="mode",
            choices=tuple(commands.MODES),
        )
    ]
    infos.extend(
        FieldInfo(name=tool, column=column, kind="bool") for tool, column in commands.TOOL_SWITCHES
    )
    infos.append(
        FieldInfo(
            name=commands.STICKER_COOLDOWN,
            column=commands.STICKER_COOLDOWN,
            kind="int",
            maximum=commands.COOLDOWN_MAX_SECONDS,
        )
    )
    infos.append(
        FieldInfo(
            name=commands.PERSONA,
            column=commands.PERSONA,
            kind="text",
            owner_only=True,
            maximum=persona.MAX_CHARS,
        )
    )
    return tuple(infos)


def field_names(*, include_persona: bool = True) -> tuple[str, ...]:
    """面板与 `/settings` 用法文案共用的字段名清单。"""
    return tuple(info.name for info in fields() if include_persona or not info.owner_only)


def is_persona_field(name: str) -> bool:
    """是否是群内人设字段（决定需要 `write:persona` 而不是 `write:settings`）。"""
    return name.strip().casefold() == commands.PERSONA


async def read_group(connection: aiosqlite.Connection, chat_id: int) -> GroupSettings:
    """读取单个群的设置；没有记录时是默认值，不写库。"""
    row = await chat_settings.get(connection, chat_id)
    return _to_group(chat_id, row)


async def update_group(
    connection: aiosqlite.Connection,
    chat_id: int,
    *,
    field: str,
    value: str,
    allow_persona: bool,
) -> GroupSettings:
    """按 `<字段> <值>` 更新一个字段并返回更新后的完整设置。

    取值规则与 `/settings` 完全同源（`commands.resolve_setting` / `resolve_persona_setting`）；
    不合法时抛 `SettingError`，由调用方翻成 HTTP 400，文案可直接给操作者看。
    """
    if not isinstance(value, str) or len(value) > MAX_VALUE_CHARS:
        raise SettingError(f"取值过长：上限 {MAX_VALUE_CHARS} 字符")
    key = field.strip().casefold()
    if is_persona_field(key):
        if not allow_persona:
            raise SettingError(commands.DENIED_TEXT)
        resolved = commands.resolve_persona_setting(f"{commands.PERSONA} {value}")
    else:
        resolved = commands.resolve_setting((key, value), field_names="、".join(field_names()))
    if isinstance(resolved, str):
        raise SettingError(resolved)
    target, parsed = resolved
    try:
        await chat_settings.upsert(connection, chat_id, **{target.column: parsed})
    except aiosqlite.Error:
        logger.exception("面板写群设置失败 chat_id=%s 字段=%s", chat_id, target.column)
        raise SettingError(commands.WRITE_FAILED_TEXT) from None
    logger.info("面板已更新群设置 chat_id=%s 字段=%s", chat_id, target.column)
    return await read_group(connection, chat_id)


async def list_groups(
    connection: aiosqlite.Connection, *, limit: int = DEFAULT_GROUP_LIMIT
) -> list[GroupSummary]:
    """群列表：以「出现过消息的群」为主体，并入「被配置过但还没说话的群」。

    只看 `chat_settings` 会漏掉还没跑过任何命令的群，而那正是操作者最需要去配置的群。
    """
    activity = {
        int(row["chat_id"]): row for row in await messages.chat_activity(connection, limit=limit)
    }
    configured = {
        int(row["chat_id"]): row for row in await chat_settings.list_all(connection, limit=limit)
    }
    summaries: list[GroupSummary] = []
    for chat_id in sorted(set(activity) | set(configured)):
        row = {**chat_settings.DEFAULTS, **(configured.get(chat_id) or {})}
        seen = activity.get(chat_id) or {}
        override = persona.sanitize(str(row.get(commands.PERSONA) or ""))
        summaries.append(
            GroupSummary(
                chat_id=chat_id,
                mode=str(row.get(commands.MODE) or "normal"),
                enabled_tools=tuple(
                    tool for tool, column in commands.TOOL_SWITCHES if row.get(column)
                ),
                sticker_cooldown=int(row.get(commands.STICKER_COOLDOWN) or 0),
                persona_set=bool(override),
                messages=int(seen.get("messages") or 0),
                last_message_at=_int_or_none(seen.get("last_at")),
                updated_at=_int_or_none(row.get("updated_at")),
            )
        )
    summaries.sort(key=lambda item: (item.last_message_at or 0, item.chat_id), reverse=True)
    return summaries[:limit]


def as_payload(value: object) -> object:
    """把服务层数据转成可 JSON 序列化的结构（面板只负责搬运，不改语义）。"""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: as_payload(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(key): as_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_payload(item) for item in value]
    return value


def _to_group(chat_id: int, row: dict[str, object]) -> GroupSettings:
    override = persona.sanitize(str(row.get(commands.PERSONA) or ""))
    return GroupSettings(
        chat_id=chat_id,
        mode=str(row.get(commands.MODE) or "normal"),
        toggles={tool: bool(row.get(column)) for tool, column in commands.TOOL_SWITCHES},
        sticker_cooldown=int(row.get(commands.STICKER_COOLDOWN) or 0),
        persona_override=override,
        persona_chars=len(override),
        owner_user_id=_int_or_none(row.get("owner_user_id")),
        updated_at=_int_or_none(row.get("updated_at")),
    )


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
