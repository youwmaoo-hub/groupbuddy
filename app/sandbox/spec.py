"""沙箱固定参数与 argv 白名单（docs/security.md §4）。

模型无法影响这里的任何取值：镜像、挂载、网络、资源上限、运行时参数全部由程序决定。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CONTAINER_LABEL = "groupbuddy=1"
CONTAINER_PREFIX = "cx-"
DEFAULT_IMAGE = "python:3.12-slim"
SANDBOX_USER = "65534:65534"  # nobody:nogroup，仅用于 Tier A（无挂载）
WORKSPACE_MOUNT = "/workspace"
NOFILE = "64:64"


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """容器参数；全部来自设置且由程序拼装，模型只能提交 code。"""

    image: str = DEFAULT_IMAGE
    memory_mb: int = 256
    cpus: float = 0.5
    pids: int = 64
    tmpfs_size_mb: int = 16
    fsize_bytes: int = 8 * 1024 * 1024
    user: str = SANDBOX_USER

    @property
    def memory(self) -> str:
        return f"{self.memory_mb}m"

    @property
    def cpus_text(self) -> str:
        return f"{self.cpus:g}"


def build_argv(
    binary: str,
    spec: SandboxSpec,
    container_name: str,
    code: str,
    *,
    workspace_dir: Path | None = None,
    keep_id: bool = False,
    host_user: str | None = None,
) -> list[str]:
    """固定顺序的 argv 白名单；code 作为单个参数传入，永不经过 shell。

    `--workdir /workspace` 只在真的挂载了 workspace_dir 时出现：无挂载的 Tier A 容器里
    没有该路径，Podman 会因 --workdir 指向不存在的目录而拒绝启动（exit 126），
    根本不会执行探针代码。
    """
    argv: list[str] = [
        binary,
        "run",
        "--rm",
        "--name",
        container_name,
        "--label",
        CONTAINER_LABEL,
        "--network=none",
        "--read-only",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,size={spec.tmpfs_size_mb}m",
        "--cap-drop=ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        str(spec.pids),
        "--memory",
        spec.memory,
        "--memory-swap",
        spec.memory,
        "--cpus",
        spec.cpus_text,
        "--ulimit",
        f"nofile={NOFILE}",
        "--ulimit",
        f"fsize={spec.fsize_bytes}:{spec.fsize_bytes}",
    ]
    if keep_id:
        argv.append("--userns=keep-id")
    if workspace_dir is not None:
        # 挂载与工作目录必须同时出现：先挂 -v，再把容器工作目录设成挂载点。
        argv += ["-v", f"{workspace_dir}:{WORKSPACE_MOUNT}:rw", "--workdir", WORKSPACE_MOUNT]
    argv += ["--user", host_user or spec.user]
    argv += [spec.image, "python", "-I", "-c", code]
    return argv


def list_argv(binary: str) -> list[str]:
    """列出本程序创建的容器（启动时清理残留用）。"""
    return [binary, "ps", "-a", "--filter", f"label={CONTAINER_LABEL}", "--format", "{{.Names}}"]


def kill_argv(binary: str, container_name: str) -> list[str]:
    return [binary, "kill", container_name]


def remove_argv(binary: str, container_name: str) -> list[str]:
    return [binary, "rm", "-f", container_name]
