# 变更记录（CHANGELOG）

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的组织方式，
版本号对应 `docs/status.md` 的提交基线。提交哈希可在 GitHub 直接打开。

## [0.1.0] - 2026-10-08

首个公开版本：单进程、单 Bot Token 的 Telegram 群宠，本机 `Ran 647 tests / OK (skipped=2)`。

### Added

- 阶段 1 最小可运行闭环（`7052da4`）：Telegram 长轮询 + 去抖 + DeepSeek + SQLite。
- 阶段 2 发言闸门（`4dc8bf3`）：主动回复判定、冷却与每窗口上限，被压住的消息 0 token。
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
