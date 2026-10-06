# 开发路线图

负责：阶段划分、每阶段交付与验收、当前进度。
上游：`docs/requirements.md`（条目编号与优先级）。
改动影响：只改本文件的阶段状态；阶段内容细节改动应回到 `docs/requirements.md`。

## 当前状态

阶段 0：**已完成**（文档骨架就绪，见 `docs/README.md`）。
阶段 1：**已完成**（最小可运行闭环，含私聊默认静默与本轮消息边界），已通过真实 Telegram + DeepSeek 端到端验收。
阶段 2：**已完成**（发言闸门：不要求 @ 的主动回复判定 + 冷却与每窗口上限）。
阶段 3：**已完成**（工具主干：注册表 / 权限判定 / 执行器 + `calc` + `search_web` 接口）。
阶段 4：**已完成**（工作区与文件：`read_file` / `write_file` + 共享路径安全）。
阶段 5：**已完成**（贴纸：`stickers` 表、情绪匹配、冷却与出站媒体通道）。
阶段 6：**已完成**（记忆：分档窗口 + 字符预算、噪声标记、模板化摘要、FTS 检索）。
阶段 7：**已完成**（沙箱 run_code：固定容器参数 + rootless Podman/Docker + fail-closed；部署前准备已收尾，VPS 上线清单见 `docs/deployment.md` §12）；Linux/Podman 真实验收待目标机执行 `scripts/verify_sandbox.py`。
一次只推进一个阶段；不得跳阶段。
阶段 0 含部署约束增补：Windows 开发 / Linux VPS 24/7 生产，同一份代码（见 `docs/deployment.md`）。
阶段 10（Web 控制面板与多实例）：**仅完成架构预留**（`docs/domain.md`、`docs/architecture.md` §10），未开发面板，未建控制面表。

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
- 验收：容器内无网络、越界写失败、超时被 kill 且容器销毁；离线覆盖 `tests/offline/test_sandbox.py`（27 条）；
  真实验收由目标机（Linux + rootless Podman）执行 `scripts/verify_sandbox.py`（上线清单见 `docs/deployment.md` §12），Tier B 未全 PASS 就设为 `SANDBOX_TIER_B=off`。
- 明确不做：Tier C、`pip install`、容器联网、自定义镜像、microVM/gVisor/Kata、Redis/K8s、配额与管理员权限。

### 阶段 8 · 权限、配额与运维

- 交付：F5.1–F5.4、`host_info`（F4.7）、四种模式（`docs/token.md` §5）、`/health`（实现属本阶段；24/7 托管与自愈属阶段 9）
- 验收：群主可开关工具等级；非管理员被拒；配额打满后优雅拒绝。

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
