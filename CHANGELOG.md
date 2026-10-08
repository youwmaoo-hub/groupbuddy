# 变更记录（CHANGELOG）

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的组织方式，
版本号对应 `docs/status.md` 的提交基线。提交哈希可在 GitHub 直接打开。

## [1.0.0] - 2026-10-08

第一个开源发布版：单进程、单 Bot Token 的 Telegram 群宠，外加一个**可选**的本地控制面板；
本机 `Ran 688 tests / OK (skipped=2)`。发布内容与安装步骤见 `release/groupbuddy-v1.0.0/`。

### Added

- **控制面板（可选，独立进程，ADR 0011）**：`python -m app.control` 起一个默认只监听 `127.0.0.1:8787`
  的 HTTP 面板，与本 Bot 共用同一个 SQLite 库；`PANEL_ENABLED=false` 时不装、不开都不影响机器人。
  - 能看：运行概览（心跳/运行时长/消息数/当日 token 与工具失败/出站队列/数据库可读）、群列表与群详情、
    日志尾部（脱敏、最多 256 KB、1–1000 行）。
  - 能改：群设置（模式、各工具开关、贴纸冷却、群人设），与 `/settings` 走**同一条校验与写路径**。
  - 凭据：写入/替换/删除 `BOT_TOKEN` 与 `LLM_API_KEY`，**只写不读**——接口永不返回明文（连掩码都不回），
    按 name 精确改 `.env`（同目录临时文件 + `chmod 0600` + `os.replace`），写入后回 `restart_required: true`。
  - 鉴权：`Authorization: Bearer <token>` 两级口令（`PANEL_TOKEN`→管理员、`PANEL_READONLY_TOKEN`→只读），
    `hmac.compare_digest` 比较，越权 403；口令非空时不足 12 字符直接被配置校验拒绝；未配口令拒绝启动。
  - 收紧响应面：关闭 `docs`/`redoc`/`openapi`，统一安全响应头与严格 CSP，`/api/*` 带 `Cache-Control: no-store`，
    前端为零构建静态页、无内联脚本；不提供公网暴露方案（远程用 SSH 隧道）。
- 服务层 `app/services/`：面板与 Telegram 命令通道共用的唯一业务入口
  （`context.py` / `settings.py` / `overview.py` / `credentials.py`），不 import Web 框架与 aiogram、不读环境变量、不拼 SQL。
- 可选依赖 `fastapi` / `uvicorn`：只在 `app/control/` 里 import，分层测试锁死；不开面板可以不装。
- 发布包 `release/groupbuddy-v1.0.0/`：只含核心代码、文档与部署说明（不含运行数据、`.env`、虚拟环境与开发用原始需求记录）。

### Changed

- 发言策略改为**默认接话**：通过入口过滤、噪声过滤、重复过滤与冷却闸门的人类消息默认回一句
  （捧场、接梗、解释、吐槽都行），弱触发词表只用于标注原因码、兜底 `general`；沉默词表 `not_addressed` 移除。
- 删除每窗口发言上限：`PROACTIVE_WINDOW_SECONDS` / `PROACTIVE_MAX_PER_WINDOW` 配置键与 `LIMIT_QUOTA` 原因码移除，
  只保留冷却（默认 20 秒）与新增的重复消息过滤（`DUPLICATE_WINDOW_SECONDS`，默认 300 秒，`repeat`）。
- 连发消息默认**不合并**：`DEBOUNCE_SECONDS=0`、`DEBOUNCE_MAX_MESSAGES=1`，每条消息各自成批，调大才恢复合并。
- 输出规则改为"已决定接话就不许沉默"：首轮 `NO_REPLY` 时程序追加一句"必须回"的追问重跑一次；
  人设里"插不上话就不说话"的措辞同步改为"接话自然一点"。
- 开源化中立化：`.env.example` 的 `LLM_BASE_URL` 改为占位端点 `https://api.example.com/v1`、
  `LLM_MODEL` 改为 `your-model-name`、`BOT_ALIASES` 改为通用示例（文档里的具体模型/人设只作为示例）。

## [0.1.0] - 2026-10-08

首个公开版本：单进程、单 Bot Token 的 Telegram 群宠，本机 `Ran 647 tests / OK (skipped=2)`。

### Added

