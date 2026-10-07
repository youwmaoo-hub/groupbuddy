# 开发路线图

负责：阶段划分、每阶段交付与验收、当前进度、技术债登记（本轮只登记、不修复）。
上游：`docs/requirements.md`（条目编号与优先级）。
改动影响：只改本文件的阶段状态；阶段内容细节改动应回到 `docs/requirements.md`。

## 当前状态

**当前事实只有一个来源：`docs/status.md`**（commit、已完成能力、本机与真机测试、真机验收证据、技术债摘要、下一步）。本节只保留阶段进度。

- 阶段 0–7：**已完成**。阶段 0 含部署约束增补（Windows 开发 / Linux VPS 24/7 生产，同一份代码，见 `docs/deployment.md`）；阶段 1 曾通过真实 Telegram + DeepSeek 端到端验收；阶段 7 的 Linux/Podman 真机验收**已完成**（13/13 PASS，commit 与日志路径见 `docs/status.md`）。
- 阶段 8（权限、配额与运维）：**已完成并通过真机验收**（真机 checkout `88531d2` = 本机 `main` HEAD：416 条全量 OK、沙箱 13 项全 PASS、migration 4 与 `host_info` Linux 行为符合契约，见 `docs/status.md` §4.2）—— 群主命令最小闭环（管理员判定 + `/settings` 回显与写入 + 非管理员被拒，见 `docs/security.md` §2.1）、日/月 token 配额（见 `docs/token.md` §4.1）、运行指标 `/stats` + `/health`（与 `storage/health.json` 同一状态，见 `docs/deployment.md` §7）、`host_info`（F4.7）、四模式完整生效（`docs/token.md` §5）以及 T12/T15；群宠体验升级已实施（`ba7afe1`：主动接话三条弱触发与人类中心、DeepSeek 大肥鱼 Persona、贴纸 catalog 与批量导入，见 `docs/requirements.md` §2.1 与 F2.8–F2.11、`docs/persona.md`、`deploy/stickers/README.md`）；阶段 8 内明确留到后续的**两项均已实施**：链 3 轮次分档（`a5bf651`，闲聊 1 轮、其余沿用全局上限）与模型档位路由（已于 `e26ea3c` 实施，见 `docs/token.md` §5.1/§5.2；`/clear` 作为阶段 8 留后项已于 `8b14aab` 补做、群级人设 Persona 已由 `c29ecac` 补做、长期笔记 `/note` 已由 `495389b` 补做（记忆体验优化第一项），工具体验优化 T31 已由 `e1dcb6a` 修复（工具清单逐轮重取），见 §阶段 8）。阶段 9（部署与 24/7 运行）：**进行中 —— 最小生产闭环已完成并通过真机实测**（systemd 用户级单元 `groupbuddy.service`、真实 `.env` 600、启动时 migration、`storage/health.json` 心跳、Telegram 真机收发、stop/start/restart 与 `SIGKILL` 自动重启；证据见 `docs/status.md` §4.3、契约见 `docs/deployment.md` §12.9），**备份/恢复与更新/回滚演练也已完成并真机验证**（`scripts/backup_db.py` + §8.1 bundle 流程，真机当前已同步到本机 `main`（群宠体验升级 + 104 槽贴纸 catalog 已上线并真机验收，2026-10-08，证据见 `docs/status.md` §4.6），证据见 `docs/status.md` §4.4），未完成部分见 §阶段 9 的「待做」。B 组技术债：T25 关键路径补测已完成（`6b93fd6`，只加测试），T7 验收脚本判定口径已修复（`4ea2326`，含 4 条离线测试），T9 repo 写入事务边界已修复（`1826d89`，含 10 条离线测试，契约见 `docs/database.md` §6），T4 容器运行时保留退出码已映射 `execution_failed`（含 2 条离线测试，契约见 `docs/tools.md` §2 `run_code`），验收脚本能力/提权覆盖 T6 与贴纸 Unix 秒 T10 已修复（`b41bff4`，含 1 + 1 条离线测试，契约见 `docs/deployment.md` §12.6、`docs/security.md` §4、`docs/database.md` §1）—— B 组技术债至此没有未修复项。阶段 10（Web 控制面板与多实例）：**未开始**。阶段 10 仅完成架构预留（`docs/domain.md`、`docs/architecture.md` §10），未开发面板、未建控制面表。
- 一次只推进一个阶段；不得跳阶段。

## 阶段表

### 阶段 1 · 最小可运行闭环

- 交付：`app/config.py`、`app/storage/db.py`+schema、`app/telegram/parse.py`、
  `app/gate/{dedupe,filters,trigger,debounce,queue}.py`、`app/llm/{client,loop,prompts}.py`、
  `app/session/{context,runner}.py`、`app/outbound/{queue,ratelimit}.py`、
  `app/telegram/{handlers,sender}.py`、`app/main.py`、`tests/offline/`
- 覆盖需求：F1.1–F1.11、F2.1、F2.6、F2.7
- 验收：
  1. 群里 @Bot 能稳定得到一次回复；
  2. 连发 4 条消息只产生 1 次模型请求（debounce 生效）；
  3. 重放同一个 `update_id` 不产生第二次回复；
  4. Bot 自己的消息不触发回复；
  5. 超过 4096 字符的回复按 `docs/security.md` §10 规则分段且内容完整；
  6. `usage` 表有本次调用的 token 记录；
  7. `tests/offline/` 全部通过（无网络、无真实凭据）；
  8. 私聊消息 0 次模型调用、0 token、不写入 `messages`（只留必要元数据）；
  9. 模型调用期间到达的消息不出现在本轮请求里，且本轮结束后只产生 1 次新一轮调用。
- 明确不做：任何工具、贴纸、摘要/FTS、workspace 文件操作、沙箱、群设置命令、模式、配额强制、webhook。

### 阶段 2 · 发言闸门

- 交付：F2.2–F2.5（可解释内容、上下文追问、冷却与每窗上限、`NO_REPLY`），
  以及不要求 @ 的主动回复判定（`docs/requirements.md` §2.1 第 1 条）。
  实现位置：`app/gate/trigger.py`（判定顺序与原因码）、`app/gate/limits.py`（冷却与每窗口上限）、
  `app/session/runner.py`（追问距离查询与冷却记账）。
