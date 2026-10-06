# 架构

负责：分层、模块职责、依赖方向、数据流、并发模型、恢复与幂等、扩展预留点、测试缝、部署与可部署性。
上游：`docs/requirements.md`（需求变化才改架构）。
改动影响：新增模块/新表/新外部依赖，需要同步 `docs/database.md`、`docs/tools.md`、`docs/deployment.md`（运行环境契约）。

## 1. 形态

单进程 Python 3.13（≥3.11 均可）、单 Bot Token、long polling、SQLite。
不使用 Redis、消息队列、微服务、Webhook、向量数据库、microVM（阶段 1–8 都不需要）。

开发环境为 Windows（可选 Docker），生产环境为 Linux VPS 按 24/7 服务运行，**同一份代码两种运行环境**。
从阶段 1 起按 24/7 标准编写（超时、优雅关闭、可停止的后台任务）；部署物（容器与 systemd 单元）在阶段 9 交付（见 `docs/deployment.md`）。

## 2. 分层与依赖方向（单向，不可反向）

```
telegram（适配层） → gate（闸门） → session（会话编排） → llm / tools → storage / outbound
```

- `app/telegram/` 是唯一 import aiogram 的地方。
- `gate/`、`session/`、`tools/`、`storage/` 不得 import aiogram，不得 import `telegram/`。
- `app/config.py` 是唯一读取环境变量的地方；其余模块只接收 `Settings`。
- `app/main.py` 只做装配：注入 LLM 客户端与发送器，便于测试替换。

## 3. 模块地图（改代码前看这里，不要全仓搜索）

| 模块 | 文件 | 职责（一句话） |
|---|---|---|
| 入口/装配 | `app/main.py` | 建 Settings、DB、Dispatcher、队列，启动 polling |
| 配置 | `app/config.py` | `.env` → `Settings`（密钥唯一出口） |
| 日志 | `app/logging_setup.py` | 结构化日志 + 敏感字段过滤（见 security §日志） |
| Telegram 适配 | `app/telegram/handlers.py` | 注册 message/command 路由 |
| | `app/telegram/parse.py` | Update → `IncomingMessage`（实体、回复、@提及、别名） |
| | `app/telegram/sender.py` | send/edit/typing；4096 字符安全分段 |
| 闸门 | `app/gate/dedupe.py` | `update_id` 幂等 |
| | `app/gate/filters.py` | 过滤自身消息、非本产品允许的来源、服务消息、无文本 |
| | `app/gate/trigger.py` | RESPOND / IGNORE / WAIT 判定 |
| | `app/gate/debounce.py` | 静默窗合并多条消息 |
| | `app/gate/queue.py` | per-chat 串行 actor（有界邮箱） |
| 会话 | `app/session/runner.py` | 一轮编排：context → llm → tools → outbound |
| | `app/session/context.py` | ContextBuilder：预算式历史 + 摘要 + 噪声过滤 |
| 模型 | `app/llm/client.py` | OpenAI 兼容客户端（base_url 可换厂商） |
| | `app/llm/loop.py` | 工具循环；轮次/时长/成本上限 |
| | `app/llm/prompts.py` | System1 人设、System2 群设定、System3 工具策略注入 |
| 工具 | `app/tools/registry.py` | name → Tool 实例；按等级裁剪可暴露清单 |
| | `app/tools/policy.py` | 权限判定唯一出口 |
| | `app/tools/executor.py` | 校验 → 权限 → 执行 → 结构化结果；失败计数与熔断 |
| | `app/tools/builtin/*.py` | calc / search_web / read_file / write_file / send_sticker / host_info / run_code |
| 沙箱 | `app/sandbox/runner.py` | 容器调用的唯一实现（阶段 7） |
| 存储 | `app/storage/db.py` | aiosqlite 连接、WAL、`user_version` 迁移 |
| | `app/storage/repo/*.py` | messages / settings / usage / stickers / notes 读写 |
| 出站 | `app/outbound/queue.py` | 统一出口；重试与退避 |
| | `app/outbound/ratelimit.py` | per-chat 与全局令牌桶 |
| 记账 | `app/observability/usage.py` | tokens / 工具调用 / 耗时 |