- 阶段 1 最小可运行闭环（`7052da4`）：Telegram 长轮询 + 去抖 + DeepSeek + SQLite。
- 阶段 2 发言闸门（`4dc8bf3`）：主动回复判定、冷却与每窗口上限，被压住的消息 0 token
  （窗口上限与"沉默词表"已于 2026-10-08 调整为默认接话，见 Unreleased）。
- 阶段 3 工具主干（`6da5dcb`）：工具注册表、程序侧权限判定、执行器、`calc`、`search_web` 接口。
- 阶段 4 工作区与文件（`4bc5b57`）：`read_file` / `write_file`，共享路径安全（限制在每群工作区）。
- 阶段 5 贴纸（`5bb8935`）：`stickers` 表、情绪匹配、冷却、`send_sticker` 出站通道。
- 阶段 6 记忆（`3d00260`）：分档窗口 + 字符预算、噪声标记、模板化摘要、FTS 检索。
- 阶段 7 沙箱（`54984c7`）：`run_code` 固定容器参数、rootless Podman/Docker、fail-closed。
- 阶段 8：四种群聊模式影响窗口/输出上限/工具档位（`78ae9cf`）、群管理员命令通道与
  `chat_settings` 原子写入（`7382639`）、`/settings`（`c49fdc5`）、每群日/月 Token 配额（`1d649b8`）、
  `/stats` 与 `/health`（`101c26c`）、`host_info` 只读字段集（`de73b57`）。
- 阶段 9：SQLite 冷备份与校验快照 + 保留策略（`bc31c41`）、systemd 用户级单元最小生产闭环（`5a5b6d5`）、
  housekeeping 定期执行 `PRAGMA optimize`（`29f6687`）。
- `/clear` 清空群消息历史（`8b14aab`）、群级人设覆盖（仅群主可写，`c29ecac`）、
  `/note` 长期笔记（`495389b`）、模型档位路由 `ModelRouter`（`e26ea3c`）、
  工具轮次按意图分档（闲聊 1 轮，`a5bf651`）。
- 群宠体验升级（`ba7afe1`）：主动接话三条弱触发（同话题 / 情绪反应 / 久静后开场，纯规则 0 token）、
  「DeepSeek 大肥鱼」群宠人设、其他 Bot 的消息在判定入口直接 `ignore` 且不占冷却与额度。
- 贴纸目录对齐公开贴纸包 `deepseek_whale_girl`（104 槽，`30cc3fe`）。
- 开源配套：`README.md`、`LICENSE`(MIT)、`CONTRIBUTING.md`、`SECURITY.md`、`CHANGELOG.md`、
  GitHub Actions 离线测试、Issue/PR 模板。

### Changed

- 每轮只响应当前触发消息：被跳过的消息视为已 pass，不补答、不顺带回答、不一次回多条，
  连发只挑一条（`50b4159`）。
- 群聊体验修正（`172ab6b`）：回复字数上限、不插嘴别人的 Bot 对话、`/help` 与指令菜单可发现、
  人设自我认识。
- repo 写入改为显式事务边界（SAVEPOINT，`1826d89`）；容器以 125/126/127 退出时改判
  `execution_failed` 并销毁容器（`d59a703`）；`stickers.last_used_at` 由进程相对秒改为 Unix 秒（`b41bff4`）。

### Fixed

- 迁移与会话上下文时序加固（`f7f34b5`）；群内无贴纸时不再向模型提供 `send_sticker`（`bafe096`）；
  工具清单逐轮重取，本轮被禁用的工具不再下发（`e1dcb6a`）。
- `.gitignore` 只忽略仓库根 `storage/`，并把被误忽略的 `app/storage` 源码纳入版本库（`d27e1e0`）；
  沙箱仅在挂载 workspace 时设置工作目录（`434f2f8`）；验收脚本区分「容器缺失」与「执行失败」（`4ea2326`）。

### Security

- 凭据只经 `BotInstance` / `Credential` 读取，任何接口不返回明文，新增凭据必须注册进日志脱敏集合
  （`docs/decisions/0006-credentials-not-in-git.md`）。
- 文件访问限制在 `storage/workspaces/<chat_id>/`；`run_code` 一律经沙箱，禁止宿主机直接执行；
  所有 Telegram 出站消息经 `app/outbound/queue.py` 统一限速与退避。

### Tests

- 关键路径补测（`6b93fd6`，T25）；`tests/offline` 全量 647 条通过（Windows 上 2 条软/硬链接用例跳过，
  见 `TODO.md` T28）。
