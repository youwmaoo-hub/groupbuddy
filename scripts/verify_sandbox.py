"""Linux/Podman 真实沙箱验收（阶段 7，docs/security.md §4）。

在目标机（Linux + rootless Podman）上运行：

    .venv/bin/python scripts/verify_sandbox.py          # 镜像必须已预拉取
    .venv/bin/python scripts/verify_sandbox.py --pull   # 允许脚本先拉取镜像

逐项打印 PASS/FAIL，任一失败退出码 1。只写 storage/workspaces/<测试 chat_id>/。
必须以运行 Bot 的同一个用户、同一份配置执行（工作目录、.env、目录属主保持一致）。
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
    env = settings.subprocess_env()
    print(
        f"路径 workspace={settings.workspace_root} 临时目录={settings.sandbox_temp_dir} "
        f"日志={settings.log_dir} 镜像={settings.sandbox_image}"
    )
    if "--pull" in argv:
        subprocess.run([backend.binary, "pull", settings.sandbox_image], check=False, env=env)
    elif subprocess.run([backend.binary, "image", "exists", settings.sandbox_image], check=False, env=env).returncode != 0:
        print(f"FAIL 镜像不存在：{settings.sandbox_image}（先执行 {backend.binary} pull {settings.sandbox_image}）")
        return 1

    runner = SandboxRunner(backend, settings)
    # tier 是显式归属（"A" Tier A、"B" Tier B、"AB" 两个 tier 都算），不再靠名字前缀猜测；
    # 这样才能让末尾的 Tier A/Tier B 结论覆盖全部相关检查项（技术债 T7）。
    results: list[tuple[str, str, bool, str]] = []

    def flag_last(detail: str) -> None:
        """把最后一条结果改判为 FAIL（用于需要人工复核 stdout 的检查项）。"""
        tier, name, _, _ = results[-1]
        results[-1] = (tier, name, False, detail)

    async def check(name: str, code: str, *, tier: str = "A", workspace: bool = False, timeout: int = 15, want_ok: bool = True, contains: str = "", error_contains: tuple[str, ...] = (), allow_codes: tuple[str, ...] = ()) -> dict[str, object] | None:
        try:
            payload = await runner.run(chat_id=VERIFY_CHAT_ID, code=code, timeout_s=timeout, workspace=workspace)
        except SandboxError as exc:
            results.append((tier, name, exc.code in allow_codes, f"{exc.code}: {exc.message}"))
            return None
        text = f"{payload['stdout']}\n{payload['stderr']}"
        ok = (payload["exit_code"] == 0) is want_ok
        if contains and contains not in text:
            ok = False
        # 负向断言额外要求出现预期的错误签名：只有退出码非零时，「容器没起来 / 解释器缺失」
        # 与「被正确拒绝」无法区分（技术债 T7）。
        if error_contains and not any(marker in text for marker in error_contains):
            ok = False
        results.append((tier, name, bool(ok), f"exit={payload['exit_code']} {text.strip()[:200]}"))
        return payload

    await check("Tier A 纯计算", "print('hello from sandbox')", contains="hello from sandbox")
    uid_payload = await check("非 root（uid != 0）", "import os; print('UID', os.getuid())", contains="UID ")
    if uid_payload is not None and "UID 0" in str(uid_payload["stdout"]):
        flag_last("容器内是 root")
    # T6：--cap-drop=ALL 与 no-new-privileges 此前只能人工读 spec.py，没有验收覆盖。
    # 直接读 /proc/self/status 而不是靠 `capsh` 之类的额外工具（镜像里不一定有）。
    # 断言用 CapBnd（bounding set）而不是 CapEff：容器内是非 root uid，CapEff 本来就是 0，
    # 真正反映 `--cap-drop=ALL` 的是从容器 init 继承下来的 bounding set。
    await check(
        "能力集清空（cap-drop=ALL）",
        "fields = dict(line.split(':', 1) for line in open('/proc/self/status') if ':' in line)\n"
        "print('CAPEFF', int(fields['CapEff'].strip(), 16), 'CAPBND', int(fields['CapBnd'].strip(), 16))\n",
        contains="CAPBND 0",
    )
    await check(
        "禁止提权（no-new-privileges）",
        "lines = open('/proc/self/status').read().splitlines()\n"
        "nnp = [line.split(':', 1)[1].strip() for line in lines if line.startswith('NoNewPrivs')]\n"
        "print('NNP', nnp[0] if nnp else 'missing')\n",
        contains="NNP 1",
    )
    # 探针先打印标记再触发被禁止的操作：标记必须出现（证明容器里的解释器确实运行了），
    # 同时 stderr 必须带预期的错误签名，否则判 FAIL。
    await check(
        "无网络",
        "print('PROBE net')\nimport socket\nsocket.create_connection(('1.1.1.1', 53), 2)\n",
        want_ok=False,
        contains="PROBE net",
        error_contains=("TimeoutError", "ConnectionError", "OSError", "gaierror", "unreachable", "Network is"),
    )
    await check(
        "只读根",
        "print('PROBE rofs')\nopen('/usr/lib/probe.txt', 'w').write('x')\n",
        want_ok=False,
        contains="PROBE rofs",
        error_contains=("Read-only file system", "PermissionError", "OSError", "EROFS", "Errno 13", "Errno 30"),
    )
    await check("单文件大小上限", "import resource; print('FSIZE', resource.getrlimit(resource.RLIMIT_FSIZE)[0])", contains="FSIZE 8388608")
    await check(
        "资源上限生效（cgroup）",
        "import os\n"
        "def rd(p):\n"
        "    try:\n"
        "        return open(p).read().strip()\n"
        "    except OSError:\n"
        "        return None\n"
        "mem = rd('/sys/fs/cgroup/memory.max') or rd('/sys/fs/cgroup/memory/memory.limit_in_bytes')\n"
        "pids = rd('/sys/fs/cgroup/pids.max') or rd('/sys/fs/cgroup/pids/pids.max')\n"
        "cpu = rd('/sys/fs/cgroup/cpu.max') or rd('/sys/fs/cgroup/cpu/cpu.cfs_quota_us')\n"
        "ok = mem == '268435456' and pids == '64' and cpu in ('50000 100000', '50000')\n"
        "print('LIMITS', ok, mem, pids, cpu)\n",
        contains="LIMITS True",
    )
    await check("超时被 kill", "import time; time.sleep(60)", timeout=1, allow_codes=("timeout",))

    workspace_root = Path(settings.workspace_root)
    other_dir = workspace_root / str(OTHER_CHAT_ID)
    other_dir.mkdir(parents=True, exist_ok=True)
    (other_dir / "other.txt").write_text("other", encoding="utf-8")

    if backend.supports_workspace_write():
        tierb = await check(
            "Tier B 本群 workspace 读写（非 root）",
            "import os; open('/workspace/probe.txt', 'w').write('hi'); "
            "print('READ', open('/workspace/probe.txt').read(), 'UID', os.getuid())",
            tier="B",
            workspace=True,
            contains="READ hi",
        )
        if tierb is not None and "UID 0" in str(tierb["stdout"]):
            flag_last("容器内是 root")
        host_file = workspace_root / str(VERIFY_CHAT_ID) / "probe.txt"
        results.append(("B", "Tier B 宿主侧可见", host_file.is_file(), str(host_file)))
        listing = await check("Tier B 其他群不可见", "import os; print('LS', sorted(os.listdir('/workspace')))", tier="B", workspace=True)
        if listing is not None and "other.txt" in str(listing["stdout"]):
            flag_last("看到了其他群的 workspace")
        await check(
            "Tier B 宿主目录不可见",
            "import os; print('VIS', os.path.exists('/.env'), os.path.exists('/app'), os.path.exists('/bot.db'))",
            tier="B",
            workspace=True,
            contains="VIS False False False",
        )
    else:
        try:
            await runner.run(chat_id=VERIFY_CHAT_ID, code="print(1)", workspace=True)
            results.append(("B", "Tier B 未验证时 fail-closed", False, "居然执行了"))
        except SandboxError as exc:
            results.append(("B", "Tier B 未验证时 fail-closed", exc.code == "sandbox_unavailable", exc.code))

    stale = await backend.list_containers()
    results.append(("AB", "执行后没有残留容器", not stale, ",".join(stale)))

    temp_dir = Path(settings.sandbox_temp_dir)
    leftovers = sorted(x.name for x in temp_dir.glob("*")) if temp_dir.exists() else []
    results.append(("AB", "临时输出目录已清理", not leftovers, ",".join(leftovers)))

    for path in (workspace_root / str(VERIFY_CHAT_ID) / "probe.txt", other_dir / "other.txt"):
        if path.exists():
            path.unlink()

    failed = 0
    for tier, name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} [{tier}] {name} | {detail}")
        if not ok:
            failed += 1
    tier_a = [ok for tier, _, ok, _ in results if "A" in tier]
    tier_b = [ok for tier, _, ok, _ in results if "B" in tier]
    print(f"Tier A：{'PASS' if tier_a and all(tier_a) else 'FAIL'}")
    if backend.supports_workspace_write():
        print(f"Tier B：{'PASS' if tier_b and all(tier_b) else 'FAIL'}")
    else:
        print("Tier B：未启用（fail-closed 生效）")
    print(f"\n合计 {len(results)} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
