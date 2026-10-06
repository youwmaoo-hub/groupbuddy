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
- 三层职责：**适配器**（今天 `app/telegram/`，将来 `app/control/`）→ **服务**（今天 `app/session/`，阶段 10 抽 `app/services/`）→ **领域/存储/工具**（`app/domain/`、`app/storage/`、`app/tools/policy.py`）。
- 适配器只做协议转换：不得直连 SQLite、workspace、工具执行器、沙箱；控制面板的一切读写经 Control API → 服务层（`docs/domain.md` §3）。
- `app/domain/` 只放对象与身份（纯数据结构），不反向依赖任何业务层。

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
| | `app/gate/filters.py` | 入口硬过滤：自身/其他 Bot、无文本、命令；私聊默认丢弃（§2.2） |
| | `app/gate/trigger.py` | 发言判定：强触发 → 可解释内容 → 上下文追问 → 冷却/窗口闸门；输出 RESPOND / WAIT / IGNORE |
| | `app/gate/limits.py` | 主动发言的冷却与每窗口上限（进程内状态，按 `chat_id` 隔离） |
| | `app/gate/debounce.py` | 静默窗合并多条消息；批次带"是否全部未点名"标记（`proactive`） |
| | `app/gate/queue.py` | per-chat 串行 actor；运行期间新消息合并为下一轮一批 |
| 会话 | `app/session/runner.py` | 一轮编排：context → llm → tools → outbound |
| | `app/session/context.py` | ContextBuilder：预算式历史 + 噪声过滤；窗口按本轮边界（`id` 快照）截断 |
| 模型 | `app/llm/client.py` | OpenAI 兼容客户端（base_url 可换厂商） |
| | `app/llm/loop.py` | 工具循环；轮次/时长/成本上限 |
| | `app/llm/prompts.py` | 固定段：全局人格（`docs/persona.md`）→ 群设定 → 工具策略 → 输出规则；动态段末条可注入当前情绪 |
| 工具（阶段 3） | `app/tools/registry.py` | name → Tool 实例；按等级裁剪可暴露清单 |
| | `app/tools/policy.py` | 权限判定唯一出口（等级 → 本群开关，见 `docs/security.md` §2） |
| | `app/tools/executor.py` | 注册表 → 权限 → schema → 执行 → 结构化结果；失败计数与熔断 |
| | `app/tools/workspace.py` | 路径解析与文件安全（workspace 越界、符号/硬链接、UTF-8、1 MB、原子写 + 单层 `.bak`）——`read_file`/`write_file` 共用的唯一实现 |
| | `app/tools/builtin/*.py` | 已实现 `calc`、`search_web`（接口）、`read_file`、`write_file`；`send_sticker`/`host_info`/`run_code` 属后续阶段 |
| 沙箱 | `app/sandbox/runner.py` | 容器调用的唯一实现（阶段 7） |
| 存储 | `app/storage/db.py` | aiosqlite 连接、WAL、`user_version` 迁移 |
| | `app/storage/repo/*.py` | messages / settings / usage / stickers / notes 读写 |
| 领域 | `app/domain/bot_instance.py` | 领域对象：`BotInstance` 与 `LLMCredentials`（凭据唯一归属，见 `docs/domain.md` §1、§4） |
| 控制面（阶段 10） | `app/control/*` | HTTP 适配器：面板 API，只调服务层（现不存在） |
| 服务（阶段 10） | `app/services/*` | 业务唯一入口（instances / credentials / chat_settings / usage / memory_admin / workspace_admin / status） |
| 出站 | `app/outbound/queue.py` | 统一出口；重试与退避 |
| | `app/outbound/ratelimit.py` | per-chat 与全局令牌桶 |
| 记账 | `app/observability/usage.py` | tokens / 工具调用 / 耗时 |

## 4. 数据流

```
Telegram Update
  → parse（→ IncomingMessage）
  → dedupe（update_id 幂等；重复直接丢弃）
  → filters（自身消息 / 服务消息 / 无文本 / 私聊默认 → 丢弃）
  → 落库 messages
  → trigger（RESPOND | WAIT | IGNORE；冷却/窗口闸门是程序侧判定）
  → debounce（静默窗合并，上限条数）
  → per-chat 队列（同群串行；运行期间新消息合并为下一轮一批）
  → ContextBuilder（本轮边界快照 + 全局人格 + 群设定 + 工具策略 + 动态历史 + 摘要/检索）
  → LLM 循环（可选 tool call）
        → registry 裁剪清单 → policy 判定 → executor 执行（sandbox 必要时）
  → 结果写入 messages
  → OutboundQueue（限速 / retry_after 退避 / 4096 分段）
  → Telegram
```

## 5. 并发模型

