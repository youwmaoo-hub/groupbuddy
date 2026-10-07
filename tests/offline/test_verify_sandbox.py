"""离线测试 `scripts/verify_sandbox.py` 的判定口径（技术债 T7）。

真机执行需要 Linux + rootless Podman；本文件用假后端在离线环境里验证判定逻辑本身：

- 负向断言（无网络 / 只读根）必须同时看到探针标记与预期错误签名，「容器没起来 /
  解释器缺失」不能再 PASS；
- `Tier A` / `Tier B` 结论按显式 tier 归属聚合（不再靠名字前缀），任何一项 FAIL 都会
  翻转对应结论。

脚本只被 import（`__main__` 守卫拦住），不启动任何进程。
"""

from __future__ import annotations

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from app.sandbox.backends import CommandResult
from tests.offline.helpers import make_settings

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "verify_sandbox.py"
MOUNT_SUFFIX = ":/workspace:rw"

# (代码里的关键字, exit_code, stdout, stderr, timed_out)；按顺序取第一个命中的。
HAPPY_PATH: list[tuple[str, int, str, str, bool]] = [
    ("time.sleep(60)", -1, "", "", True),
    ("hello from sandbox", 0, "hello from sandbox\n", "", False),
    ("print('UID'", 0, "UID 65534\n", "", False),
    ("PROBE net", 1, "PROBE net\n", "TimeoutError: timed out\n", False),
    ("PROBE rofs", 1, "PROBE rofs\n", "OSError: [Errno 30] Read-only file system\n", False),
    ("FSIZE", 0, "FSIZE 8388608\n", "", False),
    ("LIMITS", 0, "LIMITS True 268435456 64 50000 100000\n", "", False),
    ("READ", 0, "READ hi UID 65534\n", "", False),
    ("LS", 0, "LS []\n", "", False),
    ("VIS", 0, "VIS False False False\n", "", False),
]


def load_script():
    spec = importlib.util.spec_from_file_location("verify_sandbox_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ScriptedBackend:
    """按 argv 里的探针代码返回预设结果的假后端；不启动任何进程。"""

    name = "fake"
    binary = "podman"

    def __init__(self, responses: list[tuple[str, int, str, str, bool]], *, workspace_write: bool = True) -> None:
        self._responses = list(responses)
        self._workspace_write = workspace_write
        self.codes: list[str] = []

    def available(self) -> bool:
        return True

    def supports_workspace_write(self) -> bool:
        return self._workspace_write

    def _response(self, code: str) -> tuple[int, str, str, bool]:
        for key, exit_code, stdout, stderr, timed_out in self._responses:
            if key in code:
                return exit_code, stdout, stderr, timed_out
        return 0, "", "", False

    async def run(self, argv, *, env, stdout_path, stderr_path, timeout):
        code = str(argv[-1])
        self.codes.append(code)
        exit_code, stdout, stderr, timed_out = self._response(code)
        stdout_path.write_bytes(stdout.encode("utf-8"))
        stderr_path.write_bytes(stderr.encode("utf-8"))
        mount = next((arg[: -len(MOUNT_SUFFIX)] for arg in argv if str(arg).endswith(MOUNT_SUFFIX)), None)
        if mount is not None and "READ" in code:
            Path(mount, "probe.txt").write_text("hi", encoding="utf-8")
        return CommandResult(exit_code=exit_code, timed_out=timed_out)

    async def cleanup(self, container_name: str) -> None:
        return None

    async def list_containers(self) -> list[str]:
        return []

    async def close(self) -> None:
        return None


class VerifySandboxScriptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.module = load_script()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name)
        self.settings = make_settings(self.tmp, SANDBOX_TEMP_DIR=str(self.tmp / "storage" / "sandbox"))

    async def _run(self, responses: list[tuple[str, int, str, str, bool]], *, workspace_write: bool = True) -> tuple[int, str]:
        backend = ScriptedBackend(responses, workspace_write=workspace_write)
        buffer = io.StringIO()
        with (
            mock.patch.object(self.module, "load_settings", return_value=self.settings),
            mock.patch.object(self.module, "build_backend", return_value=backend),
            mock.patch.object(self.module, "subprocess", mock.Mock(run=mock.Mock(return_value=mock.Mock(returncode=0)))),
            redirect_stdout(buffer),
        ):
            code = await self.module.main([])
        return code, buffer.getvalue()

    async def test_happy_path_reports_both_tiers_pass(self) -> None:
        code, output = await self._run(HAPPY_PATH)

        self.assertEqual(0, code)
        self.assertIn("Tier A：PASS", output)
        self.assertIn("Tier B：PASS", output)
        self.assertIn("合计 13 项，失败 0 项", output)
        self.assertNotIn("FAIL", output)

    async def test_negative_checks_fail_when_the_probe_never_ran(self) -> None:
        """容器没起来 / 解释器缺失：退出码非零但探针标记与错误签名都没有 → 必须 FAIL。"""
        responses = [
            item if item[0] not in ("PROBE net", "PROBE rofs") else (item[0], 1, "", "exec: python: not found\n", False)
            for item in HAPPY_PATH
        ]
        code, output = await self._run(responses)

        self.assertEqual(1, code)
        self.assertIn("FAIL [A] 无网络", output)
        self.assertIn("FAIL [A] 只读根", output)
        self.assertIn("Tier A：FAIL", output)

    async def test_tier_a_conclusion_covers_every_check(self) -> None:
        """单项 FAIL 必须翻转 `Tier A` 结论（修复前只聚合 1 项，会漏报）。"""
        responses = [
            item if item[0] != "print('UID'" else (item[0], 0, "UID 0\n", "", False) for item in HAPPY_PATH
        ]
        code, output = await self._run(responses)

        self.assertEqual(1, code)
        self.assertIn("FAIL [A] 非 root（uid != 0）", output)
        self.assertIn("容器内是 root", output)
        self.assertIn("Tier A：FAIL", output)
        self.assertIn("Tier B：PASS", output)

    async def test_workspace_write_unsupported_requires_fail_closed(self) -> None:
        code, output = await self._run(HAPPY_PATH, workspace_write=False)

        self.assertEqual(0, code)
        self.assertIn("PASS [B] Tier B 未验证时 fail-closed", output)
        self.assertIn("Tier A：PASS", output)
        self.assertIn("Tier B：未启用（fail-closed 生效）", output)


if __name__ == "__main__":
    unittest.main()
