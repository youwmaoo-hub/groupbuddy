# 部署与运行环境

负责：运行环境契约、目录布局与持久化、配置注入、时间与 UTC、超时与优雅关闭、进程管理、健康检查、更新回滚、可迁移、Bot 与沙箱的隔离。
上游：`docs/architecture.md`（形态与分层）、`docs/security.md`（边界与权限）。
改动影响：部署方式或持久化目录变化需同步 `docs/database.md`（备份）、`TODO.md`（阶段）。

## 1. 环境契约（同一份代码，两种环境）

- 开发：本机 Windows（可选 Docker），用于编写与离线测试；沙箱在 Windows 上只用 FakeBackend 离线测试，不跑真实容器。
- 生产：Linux VPS（rootless Podman），按 24/7 服务运行；VPS 上线清单见 §12。
- 允许存在的差异只有 `.env`、容器运行时与进程托管方式；业务代码不写平台分支、不依赖 Windows 特性。
- 禁止把本机路径、用户名、主机名、IP、域名写进代码或文档。
- 路径一律用 `pathlib` + 配置项拼接，不用字符串硬编码盘符或斜杠。
- 支持部署方式：Docker/Podman 容器，或 systemd 直接跑 Python。
- 贴纸登记属一次性本地运维操作：`python scripts/register_sticker.py --chat-id … --file-id … --file-unique-id … --valence … --arousal … [--tags a,b] [--db storage/bot.db]`；只读写 SQLite、不读 `.env`，数据库 schema 版本需要 ≥2（先启动一次 Bot 应用迁移）；输出不回显 `file_id`。
- 笔记登记同样属一次性本地运维操作：`python scripts/register_note.py --chat-id … --name … --text "…" [--db storage/bot.db]`；只读写 SQLite、不需要凭据，schema 版本需要 ≥3。
- 单机单进程优先；不引入 Kubernetes、微服务、Redis（明确不做清单见 §11）。

## 2. 目录布局与持久化

- `app/`（代码）：无状态，可随时重建；容器镜像只包含代码。
- `storage/`（持久数据）：`bot.db`、`workspaces/<chat_id>/`、`logs/`、`backups/`。
- 容器部署必须把 `storage/` 挂成 volume 或绑定挂载，容器重建/升级不得丢数据。
- 目录真值以 `.env.example` 为准：`DATA_DIR`、`DB_PATH`、`WORKSPACE_ROOT`、`LOG_DIR`、`SANDBOX_TEMP_DIR`；默认值是相对路径，按**进程工作目录**解析，VPS 上建议写绝对路径（见 §12.4）。
- 首次启动由程序创建缺失目录；目录不可写时拒绝启动（fail-closed）。

## 3. 配置注入

- 只有 `app/config.py` 读取环境变量；其余模块只接收 `Settings`（见 `docs/architecture.md` §2）。
- 必填只有 `BOT_TOKEN` 与 `LLM_API_KEY`（无默认值，缺失拒绝启动）；其余键都有代码默认值（`LLM_BASE_URL`、`LLM_MODEL`、`DATA_DIR`、`DB_PATH`、`WORKSPACE_ROOT`、`LOG_DIR`、`SANDBOX_TEMP_DIR`、`TIMEZONE` 等）。生产环境建议把路径类键显式写出来（见 §12.4）。
- 实例身份：`BOT_INSTANCE_ID`（默认 `default`）。多实例部署时每实例注入不同的 `DATA_DIR`/`DB_PATH`/`WORKSPACE_ROOT`，互不共享目录（见 `docs/domain.md` §2）。
- `.env.example` 列出常用键与默认值；`.env` 只写需要覆盖的键。键名拼错会被**静默忽略**（走默认值），改完按 §12.5 核对启动日志里的 `配置加载完成` 一行。

## 4. 时间与 UTC

- 数据库内部一律 UTC（Unix 秒）；展示层与记账日再按 `TIMEZONE` 转换（默认 `Asia/Shanghai`）。
- 按天聚合的 `usage.day` 按 `TIMEZONE` 归属（见 `docs/database.md` §1）。
- 日志时间戳带时区；跨时区排查时以 UTC 为准。