## 4. 数据流

```
Telegram Update
  → parse（→ IncomingMessage）
  → dedupe（update_id 幂等；重复直接丢弃）
  → filters（自身消息 / 服务消息 / 无文本 → 丢弃）
  → 落库 messages
  → trigger（RESPOND | IGNORE | WAIT）
  → debounce（静默窗合并，上限条数）
  → per-chat 队列（同群串行）
  → ContextBuilder（人设 + 群设定 + 工具策略 + 动态历史 + 摘要/检索）
  → LLM 循环（可选 tool call）
        → registry 裁剪清单 → policy 判定 → executor 执行（sandbox 必要时）
  → 结果写入 messages
  → OutboundQueue（限速 / retry_after 退避 / 4096 分段）
  → Telegram
```

## 5. 并发模型

- 每 `chat_id` 一个串行 worker（`gate/queue.py`）：同群严格排队，避免回复乱序与交叉上下文。
- 不同群可并行；并行度受全局 LLM 并发信号量限制。
- 每群邮箱有容量上限，溢出策略：合并待处理批次并标注截断，不无限堆积。
- `update_id` 落库是幂等来源；同一条更新重复到达不会被处理两次。
- 单个 LLM 调用、单个工具调用都有超时；超时按失败处理，不阻塞队列后续任务。

## 6. 恢复与幂等

- 崩溃重启后：Telegram 会重发未确认更新，靠 `updates` 表幂等吸收（"至少一次，但只回复一次"）。
- 未完成的回复不重放历史对话，只处理新到达的更新。
- 数据库写入使用事务；同一形态的写入可重复执行而不产生重复行（唯一键 + `INSERT OR IGNORE`）。

## 7. 扩展预留（现在不实现，只留缝）

| 预留 | 现在的做法 | 将来 |
|---|---|---|
| 论坛主题 | 所有内容表带 `thread_id`（默认 NULL） | 按主题隔离记忆 |
| 横向扩展 | 单进程 polling | 需要时改 Webhook（同一 Token 只能一个 polling 进程） |
| 每群独立 Bot | 单 Token + `chat_id` 租户键 | 多 Token 部署多实例 |
| 模型档位 | 单模型名可配置 | 按复杂度路由（见 token §运行侧） |
| 代码执行强度 | Docker/Podman | gVisor/Kata/Firecracker（仅在确有高风险需求时） |
| 沙箱隔离强度 | 一次性容器，Bot 进程不接触容器运行时 socket | 受控沙箱服务 / rootless / microVM（确有必要时） |
| 部署方式 | 单机单进程 + long polling | systemd 或容器托管，24/7 自愈（阶段 9） |

## 8. 测试缝（为离线验证而存在）

- `LLMClient` 与 `Sender` 通过构造参数注入；测试用假实现（脚本化回复、记录出站）。
- `gate`/`session` 不依赖 aiogram，可直接用普通数据结构驱动。
- `tests/offline/` 用标准库 `unittest`，不需要网络、不需要真实 Bot Token、不需要 API Key。
- 本地开发（Windows）与生产（Linux VPS）跑同一套代码，不维护平台分支。

## 9. 可部署性约束（细节见 `docs/deployment.md`）

- 与宿主机解耦：不写死本机路径、用户名、平台特性；路径只用 `pathlib` + 配置项（§1）。
- 配置全注入：唯一读取环境变量的地方是 `app/config.py`（§3）。
- 单机单进程优先：不引入 Kubernetes、微服务、Redis；同一 Bot Token 只允许一个 polling 进程（§6）。
- 持久化独立：`bot.db`、`workspaces/`、日志、备份都放 `storage/`，容器重建不丢（§2）。
- 可停止与可恢复：全部外部调用有超时，收到关闭信号后优雅退出并排空队列（§5）。
- 健康检查只读：心跳 + 日志，不调用 LLM、不产生成本（§7）。
- 可迁移：换机只需重新部署代码 + 恢复持久数据 + 配置 `.env`（§9）。
