"""run_code 的唯一执行入口（docs/security.md §4、docs/tools.md §run_code）。

- 模型只能提供 code / timeout_s / workspace；
- 镜像、挂载、网络、资源上限、运行时参数全部由本模块与 app/sandbox/spec.py 决定；
- 不可用、超时、启动失败、清理失败都收敛为 SandboxError，绝不回退到宿主机执行；
- 临时输出目录用后即删；容器 --rm 兜底，异常/超时/取消/关停走 cleanup 与启动清理。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from pathlib import Path

from app.sandbox import preflight
from app.sandbox.backends import SandboxBackend
from app.sandbox.spec import CONTAINER_PREFIX, SandboxSpec, build_argv
from app.tools.registry import ToolError
from app.tools.workspace import workspace_dir

logger = logging.getLogger(__name__)

# 外层硬超时余量：CLI 自身超时后仍未退出时强制放弃并销毁容器
GRACE_SECONDS = 5.0


class SandboxError(RuntimeError):
    """沙箱执行失败；code 与 docs/tools.md §3 的错误码一致，可原样转成 ToolError。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SandboxRunner:
    """一次性容器执行器；每个实例在进程内共享并发上限与存活容器集合。"""

    def __init__(
        self,
        backend: SandboxBackend,
        settings,
        *,
        spec: SandboxSpec | None = None,
        grace_seconds: float = GRACE_SECONDS,
    ) -> None:
        self._backend = backend
        self._settings = settings
        self._spec = spec or SandboxSpec(
            image=settings.sandbox_image,
            memory_mb=settings.sandbox_memory_mb,
            cpus=settings.sandbox_cpus,
            pids=settings.sandbox_pids,
        )
        self._grace = grace_seconds
        self._limit = max(1, int(settings.sandbox_max_concurrent))
        self._slots = asyncio.Semaphore(self._limit)
        self._live: set[str] = set()
        self._temp_dir = Path(settings.sandbox_temp_dir)

    # --- 对外 ---

    def describe(self) -> dict[str, object]:
        return {
            "backend": self._backend.name,
            "available": self._backend.available(),
            "workspace_write": self._backend.supports_workspace_write(),
            "image": self._spec.image,
            "max_concurrent": self._limit,
        }

    async def run(
        self,
        *,
        chat_id: int,
        code: str,
        timeout_s: int | None = None,
        workspace: bool = False,
    ) -> dict[str, object]:
        if not self._backend.available():
            raise SandboxError("sandbox_unavailable", "沙箱运行时不可用")
        timeout = self._clamp(timeout_s)
        notes = preflight.scan(code)
        if notes:
            logger.info("run_code 预扫描提示 chat_id=%s 标签=%s", chat_id, ",".join(notes))
        mount = self._workspace(chat_id) if workspace else None
        container = f"{CONTAINER_PREFIX}{uuid.uuid4().hex[:12]}"
        stdout_path, stderr_path = self._temp_paths()
        argv = build_argv(
            self._backend.binary,
            self._spec,
            container,
            code,
            workspace_dir=mount,
            keep_id=bool(getattr(self._backend, "keep_id", False)),
            host_user=getattr(self._backend, "host_user", None),
        )
        logger.info(
            "run_code 开始 chat_id=%s 容器=%s 超时=%ss workspace=%s 镜像=%s",
            chat_id,
            container,
            timeout,
            bool(mount),
            self._spec.image,
        )
        try:
            async with self._slots:
                self._live.add(container)
                try:
                    result = await asyncio.wait_for(
                        self._backend.run(
                            argv,
                            env=self._settings.subprocess_env(),
                            stdout_path=stdout_path,
                            stderr_path=stderr_path,
                            timeout=timeout,
                        ),
                        timeout + self._grace,
                    )
                except (asyncio.TimeoutError, TimeoutError) as exc:
                    await self._destroy(container)
                    raise SandboxError("timeout", f"执行超过 {timeout} 秒，容器已销毁") from exc
                except asyncio.CancelledError:
                    await self._destroy(container)
                    raise
                except Exception as exc:  # noqa: BLE001 - 启动失败也必须 fail-closed
                    await self._destroy(container)
                    logger.warning("沙箱启动失败 chat_id=%s", chat_id, exc_info=True)
                    raise SandboxError("execution_failed", "沙箱启动失败，容器已销毁") from exc
                finally:
                    self._live.discard(container)
            if result.timed_out:
                await self._destroy(container)
                raise SandboxError("timeout", f"执行超过 {timeout} 秒，容器已销毁")
            stdout, stdout_cut, stdout_dropped = self._read_capped(stdout_path)
            stderr, stderr_cut, stderr_dropped = self._read_capped(stderr_path)
            if stdout_cut:
                stdout += f"\n[output truncated: {stdout_dropped} bytes]"
            if stderr_cut:
                stderr += f"\n[output truncated: {stderr_dropped} bytes]"
            logger.info("run_code 结束 chat_id=%s exit=%s", chat_id, result.exit_code)
            return {
                "exit_code": int(result.exit_code),
                "stdout": stdout,
                "stderr": stderr,
                "truncated": bool(stdout_cut or stderr_cut),
            }
        finally:
            for path in (stdout_path, stderr_path):
                with contextlib.suppress(OSError):
                    path.unlink()

    async def cleanup_stale(self) -> int:
        """启动时清理带 groupbuddy=1 标签的残留容器（上次进程被强杀留下的）。"""
        if not self._backend.available():
            return 0
        try:
            names = await self._backend.list_containers()
        except Exception:  # noqa: BLE001 - 清理是尽力而为
            logger.warning("无法列出残留容器", exc_info=True)
            return 0
        removed = 0
        for name in names:
            await self._destroy(name)
            removed += 1
        if removed:
            logger.info("已清理残留沙箱容器 count=%d", removed)
        return removed

    async def shutdown(self) -> None:
        """Bot 关停：销毁仍在运行的容器（幂等，可重复调用）。"""
        for name in sorted(self._live):
            await self._destroy(name)
        self._live.clear()

    # --- 内部 ---

    def _clamp(self, timeout_s: int | None) -> int:
        default = int(self._settings.sandbox_timeout_default)
        maximum = max(default, int(self._settings.sandbox_timeout_max))
        value = default if timeout_s is None else int(timeout_s)
        return max(1, min(value, maximum))

    def _workspace(self, chat_id: int) -> Path:
        if not self._backend.supports_workspace_write():
            raise SandboxError(
                "sandbox_unavailable",
                "当前沙箱后端未验证 workspace 写入（仅 rootless Podman keep-id）",
            )
        try:
            return workspace_dir(Path(self._settings.workspace_root), chat_id)
        except ToolError as exc:
            raise SandboxError("path_outside_workspace", exc.message) from exc

    def _temp_paths(self) -> tuple[Path, Path]:
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        return self._temp_dir / f"out-{token}", self._temp_dir / f"err-{token}"

    def _read_capped(self, path: Path) -> tuple[str, bool, int]:
        limit = max(1, int(self._settings.sandbox_output_kb)) * 1024
        try:
            with path.open("rb") as handle:
                data = handle.read(limit + 1)
        except OSError:
            return "", False, 0
        if len(data) <= limit:
            return data.decode("utf-8", "replace"), False, 0
        dropped = len(data) - limit
        with contextlib.suppress(OSError):
            dropped = max(0, path.stat().st_size - limit)
        return data[:limit].decode("utf-8", "replace"), True, dropped

    async def _destroy(self, container: str) -> None:
        task = asyncio.ensure_future(self._backend.cleanup(container))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - 清理失败只记日志
            logger.warning("销毁容器失败 name=%s", container, exc_info=True)
