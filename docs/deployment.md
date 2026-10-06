# 部署与运行环境

负责：运行环境契约、目录布局与持久化、配置注入、时间与 UTC、超时与优雅关闭、进程管理、健康检查、更新回滚、可迁移、Bot 与沙箱的隔离。
上游：`docs/architecture.md`（形态与分层）、`docs/security.md`（边界与权限）。
改动影响：部署方式或持久化目录变化需同步 `docs/database.md`（备份）、`TODO.md`（阶段）。

## 1. 环境契约（同一份代码，两种环境）

- 开发：本机 Windows（可选 Docker），用于编写与离线测试。
- 生产：Linux VPS，按 24/7 服务运行。
- 允许存在的差异只有 `.env`、容器运行时与进程托管方式；业务代码不写平台分支、不依赖 Windows 特性。
- 禁止把本机路径、用户名、主机名、IP、域名写进代码或文档。
- 路径一律用 `pathlib` + 配置项拼接，不用字符串硬编码盘符或斜杠。
- 支持部署方式：Docker/Podman 容器，或 systemd 直接跑 Python。
- 单机单进程优先；不引入 Kubernetes、微服务、Redis（明确不做清单见 §11）。

## 2. 目录布局与持久化

- `app/`（代码）：无状态，可随时重建；容器镜像只包含代码。
- `storage/`（持久数据）：`bot.db`、`workspaces/<chat_id>/`、`logs/`、`backups/`。
- 容器部署必须把 `storage/` 挂成 volume 或绑定挂载，容器重建/升级不得丢数据。
- 目录真值以 `.env.example` 为准：`DATA_DIR`、`DB_PATH`、`WORKSPACE_ROOT`。
- 首次启动由程序创建缺失目录；目录不可写时拒绝启动（fail-closed）。

## 3. 配置注入

- 只有 `app/config.py` 读取环境变量；其余模块只接收 `Settings`（见 `docs/architecture.md` §2）。
- 必须注入：`BOT_TOKEN`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`DB_PATH`、`WORKSPACE_ROOT`、`TIMEZONE`、`BACKUP_KEEP`。
- 实例身份：`BOT_INSTANCE_ID`（默认 `default`）。多实例部署时每实例注入不同的 `DATA_DIR`/`DB_PATH`/`WORKSPACE_ROOT`，互不共享目录（见 `docs/domain.md` §2）。
- `.env` 与 `.env.example` 键名一一对应，模块导入即校验，缺失启动失败。

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

## 11. 明确不做（阶段 1–9）

Kubernetes、微服务、Redis、外部数据库、Nginx、Webhook 入口、多机 HA、CI/CD 平台、自动扩容。