- 验收：未点名的追问会接话；纯捧场消息 0 成本；高频群里 Bot 不会连续插话。
  离线覆盖：`tests/offline/{test_gate,test_limits,test_pipeline}.py`。

### 阶段 3 · 工具主干

- 交付：`tools/registry.py`、`tools/policy.py`、`tools/executor.py`、`calc`、`search_web`（F4.1–F4.3、F4.8）
  实现位置：`app/tools/{registry,policy,executor}.py`、`app/tools/builtin/{calc,search_web}.py`、
  `app/llm/loop.py`（工具循环）、`app/llm/client.py`（tool_calls）、`app/session/runner.py`（装配）、`app/config.py`。
- 验收：模型能算数、能查资料；越权调用被拒且只回一句话；非法参数返回 `invalid_arguments`。
  离线覆盖：`tests/offline/{test_calc,test_search,test_policy,test_executor,test_loop,test_pipeline}.py`。
  注：`search_web` 真实后端未定（`docs/requirements.md` §4 #1），默认 `SEARCH_BACKEND=none` 时不下发该工具。

### 阶段 4 · 工作区与文件

- 交付：F4.4（`read_file`、`write_file`、路径安全、原子写 + `.bak`）
  实现位置：`app/tools/workspace.py`（共享路径与文件安全）、`app/tools/builtin/{read_file,write_file}.py`、
  `app/tools/builtin/__init__.py`（注册，走 `allow_read`/`allow_write` 群开关）。
- 验收：`docs/security.md` §11 的路径逃逸用例全部被拒；覆盖写有备份。
  离线覆盖：`tests/offline/test_files.py`（路径逃逸/符号与硬链接/跨群隔离/行区间/UTF-8/1 MB/单层 `.bak`/原子写）与 `test_pipeline.py` 的两个端到端用例。
- 明确不做：阶段 5 及之后（`send_sticker`、记忆与 FTS、`run_code` 沙箱、`host_info`/权限/配额/群主命令）；
  不判断 Telegram 用户身份（`allow_write` 默认关闭，谁能开属阶段 8）；不做目录列举/通配符/删除/重命名；不做版本链与自动清理。

### 阶段 5 · 贴纸

- 交付：F4.5（`stickers` 表、情绪匹配、冷却）
  实现位置：`app/storage/schema.sql`（migration 2）、`app/storage/repo/stickers.py`、`app/tools/builtin/send_sticker.py`、
  `app/session/mood.py`、`app/outbound/{queue,ratelimit}.py`（贴纸通道）、`scripts/register_sticker.py`（运维登记，一次性）。
- 验收：情绪匹配合理、受冷却与限速约束、模型上下文不出现 `file_id`。
  离线覆盖：`tests/offline/{test_stickers,test_mood,test_outbound,test_pipeline}.py`。
- 明确不做：群主 `/sticker` 命令与面板（阶段 8/10）；自动抓取/学习/贴纸包管理；语音与通用 `send_media()`（阶段 11+）；
  mood 持久化与情绪历史；贴纸统计与审计；不判断 Telegram 用户身份（`allow_sticker` 默认开，谁能改属阶段 8）。

### 阶段 6 · 记忆

- 交付：F3.1–F3.4（动态窗口、噪声标记、模板化摘要、FTS5 检索）
  实现位置：`app/session/{noise,retrieval,summary}.py`、`app/session/context.py`（唯一组装点）、
  `app/storage/repo/{summaries,notes}.py`（FTS 显式同步）、migration 3（summaries/notes/FTS + `usage.purpose`）、
  `scripts/register_note.py`（一次性运维写入口）。
- 验收：长会话后仍能回答"之前那个怎么搞的"；摘要遵循模板；检索只补背景。
  离线覆盖：`tests/offline/{test_noise,test_retrieval,test_summary}.py` 与 `test_storage.py`/`test_pipeline.py` 扩展。
- 明确不做：向量检索/embedding、Redis、跨群/全局记忆、用户画像、群主 memory 命令、面板、Forum Topic 实际逻辑、
  mode 路由、search_web 后端与知识缺口行为、阶段 7 sandbox；不引入新依赖（含分词库）；不把消息原文索引进 FTS。

### 阶段 7 · 沙箱 run_code

- 交付：F4.6（`app/sandbox/` + 固定容器参数）；`spec.py` 是 argv 白名单唯一拼装点，`backends.py` 启动时探测一次后端
  （rootless Podman 优先、Docker 备选）并只用 CLI 调用，`runner.py` 是唯一执行入口（并发 2、超时 kill 并销毁容器、
  输出各 8 KB 截断、临时输出目录用后即删、启动清理 `groupbuddy=1` 残留容器），`preflight.py` 只记日志提示；
  工具与装配见 `app/tools/builtin/run_code.py`；Tier B 仅在 rootless Podman + `SANDBOX_TIER_B=auto` 时可用。
- 前置：本机有可用的 Podman/Docker；否则 `run_code` 一律返回 `sandbox_unavailable`（fail-closed，不退化到宿主机）。
  Bot 进程不接触 docker/podman socket（见 `docs/security.md` §4、`docs/deployment.md` §10）。
- 验收：容器内无网络、越界写失败、超时被 kill 且容器销毁；离线覆盖 `tests/offline/test_sandbox.py`（26 条）；
  真实验收由目标机（Linux + rootless Podman）执行 `scripts/verify_sandbox.py`（上线清单与判读口径见 `docs/deployment.md` §12.6）。
  **真机结果**：已完成，13 项全 PASS（Tier A 7/7、Tier B 4/4），证据见 `docs/status.md`；Tier B 未全 PASS 时应设为 `SANDBOX_TIER_B=off`。
  该脚本的判定口径曾偏弱，已于 `4ea2326` 修复（探针标记 + 错误签名 + 显式 tier 聚合 + 4 条离线测试，见下方技术债 T7）。
