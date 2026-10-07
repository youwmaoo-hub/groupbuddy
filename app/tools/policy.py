"""权限判定唯一出口：等级 → 本群开关 → 模式工具档位 → 可用工具清单（docs/security.md §2）。"""

from __future__ import annotations

from app import modes
from app.tools.registry import ToolContext, ToolRegistry

# 等级映射的唯一权威表：docs/security.md §2（L0–L4）。None = 无群开关，人人可用。
POLICY_COLUMNS: dict[str, str | None] = {
    "calc": None,
    "search_web": "allow_search",
    "read_file": "allow_read",
    "write_file": "allow_write",
    "send_sticker": "allow_sticker",
    "run_code": "allow_code",
    "host_info": "allow_host_info",
}

DENIED = "permission_denied"


class Policy:
    """只读判定，不写库、不调模型；模型不能提升自己的权限。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def allowed_names(self, context: ToolContext) -> tuple[str, ...]:
        """已注册 ∩ 本群允许 ∩ 模式档位；注入 System3 与 tools 参数的唯一来源。"""
        return tuple(name for name in self._registry.names() if self._enabled(name, context))

    def check(self, name: str, context: ToolContext) -> str | None:
        """允许返回 None，否则返回错误码（目前只有 permission_denied）。"""
        if self._registry.get(name) is None:
            return DENIED
        if not self._enabled(name, context):
            return DENIED
        return None

    def _enabled(self, name: str, context: ToolContext) -> bool:
        """第 2 步：该工具在本群是否开启；未知工具一律拒绝（fail-closed）。

        模式档位（docs/token.md §5）叠加在本群开关之上：
        economy 只放 L0 且贴纸关，smart 额外放行 L0 只读，unrestricted 放行全部工具。
        模式本身只有群管理员能设置（`/settings mode`），模型不能提升自己的权限。
        """
        column = POLICY_COLUMNS.get(name)
        if column is None and name not in POLICY_COLUMNS:
            return False
        profile = modes.profile_for(context.group)
        tool = self._registry.get(name)
        level = tool.spec.level if tool is not None else None
        if not profile.stickers and name == "send_sticker":
            return False
        if profile.levels is not None and level not in profile.levels:
            return False
        if profile.ignore_switches:
            return True
        if column is None:
            return True
        if bool(int(context.group.get(column, 0) or 0)):
            return True
        return profile.readonly_regardless_of_switch and level == modes.READONLY_LEVEL
