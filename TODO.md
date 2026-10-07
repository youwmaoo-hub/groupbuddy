# 开发路线图

负责：阶段划分、每阶段交付与验收、当前进度、技术债登记（本轮只登记、不修复）。
上游：`docs/requirements.md`（条目编号与优先级）。
改动影响：只改本文件的阶段状态；阶段内容细节改动应回到 `docs/requirements.md`。

## 当前状态

**当前事实只有一个来源：`docs/status.md`**（commit、已完成能力、本机与真机测试、真机验收证据、技术债摘要、下一步）。本节只保留阶段进度。

- 阶段 0–7：**已完成**。阶段 0 含部署约束增补（Windows 开发 / Linux VPS 24/7 生产，同一份代码，见 `docs/deployment.md`）；阶段 1 曾通过真实 Telegram + DeepSeek 端到端验收；阶段 7 的 Linux/Podman 真机验收**已完成**（13/13 PASS，commit 与日志路径见 `docs/status.md`）。
- 阶段 8（权限、配额与运维）：**进行中** —— 已完成群主命令最小闭环（管理员判定 + `/settings` 回显 + 非管理员被拒，见 `docs/security.md` §2.1）与 T12；配额、`/stats`、`/health` + `storage/health.json`、`host_info`、四模式待做。阶段 9（部署与 24/7 运行）、阶段 10（Web 控制面板与多实例）：**未开始**。阶段 10 仅完成架构预留（`docs/domain.md`、`docs/architecture.md` §10），未开发面板、未建控制面表。
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
  该脚本的判定口径偏弱（见下方技术债 T7）。
- 明确不做：Tier C、`pip install`、容器联网、自定义镜像、microVM/gVisor/Kata、Redis/K8s、配额与管理员权限。

### 阶段 8 · 权限、配额与运维

- 交付：F5.1–F5.4、`host_info`（F4.7）、四种模式（`docs/token.md` §5）、`/health`（实现属本阶段；24/7 托管与自愈属阶段 9）
- 验收：群主可开关工具等级；非管理员被拒；配额打满后优雅拒绝。
- 已完成（`7382639` F5.2、`c49fdc5` F5.1）：群主命令通道 —— `app/ops/admin.py` 管理员判定（只认 `getChatAdministrators`、进程内缓存、失败 fail-closed）、`app/ops/commands.py` `/settings` 回显与 `/settings <字段> <值>` 写入（字段白名单：模式、6 个工具开关、贴纸冷却；非法输入不写库；改完当轮生效）、命令不进模型不写 messages 0 token、未知命令静默、非管理员固定文案；`chat_settings.upsert` 改为单条原子写入（T12）。
- 待做：F5.3 配额、F5.4 `/stats` + `/health` + `storage/health.json`、F4.7 `host_info`、四模式（窗口/输出上限/工具档位）生效；`tool_failures` 表（T15）与 7 天清理。

### 阶段 9 · 部署与 24/7 运行

- 交付：`Dockerfile`/`compose.yaml`（或 `deploy/bot.service`）、持久化目录约定、优雅关闭、
  健康检查、备份与恢复演练、更新回滚流程；全部按 `docs/deployment.md`。
- 前置：阶段 7 沙箱可用（需要容器运行时）。
- 验收：容器/VPS 重建后数据仍在（`bot.db` 与 workspace 未丢）；程序重启后自动恢复运行；
  SIGTERM 能优雅退出；上一份备份能恢复出可用数据库；日志与错误消息中无 Secret。

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

4. **T4（P1）CLI 非零退出不映射 `execution_failed`**（用户点名）— `app/sandbox/runner.py:143-149`、`app/sandbox/backends.py:128-129`：
   只有后端调用**抛异常**时才映射（`runner.py:128-131`）；Podman 以 125/126/127 退出时 argv 原样成为工具结果，
   「容器没起来」与「程序正常失败」不可区分 —— 阶段 7 首次真机验收的 `--workdir /workspace` 事故正是由此漏报。契约见 `docs/tools.md` §2 `run_code`。