## 5. 超时与优雅关闭

- 全部外部调用有上限：LLM 请求、工具执行、沙箱执行、Telegram 出站、数据库忙等；禁止无限等待。
- SIGTERM/SIGINT：停止接收新更新 → 限时排空当前任务与出站队列 → 落库并关闭数据库与 HTTP 连接。
- 排空超时后强制退出；出站队列中未发送的消息**不重试**（避免重复发送）。
- 所有后台任务（清理、摘要、备份）必须可停止、可恢复，不依赖手动 Ctrl+C。

## 6. 进程管理与自愈

- 单机单进程；同一 Bot Token 只允许一个 polling 进程。
- 托管方式（阶段 9 交付）：systemd（`Restart=always`）或容器 `restart: unless-stopped`。
- VPS 重启后自动拉起；SQLite 与 workspace 保留，直接恢复运行。
- 实例生命周期由部署控制：创建/停用实例 = 写配置 + 启/停进程；阶段 1–9 不做进程内热加载（见 `docs/architecture.md` §10）。

## 7. 健康检查

- 只读轻量：进程存活、最后一次成功处理更新的时间戳、数据库可读、出站队列深度。
- 形态：`storage/health.json` 心跳 + 日志；不新开 HTTP 端口。
- 健康检查不得调用 LLM、不得产生 token 成本；失败只告警、不自动重启（避免重启风暴）。

## 8. 更新与回滚

- 更新 = 拉取新代码 / 重建镜像 → 停旧起新 → 迁移在启动时前进；数据目录不动。
- 回滚 = 起上一个镜像或提交；回滚前先备份数据库（见 `docs/database.md` §5）。
- `user_version` 高于代码支持的版本（降级运行）时拒绝启动，不静默改库。

## 9. 可迁移

- 只依赖三样：容器运行时、持久目录、`.env`。
- 不得依赖特定 VPS 厂商、IP、域名、用户名、磁盘绝对路径。
- 换机步骤固定为：重新部署代码 + 恢复持久数据 + 配置 `.env`；任何一步需要改代码都算缺陷。

## 10. 系统隔离（Bot 与沙箱）

- Bot 进程以非 root 专用用户运行，不属于 `docker` 组。
- Bot 进程自身**不挂载 docker/podman socket**，拿不到创建容器或宿主 root 的能力。
- `run_code` 经独立沙箱执行（见 `docs/security.md` §4）；沙箱只看到本群 workspace 与一个干净临时目录。
- 若确需调用容器运行时，只能由权限受限的独立组件用固定模板调用（白名单参数）。
- 模型永远拿不到宿主 shell、容器 socket、宿主目录、宿主环境变量。
- 沙箱镜像 `python:3.12-slim` 由**部署阶段预拉取**（`podman pull` / `docker pull`），运行期不 pull、容器无网络；
  `run_code` 运行期只做本地执行，不做任何下载。
- 沙箱后端用 rootless Podman：专用非 root 用户运行，`SANDBOX_TIER_B=auto` 时用 `--userns=keep-id` 映射宿主 uid，
  容器内仍是非 root 用户并只能读写本群 workspace；Docker 只支持 Tier A（无 workspace 写入）。
- 上线或换机后跑一次真实验收 `scripts/verify_sandbox.py`（无网络、非 root、只读根、越界写失败、超时销毁、
  其他群 workspace 与宿主目录不可见）；Tier B 任一项不 PASS 就把 `SANDBOX_TIER_B=off` 只保留 Tier A。

## 11. 明确不做（阶段 1–9）

Kubernetes、微服务、Redis、外部数据库、Nginx、Webhook 入口、多机 HA、CI/CD 平台、自动扩容。

## 12. Linux VPS 上线准备（阶段 7 沙箱）

