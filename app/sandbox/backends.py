"""容器运行时后端：探测一次、运行期不再探测（docs/security.md §4、docs/deployment.md §10）。

- argv 全部来自 app/sandbox/spec.py 的白名单，永不使用 shell 字符串；
- 子进程环境由 Settings.subprocess_env() 提供，绝不含密钥；
- 找不到可用运行时一律 fail-closed（UnavailableBackend）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.sandbox.spec import kill_argv, list_argv, remove_argv

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_SECONDS = 5.0
QUICK_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class CommandResult:
    """一次运行的收尾状态；stdout/stderr 由后端写入调用方给的临时文件。"""

    exit_code: int
    timed_out: bool = False


class SandboxBackend(Protocol):
    name: str
    binary: str

    def available(self) -> bool: ...

    def supports_workspace_write(self) -> bool: ...

    async def run(
        self,
        argv: list[str],
        *,
        env: dict[str, str],
        stdout_path: Path,
        stderr_path: Path,
        timeout: float,
    ) -> CommandResult: ...

    async def cleanup(self, container_name: str) -> None: ...

    async def list_containers(self) -> list[str]: ...

    async def close(self) -> None: ...


async def _spawn(argv: list[str], *, env: dict[str, str], capture: bool) -> tuple[int, str]:
    """最小的子进程封装：无 shell、无 stdin、可选捕获输出。"""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
        env=env,
    )
    stdout, stderr = await proc.communicate()
    text = (stdout or b"").decode("utf-8", "replace") + (stderr or b"").decode("utf-8", "replace")
    return proc.returncode if proc.returncode is not None else -1, text


class CliBackend:
    """podman/docker CLI 后端（唯一真实实现）。"""

    def __init__(
        self,
        binary: str,
        *,
        version: str = "",
        keep_id: bool = False,
        host_user: str | None = None,
        supports_workspace: bool = False,
        base_env: dict[str, str] | None = None,
    ) -> None:
        self.name = Path(binary).name
        self.binary = binary
        self.version = version
        # CLI 自己的环境（列表/清理用）：白名单拷贝，绝不含密钥
        self._env = dict(base_env or {})
        # keep-id：rootless Podman 下把宿主用户映射进容器，容器内非 root 用户可写挂载目录
        self.keep_id = keep_id
        self.host_user = host_user
        self._supports_workspace = supports_workspace

    def available(self) -> bool:
        return True

    def supports_workspace_write(self) -> bool:
        return self._supports_workspace

    async def run(
        self,
        argv: list[str],
        *,
        env: dict[str, str],
        stdout_path: Path,
        stderr_path: Path,
        timeout: float,
    ) -> CommandResult:
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=env,
            )
            try:
                code = await asyncio.wait_for(proc.wait(), timeout)
            except (asyncio.TimeoutError, TimeoutError):
                with contextlib.suppress(ProcessLookupError, OSError):
                    proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()
                return CommandResult(exit_code=-1, timed_out=True)
        return CommandResult(exit_code=code if code is not None else -1)

    async def cleanup(self, container_name: str) -> None:
        for argv in (kill_argv(self.binary, container_name), remove_argv(self.binary, container_name)):
            with contextlib.suppress(Exception):
                await asyncio.wait_for(_spawn(argv, env=self._env, capture=True), QUICK_TIMEOUT_SECONDS)

    async def list_containers(self) -> list[str]:
        code, text = await asyncio.wait_for(
            _spawn(list_argv(self.binary), env=self._env, capture=True), QUICK_TIMEOUT_SECONDS
        )
        if code != 0:
            raise RuntimeError("列出容器失败")
        return [line.strip() for line in text.splitlines() if line.strip()]

    async def close(self) -> None:
        return None


class UnavailableBackend:
    """没有任何可用运行时：所有调用 fail-closed（绝不回退宿主机执行）。"""

    name = "none"
    binary = "podman"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def available(self) -> bool:
        return False

    def supports_workspace_write(self) -> bool:
        return False

    async def run(self, argv: list[str], **kwargs: object) -> CommandResult:
        raise RuntimeError(self.reason)

    async def cleanup(self, container_name: str) -> None:
        return None

    async def list_containers(self) -> list[str]:
        return []

    async def close(self) -> None:
        return None


class FakeBackend:
    """离线测试用假后端：记录 argv/环境/路径，不启动任何进程。"""

    name = "fake"
    binary = "podman"

    def __init__(
        self,
        *,
        available: bool = True,
        supports_workspace_write: bool = True,
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
        timed_out: bool = False,
        stale: tuple[str, ...] = (),
        delay: float = 0.0,
        hang: bool = False,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.cleaned: list[str] = []
        self._available = available
        self._supports_workspace = supports_workspace_write
        self._exit_code = exit_code
        self._stdout = stdout
        self._stderr = stderr
        self._timed_out = timed_out
        self._stale = stale
        self._delay = delay
        self._hang = hang

    def available(self) -> bool:
        return self._available

    def supports_workspace_write(self) -> bool:
        return self._supports_workspace

    async def run(
        self,
        argv: list[str],
        *,
        env: dict[str, str],
        stdout_path: Path,
        stderr_path: Path,
        timeout: float,
    ) -> CommandResult:
        self.calls.append(
            {
                "argv": list(argv),
                "env": dict(env),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "timeout": timeout,
            }
        )
        if self._hang:
            await asyncio.sleep(3600)
        if self._delay:
            await asyncio.sleep(self._delay)
        stdout_path.write_bytes(self._stdout.encode("utf-8"))
        stderr_path.write_bytes(self._stderr.encode("utf-8"))
        return CommandResult(exit_code=self._exit_code, timed_out=self._timed_out)

    async def cleanup(self, container_name: str) -> None:
        self.cleaned.append(container_name)

    async def list_containers(self) -> list[str]:
        return list(self._stale)

    async def close(self) -> None:
        return None


def _probe_version(binary: str, env: dict[str, str]) -> str | None:
    try:
        done = subprocess.run(  # noqa: S603 - 固定参数、无 shell
            [binary, "--version"],
            capture_output=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (done.stdout + done.stderr).decode("utf-8", "replace").strip()
    return text.splitlines()[0] if text else ""


def _host_ids() -> tuple[int, int] | None:
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        return int(os.getuid()), int(os.getgid())  # type: ignore[attr-defined]
    return None


def build_backend(settings) -> SandboxBackend:
    """启动时探测一次并固定（SANDBOX_BACKEND=auto：Podman 优先、Docker 备选）。"""
    choice = settings.sandbox_backend
    if choice == "none":
        logger.warning("沙箱已关闭（SANDBOX_BACKEND=none）：run_code 返回 sandbox_unavailable")
        return UnavailableBackend("SANDBOX_BACKEND=none")
    env = settings.subprocess_env()
    candidates = ("podman", "docker") if choice == "auto" else (choice,)
    for name in candidates:
        binary = shutil.which(name)
        if not binary:
            continue
        version = _probe_version(binary, env)
        if version is None:
            logger.warning("容器运行时探测失败，跳过 backend=%s", name)
            continue
        ids = _host_ids()
        rootless = name == "podman" and ids is not None and ids[0] != 0
        keep_id = bool(rootless and settings.sandbox_tier_b != "off")
        host_user = f"{ids[0]}:{ids[1]}" if (keep_id and ids is not None) else None
        logger.info(
            "沙箱后端就绪 backend=%s version=%s workspace=%s keep_id=%s",
            name,
            version,
            keep_id,
            keep_id,
        )
        return CliBackend(
            binary,
            version=version,
            keep_id=keep_id,
            host_user=host_user,
            supports_workspace=keep_id,
            base_env=env,
        )
    logger.error("未找到可用容器运行时：run_code 返回 sandbox_unavailable（不退化到宿主机执行）")
    return UnavailableBackend("未找到可用容器运行时（podman/docker）")
