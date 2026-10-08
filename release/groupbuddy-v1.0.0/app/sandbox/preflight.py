"""代码预扫描：辅助提示，不是安全边界（docs/security.md §4）。

真正的边界由 app/sandbox 的容器参数提供；这里只给日志与模型一点提示。
"""

from __future__ import annotations

import re

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("os.system", re.compile(r"os\.system\s*\(")),
    ("subprocess", re.compile(r"\bsubprocess\b")),
    ("eval/exec", re.compile(r"\b(eval|exec)\s*\(")),
    ("动态导入", re.compile(r"__import__\s*\(|importlib\.import_module")),
    ("网络", re.compile(r"\b(socket|urllib|requests|httpx|aiohttp)\b")),
    ("文件写入", re.compile(r"open\s*\([^)]*['\"]w")),
    ("宿主路径", re.compile(r"['\"]/(etc|proc|sys|var/run|root|home)/")),
    ("docker/podman", re.compile(r"\b(docker|podman)\b")),
)


def scan(code: str) -> list[str]:
    """返回可疑点标签列表（只用于日志与提示，调用方不得据此放行或拒绝）。"""
    return [label for label, pattern in PATTERNS if pattern.search(code or "")]