正式生产目标是 **Linux + rootless Podman**；Windows 只做开发与离线测试（沙箱走 FakeBackend，不跑真实容器）。
本节是 VPS 到位后的上线清单。**真机验收已在阶段 7 完成**（Debian 12 + rootless Podman 4.3.1 + cgroup v2 + Python 3.11.2，13 项全 PASS：Tier A 7/7、Tier B 4/4）；
当前事实、commit 与证据路径见 `docs/status.md`，条件与判读契约仍以本节 §12.1–§12.7 为准。

### 12.1 目标机条件

- Linux（x86_64 / arm64）+ systemd + cgroup v2；Podman ≥ 4 且以 rootless 运行（`podman info` 显示 `cgroupVersion: v2`）。
- 专用非 root 用户运行 Bot（下称 `<bot 用户>`）：不属于 `docker` 组、不挂载 podman socket。
- 已装 Python ≥3.11 虚拟环境与 Podman CLI；项目目录含 `app/`、`.env`、`storage/`。
  （真机基线是 Debian 12 官方 `python3.11` + `python3-venv`，**不要求 3.12**；本机开发环境为 3.13。应用代码不使用任何 3.12 专有特性，`python:3.12-slim` 只是**沙箱镜像**，与宿主解释器无关。）
- 资源建议：内存 ≥ 1 GB（Bot 常驻 + `SANDBOX_MEMORY_MB` 256 × `SANDBOX_MAX_CONCURRENT` 2），磁盘 ≥ 5 GB（镜像 + 数据 + 日志）。
- 容器运行时是**可选依赖**：没有 Podman/Docker 时 Bot 照常运行，只是 `run_code` 一律 `sandbox_unavailable`（fail-closed，不退回宿主机）。

### 12.2 安装并启用 rootless Podman（一次性）

```bash
sudo apt-get update && sudo apt-get install -y podman        # Debian/Ubuntu；RHEL 系用 dnf install podman
sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 <bot 用户>
sudo loginctl enable-linger <bot 用户>
```

用**运行 Bot 的同一个用户**（不加 `sudo`）核对：

```bash
sudo -iu <bot 用户>
podman info --format '{{.Host.Security.Rootless}}'   # 必须输出 true
grep <bot 用户> /etc/subuid /etc/subgid               # 各一行，范围不重叠
```

- 报 subuid/subgid 相关错误时执行 `podman system migrate` 后重试。
- 拉镜像受网络影响：部署阶段先配好镜像源或代理；运行期不再下载（见 §12.3）。

### 12.3 预拉沙箱镜像（运行期禁止 pull）

```bash
podman pull python:3.12-slim
podman image exists python:3.12-slim && echo IMAGE_OK
```

### 12.4 目录、属主与 `.env`

- VPS 上用绝对路径写 `DATA_DIR`、`DB_PATH`、`WORKSPACE_ROOT`、`LOG_DIR`、`SANDBOX_TEMP_DIR`（默认值是相对**进程工作目录**的相对路径）。
- `storage/`（`bot.db`、`workspaces/`、`logs/`、`sandbox/`）属主必须是 `<bot 用户>`；程序首次启动创建缺失目录，不可写则拒绝启动。
- `.env` 权限 `600`、属主同一用户；不要放进 `storage/`，不要提交进 Git。
- 沙箱键保持默认即可：`SANDBOX_BACKEND=auto`、`SANDBOX_IMAGE=python:3.12-slim`、`SANDBOX_TIER_B=auto`、`SANDBOX_MAX_CONCURRENT=2`；**不要**改成运行期自动拉取镜像。

### 12.5 启动 Bot

```bash
cd <项目根>            # 含 app/、.env、storage/
.venv/bin/python -m app.main
```

启动日志逐项核对（任一不对先不要开放 `run_code`）：

