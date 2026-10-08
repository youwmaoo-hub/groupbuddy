"""四种模式（docs/token.md §5）的唯一权威表：窗口 / 输出上限 / 工具档位 / 贴纸。

模式由群管理员通过 `/settings mode <值>` 设置（`app/ops/commands.py`），读取方：
`ContextBuilder`（窗口）、`Responder`（输出上限）、`Policy`（工具档位）。
未知或缺失的模式一律按 `normal` 处理（fail-safe，也是升级前的默认行为）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.config import Settings

ECONOMY = "economy"
NORMAL = "normal"
SMART = "smart"
UNRESTRICTED = "unrestricted"

#: 合法模式名（唯一来源；`app/ops/commands.py` 的字段校验也用它）。
MODES: tuple[str, ...] = (ECONOMY, NORMAL, SMART, UNRESTRICTED)

#: economy 的"短"输出上限（docs/token.md §5）。
ECONOMY_MAX_OUTPUT_TOKENS = 256

#: 输出上限口径：短 / 用 `LLM_MAX_OUTPUT_TOKENS` / 不限（不发送 max_tokens）。
SHORT = "short"
CONFIGURED = "configured"
UNLIMITED = "unlimited"

#: economy 只放行的等级（docs/security.md §2 的 L0 只读）。
READONLY_LEVEL = "L0"


@dataclass(frozen=True, slots=True)
class ModeProfile:
    """一种模式对四件事的影响（docs/token.md §5 的四个列）。"""

    name: str
    window: int | None  # None = 沿用意图分档（只有 normal 这样）
    output: str  # SHORT | CONFIGURED | UNLIMITED
    levels: frozenset[str] | None  # None = 不限等级，按群开关
    readonly_regardless_of_switch: bool  # smart：L0 只读工具无视开关仍可用
    ignore_switches: bool  # unrestricted：放行全部已注册工具
    stickers: bool


PROFILES: dict[str, ModeProfile] = {
    # 最小窗口、只读工具、短输出、贴纸关
    ECONOMY: ModeProfile(
        ECONOMY,
        window=10,
        output=SHORT,
        levels=frozenset({READONLY_LEVEL}),
        readonly_regardless_of_switch=False,
        ignore_switches=False,
        stickers=False,
    ),
    # 现状：窗口按意图分档、工具按群开关、正常输出
    NORMAL: ModeProfile(
        NORMAL,
        window=None,
        output=CONFIGURED,
        levels=None,
        readonly_regardless_of_switch=False,
        ignore_switches=False,
        stickers=True,
    ),
    # 最长窗口 + 群设定之外再多给 L0 只读工具
    SMART: ModeProfile(
        SMART,
        window=50,
        output=CONFIGURED,
        levels=None,
        readonly_regardless_of_switch=True,
        ignore_switches=False,
        stickers=True,
    ),
    # 全部工具（模式本身只有管理员能设置）、输出不限
    UNRESTRICTED: ModeProfile(
        UNRESTRICTED,
        window=50,
        output=UNLIMITED,
        levels=None,
        readonly_regardless_of_switch=False,
        ignore_switches=True,
        stickers=True,
    ),
}


def normalize(value: object) -> str:
    """把配置值收敛成已知模式名；未知、空值、非字符串都按 `normal`。"""
    name = str(value or "").strip().casefold()
    return name if name in PROFILES else NORMAL


def profile_for(value: object) -> ModeProfile:
    """取档位：可传 `chat_settings` 行（含 `mode` 的映射）或模式名本身。"""
    if isinstance(value, Mapping):
        return PROFILES[normalize(value.get("mode"))]
    return PROFILES[normalize(value)]


def output_limit(profile: ModeProfile, settings: Settings) -> int | None:
    """该模式的 `max_tokens`：整数或 None（None = 不发送，即不限）。"""
    if profile.output == SHORT:
        return ECONOMY_MAX_OUTPUT_TOKENS
    if profile.output == CONFIGURED:
        return settings.llm_max_output_tokens
    return None
