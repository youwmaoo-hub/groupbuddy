"""权限判定唯一出口：等级 → 本群开关 → 可用工具清单（docs/security.md §2）。"""

from __future__ import annotations

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
        """已注册 ∩ 本群允许；注入 System3 与 tools 参数的唯一来源。"""
        return tuple(name for name in self._registry.names() if self._enabled(name, context))

    def check(self, name: str, context: ToolContext) -> str | None:
        """允许返回 None，否则返回错误码（目前只有 permission_denied）。"""
        if self._registry.get(name) is None:
            return DENIED
        if not self._enabled(name, context):
            return DENIED
        return None

    @staticmethod
    def _enabled(name: str, context: ToolContext) -> bool:
        """第 2 步：该工具等级在本群是否开启；未知工具一律拒绝（fail-closed）。

        第 3 步（触发者身份）随阶段 8 的群主命令/权限一起落地：阶段 3 只有 L0 工具。
        """
        column = POLICY_COLUMNS.get(name)
        if column is None:
            return name in POLICY_COLUMNS
        return bool(int(context.group.get(column, 0) or 0))