- `配置加载完成 … SANDBOX_BACKEND=auto …`：确认 `.env` 真被读到（键名拼错会被静默忽略，见 §3）。
- `沙箱状态 {'backend': 'podman', 'available': True, 'workspace_write': True|False, …}`：`available=False` 说明后端不可用，此时 `run_code` 一律 `sandbox_unavailable`（fail-closed）。
- `Bot 就绪 username=… bot_id=… model=…`：轮询已建立。
- 停止用 `SIGTERM`（`Ctrl+C` 或 `kill <pid>`）：停收更新 → 限时排空 10 秒 → 落库并关闭；**不要** `kill -9`。
- 阶段 1–9 不做进程内热加载：改 `.env` 或代码后重启进程。

### 12.6 真机验收 `scripts/verify_sandbox.py`

```bash
cd <项目根>
.venv/bin/python scripts/verify_sandbox.py           # 镜像已预拉取（推荐）
.venv/bin/python scripts/verify_sandbox.py --pull    # 允许脚本先拉取镜像（仅部署阶段）
```

- 必须与 Bot 用**同一个用户、同一份配置**执行；脚本只写 `storage/workspaces/999001/`（结束时删除）与沙箱临时目录探针。
- 输出逐项 `PASS/FAIL`，末尾给出 `Tier A` / `Tier B` 结论与 `合计 N 项，失败 M 项`；退出码 0 = 全部通过。
- **判读注意（已核实）**：`无网络` 与 `只读根` 是「期望非零退出」的负向断言，只要退出码非零就 PASS，
  **区分不出「容器根本没启动」与「被正确拒绝」**（阶段 7 首次验收曾因此漏报 7 项 workdir 启动失败）；
  且正文里 `Tier A：PASS` 只聚合名字以 `Tier A` 开头的 1 个检查项。
  判读时必须同时看逐项输出、`合计 N 项，失败 M 项` 与失败计数（技术债见 `TODO.md`）。

| 结论 | 判定方式 | 后续动作 |
|---|---|---|
| Tier A 通过 | Tier A 各项全 PASS：纯计算、非 root、无网络、只读根、fsize 上限、cgroup 资源上限、超时销毁、无残留容器、临时目录已清理 | 可开放纯计算 `run_code` |
| Tier B 通过 | `workspace_write=True` 且 Tier B 各项全 PASS：本群 workspace 读写且容器内非 root、其他群不可见、宿主目录不可见 | 可开放 `workspace=true` |
| Tier B 失败 | `workspace_write=False`，或 Tier B 任一项 FAIL | 在 `.env` 写 `SANDBOX_TIER_B=off` 并重启，只保留 Tier A；**不要**用 privileged / root / 宿主目录挂载放宽 |

### 12.7 开放 `run_code`（群开关）

- `run_code` 是 L3 工具，群开关 `chat_settings.allow_code` 默认 0；`workspace=true` 还需要 `allow_write`（见 `docs/security.md` §2）。
- 阶段 8 之前没有群主命令，只能按 `docs/database.md` §2 直接改 `chat_settings`（先停进程再改，避免并发写）；改完重启进程。
- 验收未通过或不确定时保持关闭：默认关闭时该工具不会出现在提示词里。

### 12.8 24/7 运行注意（当前实现已具备）

- 数据全在 `storage/`：SQLite（WAL + `busy_timeout=5000`）、每群 `workspaces/`、`logs/`、`sandbox/`；备份与恢复见 §8 与 `docs/database.md` §5（自动备份任务属阶段 9，当前需人工 `sqlite3 .backup`；WAL 模式下不要直接 `cp` 数据库文件）。
- 日志：`LOG_DIR` 下 5 MB × 3 轮转，统一经 SecretFilter 脱敏；日常 `LOG_LEVEL=INFO` 足够，排查时临时改 DEBUG。
- 沙箱临时文件用后即删；启动时清理带 `groupbuddy=1` 标签的残留容器；被 `SIGKILL` 后可能留下空临时目录，直接清空 `SANDBOX_TEMP_DIR` 即可。
- 健康检查（`storage/health.json`）与 `/health` 属阶段 8；当前以「进程存活 + 日志 + `scripts/verify_sandbox.py` 是否通过」判断状态。
- 单机单进程：同一个 Bot Token 只允许一个 polling 进程；进程托管（systemd 或容器 `restart`）属阶段 9。