- 每 `chat_id` 一个串行 worker（`gate/queue.py`）：同群严格排队，避免回复乱序与交叉上下文。
- 不同群可并行；并行度受全局 LLM 并发信号量限制。
- **本轮（round）边界**：一轮只以"开始处理时已入库"的消息为输入（`messages.max_id` 快照）；模型调用期间新到的消息只落库，不并入本轮。
- **运行期间合并**：每个 `chat_id` 最多只有一个待处理批次，新消息并入其中并只保留最新 N 条（`debounce_max_messages`，默认 5），因此"Bot 正在思考"不会持续产生新的模型调用。
- **每轮一次**：同一群同时只有一个回复任务，一轮最多一次模型调用（阶段 3 起为一次工具循环内不超过轮次上限）与一次回复。
- **主动发言闸门**：未点名的候选消息（`question`/`troubleshoot`/`resource`/`followup`）先过冷却与每窗口上限，被压住即 `wait`（0 token、只入库）；被点名不受限制（`docs/requirements.md` §2.1）。
- 每群邮箱有容量上限，溢出策略：合并待处理批次并保留最新若干条，不无限堆积。
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
| 情绪注入 | 动态段末条可选，默认不注入 | 阶段 5+ 由贴纸/情绪数据驱动（`docs/persona.md` §2） |
| 控制面板与多实例 | 单进程单实例、`chat_id` 租户键、控制面不存在 | 每实例一进程 + Control API 调服务层（阶段 10，对象与租户键见 `docs/domain.md`） |
| 凭据存储 | `.env` → `BotInstance`（只写不读、掩码） | 面板写入 + 加密存储 + 审计（阶段 10，见 `docs/security.md` §6） |
| 多用户身份 | Telegram 用户 id 即身份 | WebUser 与 TelegramActor 分离，服务层收 `Principal`（阶段 10，见 `docs/domain.md` §3） |
| 语音输入输出 | 不存在 | 输入走工具层、输出走 `OutboundQueue` 新增媒体方法（阶段 11+，见 `docs/domain.md` §5） |

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

## 10. 控制面板接入点与返工风险（阶段 10 预留，现在不实现）

对象、身份与租户键见 `docs/domain.md`；面板只经 Control API → 服务层访问。

| # | 问题（现状） | 为什么会返工 | 现在如何预留 |
|---|---|---|---|
| 1 | `chat_id` 是唯一租户键 | 多实例下群 ID 撞车，要全表加列 + 全路径改造 | 租户键固定 `(bot_instance_id, chat_id)`；实例隔离用"每实例一份存储根"，现有表不加列 |
| 2 | 业务逻辑只经 Telegram 路径可达，repo 对任何模块开放 | 面板要么复制一套会话逻辑，要么直连 SQLite → 两套事实来源 | 定三层边界（§2）；面板只能经服务层；分层测试锁死（`tests/offline/test_layering.py`） |
| 3 | 凭据散在 `app/main.py` 与 `app/llm/client.py`，被当普通配置 | 面板写入/替换密钥时要到处改，且容易回传明文 | `app/domain/bot_instance.py` + `Settings.bot_instance()` 作唯一出口；只写不读 + 掩码（`docs/security.md` §6） |
| 4 | 没有身份模型，Telegram `user_id` 当用户 | Web 用户与 Telegram 用户混为一种身份 → 越权、审计缺失 | `Principal` 与服务层入参分离（`docs/domain.md` §3） |
| 5 | 权限判定入口阶段 3 才存在，`chat_settings` 可被直写 | 面板直写 `allow_*` 绕过策略；前端隐藏按钮被当授权 | 授权只由后端判定，设置写入走同一入口（`docs/security.md` §2） |
| 6 | 队列/限速器/去重是进程内按 `chat_id` 的状态 | 多实例塞进一个进程会互相干扰（429 退避、出站配额） | 单进程 = 单实例，多实例 = 多进程；控制面不共享运行态，不引 Redis（§1） |
| 7 | `usage` 与设置无实例维度 | 面板的配额、账单、状态需要跨实例聚合 | 运行态数据留实例库；控制面记实例级汇总（阶段 10 建表，`docs/database.md` §7） |
| 8 | 出站只有文本 `send_message` | 语音/图片进来要改所有调用点 | 出站消息将来加 `kind`；语音走"新增方法、不改签名"（`docs/domain.md` §5） |
| 9 | 日志脱敏只依赖 `Settings.secrets` 两个字段 | 面板新增凭据不会被脱敏 | `AGENTS.md` §3 规则 16：新增凭据必须注册进脱敏集合 |
| 10 | 实例在装配期固定（`build_router`/`parse_update` 注入 bot 身份） | 面板"创建 Bot"后期待热生效，误以为架构不支持 | 实例生命周期由部署控制（写配置 + 启进程），不做热加载（`docs/deployment.md` §6） |