5. **T5（P2）沙箱 stderr 未清洗** — 容器/CLI 的 stderr 原样进入模型上下文（`runner.py:138,146-148`），与 `docs/security.md` §3「上下文里不出现宿主机绝对路径」冲突。
6. **T6（P2）`--cap-drop=ALL` 与 `no-new-privileges` 未被验收覆盖** — 实现在 `app/sandbox/spec.py:68-70`，但 `scripts/verify_sandbox.py` 无对应检查项。
7. **T7（P2）验收脚本判定口径弱** — `want_ok=False` 的两项（无网络、只读根）任何非零退出都 PASS，区分不出「容器没启动」；
   `Tier A：PASS` 汇总只聚合 1 项（`scripts/verify_sandbox.py:66,76-77,145-149`）。判读口径见 `docs/deployment.md` §12.6。
8. **T8（P2）`resolve_path` 未复核 base 自身** — `app/tools/workspace.py:45-47` 只对拼接后的目标做 `is_relative_to`，未像 `:63-71` 那样逐段查符号链接；base 目录本身被替换为符号链接时没有保护。

### 数据与记忆

9. **T9（P1）没有事务边界** — 各 repo 自己 `commit()`（`app/storage/repo/summaries.py:65,136`、`notes.py:48`、`stickers.py:73,90`），
   主表 + FTS 的多语句写可能半提交、或被其他任务顺带提交；无 `rollback`。契约见 `docs/database.md` §6。
10. **T10（P1）`stickers.last_used_at` 存 `time.monotonic()`**（`app/tools/builtin/send_sticker.py:113,117,146`），与 `docs/database.md` §1「统一 Unix 秒」冲突；重启后「优先未近期使用」的 tie-break 语义反转（`send_sticker.py:89-96`）。
11. **T11（P2）迁移解析脆弱** — 裸 `;` 切分（`app/storage/db.py:30`）、编号缺口/重复块无校验（`db.py:25,43`）、版本校验只看块数量（`db.py:67`）。
12. **T12（P2，已修复，`7382639`）`chat_settings.upsert` 读-改-写无锁**（`app/storage/repo/chat_settings.py`）：两次 await 之间可被改写，存在丢更新 —— 阶段 8 F5.2 改为单条原子 `INSERT … ON CONFLICT DO UPDATE`，只写调用方给出的列（离线测试用 `mock` 断言不再读取当前设置）。
13. **T13（P2）`notes` 没有运行时写入路径** — 只有运维脚本 `scripts/register_note.py`；500 字上限也只在脚本里校验（`app/storage/repo/notes.py` 层无约束）。
14. **T14（P2）`thread_id` 恒为 NULL** — `messages.recent()` 支持该参数（`app/storage/repo/messages.py:69-71`）但没有调用方传入；摘要、游标、FTS 都是 chat 级（阶段 8 做论坛主题隔离）。
15. **T15（P2）`tool_failures` 表未建**（阶段 8），熔断状态只在进程内存（与 `docs/security.md` §9 一致）。
16. **T16（P2）纵深防御缺口** — `stickers.mark_used` 只按 `id`（`app/storage/repo/stickers.py:88-90`）、`DELETE FROM summaries WHERE id=?`（`summaries.py:134`）；当前所有调用路径都带 chat 校验，审查未发现可利用的越权路径。

### 工具与契约

17. **T17（P2）`ToolExecutor(max_payload_bytes=...)` 参数无效**（`app/tools/executor.py:43,127-128`）：实际上限由各 `ToolSpec.max_payload_bytes`（默认 4096，`registry.py:67`）决定。
18. **T18（P2）`read_file` 的续读前提不成立** — 单次超过 16 KB 时整包丢弃 `too_large`，模型拿不到 `total_lines`（`docs/tools.md` §4）。
19. **T19（P2）`SANDBOX_OUTPUT_KB` 与 20480 耦合** — 调大沙箱输出上限后，stdout+stderr 很容易超过 `run_code` 的 `ToolSpec` 上限，工具结果整包 `too_large`（`app/tools/executor.py:133-138`）。
20. **T20（P2）`calc` 值域只对整数生效** — 结果绝对值 ≤10^100 的检查只覆盖 `int`，浮点结果只校验有限性（`app/tools/builtin/calc.py:90-97`）。

### 代码质量与死代码