- 明确不做：Tier C、`pip install`、容器联网、自定义镜像、microVM/gVisor/Kata、Redis/K8s、配额与管理员权限。

### 阶段 8 · 权限、配额与运维

- 交付：F5.1–F5.4、`host_info`（F4.7）、四种模式（`docs/token.md` §5）、`/health`（实现属本阶段；24/7 托管与自愈属阶段 9）
- 验收：群主可开关工具等级；非管理员被拒；配额打满后优雅拒绝。
- 已完成（`7382639` F5.2、`c49fdc5` F5.1）：群主命令通道 —— `app/ops/admin.py` 管理员判定（只认 `getChatAdministrators`、进程内缓存、失败 fail-closed）、`app/ops/commands.py` `/settings` 回显与 `/settings <字段> <值>` 写入（字段白名单：模式、6 个工具开关、贴纸冷却；非法输入不写库；改完当轮生效）、命令不进模型不写 messages 0 token、未知命令静默、非管理员固定文案；`chat_settings.upsert` 改为单条原子写入（T12）。
- 已完成（`1d649b8` F5.3）：日/月 token 配额 —— `app/ops/quota.py` `QuotaGuard`（`QUOTA_DAILY_TOKENS` / `QUOTA_MONTHLY_TOKENS`，按 `chat_id` 分别统计，`0` 或未配置 = 不限额）、调用模型前判定（`>=` 上限即拒绝）、超额本轮不调模型不记账只回一句提示、命令不消耗配额；统计复用 `usage.tokens_used`（`input_tokens + output_tokens`，缓存命中不重复计入）。契约见 `docs/token.md` §4.1。
- 已完成（`101c26c` F5.4）：运行指标 —— `app/ops/metrics.py` `/stats`（复用 `usage.summary_for_day` + `tool_failures.count`，按群当日 token 用量、工具调用/失败与错误率、配额余量；读取失败只回固定短句）、`app/ops/health.py` `/health` 与 `storage/health.json` 心跳**共用同一个 `HealthState`**（60 秒周期、原子写、快照无路径/堆栈/凭据）；`tool_failures` 表随 migration 4 建立（`app/storage/repo/tool_failures.py`，计入熔断的失败留痕、按群区间计数、7 天清理即 T15），命令仍走管理员判定、0 token、不进模型。契约见 `docs/security.md` §2.1、`docs/deployment.md` §7、`docs/database.md` §2/§4。
- 已完成（`de73b57` F4.7）：`host_info` —— `app/tools/builtin/host_info.py`（L4、`allow_host_info` 默认关、`build_registry` 始终注册），只暴露 `cpu`/`memory`/`disk_free`/`python`/`uptime_s`，`fields` 可选（去重、未知字段 `invalid_arguments`）；不读环境变量、不列进程、不查网络接口，不含主机名/用户名/IP/路径；取不到的字段返回 `null`。契约见 `docs/tools.md` §host_info、`docs/requirements.md` F4.7。
- 已完成（`78ae9cf` 四模式，阶段 8 收尾）：`app/modes.py` 作为 `docs/token.md` §5 的唯一权威表 —— economy（窗口 10、只 L0、输出 256、贴纸关）、normal（意图分档 10/20/50、群开关、配置输出）、smart（窗口 50 + 额外 L0 只读）、unrestricted（窗口 50 + 全部已注册工具 + 输出不限）；`app/session/context.py` 按模式定窗口、`app/session/runner.py` 按模式定输出上限、`app/tools/policy.py` 按模式定工具档位、`app/ops/commands.py` 的 `MODES` 指向同一来源；模式只能由管理员 `/settings mode <值>` 修改，未知值按 normal，默认（normal）行为与升级前一致。契约见 `docs/token.md` §5、`docs/security.md` §2.2。
- 真机验收（`88531d2`，2026-10-07）：VPS 工作树干净、跟踪文件 132；bot 用户全量 `Ran 416 tests` / `OK` / 退出码 0（无 skip、无 FAIL/ERROR）；`scripts/verify_sandbox.py` 13 项全 PASS、失败 0（与阶段 7 无回归）；migration 4 建出 `tool_failures` + 两个索引（`user_version` = 4）；`host_info` Linux 实测 cpu=2、memory=4105363456（= `/proc/meminfo`）、disk_free=35596984320、python=`3.11.2`、uptime_s=68691（= `/proc/uptime`）。逐项结果见 `docs/status.md` §4.2。
- 已完成（`8b14aab`，阶段 8 留后项补做）：`/clear` —— `app/ops/commands.py` 的 `_clear`（管理员限定、只删本群 `messages` 原文、摘要与用量保留、带参数只回用法、失败固定短句），复用既有 `messages.clear_chat`（T21 死代码条目随之关闭）；契约见 `docs/security.md` §2.1、`docs/database.md` §4。
- 已完成（`c29ecac`，批处理里程碑 A）：群级人设 Persona —— `/settings persona_override <文本>` **仅群主（Telegram `creator`）可写**，普通管理员与成员一律按固定拒绝文案处理且文案不含字段名；`app/ops/persona.py` 是唯一读取/清洗入口（单行化、上限 500 字符、`off`/`关` 清除），优先级 本群覆盖 > 部署侧 `PERSONA` > 内置人格；`app/ops/admin.py` 新增 `ChatRoles` + `is_owner`（与管理员同一份 300 秒缓存，失败 fail-closed），`app/telegram/admins.py` 一次 `getChatAdministrators` 同时取两者；确认与回显只出现字数、不回显正文。契约见 `docs/persona.md` §2、`docs/security.md` §2.1。
- 已完成（`495389b`，批处理里程碑 B 第一项）：长期笔记 `/note` —— 填上 `docs/memory.md` §6 一直标注「尚未实现」的写入路径。`app/ops/notes.py`（纯文本：解析/列出/查看/记住/删除、名称 ≤50 字符与正文 ≤500 字符上限、时间戳渲染）、`app/ops/text.py`（人设与笔记共用的单行化）、`app/ops/commands.py` 的 `_note`（**仅群主**，与 `persona_override` 同一 `is_owner` 判定与固定拒绝文案；0 token、不进模型；写入后回读拿权威 `version`）、`app/storage/repo/notes.py` 新增 `list_for_chat` / `delete`（删除同步清 `notes_fts` 外部内容表）；同名覆盖 `version` +1，确认与列表只回名称/版本/字数、不回显正文，写入或删除失败只回固定短句。契约见 `docs/memory.md` §6、`docs/security.md` §2.1、`docs/database.md` §3/§4。
- 已完成（`e1dcb6a`，工具体验优化）：T31 工具清单逐轮重取 —— `app/llm/loop.py` 每一轮重新取工具清单，本轮被禁用/熔断的工具不再下发给模型（清单为空即不带工具、强制给答案），`app/tools/executor.py` 的 `cooldown` 文案改用 `BreakerConfig.round_failures` 而不是写死 2。修复前第 1 轮快照会让模型继续调用只可能返回 `cooldown` 的工具，白花一整轮模型调用与 token，与 `docs/tools.md` §1、`docs/security.md` §9、F4.8 验收「失败工具不再重复调用」不符。契约见 `docs/tools.md` §1、`docs/security.md` §9、`docs/token.md` §6。
- 已完成（`e26ea3c`，主路线）：模型档位路由（最小规则型）—— 新增唯一入口 `app/llm/routing.py` 的 `ModelRouter.choose(*, intent, purpose)`：默认档 = `app/config.py` 的 `LLM_MODEL`（`deepseek-flash`），可选升级档 = 新增配置键 `LLM_MODEL_STRONG`（留空或与默认同名即视为未配置）；只有 `purpose=chat` 且 `intent=complex` 且存在升级档时才换模型，其余（简单聊天、普通任务、summary 与后台任务、无法判断）一律默认档，summary 的 `purpose="summary"` 与记账口径不变。复杂判定复用既有纯规则（`ContextBuilder.intent`：代码块 / 单条 ≥400 字 / 链接 / 指代检索需求；`window_size` 改为先取 intent 再映射窗口，旧语义不变），**不新增独立 AI 分类器、不增加额外一次 LLM 判断、不引入新依赖**；路由点在配额判定之后，不绕过 quota / tool policy / sandbox / 权限；选择过程抛错即 fail-safe 回默认档；`usage` 记最终实际使用的 model（`purpose=chat`）。`Responder.reply` 新增可选 `model` 参数并保留 `model or settings.llm_model` 兜底；`SessionRunner` 可注入 `router`。`LLM_MODEL_STRONG` 留空时行为与成本与升级前完全一致（真机 `.env` 无该键，未同步也不改变运行期行为），启用属部署决策（缓存按模型隔离，升级轮可能按未命中价计费）。契约见 `docs/token.md` §5/§5.1、`docs/architecture.md` §3/§7/§8、`docs/deployment.md` §3、`docs/requirements.md` 未决问题 #2；测试 12 + 5 条（见 `docs/status.md` §3）。
- 已完成（`a5bf651`，主路线续项）：链式工具轮次优化（按意图分档）—— 同一入口 `app/llm/routing.py` 新增 `TOOL_ROUNDS_BY_INTENT` 与 `tool_round_limit(intent, settings)`，`SessionRunner` 每轮把它作为 `Responder.reply(max_rounds=...)` 传入：**只把全局上限 `TOOL_MAX_ROUNDS`（默认 2，可选 0–4）调低，不突破部署方设置**，未登记意图与异常输入一律回全局上限。闲聊取 **1 轮**（`docs/token.md` §3 链 3 原表写 0 轮，但 0 轮意味着该轮完全不下发工具，会连贴纸工具 `send_sticker` 一起关掉，与贴纸功能冲突，故取 1 轮：保住一次工具调用又比默认档少一整轮）；**default 不降到 1**（default 覆盖普通任务里常见的 read→write 两步链，无真实证据下调会切成半成品回复）；complex 与无法判断沿用全局上限，部署方把 `TOOL_MAX_ROUNDS` 设为 4 即对应表里的「代码调试 4 轮」。`usage.tool_calls` 与实际轮次一致。契约见 `docs/token.md` §3/§5/§5.2、`docs/architecture.md` §3/§7/§8、`docs/deployment.md` §3；测试 5 + 4 条（见 `docs/status.md` §3）。
- 已完成并已真机上线（`ba7afe1` + 贴纸 catalog 104 槽 `30cc3fe`，群宠体验升级，2026-10-08；真机部署与验收证据见 `docs/status.md` §4.6）：三个方向一起落地 —— ①主动接话：`app/gate/trigger.py` 新增三条弱触发 `topic`（与 Bot 上一条发言共享非停用 2 字组，窗口 `PROACTIVE_TOPIC_MAX_MESSAGES` 默认 8）、`emotion`（情绪/反应词）、`quiet_open`（Bot 从未发言、或距上次发言 ≥ `PROACTIVE_QUIET_MESSAGES` 默认 20 条，且本条 ≥6 字），全部纯规则 0 token，**只提高候选量、不改冷却（20 秒）与窗口上限（每 300 秒 3 次）**；人类中心——`app/gate/filters.py` 与 `trigger.decide` 首行双重丢弃 Bot 作者消息（原因码 `bot_author`），其他 Bot 说话不计入冷却、额度与「话题已被回答」；`app/storage/repo/messages.py` 新增 `last_assistant_text`，`app/session/runner.py` 判定时带上它。②Persona：内置 `GLOBAL_PERSONA` 换成「DeepSeek 大肥鱼」AI 群宠定位（知道自己是 AI、知道「大肥鱼 / 鲸鱼娘」是二创形象、自称「本大肥鱼/大肥鱼/我」、技术场景少用梗、不影响权限/安全/事实），`docs/persona.md` §1/§4/§5 同步（§4 仍与代码逐字一致）。③贴纸：`deploy/stickers/catalog.json` 定义 104 个情绪槽位（不含素材本体，逐张对齐公开贴纸包 `deepseek_whale_girl`，MIT © 2026 Dejavu Moe / `DejavuMoe/deepseek_wale_girl`；生成与对齐口径见 `deploy/stickers/README.md`）、`deploy/stickers/README.md` 写规格与来源/许可政策及三种导入流程，新增 `app/ops/sticker_catalog.py`（manifest 校验、路径穿越防护、按 emoji 匹配贴纸包、幂等 UPSERT）+ `scripts/register_sticker.py --manifest`（本地目录批量，新增 `--asset-dir`/`--dry-run`，单张模式参数与输出不变）+ `scripts/import_sticker_set.py`（按 emoji 从 Telegram 贴纸包导入，只读 `BOT_TOKEN` 环境变量、不回显 Token）；素材不入 Git（`/deploy/stickers/assets/` 已 `.gitignore`），`send_sticker` 核心逻辑不变。契约见 `docs/requirements.md` §2.1/F2.8–F2.11、`docs/security.md` §12、`docs/deployment.md` §1/§3/§12.10、`deploy/stickers/README.md`；测试 7 + 4 + 19 条（见 `docs/status.md` §3）。**改变运行期行为与提示词，真机需随下一次部署复验，且需先按 §12.10 关掉 Privacy Mode 或把 Bot 设为群管理员。**

