"""群记忆笔记（notes）：命令侧的解析、清洗与文案（docs/memory.md §6、docs/security.md §2.1）。

笔记是**长期事实**（群规、偏好、项目状态），不参与短期窗口：由群主通过 `/note` 增删查，
写库与 FTS 同步在 `app/storage/repo/notes.py`，检索（`summaries` + `notes`）在
`app/session/retrieval.py`，注入位置在 `app/session/context.py` 的记忆块。

本模块只做纯文本处理与渲染：无 aiogram、无数据库、无授权判定（授权在命令层），
因此未来 Web 控制面板可以直接复用同一套规则。
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.ops.text import single_line
from app.storage.repo_models import NoteRow

#: 单条笔记正文上限（字符数，按清洗后的单行文本计算；与 docs/memory.md §6 一致）。
MAX_CHARS = 500

#: 笔记名上限：名字只用来定位一条笔记。
MAX_NAME_CHARS = 50

#: `/note` 列表一次最多列出多少条（超出只影响回显，不影响存储）。
LIST_LIMIT = 50

#: 保留字：与「列出全部」「删除」的语法冲突，不能用作笔记名。
LIST_WORDS = frozenset({"list", "列表", "全部"})
DELETE_WORDS = frozenset({"del", "delete", "删除", "忘掉"})

USAGE_TEXT = (
    "用法：/note（列出全部）、/note <名称>（查看）、"
    "/note <名称> <内容>（记住）、/note del <名称>（删除）"
)

Action = Literal["list", "show", "save", "delete"]


@dataclass(frozen=True, slots=True)
class Request:
    """已解析的 `/note` 请求（授权判定之前，纯语法）。"""

    action: Action
    name: str = ""
    text: str = ""


def sanitize(text: str) -> str:
    """笔记正文/名字的单行化：与命令的其余文本（人设）共用同一套清洗。"""
    return single_line(text)


def parse(args: tuple[str, ...], rest: str) -> Request | str:
    """解析 `/note` 参数：成功返回 `Request`，失败返回一条可直接回复的文案（不写库）。

    `rest` 是命令名之后的原文，用来取可含空格的正文字；`args` 用于判断子命令与名称。
    """
    if not args:
        return Request(action="list")
    head = args[0].casefold()
    if head in LIST_WORDS:
        return Request(action="list") if len(args) == 1 else USAGE_TEXT
    if head in DELETE_WORDS:
        if len(args) != 2:
            return USAGE_TEXT
        return _named("delete", args[1])
    request = _named("show", args[0])
    if isinstance(request, str):
        return request
    text = sanitize(rest[len(args[0]) :])
    if not text:
        return request
    if len(text) > MAX_CHARS:
        return f"笔记内容过长：上限 {MAX_CHARS} 字符（当前 {len(text)}）"
    return Request(action="save", name=request.name, text=text)


def _named(action: Action, raw_name: str) -> Request | str:
    """校验笔记名（保留字与长度），返回对应请求或用法文案。"""
    name = sanitize(raw_name)
    if not name or name.casefold() in LIST_WORDS or name.casefold() in DELETE_WORDS:
        return USAGE_TEXT
    if len(name) > MAX_NAME_CHARS:
        return f"笔记名过长：上限 {MAX_NAME_CHARS} 字符（当前 {len(name)}）"
    return Request(action=action, name=name)


def render_list(rows: Sequence[NoteRow]) -> str:
    """列出本群笔记：名称、版本、字数与更新时间；正文不在列表里复读。"""
    if not rows:
        return f"本群还没有笔记。\n{USAGE_TEXT}"
    lines = [f"本群笔记（{len(rows)} 条）"]
    lines.extend(
        f"{row.name}（v{row.version}，{len(row.text)} 字，{stamp(row.updated_at)}）" for row in rows
    )
    lines.append("用 /note <名称> 查看内容，/note del <名称> 删除。")
    return "\n".join(lines)


def render_show(row: NoteRow) -> str:
    """查看一条笔记的正文（只有群主能走到这里）。"""
    return f"笔记「{row.name}」（v{row.version}，{len(row.text)} 字，{stamp(row.updated_at)}）\n{row.text}"


def render_saved(row: NoteRow) -> str:
    """写入后的确认：只回名称、版本与字数（同名人设不回显正文的口径一致）。"""
    return f"{'已更新' if row.version > 1 else '已记住'}笔记「{row.name}」（v{row.version}，{len(row.text)} 字）。"


def render_deleted(name: str) -> str:
    return f"已删除笔记「{name}」。"


def missing(name: str) -> str:
    """共同的「查无此笔记」文案：删除与查看共用。"""
    return f"没有这条笔记：{name}"


def stamp(moment: int) -> str:
    """库内 Unix 秒 → 本地时间文本（只用于回显，不参与检索与排序）。"""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(moment)))
    except (OSError, OverflowError, ValueError):  # 极端的坏数据只影响回显
        return "时间未知"
