"""工作区路径与文件安全：read_file / write_file 的唯一共享实现（docs/security.md §3、§11）。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from app.tools.registry import ToolError

PATH_ERROR = "path_outside_workspace"
NOT_FOUND = "not_found"
INVALID = "invalid_arguments"
TOO_LARGE = "too_large"

MAX_FILE_BYTES = 1024 * 1024  # 单个文件上限：读与写各自适用（docs/security.md §3）
MAX_READ_LINES = 200  # 单次读取行数上限（docs/tools.md §4）
READ_MAX_BYTES = 16 * 1024  # 单次读取返回字节上限（200 行 × 80 字节的余量）


def resolve_path(workspace_root: Path, chat_id: int, user_path: str) -> tuple[Path, str]:
    """把模型给的相对路径解析到本群 workspace 内；任何越界直接 ToolError。

    返回 (绝对路径, workspace 内相对 POSIX 路径)；错误消息永不回显宿主机绝对路径。
    """
    raw = str(user_path).strip()
    if not raw or "\x00" in raw:
        raise ToolError(PATH_ERROR, "路径不合法")
    if raw.startswith(("/", "\\")) or "\\" in raw or ":" in raw:
        raise ToolError(PATH_ERROR, "只允许 workspace 内的 / 分隔相对路径")

    parts: list[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ToolError(PATH_ERROR, "路径不能包含 ..")
        if part in (".", "..") or part != part.strip():
            raise ToolError(PATH_ERROR, "路径不合法")
        parts.append(part)
    if not parts:
        raise ToolError(PATH_ERROR, "路径不能为空")

    base = workspace_root / str(chat_id)
    base.mkdir(parents=True, exist_ok=True)
    base = base.resolve()

    current = base
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ToolError(PATH_ERROR, "不支持符号链接")

    target = current.resolve()
    if not target.is_relative_to(base):
        raise ToolError(PATH_ERROR, "路径越界")
    return target, PurePosixPath(*parts).as_posix()


def workspace_dir(workspace_root: Path, chat_id: int) -> Path:
    """每群 workspace 根：创建 + resolve + 复核仍在本实例 workspace 根内（沙箱挂载源）。"""
    base = workspace_root / str(chat_id)
    base.mkdir(parents=True, exist_ok=True)
    if base.is_symlink():
        raise ToolError(PATH_ERROR, "不支持符号链接")
    resolved = base.resolve()
    root = workspace_root.resolve()
    if not resolved.is_relative_to(root):
        raise ToolError(PATH_ERROR, "工作区路径越界")
    return resolved


def read_text_file(path: Path) -> str:
    """读取 UTF-8 文本；超限 too_large，非文本 invalid_arguments。"""
    if not path.is_file():
        raise ToolError(NOT_FOUND, "路径不存在或不是普通文件")
    reject_hardlink(path)
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ToolError(TOO_LARGE, "文件超过 1 MB 上限")
    try:
        data = path.read_bytes()
    except OSError:
        raise ToolError(NOT_FOUND, "文件读取失败") from None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ToolError(INVALID, "只支持 UTF-8 文本文件") from None


def atomic_write_text(path: Path, content: str) -> tuple[int, str | None]:
    """覆盖前把旧内容复制为 <name>.bak（只保留一层），再临时文件 + fsync + os.replace。"""
    data = content.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ToolError(TOO_LARGE, "单次写入超过 1 MB 上限")
    parent = path.parent
    if not parent.is_dir():
        raise ToolError(NOT_FOUND, "上级目录不存在")

    backup_name: str | None = None
    if path.exists():
        if not path.is_file():
            raise ToolError(NOT_FOUND, "路径不存在或不是普通文件")
        reject_hardlink(path)
        backup = path.with_name(path.name + ".bak")
        if backup.exists() and (backup.is_symlink() or not backup.is_file()):
            raise ToolError(PATH_ERROR, "备份路径不可写")
        if backup.is_symlink():
            raise ToolError(PATH_ERROR, "备份路径不可写")
        shutil.copyfile(path, backup)
        backup_name = backup.name

    handle, temp_name = tempfile.mkstemp(dir=parent, prefix=".write-", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise ToolError("internal_error", "写入失败") from None
    _fsync_dir(parent)
    return len(data), backup_name


def reject_hardlink(path: Path) -> None:
    """硬链接可能指向 workspace 外的文件（docs/security.md §11 第 2 条）。"""
    try:
        links = path.stat().st_nlink
    except OSError:
        raise ToolError(NOT_FOUND, "路径不存在或不是普通文件") from None
    if links > 1:
        raise ToolError(PATH_ERROR, "不支持硬链接")


def _fsync_dir(path: Path) -> None:
    """目录 fsync 只在 POSIX 有意义；Windows 打不开目录，失败忽略。"""
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