### 阶段 9 · 部署与 24/7 运行

- 交付：`Dockerfile`/`compose.yaml`（或 `deploy/bot.service`）、持久化目录约定、优雅关闭、
  健康检查、备份与恢复演练、更新回滚流程；全部按 `docs/deployment.md`。
- 前置：阶段 7 沙箱可用（需要容器运行时）。
- 验收：容器/VPS 重建后数据仍在（`bot.db` 与 workspace 未丢）；程序重启后自动恢复运行；
  SIGTERM 能优雅退出；上一份备份能恢复出可用数据库；日志与错误消息中无 Secret。
- 已完成（最小生产闭环，2026-10-07 真机实测，证据见 `docs/status.md` §4.3）：采用 **systemd 用户级单元** `groupbuddy.service`（`/home/bot/.config/systemd/user/`，`Restart=always` + `RestartSec=5` + `KillSignal=SIGTERM` + `TimeoutStopSec=30` + `NoNewPrivileges=yes`，配合 `Linger=yes` 开机自启；模板与命令见 `docs/deployment.md` §12.9），**不引入容器编排、不开新端口、不改代码**；真实 `.env`（`600`、`bot:bot`、绝对路径）就位；启动时 migration 到 `user_version`=4；`storage/health.json` 60 秒心跳；Telegram 真机收发（`updates`/`messages`/`usage` 落库、`last_update_at` 更新、日志无 WARNING/ERROR）；`systemctl --user stop` 走 SIGTERM 优雅关闭（`收到信号 signum=15` → `已关闭`）、`start`/`restart` 恢复、`kill -9` 后 `NRestarts` 0→1 自动拉起。
- 已完成（备份/恢复与更新/回滚演练，2026-10-07 真机实测，证据见 `docs/status.md` §4.4）：新增 `app/storage/backup.py` + `scripts/backup_db.py`（标准库 `sqlite3` 冷快照 → `storage/backups/bot.db.YYYYMMDD-HHMM`、单文件快照、`PRAGMA integrity_check` + 各表行数校验、按 `--keep` 保留最近 N 份；契约见 `docs/database.md` §5）与 6 条离线测试；在线备份不影响 Bot、快照 SHA256 可复现；以 bot 身份恢复出独立副本后与线上逐项一致（`IDENTICAL=yes`）、应用层可打开（`migrations_version`=4）；按 `docs/deployment.md` §8.1 本地 bundle 流程完成更新（`88531d2`→`bc31c41`）、坏版本启动失败可检出（`Result=exit-code`、`ExecMainStatus=1`、日志 `ERROR`、`Restart=always` 自动重试）、回滚到上一版本后 systemd 恢复 `active` 且 `bot.db`/workspace 未丢；bundle 已持久化到 `/home/bot/bundles/` 并重指 `origin`；演练后真机复跑：422 条全量 OK、沙箱 13 项全 PASS、`getMe` 正常、日志无 Secret（`telegram_token_like=0`、`api_key_like=0`、`[redacted]` 15 处）、`.env` 600 且未被 git 跟踪。演练用坏版本是本地一次性分支 `stage9-broken-probe`（`7474c42`，永不合并进 `main`）。
- 已完成（阶段 9 小优化 `PRAGMA optimize` 例行化，`29f6687`）：`app/storage/db.py` 新增 `optimize()`；housekeeping 循环加 `OPTIMIZE_INTERVAL_SECONDS`（7 天）门槛，启动后第一次清理执行一次、之后每 7 天一次，失败只记 `后台清理失败` 且下一轮重试；4 条离线测试（`tests/offline/test_storage.py`：只发一条 `PRAGMA optimize`、真实迁移库可重复执行；`tests/offline/test_main.py`：跑过 ≥4 轮清理仍只优化一次、失败重试）；契约见 `docs/database.md` §4 维护行、`docs/architecture.md` §5。
- 待做（阶段 9 剩余）：程序内自动备份任务与 `BACKUP_INTERVAL_SECONDS`/`BACKUP_KEEP` 环境键（当前仅手工跑脚本）、容器托管（`Dockerfile`/`compose.yaml`，可选路径）、体积膨胀时的 `VACUUM`（离线手工，不在进程内自动跑）、正式远端（GitHub）。

