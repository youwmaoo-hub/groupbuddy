"""凭据服务：面板可以**写入/清除**凭据，永远不能读回（docs/requirements.md F6.3）。

设计要点（与 docs/security.md §2 一致）：
- 读取方向只提供 `configured`（是否已配置）与来源（`.env` 还是环境变量），
  既不返回明文，也不返回「掩码片段」——掩码片段本身就是一次信息泄露；
- 写入方向只认白名单里的键名，值里出现换行一律拒绝：否则一个请求就能往 `.env`
  注入任意环境变量（例如把 `LLM_BASE_URL` 指到别处）；
- 写 `.env` 用「同目录临时文件 + `os.replace`」原子替换，并尽量收紧为 0600；
- 改完凭据必须重启机器人进程才生效（`.env` 只在启动时读取），面板不复述、不代跑重启。
"""

from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)

#: 允许面板管理的凭据键（环境变量名 → 人类可读标签）。顺序即展示顺序。
SECRET_SPECS: tuple[tuple[str, str], ...] = (
    ("BOT_TOKEN", "Telegram Bot Token（@BotFather 申请）"),
    ("LLM_API_KEY", "模型 API Key（OpenAI 兼容服务）"),
)

#: 凭据值的字符上限：只在拦住异常大的请求体，不代替服务端的合法性校验。
MAX_SECRET_CHARS = 4096


class CredentialError(ValueError):
    """凭据操作不合法；`str(exc)` 是可直接展示的中文说明，且绝不包含值本身。"""


@dataclass(frozen=True, slots=True)
class CredentialStatus:
    """一条凭据的状态：只有「有没有」，没有「是什么」。"""

    name: str
    label: str
    configured: bool
    source: str  # ".env" | "环境变量" | "未配置"


def status(settings: Settings, *, env_path: Path) -> list[CredentialStatus]:
    """读取全部凭据的配置状态（不含任何明文或掩码片段）。"""
    in_file = _keys_in_env_file(env_path)
    result: list[CredentialStatus] = []
    for name, label in SECRET_SPECS:
        configured = bool(str(_value_of(settings, name) or "").strip())
        if not configured:
            source = "未配置"
        elif name in in_file:
            source = ".env"
        else:
            source = "环境变量"
        result.append(CredentialStatus(name=name, label=label, configured=configured, source=source))
    return result


def write(*, env_path: Path, name: str, value: str) -> None:
    """把一条凭据写进 `.env`（存在即替换该行，不存在则追加）；只写不读。"""
    key = _checked_name(name)
    clean = _checked_value(value)
    lines = _read_lines(env_path)
    replacement = f"{key}={clean}"
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.split("=", 1)[0].strip() == key:
            lines[index] = replacement
            break
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(replacement)
    _write_lines(env_path, lines)
    logger.info("面板已写入凭据 key=%s（值不记录）", key)


def clear(*, env_path: Path, name: str) -> None:
    """删除 `.env` 里的一条凭据；键不存在也算成功（幂等）。"""
    key = _checked_name(name)
    lines = _read_lines(env_path)
    remaining = [
        line
        for line in lines
        if not (
            not line.lstrip().startswith("#")
            and "=" in line
            and line.split("=", 1)[0].strip() == key
        )
    ]
    if remaining == lines:
        logger.info("面板清除凭据 key=%s（原本不存在）", key)
        return
    _write_lines(env_path, remaining)
    logger.info("面板已清除凭据 key=%s", key)


def _checked_name(name: str) -> str:
    key = str(name or "").strip().upper()
    if key not in {spec[0] for spec in SECRET_SPECS}:
        raise CredentialError(f"不支持的凭据名：{name}")
    return key


def _checked_value(value: str) -> str:
    if not isinstance(value, str):
        raise CredentialError("凭据值必须是字符串")
    clean = value.strip()
    if not clean:
        raise CredentialError("凭据值不能为空（要清除请用删除）")
    if len(clean) > MAX_SECRET_CHARS:
        raise CredentialError(f"凭据值过长：上限 {MAX_SECRET_CHARS} 字符")
    if "\n" in clean or "\r" in clean:
        raise CredentialError("凭据值不能包含换行")
    return clean


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise CredentialError(f"读取 {path.name} 失败：{error.strerror or error}") from error


def _write_lines(path: Path, lines: list[str]) -> None:
    """原子替换 + 尽量收紧权限；写入失败只报固定短句（不泄露路径细节以外的内容）。"""
    payload = "\n".join(lines) + "\n"
    temporary = path.with_name(path.name + ".panel.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(payload, encoding="utf-8")
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - 清理失败不影响错误语义
            logger.warning("面板写入凭据后清理临时文件失败 path=%s", temporary)
        raise CredentialError(f"写入失败：{error.strerror or error}") from error


def _keys_in_env_file(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in _read_lines(path):
        stripped = line.lstrip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def _value_of(settings: Settings, name: str) -> object:
    return getattr(settings, name.lower(), "")
