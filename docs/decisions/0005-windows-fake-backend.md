# ADR 0005：Windows 开发用 FakeBackend，真实容器只在 Linux 验证

状态：已接受
负责：为什么 Windows 用 FakeBackend，沙箱结论只能来自真机。
上游：`docs/architecture.md` §12、`docs/deployment.md` §12。
改动影响：推翻本决策时新增 ADR；同步 `docs/architecture.md` §12 与测试说明。

## 背景

- 日常开发在 Windows 上进行，而沙箱依赖 Linux 容器运行时。
- 上层逻辑（闸门、工具权限、执行器、runner、错误映射）与 runtime 无关，必须能在离线环境被测试。

## 决策

- 沙箱以 `SandboxBackend` 协议为边界；离线测试与 Windows 开发使用 `FakeBackend`，它复用与真实后端完全相同的上层代码路径（policy → executor → runner → 工具结果）。
- Windows 上不安装容器运行时；真实容器行为只在 Linux 真机验证。

## 备选与放弃原因

- **Windows 上装 Podman machine / WSL2**：环境复杂度高，且验证结论不能外推到真机（不同的 userns、cgroup、挂载语义）。
- **在测试里直接打桩 `run_code` 工具返回**：会绕过 policy/executor/runner，覆盖面反而更小。

## 后果

- **本机的绿色结果不能证明沙箱行为**，因此 `AGENTS.md` §3.18 要求区分证据来源，`docs/status.md` 分列本机与真机结果。
- 平台条件用例在 Windows 上跳过（文件软/硬链接，技术债 T28），所以本机是 `OK (skipped=2)`、真机是 `OK`。
- 结论：任何沙箱改动都必须「本机跑用例 + 真机重跑同一套用例」，两类证据同时给。

## 验证方式

- `tests/offline/test_sandbox.py`、`tests/offline/test_run_code.py` 在本机通过。
- 真机：同一套 283 个测试通过（无 skip），另有 `scripts/verify_sandbox.py` 13 项。