### 阶段 10 · Web 控制面板与多实例（暂不开发，仅预留）

- 前置：阶段 8（设置与配额）、阶段 9（部署与持久化）。
- 覆盖需求：F6.1–F6.5（语音 F6.6 属阶段 11+）。
- 子步骤：10.1 抽服务层（`app/services/`，把现在散在 `session/` 与 `repo/` 的读写收成唯一入口）
  → 10.2 控制库与凭据加密（`bot_instances`/`users`/`credentials`/`audit_log` + 主密钥托管，见 `docs/database.md` §7）
  → 10.3 Control API（HTTP 适配器 `app/control/`；引入 Web 框架属新依赖，需单独批准）
  → 10.4 前端（任意栈，只调 Control API）。
- 验收：面板只能经服务层读写；凭据只写不读且掩码显示；越权请求由后端拒绝；两个实例的记忆/workspace/配额互不可见；Web 用户与 Telegram 用户身份不混用。
- 明确不做：实例热加载、多实例共享运行态（队列/限速器/去重）、为面板引入 Redis / 微服务 / K8s。

## 推进规则

1. 一次只做一个阶段；阶段内按交付清单顺序实现。
2. 每阶段结束跑一次 `tests/offline/`，并手工验证验收清单。
3. 发现需要改契约或改需求：先停下来说明，改动后再继续（见 `AGENTS.md` §5）。
## 技术债与已知缺陷（只登记，不在文档治理任务中修复）

