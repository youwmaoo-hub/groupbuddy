# ADR 0003：沙箱优选 rootless Podman，Docker 只作 Tier A 备选

状态：已接受
负责：为什么优选 rootless Podman、Docker 只作 Tier A 备选。
上游：`docs/deployment.md` §12、`docs/security.md` §4。
改动影响：推翻本决策时新增 ADR 并把本文件标 `被取代`；同步 `docs/security.md` §4、`docs/deployment.md` §12。

## 背景

- 真机已装 rootless Podman 4.3.1（cgroup v2、overlay、crun），`bot` 用户 uid 1002、非 root、不在 `docker` 组。
- Tier B 需要把本群工作区目录挂进容器，并要求容器内用户与宿主目录属主一致（否则写不进去）。

## 决策

- `SANDBOX_BACKEND=auto` 时优先 rootless Podman；Docker 只作为备选，且**只支持 Tier A**。
- 启动时探测一次（`app/sandbox/backends.py`）：rootless Podman 才能启用 `--userns=keep-id` 与 Tier B；`SANDBOX_TIER_B=off` 可显式关闭 Tier B。
- keep_id 生效时，Tier A 与 Tier B 都追加 `--userns=keep-id --user <宿主 uid:gid>`（真机 Tier A 观察到的容器内 UID 是 1002，与 `docs/security.md` §4 一致）。

## 备选与放弃原因

- **rootful Podman / docker 组**：等于给进程 root 等价权限，放弃隔离，否决。
- **privileged 容器**：跳过全部限制，否决。
- **Docker rootless**：真机没有，且与 Podman 功能重叠，不引入第二套 runtime。

## 后果

- 长期运行需要 `bot` 用户有 subuid/subgid 映射与 `loginctl enable-linger`（属阶段 9 部署内容）。
- Docker 后端下 `workspace=true` 一律返回 `sandbox_unavailable`（fail-closed，不会偷偷降级）。
- 真机与开发机行为不同：Windows 上只有 FakeBackend（ADR 0005），沙箱结论只能由真机给出。

## 验证方式

- 真机 `podman info`：rootless=true、cgroup v2、driver overlay、runtime crun。
- `scripts/verify_sandbox.py`：非 root（UID 1002）、Tier B 读写与隔离 4 项全 PASS。