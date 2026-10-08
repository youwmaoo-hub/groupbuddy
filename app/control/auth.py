"""面板鉴权：口令 → 权限级别（docs/requirements.md F6.4、docs/security.md §2）。

三条不给商量的事：
- 授权只由后端判定。前端隐藏按钮只是界面礼貌，不构成任何授权；
- 口令比对用 `hmac.compare_digest`，避免按字符比较泄漏前缀信息；
- 口令只以 `Authorization: Bearer` 头传递，不走 Cookie、不进 URL：
  没有 Cookie 就没有 CSRF 面，URL 也不会把口令写进访问日志。
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from enum import IntEnum

AUTH_HEADER = "Authorization"
BEARER_PREFIX = "bearer "


class Level(IntEnum):
    """权限级别；数值可直接比较（`level < Level.ADMIN` 即只读）。"""

    NONE = 0
    VIEWER = 1
    ADMIN = 2


class ApiError(Exception):
    """面板对外错误：`message` 是可直接展示的中文说明，不含内部细节与凭据。"""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PanelAuth:
    """面板口令集合；两个都为空表示面板未配置（入口会拒绝启动）。"""

    admin_token: str = ""
    readonly_token: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.admin_token or self.readonly_token)

    def level_for(self, token: str) -> Level:
        first = token.strip()
        if not first:
            return Level.NONE
        if self.admin_token and hmac.compare_digest(first, self.admin_token):
            return Level.ADMIN
        if self.readonly_token and hmac.compare_digest(first, self.readonly_token):
            return Level.VIEWER
        return Level.NONE

    def level_from_header(self, header: str | None) -> Level:
        return self.level_for(extract_token(header))


def extract_token(header: str | None) -> str:
    """从 `Authorization: Bearer <token>` 取出令牌；格式不对一律返回空串（fail-closed）。"""
    if not header:
        return ""
    value = header.strip()
    if value.lower().startswith(BEARER_PREFIX):
        return value[len(BEARER_PREFIX) :].strip()
    return ""