> 等级：**P0** = 功能静默失效或导致无法启动；**P1** = 正确性/一致性风险；**P2** = 质量与可维护性。
> 全部条目都在 commit `434f2f8` 上核实过（含 `文件:行号`）；其中 T1/T2/T3 已于 `f7f34b5` 修复（见下）。**登记不等于已批准修复**：修复需单独开任务，并按 `AGENTS.md` 的变更分级处理。

### 高危（T1–T3 已修复，保留历史）

1. **T1（P0）摘要「静默 ≥ 120 秒」触发恒不成立 — 已修复（commit `f7f34b5`）**：原实现 `app/session/summary.py` 默认 `time.monotonic()`（`app/main.py:167` 也显式传 monotonic），
   与 `pending.last_at`（`MAX(created_at)`＝Unix 秒，`app/storage/repo/messages.py:92,118`）差值约 −1.7e9，条件永不满足；离线测试用同域假时钟（`tests/offline/test_summary.py:75-79`、`tests/offline/helpers.py:19-29`）掩盖了它。
   修复：`SummaryService` 默认时钟改 `time.time`，`app/main.py` 不再注入时钟；新增 `tests/offline/test_summary.py` 的 `ClockDomainTests` 2 条（不注入假时钟）。原影响：只剩「≥40 条消息」「≥6000 字符且 ≥10 条」两条触发路径。契约见 `docs/memory.md` §4。
2. **T2（P0）迁移失败不可恢复 — 已修复（commit `f7f34b5`）**：原实现 `app/storage/db.py:72-76` 没有 `BEGIN`/`rollback`，而 migration 3 的 `ALTER TABLE usage ADD COLUMN purpose`（`app/storage/schema.sql:83`）不幂等；
   若迁移中途失败或进程被杀，`user_version` 停在 2 而列已存在，重跑报 `OperationalError: duplicate column name: purpose`，**Bot 永久无法启动**（已用内存 SQLite 复现；本机与真机的迁移块都已成功应用，未触发）。
   修复：每块 `BEGIN IMMEDIATE` + 失败 `rollback`（不推进 `user_version`），仅对 `("usage", "purpose")` 这一历史半升级形态做严格限定的兼容跳过，其他重复 DDL 仍抛真实错误；新增 `MigrationAtomicityTests` 7 条。契约见 `docs/database.md` §1/§6。
3. **T3（P1）本轮用户消息可能被裁光 — 已修复（commit `f7f34b5`）**：原 `app/session/context.py` 在 `reserved` 已超预算时会把本轮消息一并 pop，违反 `docs/memory.md` §2 与 F3.1 的「本轮永不丢」。
   修复：`build()` 生成 `keep = frozenset(item.message_id for item in batch.items)` 并传入两处 `_trim(..., keep=keep)`，`_trim` 循环遇 `keep` 即停；新增 `test_oversized_batch_survives_budget_trim`。

### 安全与沙箱

4. **T4（P1，已修复，`d59a703`）CLI 非零退出不映射 `execution_failed`**（用户点名）— 原状：只有后端调用**抛异常**时才映射（`runner.py:128-131`）；
   Podman 以 125/126/127 退出时 argv 原样成为工具结果，「容器没起来」与「程序正常失败」不可区分 —— 阶段 7 首次真机验收的 `--workdir /workspace` 事故正是由此漏报。
   修复：`app/sandbox/backends.py` 新增 `CLI_FAILURE_EXIT_CODES = frozenset({125, 126, 127})`，`runner.py` 在超时判定之后、读输出之前按该集合映射为 `SandboxError("execution_failed", …)` 并销毁容器，argv 退出码不再返回给模型；
   离线测试 2 条（`tests/offline/test_sandbox.py` 的 `RunnerTests`），契约见 `docs/tools.md` §2 `run_code`。**改动运行期行为，真机需随下一次部署复验。**
5. **T5（P2）沙箱 stderr 未清洗** — 容器/CLI 的 stderr 原样进入模型上下文（`runner.py:138,146-148`），与 `docs/security.md` §3「上下文里不出现宿主机绝对路径」冲突。
6. **T6（P2，已修复，`b41bff4`）`--cap-drop=ALL` 与 `no-new-privileges` 未被验收覆盖** — 实现在 `app/sandbox/spec.py:68-70`，但 `scripts/verify_sandbox.py` 无对应检查项。
   修复：新增两项 Tier A 检查，直接读容器内 `/proc/self/status`（不依赖 `capsh` 等镜像里可能没有的工具）——「能力集清空」要求 `CapBnd`（bounding set）为 0（容器内是非 root，`CapEff` 本来就是 0 所以不作断言），「禁止提权」要求 `NoNewPrivs` 为 1；字段缺失即 FAIL。脚本从 13 项变 15 项，判读口径同步到 `docs/deployment.md` §12.6 与 `docs/security.md` §4；`tests/offline/test_verify_sandbox.py` 加 1 条负路径（仍带能力位 / 仍允许提权必须 FAIL 并翻转 `Tier A`）并扩充全绿用例断言。**只改验收脚本与测试，不影响 Bot 运行期行为；真机需在下一次部署时复跑对齐 15 项。**
