# ADR 0002：Bot 进程与沙箱分离：不挂容器 socket，用固定 argv 调 CLI

状态：已接受
负责：为什么沙箱不挂容器 socket，而是用固定 argv 调 CLI。
上游：`docs/requirements.md` F4.x、`docs/security.md` §4。
改动影响：推翻本决策时新增 ADR 并把本文件标 `被取代`；同步 `docs/security.md` §4、`docs/tools.md` §`run_code`、`docs/architecture.md` §6。

## 背景

- `run_code` 执行的是模型写出来的代码，是整套系统里风险最高的入口（`docs/security.md` §4）。
- Bot 进程本身持有 Bot Token 与 LLM Key，跑在同一宿主机上。

## 决策

- Bot 进程**从不**挂载 `/var/run/docker.sock` 或 Podman socket（挂载等于交出宿主 root）。
- 沙箱只通过「参数数组调用 runtime CLI」实现：`app/sandbox/spec.py` 是唯一 argv 组装点，`app/sandbox/backends.py` 负责探测与调用，`app/sandbox/runner.py` 负责生命周期与错误映射。
- 每个任务一个一次性容器，用 `--rm` 语义（执行后销毁），不用 shell 拼接命令。
- fail-closed：后端不可用或参数无法满足时返回 `sandbox_unavailable`，不做「降级为在宿主上直接执行」。

## 备选与放弃原因

- **挂 socket 让 Bot 自己起容器**：等于给进程宿主 root 权限，直接否决。
- **DinD（容器里跑 Docker）**：需要 privileged，攻击面更大，否决。
- **进程内 exec / 受限子进程**：没有文件系统与资源隔离，等同于「宿主直接执行」，违反 `AGENTS.md` §3.10。
- **microVM（Kata / Firecracker）**：真机不支持嵌套虚拟化，属 `docs/requirements.md` §3 已否定方案。
- **远端沙箱服务**：可作为阶段 8 之后的评估方向，当前不引入（见 ADR 0008）。

## 后果

- 宿主必须安装 Podman（或 Docker）CLI，且预拉镜像；运行期不 pull。
- 输出只能经 CLI 收集，因此 stdout/stderr 的上限、编码与清洗都由我们自己控制（stderr 未清洗是已知技术债 T5）。
- 沙箱行为随 runtime 版本变化，能力必须每次在真机验收（`scripts/verify_sandbox.py`）。
- 任何对 argv 的改动都属于 `AGENTS.md` §8 级别 4（安全变化），必须显式审查。

## 验证方式

- `tests/offline/test_sandbox.py`：锁定 argv 与 Tier A/B 两档的差异。
- 真机 `scripts/verify_sandbox.py`：13 项全 PASS（Tier A 7/7、Tier B 4/4，见 `docs/status.md` §4.2）。