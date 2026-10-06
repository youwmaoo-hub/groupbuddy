"""沙箱层离线测试：argv 白名单、fail-closed、超时销毁、输出截断、临时文件清理。

真实容器验收在 Linux/Podman 上用 scripts/verify_sandbox.py（AGENTS.md §3 规则 13）。
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic import ValidationError

from app.sandbox.backends import CliBackend, FakeBackend, UnavailableBackend, build_backend
from app.sandbox.preflight import scan
from app.sandbox.runner import SandboxError, SandboxRunner
from app.sandbox.spec import SandboxSpec, build_argv
from app.tools.builtin import build_registry
from app.tools.builtin.run_code import RunCodeArgs, RunCodeTool
from app.tools.registry import ToolContext, ToolError
from tests.offline.helpers import make_settings

WHITELIST_ENV = {
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "XDG_RUNTIME_DIR",
    "XDG_DATA_HOME",
    "DBUS_SESSION_BUS_ADDRESS",
    "CONTAINER_HOST",
}


def make_spec() -> SandboxSpec:
    return SandboxSpec(image="python:3.12-slim", memory_mb=256, cpus=0.5, pids=64)


class ArgvTests(unittest.TestCase):
    """容器参数是程序固定的白名单（模型只能提交 code）。"""

    def test_tier_a_argv_is_whitelisted_and_has_no_mount(self) -> None:
        argv = build_argv("podman", make_spec(), "cx-abc", "print(1)")
        joined = " ".join(argv)
        for flag in (
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "no-new-privileges",
            "--pids-limit 64",
            "--memory 256m",
            "--memory-swap 256m",
            "--cpus 0.5",
            "--tmpfs /tmp:rw,noexec,nosuid,size=16m",
            "--ulimit nofile=64:64",
            "--ulimit fsize=8388608:8388608",
            "--workdir /workspace",
            "--label groupbuddy=1",
        ):
            self.assertIn(flag, joined)
        self.assertIn("--rm", argv)
        self.assertNotIn("-v", argv)
        self.assertNotIn("--userns=keep-id", argv)
        self.assertNotIn("--privileged", joined)
        self.assertEqual("65534:65534", argv[argv.index("--user") + 1])
        self.assertEqual(["python", "-I", "-c", "print(1)"], argv[-4:])
        self.assertNotIn("sh", argv)

    def test_tier_b_argv_mounts_only_workspace_with_keep_id(self) -> None:
        argv = build_argv(
            "podman",
            make_spec(),
            "cx-abc",
            "print(1)",
            workspace_dir=Path("/srv/ws/42"),
            keep_id=True,
            host_user="1001:1001",
        )
        self.assertIn("--userns=keep-id", argv)
        self.assertIn(f"{Path('/srv/ws/42')}:/workspace:rw", argv)
        self.assertEqual("1001:1001", argv[argv.index("--user") + 1])
        self.assertIn("--network=none", argv)
        self.assertIn("--read-only", argv)
        self.assertEqual(1, sum(1 for item in argv if item.startswith("-v")))

    def test_preflight_scan_is_only_a_hint(self) -> None:
        labels = scan("import os\nos.system('ls')\nsubprocess.run(['ls'])")
        self.assertIn("os.system", labels)
        self.assertIn("subprocess", labels)
        self.assertEqual([], scan("print(sum(range(10)))"))


class BackendChoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_none_backend_fails_closed(self) -> None:
        backend = build_backend(make_settings(self.tmp, SANDBOX_BACKEND="none"))
        self.assertIsInstance(backend, UnavailableBackend)
        self.assertFalse(backend.available())

    def test_auto_without_runtime_fails_closed(self) -> None:
        settings = make_settings(self.tmp, SANDBOX_BACKEND="auto")
        with mock.patch("app.sandbox.backends.shutil.which", return_value=None):
            backend = build_backend(settings)
        self.assertIsInstance(backend, UnavailableBackend)
        self.assertFalse(backend.available())

    def test_rootless_podman_enables_workspace_write(self) -> None:
        settings = make_settings(self.tmp, SANDBOX_BACKEND="auto", SANDBOX_TIER_B="auto")
        with (
            mock.patch("app.sandbox.backends.shutil.which", return_value="podman"),
            mock.patch("app.sandbox.backends._probe_version", return_value="podman version 4.9.3"),
            mock.patch("app.sandbox.backends._host_ids", return_value=(1001, 1001)),
        ):
            backend = build_backend(settings)
        self.assertIsInstance(backend, CliBackend)
        self.assertTrue(backend.supports_workspace_write())
        self.assertTrue(backend.keep_id)  # type: ignore[attr-defined]
        self.assertEqual("1001:1001", backend.host_user)  # type: ignore[attr-defined]

    def test_rootful_podman_and_docker_never_enable_workspace_write(self) -> None:
        settings = make_settings(self.tmp, SANDBOX_BACKEND="auto")
        with (
            mock.patch("app.sandbox.backends.shutil.which", return_value="podman"),
            mock.patch("app.sandbox.backends._probe_version", return_value="podman version 4.9.3"),
            mock.patch("app.sandbox.backends._host_ids", return_value=(0, 0)),
        ):
            rootful = build_backend(settings)
        self.assertFalse(rootful.supports_workspace_write())
        with (
            mock.patch("app.sandbox.backends.shutil.which", return_value="docker"),
            mock.patch("app.sandbox.backends._probe_version", return_value="Docker version 27.0.0"),
            mock.patch("app.sandbox.backends._host_ids", return_value=(1001, 1001)),
        ):
            docker = build_backend(make_settings(self.tmp, SANDBOX_BACKEND="docker"))
        self.assertTrue(docker.available())
        self.assertFalse(docker.supports_workspace_write())

    def test_tier_b_off_disables_workspace_write(self) -> None:
        settings = make_settings(self.tmp, SANDBOX_BACKEND="podman", SANDBOX_TIER_B="off")
        with (
            mock.patch("app.sandbox.backends.shutil.which", return_value="podman"),
            mock.patch("app.sandbox.backends._probe_version", return_value="podman version 4.9.3"),
            mock.patch("app.sandbox.backends._host_ids", return_value=(1001, 1001)),
        ):
            backend = build_backend(settings)
        self.assertFalse(backend.supports_workspace_write())

    def test_subprocess_env_has_no_secrets(self) -> None:
        os.environ["BOT_TOKEN"] = "secret-token"
        os.environ["LLM_API_KEY"] = "secret-key"
        try:
            env = make_settings(self.tmp).subprocess_env()
        finally:
            os.environ.pop("BOT_TOKEN", None)
            os.environ.pop("LLM_API_KEY", None)
        self.assertNotIn("BOT_TOKEN", env)
        self.assertNotIn("LLM_API_KEY", env)
        self.assertTrue(set(env) <= WHITELIST_ENV)


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def make_runner(self, backend, *, overrides: dict[str, object] | None = None, grace: float = 0.05):
        values: dict[str, object] = {
            "SANDBOX_MAX_CONCURRENT": 1,
            "SANDBOX_OUTPUT_KB": 1,
            "SANDBOX_TEMP_DIR": str(self.tmp / "sandbox"),
            "WORKSPACE_ROOT": str(self.tmp / "storage" / "workspaces"),
        }
        values.update(overrides or {})
        settings = make_settings(self.tmp, **values)
        return SandboxRunner(backend, settings, grace_seconds=grace), settings

    def temp_files(self) -> list[Path]:
        return list((self.tmp / "sandbox").glob("*"))

    async def test_tier_a_run_returns_output_and_cleans_temp(self) -> None:
        backend = FakeBackend(stdout="hello\n")
        runner, _ = self.make_runner(backend)
        result = await runner.run(chat_id=42, code="print('hello')")
        self.assertEqual(0, result["exit_code"])
        self.assertEqual("hello\n", result["stdout"])
        self.assertFalse(result["truncated"])
        self.assertEqual([], self.temp_files())
        argv = backend.calls[0]["argv"]
        self.assertNotIn("-v", argv)  # type: ignore[operator]
        self.assertEqual([], backend.cleaned)

    async def test_unavailable_backend_returns_sandbox_unavailable(self) -> None:
        runner, _ = self.make_runner(UnavailableBackend("无运行时"))
        with self.assertRaises(SandboxError) as ctx:
            await runner.run(chat_id=42, code="print(1)")
        self.assertEqual("sandbox_unavailable", ctx.exception.code)

    async def test_workspace_without_capability_fails_closed(self) -> None:
        backend = FakeBackend(supports_workspace_write=False)
        runner, _ = self.make_runner(backend)
        with self.assertRaises(SandboxError) as ctx:
            await runner.run(chat_id=42, code="print(1)", workspace=True)
        self.assertEqual("sandbox_unavailable", ctx.exception.code)
        self.assertEqual([], backend.calls)

    async def test_workspace_mount_is_per_chat(self) -> None:
        backend = FakeBackend(stdout="ok")
        runner, settings = self.make_runner(backend)
        await runner.run(chat_id=42, code="print('ok')", workspace=True)
        expected = Path(settings.workspace_root) / "42"
        argv = backend.calls[0]["argv"]
        self.assertIn(f"{expected.resolve()}:/workspace:rw", argv)  # type: ignore[operator]
        self.assertTrue(expected.is_dir())
        self.assertEqual([], self.temp_files())

    async def test_output_is_truncated_with_marker(self) -> None:
        backend = FakeBackend(stdout="x" * 2000)
        runner, _ = self.make_runner(backend)
        result = await runner.run(chat_id=42, code="print('x' * 2000)")
        self.assertTrue(result["truncated"])
        self.assertEqual("x" * 1024, result["stdout"][:1024])  # type: ignore[index]
        self.assertIn("[output truncated: 976 bytes]", result["stdout"])  # type: ignore[operator]
        self.assertEqual([], self.temp_files())

    async def test_backend_timeout_destroys_container(self) -> None:
        backend = FakeBackend(timed_out=True)
        runner, _ = self.make_runner(backend)
        with self.assertRaises(SandboxError) as ctx:
            await runner.run(chat_id=42, code="import time; time.sleep(30)", timeout_s=1)
        self.assertEqual("timeout", ctx.exception.code)
        self.assertEqual(1, len(backend.cleaned))
        self.assertTrue(backend.cleaned[0].startswith("cx-"))
        self.assertEqual([], self.temp_files())

    async def test_hard_timeout_destroys_container(self) -> None:
        backend = FakeBackend(hang=True)
        runner, _ = self.make_runner(backend)
        with self.assertRaises(SandboxError) as ctx:
            await runner.run(chat_id=42, code="while True: pass", timeout_s=1)
        self.assertEqual("timeout", ctx.exception.code)
        self.assertEqual(1, len(backend.cleaned))
        self.assertEqual([], self.temp_files())

    async def test_cancellation_destroys_container(self) -> None:
        backend = FakeBackend(hang=True)
        runner, _ = self.make_runner(backend)
        task = asyncio.create_task(runner.run(chat_id=42, code="while True: pass", timeout_s=30))
        await asyncio.sleep(0.02)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.02)
        self.assertEqual(1, len(backend.cleaned))
        self.assertEqual([], self.temp_files())

    async def test_startup_cleanup_removes_stale_containers(self) -> None:
        backend = FakeBackend(stale=("cx-old1", "cx-old2"))
        runner, _ = self.make_runner(backend)
        self.assertEqual(2, await runner.cleanup_stale())
        self.assertEqual(["cx-old1", "cx-old2"], backend.cleaned)

    async def test_shutdown_destroys_live_container(self) -> None:
        backend = FakeBackend(hang=True)
        runner, _ = self.make_runner(backend)
        task = asyncio.create_task(runner.run(chat_id=42, code="while True: pass", timeout_s=30))
        await asyncio.sleep(0.02)
        await runner.shutdown()
        self.assertEqual(1, len(backend.cleaned))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_timeout_is_clamped_to_max(self) -> None:
        backend = FakeBackend()
        runner, _ = self.make_runner(backend, overrides={"SANDBOX_TIMEOUT_DEFAULT": 15, "SANDBOX_TIMEOUT_MAX": 30})
        await runner.run(chat_id=42, code="print(1)", timeout_s=29)
        self.assertEqual(29, backend.calls[0]["timeout"])
        await runner.run(chat_id=42, code="print(1)", timeout_s=30)
        self.assertEqual(30, backend.calls[1]["timeout"])


class FakeRunner:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._error = error

    def describe(self) -> dict[str, object]:
        return {"backend": "fake"}

    async def run(self, *, chat_id, code, timeout_s=None, workspace=False):
        self.calls.append({"chat_id": chat_id, "code": code, "timeout_s": timeout_s, "workspace": workspace})
        if self._error is not None:
            raise self._error
        return {"exit_code": 0, "stdout": "ok", "stderr": "", "truncated": False}


class RunCodeToolTests(unittest.IsolatedAsyncioTestCase):
    def context(self, *, allow_write: int = 1) -> ToolContext:
        return ToolContext(chat_id=42, user_id=7, group={"allow_write": allow_write})

    async def test_workspace_requires_allow_write(self) -> None:
        tool = RunCodeTool(FakeRunner())
        with self.assertRaises(ToolError) as ctx:
            await tool.run(RunCodeArgs(code="print(1)", workspace=True), self.context(allow_write=0))
        self.assertEqual("permission_denied", ctx.exception.code)

    async def test_result_passthrough_and_workspace_flag(self) -> None:
        runner = FakeRunner()
        tool = RunCodeTool(runner)
        payload = await tool.run(RunCodeArgs(code="print(1)", workspace=True), self.context())
        self.assertEqual(0, payload["exit_code"])
        self.assertTrue(runner.calls[0]["workspace"])
        self.assertEqual(15, runner.calls[0]["timeout_s"])

    async def test_sandbox_error_maps_to_tool_error(self) -> None:
        tool = RunCodeTool(FakeRunner(error=SandboxError("timeout", "执行超过 1 秒，容器已销毁")))
        with self.assertRaises(ToolError) as ctx:
            await tool.run(RunCodeArgs(code="print(1)"), self.context())
        self.assertEqual("timeout", ctx.exception.code)
        self.assertIn("容器已销毁", ctx.exception.message)

    async def test_arguments_are_bounded(self) -> None:
        for bad in ({"code": ""}, {"code": "print(1)", "timeout_s": 0}, {"code": "print(1)", "timeout_s": 31}, {"code": "print(1)", "extra": 1}):
            with self.assertRaises(ValidationError):
                RunCodeArgs(**bad)

    def test_spec_is_l3_with_frozen_payload(self) -> None:
        tool = RunCodeTool(FakeRunner())
        self.assertEqual("run_code", tool.spec.name)
        self.assertEqual("L3", tool.spec.level)
        self.assertEqual(35.0, tool.spec.timeout_seconds)
        self.assertEqual(20480, tool.spec.max_payload_bytes)

    def test_registry_registers_run_code_only_with_sandbox(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        settings = make_settings(Path(tmp.name))
        registry = build_registry(settings, store=object(), outbound=object(), mood=object())
        self.assertNotIn("run_code", registry.names())
        registry = build_registry(settings, store=object(), outbound=object(), mood=object(), sandbox=FakeRunner())
        self.assertIn("run_code", registry.names())