7. **T7（P2，已修复，`4ea2326`）验收脚本判定口径弱** — `want_ok=False` 的两项（无网络、只读根）任何非零退出都 PASS，区分不出「容器没启动」；
   `Tier A：PASS` 汇总只聚合 1 项（原 `scripts/verify_sandbox.py:66,76-77,145-149`）。判读口径见 `docs/deployment.md` §12.6。
   **已修复（`4ea2326`）**：两条负向断言先打印探针标记（`PROBE net`/`PROBE rofs`）再触发禁止操作，判定要求「退出码符合预期 + 探针标记出现 + 预期错误签名出现」三者同时成立（`check()` 新增 `error_contains`）；`results` 改为 `(tier, name, ok, detail)` 四元组，逐项输出带 `[A]`/`[B]`/`[AB]` 标记，`Tier A`/`Tier B` 按显式 tier 归属聚合全部相关项（含 2 项全局清理检查），任一项 FAIL 都翻转结论；新增 `tests/offline/test_verify_sandbox.py` 4 条（假后端跑脚本 `main()`：全绿、容器没起来、单项非 root 失败会翻转 `Tier A`、Tier B 未启用 fail-closed），并用旧脚本反向验证过 4 条会失败。真机复跑安排在下一次部署/里程碑。
8. **T8（P2）`resolve_path` 未复核 base 自身** — `app/tools/workspace.py:45-47` 只对拼接后的目标做 `is_relative_to`，未像 `:63-71` 那样逐段查符号链接；base 目录本身被替换为符号链接时没有保护。

### 数据与记忆

9. **T9（P1，已修复，`1826d89`）没有事务边界** — 原状：各 repo 自己 `commit()`（`app/storage/repo/summaries.py:65,136`、`notes.py:48`、`stickers.py:73,90`），
   主表 + FTS 的多语句写可能半提交、或被其他任务顺带提交；无 `rollback`。修复：新增 `app/storage/tx.py` 的 `transaction()`（`SAVEPOINT` … `RELEASE` / `ROLLBACK TO`；整进程共享一条连接，`BEGIN` 会冲突），14 个写入入口（`messages` insert/clear_chat、`chat_settings.upsert`、`usage.record`、`updates` mark_seen/purge_old、`tool_failures` record/purge_old、`notes` upsert/delete、`summaries` insert/prune、`stickers` register/mark_used）统一在事务内完成并去掉自己的 `commit()`，失败整体回滚；离线测试 10 条（`tests/offline/test_transactions.py`），契约见 `docs/database.md` §6。**改动运行期写入路径，真机需随下一次部署复验。**
10. **T10（P1，已修复，`b41bff4`）`stickers.last_used_at` 存 `time.monotonic()`**（`app/tools/builtin/send_sticker.py:113,117,146`），与 `docs/database.md` §1「统一 Unix 秒」冲突；重启后「优先未近期使用」的 tie-break 语义反转（`send_sticker.py:89-96`）。
    修复：`SendStickerTool` 拆成两个时钟——群内冷却仍用 `time.monotonic`（进程相对秒、不落库），落库改 `wall_clock`（默认 `time.time`）写 Unix 秒；契约偏差从 `docs/database.md` §1 移除（旧值只可能残留在本机开发库，数值比 Unix 秒小、语义仍是「很久没用过」，真机 `stickers` 为 0 行）；离线测试 `tests/offline/test_stickers.py` 更新断言并新增 1 条（冷却时钟 1000.0 时落库值必须 > 1.6e9 且不等于进程相对秒）。**改运行期写入值，真机需随下一次部署复验。**
11. **T11（P2）迁移解析脆弱** — 裸 `;` 切分（`app/storage/db.py:30`）、编号缺口/重复块无校验（`db.py:25,43`）、版本校验只看块数量（`db.py:67`）。
12. **T12（P2，已修复，`7382639`）`chat_settings.upsert` 读-改-写无锁**（`app/storage/repo/chat_settings.py`）：两次 await 之间可被改写，存在丢更新 —— 阶段 8 F5.2 改为单条原子 `INSERT … ON CONFLICT DO UPDATE`，只写调用方给出的列（离线测试用 `mock` 断言不再读取当前设置）。
13. **T13（P2）`notes` 没有运行时写入路径** — 只有运维脚本 `scripts/register_note.py`；500 字上限也只在脚本里校验（`app/storage/repo/notes.py` 层无约束）。
14. **T14（P2）`thread_id` 恒为 NULL** — `messages.recent()` 支持该参数（`app/storage/repo/messages.py:69-71`）但没有调用方传入；摘要、游标、FTS 都是 chat 级（阶段 8 做论坛主题隔离）。
15. **T15（P2，已修复，`101c26c`）`tool_failures` 表未建**（阶段 8 F5.4）—— migration 4 建表 + `idx_tool_failures_tool_time` / `idx_tool_failures_chat_time`，计入熔断的失败经 `ToolExecutor.failure_recorder` 留痕，启动时与每小时清理 7 天前记录（`app/storage/repo/tool_failures.py`）；进程内熔断计数仍在内存（与 `docs/security.md` §9 一致）。
16. **T16（P2）纵深防御缺口** — `stickers.mark_used` 只按 `id`（`app/storage/repo/stickers.py:88-90`）、`DELETE FROM summaries WHERE id=?`（`summaries.py:134`）；当前所有调用路径都带 chat 校验，审查未发现可利用的越权路径。

### 工具与契约

17. **T17（P2）`ToolExecutor(max_payload_bytes=...)` 参数无效**（`app/tools/executor.py:43,127-128`）：实际上限由各 `ToolSpec.max_payload_bytes`（默认 4096，`registry.py:67`）决定。
18. **T18（P2）`read_file` 的续读前提不成立** — 单次超过 16 KB 时整包丢弃 `too_large`，模型拿不到 `total_lines`（`docs/tools.md` §4）。
19. **T19（P2）`SANDBOX_OUTPUT_KB` 与 20480 耦合** — 调大沙箱输出上限后，stdout+stderr 很容易超过 `run_code` 的 `ToolSpec` 上限，工具结果整包 `too_large`（`app/tools/executor.py:133-138`）。
20. **T20（P2）`calc` 值域只对整数生效** — 结果绝对值 ≤10^100 的检查只覆盖 `int`，浮点结果只校验有限性（`app/tools/builtin/calc.py:90-97`）。

