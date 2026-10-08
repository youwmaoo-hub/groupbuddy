"""群级人设（Persona）：唯一的读取与清洗入口（docs/persona.md §2、docs/security.md §2.1）。

优先级：本群 `chat_settings.persona_override` > 部署侧 `PERSONA` > 内置 `GLOBAL_PERSONA`。
本模块只决定「哪段文本生效」与「允许写入什么文本」——注入位置由 `app/llm/prompts.py` 决定，
且只替换 system prompt 的「## 全局人格」段；人设不决定是否说话、工具与权限（docs/persona.md §3）。

- `resolve`：读取入口（`app/session/context.py` 调用）。
- `sanitize` / `is_clear` / `MAX_CHARS`：写入入口（`app/ops/commands.py` 调用）；
  未来 Web 控制面板直接复用它，不必再实现一遍规则。
"""

from __future__ import annotations

from app.ops.text import single_line

#: 单群人设文本上限（字符数，按清洗后的单行文本计算）。
MAX_CHARS = 500

#: 表示「清除本群人设、回退到部署侧 PERSONA」的值。
CLEAR_VALUES = frozenset({"off", "关"})


def sanitize(text: str) -> str:
    """把任意输入压成单行：控制字符（含换行、制表、C1）折成空格，空白归一化，去首尾。

    人设只进 system prompt 的一个段落，多行文本会破坏段结构，因此在写入侧就折平。
    实现与人设无关，交给 `app/ops/text.single_line`（笔记正文用同一套规则）。
    """
    return single_line(text)


def is_clear(text: str) -> bool:
    """`sanitize` 之后的文本是否表示清除本群人设（`off` / `关`，大小写不敏感）。"""
    return text.casefold() in CLEAR_VALUES


def resolve(group: dict[str, object] | None, deploy_persona: str) -> str:
    """本群覆盖 > 部署侧 `PERSONA`；两者都没有时返回空串，由 `prompts` 回退内置人格。"""
    override = sanitize(str((group or {}).get("persona_override") or ""))
    if override:
        return override
    return str(deploy_persona or "").strip()
