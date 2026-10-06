# 开发路线图

负责：阶段划分、每阶段交付与验收、当前进度。
上游：`docs/requirements.md`（条目编号与优先级）。
改动影响：只改本文件的阶段状态；阶段内容细节改动应回到 `docs/requirements.md`。

## 当前状态

阶段 0：**已完成**（文档骨架就绪，见 `docs/README.md`）。
阶段 1：**已完成**（最小可运行闭环，含私聊默认静默与本轮消息边界）。完成阶段 1 并通过验收后再进入阶段 2；不得跳阶段。
阶段 0 含部署约束增补：Windows 开发 / Linux VPS 24/7 生产，同一份代码（见 `docs/deployment.md`）。
阶段 10（Web 控制面板与多实例）：**仅完成架构预留**（`docs/domain.md`、`docs/architecture.md` §10），未开发面板，未建控制面表；阶段 2 仍未开始。

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

- 交付：F2.2–F2.5（可解释内容、上下文追问、冷却与每窗上限、ignore），
  以及不要求 @ 的主动回复判定（`docs/requirements.md` §2.1 第 1 条）
- 验收：未点名的追问会接话；纯捧场消息 0 成本；高频群里 Bot 不会连续插话。

### 阶段 3 · 工具主干

- 交付：`tools/registry.py`、`tools/policy.py`、`tools/executor.py`、`calc`、`search_web`（F4.1–F4.3、F4.8）
- 验收：模型能算数、能查资料；越权调用被拒且只回一句话；非法参数返回 `invalid_arguments`。

### 阶段 4 · 工作区与文件

- 交付：F4.4（`read_file`、`write_file`、路径安全、原子写 + `.bak`）
- 验收：`docs/security.md` §11 的路径逃逸用例全部被拒；覆盖写有备份。

### 阶段 5 · 贴纸

- 交付：F4.5（`stickers` 表、情绪匹配、冷却）
- 验收：情绪匹配合理、受冷却与限速约束、模型上下文不出现 `file_id`。

### 阶段 6 · 记忆

- 交付：F3.1–F3.4（动态窗口、噪声标记、模板化摘要、FTS5 检索）
- 验收：长会话后仍能回答"之前那个怎么搞的"；摘要遵循模板；检索只补背景。

### 阶段 7 · 沙箱 run_code

- 交付：F4.6（`app/sandbox/runner.py` + 固定容器参数）
- 前置：本机有可用的 Docker/Podman；否则该工具保持 fail-closed。
  调用方式在阶段 7 决定：Bot 进程不接触 docker/podman socket（见 `docs/security.md` §4、`docs/deployment.md` §10）。
- 验收：容器内无网络、越界写失败、超时被 kill 且容器销毁。

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