### 代码质量与死代码

21. **T21（P2）无调用方的死代码**：`Debouncer.flush/flush_all/pending_chats`（`app/gate/debounce.py:76,79,85`）、`UpdateDeduplicator.purge`（`app/gate/dedupe.py:20`）、`Settings.env_present`（`app/config.py:230`）、`get_logger`（`app/logging_setup.py:66`）、`StickerStore` 协议（`app/storage/repo/stickers.py:93`）、`SandboxErrorLike`（`app/tools/builtin/run_code.py:43`）。（原条目里的 `messages.clear_chat` 已被 `/clear` 接上，`8b14aab`，不再计入死代码。）
22. **T22（P2）docstring 失准**：`app/config.py:205` 称 `Settings` 不可变但没设 `frozen`；`app/gate/dedupe.py:1` 写「批次级去重」实为逐 `update_id`。
23. **T23（P2）装配路径瑕疵**：`app/main.py:67` 重复调用 `apply_migrations`（第二次为空操作）；`:185`/`:190` 正常路径 `shutdown()` 走两次；`app/sandbox/backends.py:290-296` 日志占位符把 `keep_id` 填进 `workspace=%s`；`app/tools/workspace.py:109-110` 死代码。
24. **T24（P2）业务层反向依赖适配层**：`app/gate/debounce.py:10`、`app/gate/filters.py:7`、`app/gate/trigger.py:14`、`app/session/runner.py:22` 反向 import `app.telegram.parse`，与 `docs/architecture.md` §2 冲突；`app/telegram/__init__.py` 一旦变成 re-export 就形成环。

### 测试与工程

25. **T25（P1，已补测，`6b93fd6`）关键路径零覆盖**：`app/main.py`、`app/logging_setup.py`、`app/telegram/handlers.py`、`app/telegram/sender.py` 原先没有任何测试；`CliBackend.run` 与 `DeepSeekClient` 的类体从未执行；`SecretFilter` 无测试。
    A1–A3 修复期间正是这个缺口让 `app/main.py` 引用 `time.monotonic` 却未 `import time` 的装配缺陷（后台摘要任务一启动即 `NameError`）躲过了全部离线测试，直到改时钟域时才暴露。
    已补齐（只加测试、不改产品代码）：`tests/offline/test_logging.py` 10 条（`SecretFilter` 的 msg/tuple/dict 三条脱敏路径、根 logger 装配与轮转文件、噪声库降级、`get_logger`）、`test_telegram_sender.py` 7 条（异常 → `RateLimited`/`SendFailed`、不设 `parse_mode`）、`test_handlers.py` 4 条（update → runner、异常不外抛）、`test_client.py` 13 条（请求组装、usage/tool_calls 提取、错误翻译、`aclose`）、`test_main.py` 8 条（DB 探测、失败留痕、`stop()` 收尾、每小时清理、信号注册）、`test_sandbox.py::CliBackendRunTests` 3 条（真实子进程退出码 0/3、超时销毁）；全量 546 条 OK。契约同步：`docs/architecture.md` §8、`docs/decisions/0006-credentials-not-in-git.md`。真机尚未同步（只含测试与文档，不影响运行期行为）。
26. **T26（P2）分层测试缺口**：`tests/offline/test_layering.py` 只锁 5 条规则，未覆盖「适配器不得直连 SQLite/workspace/执行器/沙箱」，也不禁止 T24 的反向 import；`test_layering.py:118` 的断言文案 `config/tools/config` 疑似笔误。
27. **T27（P2）依赖无上限**：`requirements.txt` 全用 `>=`，本机 openai 3.24.0 / 真机 3.26.0 已漂移；无锁文件、无 CI、无 lint/类型检查。
28. **T28（P2）平台条件跳过**：Windows 上软/硬链接相关 3 条用例 `skipTest`（`tests/offline/test_files.py:90,103,127`），本机全绿不代表 Linux 行为（真机已跑同一套测试，见 `docs/status.md`）。
29. **T29（P2）测试环境副作用与 flaky 风险**：`tests/offline/test_sandbox.py:162-169` 直接改 `os.environ`；`test_executor.py:39` 与 `test_sandbox.py:263,267,281` 依赖 `sleep` 时序。
30. **T30（P2）代码注释与当前实现不符（文档治理阶段不动代码，仅登记）**：`app/tools/policy.py:43` 仍写「阶段 3 只有 L0 工具」，但 L0–L3 均已注册（见 `docs/tools.md` §3）。修注释属代码改动，需另开任务。
31. **T31（P1，已修复，`e1dcb6a`）工具清单在本轮内被快照**（工具契约；`app/llm/loop.py:89`）：第 1 轮取一次清单后，后续轮次继续下发「本轮已禁用/已熔断」的工具，模型会调用只可能返回 `cooldown` 的工具，白花一整轮模型调用与 token，与 `docs/tools.md` §1、`docs/security.md` §9「本轮从可用清单移除」及 F4.8 验收「失败工具不再重复调用」不符。修复：每轮重新取清单（为空即不带工具、强制给答案）；`cooldown` 文案改用 `BreakerConfig.round_failures`。回归：`tests/offline/test_loop.py`（未修复时 `spec_calls` 断言失败）、`tests/offline/test_executor.py`。发现于工具体验优化。

### 已确认没有问题的部分（避免重复排查）

- 未见 SQL 注入点：值全部走 `?` 占位符，动态 SQL 只拼固定列名/条件；FTS `MATCH` 串参数化且词表受正则限制（实测 `near` 与小写 `or/and/not` 在 FTS5 中按普通 token 处理）。
- 未见跨群越权读取路径：messages / summaries / notes / stickers / usage / chat_settings 的查询都带 `chat_id` 条件。
- 摘要的模板、游标、失败不推进语义与 `docs/memory.md` §4、`docs/database.md` §3 一致。
- 沙箱 argv 的 12 项固定参数在 `app/sandbox/spec.py` 内一致，模型无法影响镜像/挂载/runtime。
