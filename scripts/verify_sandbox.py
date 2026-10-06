"""Linux/Podman 真实沙箱验收（阶段 7，docs/security.md §4）。

在目标机（Linux + rootless Podman）上运行：

    .venv/bin/python scripts/verify_sandbox.py          # 镜像必须已预拉取
    .venv/bin/python scripts/verify_sandbox.py --pull   # 允许脚本先拉取镜像

逐项打印 PASS/FAIL，任一失败退出码 1。只写 storage/workspaces/<测试 chat_id>/。
运行期 pull 由部署阶段负责（SANDBOX_BACKEND 的 run_code 自身永不 pull）。
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.sandbox.backends import build_backend  # noqa: E402
from app.sandbox.runner import SandboxError, SandboxRunner  # noqa: E402

VERIFY_CHAT_ID = 999001
OTHER_CHAT_ID = 999002


def load_settings() -> Settings:
    try:
        return Settings()
    except Exception:  # noqa: BLE001 - 验收脚本可以没有真实凭据
        return Settings(BOT_TOKEN="verify", LLM_API_KEY="verify", _env_file=None)


async def main(argv: list[str]) -> int:
    settings = load_settings()
    settings.ensure_directories()
    backend = build_backend(settings)
    print(f"后端 backend={backend.name} available={backend.available()} workspace_write={backend.supports_workspace_write()}")
    if not backend.available():
        print("FAIL 没有可用的容器运行时：安装 rootless Podman 后重试")
        return 1
    if "--pull" in argv:
        subprocess.run([backend.binary, "pull", settings.sandbox_image], check=False)
    elif subprocess.run([backend.binary, "image", "exists", settings.sandbox_image], check=False).returncode != 0:
        print(f"FAIL 镜像不存在：{settings.sandbox_image}（先执行 {backend.binary} pull {settings.sandbox_image}）")
        return 1

    runner = SandboxRunner(backend, settings)
    results: list[tuple[str, bool, str]] = []

    async def check(name: str, code: str, *, workspace: bool = False, timeout: int = 15, want_ok: bool = True, contains: str = "", allow_codes: tuple[str, ...] = ()) -> dict[str, object] | None:
        try:
            payload = await runner.run(chat_id=VERIFY_CHAT_ID, code=code, timeout_s=timeout, workspace=workspace)
        except SandboxError as exc:
            results.append((name, exc.code in allow_codes, f"{exc.code}: {exc.message}"))
            return None
        text = f"{payload['stdout']}\n{payload['stderr']}"
        ok = (payload["exit_code"] == 0) is want_ok
        if contains and contains not in text:
            ok = False
        results.append((name, bool(ok), f"exit={payload['exit_code']} {text.strip()[:200]}"))
        return payload

    await check("Tier A 纯计算", "print('hello from sandbox')", contains="hello from sandbox")
    uid_payload = await check("非 root（uid != 0）", "import os; print('UID', os.getuid())", contains="UID ")
    if uid_payload is not None and "UID 0" in str(uid_payload["stdout"]):
        results[-1] = (results[-1][0], False, "容器内是 root")
    await check("无网络", "import socket; socket.create_connection(('1.1.1.1', 53), 2)", want_ok=False)
    await check("只读根", "open('/usr/lib/probe.txt', 'w').write('x')", want_ok=False)
    await check("单文件大小上限", "import resource; print('FSIZE', resource.getrlimit(resource.RLIMIT_FSIZE)[0])", contains="FSIZE 8388608")
    await check("超时被 kill", "import time; time.sleep(60)", timeout=1, allow_codes=("timeout",))

    workspace_root = Path(settings.workspace_root)
    other_dir = workspace_root / str(OTHER_CHAT_ID)
    other_dir.mkdir(parents=True, exist_ok=True)
    (other_dir / "other.txt").write_text("other", encoding="utf-8")

    if backend.supports_workspace_write():
        await check(
            "Tier B 本群 workspace 读写",
            "open('/workspace/probe.txt', 'w').write('hi'); print('READ', open('/workspace/probe.txt').read())",
            workspace=True,
            contains="READ hi",
        )
        host_file = workspace_root / str(VERIFY_CHAT_ID) / "probe.txt"
        results.append(("Tier B 宿主侧可见", host_file.is_file(), str(host_file)))
        listing = await check("Tier B 其他群不可见", "import os; print('LS', sorted(os.listdir('/workspace')))", workspace=True)
        if listing is not None and "other.txt" in str(listing["stdout"]):
            results[-1] = (results[-1][0], False, "看到了其他群的 workspace")
        await check(
            "Tier B 宿主目录不可见",
            "import os; print('VIS', os.path.exists('/.env'), os.path.exists('/app'), os.path.exists('/bot.db'))",
            workspace=True,
            contains="VIS False False False",
        )
    else:
        try:
            await runner.run(chat_id=VERIFY_CHAT_ID, code="print(1)", workspace=True)
            results.append(("Tier B 未验证时 fail-closed", False, "居然执行了"))
        except SandboxError as exc:
            results.append(("Tier B 未验证时 fail-closed", exc.code == "sandbox_unavailable", exc.code))

    stale = await backend.list_containers()
    results.append(("执行后没有残留容器", not stale, ",".join(stale)))

    for path in (workspace_root / str(VERIFY_CHAT_ID) / "probe.txt", other_dir / "other.txt"):
        if path.exists():
            path.unlink()

    failed = 0
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {name} | {detail}")
        if not ok:
            failed += 1
    print(f"\n合计 {len(results)} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
