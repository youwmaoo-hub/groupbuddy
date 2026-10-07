"""host_info：只读、最小字段集的运行环境信息（docs/tools.md §host_info）。

只允许 `cpu` / `memory` / `disk_free` / `python` / `uptime_s` 五个字段；
不读环境变量、不列进程、不查网络接口、不含主机名/用户名/IP/目录路径。
"""

from __future__ import annotations

import os
import platform
import shutil
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.tools.registry import ToolContext, ToolSpec

#: 冻结字段集与顺序（docs/tools.md §2 冻结表）
FIELDS: tuple[str, ...] = ("cpu", "memory", "disk_free", "python", "uptime_s")

_PROCESS_START = time.monotonic()


class HostInfoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[str] = Field(default_factory=list, max_length=len(FIELDS))

    @field_validator("fields")
    @classmethod
    def _clean_fields(cls, value: list[str]) -> list[str]:
        """只接受冻结字段集；去重且保持请求顺序；未知字段由 executor 映射为 invalid_arguments。"""
        cleaned: list[str] = []
        for item in value:
            name = str(item).strip()
            if name not in FIELDS:
                raise ValueError("未知字段")
            if name not in cleaned:
                cleaned.append(name)
        return cleaned


class HostInfoTool:
    spec = ToolSpec(
        name="host_info",
        level="L4",
        description=(
            "查看运行环境的最小信息：CPU 核数、内存总量、磁盘剩余空间、Python 版本、运行时长。"
            "可选 fields 指定字段：cpu / memory / disk_free / python / uptime_s。"
            "返回数值，不返回环境变量、进程、网络接口、主机名或路径。"
        ),
        args_model=HostInfoArgs,
        timeout_seconds=2.0,
    )

    def __init__(self, data_dir: Path | str | None = None, *, clock=None) -> None:
        #: 只用于取磁盘剩余空间，路径本身绝不进入返回值
        self._data_dir = Path(data_dir) if data_dir is not None else Path.cwd()
        self._clock = clock or time.monotonic

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        wanted = tuple(getattr(args, "fields", ())) or FIELDS  # type: ignore[arg-type]
        values: dict[str, object] = {
            "cpu": _cpu_count(),
            "memory": _memory_total(),
            "disk_free": _disk_free(self._data_dir),
            "python": platform.python_version(),
            "uptime_s": _uptime_seconds(self._clock()),
        }
        return {name: values[name] for name in wanted}


def _cpu_count() -> int | None:
    """CPU 核数；拿不到返回 None。"""
    try:
        return os.cpu_count()
    except (NotImplementedError, OSError):
        return None


def _memory_total() -> int | None:
    """内存总量（字节）；只问操作系统，不读环境变量；平台上不可用返回 None。"""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, ValueError, OSError):
        return None
    if not isinstance(pages, int) or not isinstance(page_size, int) or pages <= 0 or page_size <= 0:
        return None
    return pages * page_size


def _disk_free(path: Path) -> int | None:
    """`path` 所在文件系统的剩余空间（字节）；拿不到返回 None。"""
    try:
        return int(shutil.disk_usage(path).free)
    except OSError:
        return None


def _uptime_seconds(now: float) -> int:
    """宿主机运行时长（Linux 读 `/proc/uptime`）；读不到时退回本进程运行时长。"""
    try:
        with open("/proc/uptime", encoding="ascii") as handle:
            return max(0, int(float(handle.read().split()[0])))
    except (OSError, ValueError, IndexError):
        return max(0, int(now - _PROCESS_START))
