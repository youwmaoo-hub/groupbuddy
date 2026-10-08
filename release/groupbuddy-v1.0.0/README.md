# groupbuddy · Telegram 群宠 Bot

A single-process Telegram group-pet bot: it decides *when* to speak, keeps per-group
memory, and can call tools (calculator / web search / files / stickers / sandboxed code)
while every permission decision stays in code, never in the model.

单进程、单 Bot Token 的 Telegram 群宠：多群共用人设，数据与工作区严格隔离；
**该说话时才说话**；权限与安全边界由程序裁决，不由模型裁决。

[![tests](https://github.com/youwmaoo-hub/groupbuddy/actions/workflows/tests.yml/badge.svg)](https://github.com/youwmaoo-hub/groupbuddy/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![python](https://img.shields.io/badge/python-3.13-blue.svg)

## 它是什么

- 一个**爱接话但不刷屏**的群成员：通过筛选的人类消息默认接一句（捧场、接梗、解释、吐槽都行），
  只有噪声、重复刷屏和 20 秒冷却会让人看不到回复，被压住的消息花 0 token；判定顺序与原因码见 [`docs/requirements.md`](docs/requirements.md) §2.1。
- 一个人格驱动的对话者：全局人设 + 群级覆盖 + 动态语气段三层分离（见 [`docs/persona.md`](docs/persona.md)），
  本轮只回应当前触发消息，被跳过的消息不补答。
- 一个有记忆的成员：分档窗口、字符预算、模板化摘要、SQLite FTS5 检索（见 [`docs/memory.md`](docs/memory.md)）。
- 一个能动手的成员：`calc` / `search_web` / `read_file` / `write_file` / `send_sticker` / `host_info` /
  `run_code`（rootless Podman 或 Docker 沙箱，无网络、只读根、非 root、fail-closed）。

不是通用 Bot 框架，也不做多租户 SaaS：一进程、一 Token、多群隔离，够用且可审计。

## 快速开始

要求 **Python ≥3.11**（开发与验收基线 3.13），以及一个 Telegram Bot Token 与一个 OpenAI 兼容的 LLM Key。

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
cp .env.example .env                           # 然后填 BOT_TOKEN / LLM_API_KEY
.venv/bin/python -m app.main
```

`.env` 永不入库（见 `docs/security.md` §6）；仓库里只有 `.env.example` 的占位值。私聊默认完全不处理（`ALLOW_PRIVATE_CHAT=false`）；`run_code` 需要 `SANDBOX_BACKEND` 指向可用的
rootless Podman/Docker，缺省 `auto` 在探测不到时会**拒绝执行**而不是退回宿主机。

可选：`SEARCH_BACKEND=none|fake`（`none` 时不注册 `search_web`）、`LLM_MODEL_STRONG`（复杂轮升级档，
留空即不升级）、`QUOTA_DAILY_TOKENS` / `QUOTA_MONTHLY_TOKENS`（每群配额，0 = 不限额）。

## 离线测试

全部用例离线运行：假 LLM 客户端 + 假发送器，无网络、无真实 Token、无数据库写入宿主机。

```bash
python -m unittest discover -s tests -t .
# Ran 688 tests / OK (skipped=2)
```

- 当前基线见 [`docs/status.md`](docs/status.md) §3（本机 688 通过；Windows 上有 2 条软/硬链接用例跳过）。
- 与沙箱、容器、部署有关的结论必须另上真机验证：本机（Windows、离线、FakeBackend）只能证明离线逻辑。
- **测试是契约**：不允许为了变绿而放宽断言、删用例或跳过失败用例（见 `AGENTS.md` §3）。

## 部署

真机走 systemd 用户级单元 + rootless Podman，持久化目录与备份/恢复/回滚演练见
[`docs/deployment.md`](docs/deployment.md)（唯一权威）。代码同步用 `git bundle` 或直接 `git pull`，
两者都只依赖提交历史，可离线回滚。

## 控制面板（可选）

一个**可选的第二个进程**，与本 Bot 共用同一个 SQLite 库，只在需要看状态 / 改群设置时开：

```bash
# .env 里加（口令用 python -c "import secrets;print(secrets.token_urlsafe(24))" 生成）
# PANEL_ENABLED=true
# PANEL_TOKEN=<管理员口令，≥12 字符>
# PANEL_READONLY_TOKEN=<只读口令，可留空>
.venv/bin/python -m app.control              # 默认 127.0.0.1:8787
ssh -L 8787:127.0.0.1:8787 <user>@<vps>      # 远程用 SSH 隧道，不要直接开端口
```

- 能做：看运行概览与日志尾部（脱敏）、列群看群、改群设置（模式 / 工具开关 / 贴纸冷却 / 群人设）、
  写入或替换 `BOT_TOKEN` 与 `LLM_API_KEY`。
- 不做：不启停机器人、不写 `.env` 以外的文件、没有多用户账号、不提供公网暴露方案。
- 默认关闭且没有口令就拒绝启动；鉴权走 `Authorization: Bearer <token>`（管理员 / 只读两级）。
  完整步骤见 [`docs/deployment.md`](docs/deployment.md) §13，安全边界见 `docs/security.md` §2.3，
  为什么这样选见 [ADR 0011](docs/decisions/0011-control-panel-fastapi.md)。
- `fastapi` / `uvicorn` 是**可选依赖**，只在 `app/control/` 里 import；不开面板可以不装。

## 目录结构

```
app/
  ├── gate/       发言闸门：筛选、触发、去抖、去重、冷却
  ├── llm/        提示词、客户端、模型档位路由、工具轮次分档
  ├── session/    一轮回复的编排：上下文拼装、检索、情绪、摘要
  ├── tools/      工具注册表、程序侧权限判定、执行器、内置工具、共享工作区
  ├── sandbox/    容器沙箱（argv 冻结、fail-closed、退出码语义）
  ├── outbound/   出站队列 + 限速/退避（所有 Telegram 出站消息的唯一通道）
  ├── storage/    SQLite 访问层、repo、迁移、事务边界、冷备份
  ├── ops/        运维命令、配额、指标、贴纸目录
  ├── telegram/   入站解析、handler、发送器、管理员判定
  ├── control/    控制面板 HTTP 适配器（可选依赖：fastapi/uvicorn + 零构建静态页）
  ├── services/   业务唯一入口：面板与命令通道共用的读写路径
  └── domain/     领域对象与身份模型
tests/offline/    43 个文件、688 条离线用例
docs/             设计文档（入口见 docs/README.md 路由表）
scripts/          导入/备份/沙箱验收脚本
```

## 文档地图

先读 [`docs/README.md`](docs/README.md) 的路由表，再按需只读 1–3 个文档：

| 想了解 | 读这个 |
|---|---|
| 怎么干活、任务边界、完成标准 | [`AGENTS.md`](AGENTS.md) |
| 分层、数据流、并发、恢复 | [`docs/architecture.md`](docs/architecture.md) |
| 需求条目、行为规则、验收标准 | [`docs/requirements.md`](docs/requirements.md) |
| 人格与三层人设 | [`docs/persona.md`](docs/persona.md) |
| 工具契约（输入输出/等级/超时/错误码） | [`docs/tools.md`](docs/tools.md) |
| 权限、路径、沙箱、密钥、日志、429 | [`docs/security.md`](docs/security.md) |
| 记忆、摘要、FTS 检索 | [`docs/memory.md`](docs/memory.md) |
| 表结构、索引、迁移、保留清理 | [`docs/database.md`](docs/database.md) |
| Token/成本优化 | [`docs/token.md`](docs/token.md) |
| 为什么这样设计（ADR） | [`docs/decisions/`](docs/decisions/) |
| 控制面板怎么开、怎么用、怎么关 | [`docs/deployment.md`](docs/deployment.md) §13 |
| 当前基线、测试与验收证据 | [`docs/status.md`](docs/status.md) |
| 路线图与阶段验收标准 | [`TODO.md`](TODO.md) |

文档约定：每条规则只有一个权威文件，其它文件只引用；每份文档头部都有「负责 / 上游 / 改动影响」三行。

仓库根目录的 `优化与前言.txt` 与 `流程与要求.txt` 是最初的需求原始记录，按 `AGENTS.md` §14 保持原样不改
（其中只有 `chat_id` 语义说明与 `-100123456` 这类示例 id，没有真实凭据或真实群 id）。

## 安全与隐私

- 凭据只经 `Settings.bot_instance()` 读取，任何接口不返回明文，新增凭据必须注册进日志脱敏集合；
  `.env`、Token、API Key、运行数据库、`storage/`、备份、贴纸素材都不进版本库（见 `.gitignore`）。
- 文件访问被限制在 `storage/workspaces/<chat_id>/`；`run_code` 一律经沙箱，禁止宿主机直接执行。
- 所有 Telegram 出站消息必须经 `app/outbound/queue.py`（统一限速、退避、事件 ID 去重）。
- 文档与测试中的实例标识（bot 用户名、bot id、群 id、VPS 主机名与路径）已替换为 `<bot-username>`、
  `<group-chat-id>`、`<vps-host>`、`<bot-home>` 这类占位符。
- 第三方素材：贴纸目录引用的公开贴纸包来源与许可见 [`deploy/stickers/README.md`](deploy/stickers/README.md)；
  素材本体不入库。

## 贡献

见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。安全问题的报告方式见 [`SECURITY.md`](SECURITY.md)，
版本变更记录见 [`CHANGELOG.md`](CHANGELOG.md)。

## 许可证

[MIT](LICENSE) © 2026 youwmaoo-hub