21. **T21（P2）无调用方的死代码**：`Debouncer.flush/flush_all/pending_chats`（`app/gate/debounce.py:76,79,85`）、`UpdateDeduplicator.purge`（`app/gate/dedupe.py:20`）、`Settings.env_present`（`app/config.py:230`）、`get_logger`（`app/logging_setup.py:66`）、`messages.clear_chat`（阶段 8 预留，`app/storage/repo/messages.py:149`）、`StickerStore` 协议（`app/storage/repo/stickers.py:93`）、`SandboxErrorLike`（`app/tools/builtin/run_code.py:43`）。
22. **T22（P2）docstring 失准**：`app/config.py:205` 称 `Settings` 不可变但没设 `frozen`；`app/gate/dedupe.py:1` 写「批次级去重」实为逐 `update_id`。
23. **T23（P2）装配路径瑕疵**：`app/main.py:67` 重复调用 `apply_migrations`（第二次为空操作）；`:185`/`:190` 正常路径 `shutdown()` 走两次；`app/sandbox/backends.py:290-296` 日志占位符把 `keep_id` 填进 `workspace=%s`；`app/tools/workspace.py:109-110` 死代码。
24. **T24（P2）业务层反向依赖适配层**：`app/gate/debounce.py:10`、`app/gate/filters.py:7`、`app/gate/trigger.py:14`、`app/session/runner.py:22` 反向 import `app.telegram.parse`，与 `docs/architecture.md` §2 冲突；`app/telegram/__init__.py` 一旦变成 re-export 就形成环。

### 测试与工程

25. **T25（P1）关键路径零覆盖**：`app/main.py`、`app/logging_setup.py`、`app/telegram/handlers.py`、`app/telegram/sender.py` 没有任何测试；`CliBackend.run` 与 `DeepSeekClient` 的类体从未执行；`SecretFilter` 无测试。
    A1–A3 修复期间正是这个缺口让 `app/main.py` 引用 `time.monotonic` 却未 `import time` 的装配缺陷（后台摘要任务一启动即 `NameError`）躲过了全部离线测试，直到改时钟域时才暴露——该覆盖缺口有实际价值，仍待补。
26. **T26（P2）分层测试缺口**：`tests/offline/test_layering.py` 只锁 5 条规则，未覆盖「适配器不得直连 SQLite/workspace/执行器/沙箱」，也不禁止 T24 的反向 import；`test_layering.py:118` 的断言文案 `config/tools/config` 疑似笔误。
27. **T27（P2）依赖无上限**：`requirements.txt` 全用 `>=`，本机 openai 3.24.0 / 真机 3.26.0 已漂移；无锁文件、无 CI、无 lint/类型检查。
28. **T28（P2）平台条件跳过**：Windows 上软/硬链接相关 3 条用例 `skipTest`（`tests/offline/test_files.py:90,103,127`），本机全绿不代表 Linux 行为（真机已跑同一套测试，见 `docs/status.md`）。
29. **T29（P2）测试环境副作用与 flaky 风险**：`tests/offline/test_sandbox.py:162-169` 直接改 `os.environ`；`test_executor.py:39` 与 `test_sandbox.py:263,267,281` 依赖 `sleep` 时序。
30. **T30（P2）代码注释与当前实现不符（文档治理阶段不动代码，仅登记）**：`app/tools/policy.py:43` 仍写「阶段 3 只有 L0 工具」，但 L0–L3 均已注册（见 `docs/tools.md` §3）。修注释属代码改动，需另开任务。

### 已确认没有问题的部分（避免重复排查）

- 未见 SQL 注入点：值全部走 `?` 占位符，动态 SQL 只拼固定列名/条件；FTS `MATCH` 串参数化且词表受正则限制（实测 `near` 与小写 `or/and/not` 在 FTS5 中按普通 token 处理）。
- 未见跨群越权读取路径：messages / summaries / notes / stickers / usage / chat_settings 的查询都带 `chat_id` 条件。
- 摘要的模板、游标、失败不推进语义与 `docs/memory.md` §4、`docs/database.md` §3 一致。
- 沙箱 argv 的 12 项固定参数在 `app/sandbox/spec.py` 内一致，模型无法影响镜像/挂载/runtime。
