# 当前状态（唯一事实来源）

负责：**当前基线**——commit、已完成阶段与能力、本机与真机测试结果、真机验收证据、技术债摘要、下一步。
上游：`docs/README.md` §2 路由表。
改动影响：本文件不是契约，只记录事实。契约在 `docs/requirements.md`、`docs/architecture.md`、`docs/security.md`、`docs/tools.md`、`docs/database.md`、`docs/deployment.md`。**每次提交、每次验收、每次阶段结束都要更新本文件**；其他文档不再各自维护「当前状态/进度/测试数字」，只指向这里（`AGENTS.md` §7、`TODO.md` §当前状态）。

## 1. 当前基线

| 项 | 值 |
|---|---|
| 代码 commit | `1826d8916db4fbf75a23939c00e5fd3a11ae840e`（短 `1826d89`，分支 `main`；阶段 9 之后的真实使用修复 `bafe096` + 其基线记录、阶段 8 留后项 `/clear` `8b14aab`、群级人设 Persona `c29ecac`、长期笔记 `/note` `495389b`、工具清单逐轮重取 `e1dcb6a`、关键路径补测 T25 `6b93fd6`、验收脚本判定口径 T7 `4ea2326`、repo 写入事务边界 T9 `1826d89`，见 §4.5、§5、§6） |
| 跟踪文件数 | 149（`git ls-files`；Persona 新增 `app/ops/persona.py`、`tests/offline/test_persona.py`、`tests/offline/test_admins.py`；长期笔记新增 `app/ops/notes.py`、`app/ops/text.py`、`tests/offline/test_notes.py`；T25 新增 `tests/offline/test_logging.py`、`test_telegram_sender.py`、`test_handlers.py`、`test_client.py`、`test_main.py`；T7 新增 `tests/offline/test_verify_sandbox.py`；T9 新增 `app/storage/tx.py`、`tests/offline/test_transactions.py`） |
| 提交数 | 49（阶段提交 + 文档治理 `b529741` + A1–A3 修复 `f7f34b5` + 文档同步 `3347301` + 部署记录 + 阶段 8 F5.2 `7382639` + F5.1 `c49fdc5` + F5.3 `1d649b8` + F5.4 `101c26c` + 基线 `ad560f4` + F4.7 `de73b57` + 四模式 `78ae9cf` + 四模式基线 `88531d2` + 真机验收记录 `d5e48f0` + 阶段 9 托管文档 `5a5b6d5` + 阶段 9 基线 `cb30c10` + 备份与校验 `bc31c41` + 阶段 9 演练记录 `bed250b` + 真实使用修复 `bafe096` + 其基线记录 + 真机同步与复验记录 `a4e1afc` + `/clear` `8b14aab` + 其基线记录 + 群级人设 Persona `c29ecac` + 其基线记录 + 长期笔记 `/note` `495389b` + 其基线记录 + 工具清单逐轮重取 `e1dcb6a` + 其基线记录 + 模型档位路由与轮次分档评估 + 关键路径补测 T25 `6b93fd6` + 其基线记录 + 验收脚本判定口径 T7 `4ea2326` + 其基线记录 + repo 写入事务边界 T9 `1826d89` + 其基线记录） |
| 本机工作树 | 干净（`git status --porcelain` 无输出）；本机 `main` HEAD 比真机多 `/clear`、Persona、`/note`、工具清单修复、T25 补测、T7 修复与 T9 事务边界七个提交（真机仍是 `26e946d`） |
| 真机仓库 | `/home/bot/app` = detached HEAD @ `26e946d`（与上表代码 commit 完全一致），工作树干净，属主 `bot:bot`，跟踪文件 135；**Bot 已在真机运行**：systemd 用户级单元 `groupbuddy.service`（`ActiveState=active`、`Restart=always`，见 §4.3） |
| 真机远端 | `origin` = VPS `/home/bot/bundles/dsh_deploy_bafe096.bundle`（Bot 用户持久目录，`/tmp` 会被清理；bundle 含 `refs/heads/main`，可 `git fetch`；仍未配置正式远端，未建 GitHub remote、未 push） |
| 运行时目录 | 真机 `storage/`：`bot.db`（118784 字节，`user_version`=4，另有 WAL 的 `-wal`/`-shm`）、存储日志 `logs/bot.log`、`health.json`（60 秒心跳）、`sandbox/`、`workspaces/`、`backups/`（两份已验证快照，见 §4.4），属主 `bot:bot`；真实 `.env` 在 `/home/bot/app/.env`（`600`、`bot:bot`，**内容与凭据值一律不记录**） |

## 2. 已完成阶段与能力

| 阶段 | 状态 | 能力 |
|---|---|---|
| 0 | 已完成 | 文档骨架 + 部署约束 |
| 1 | 已完成 | 最小闭环：long polling、入站过滤、落库、幂等、debounce、per-chat 串行、出站队列与限速、4096 分段、私聊默认静默、本轮消息边界 |
| 2 | 已完成 | 发言闸门：强触发 / 可解释内容 / 追问 / 冷却与每窗口上限 / `NO_REPLY` |
| 3 | 已完成 | 工具主干：注册表、权限判定（唯一入口）、执行器、熔断 + `calc` + `search_web` 接口 |
| 4 | 已完成 | 工作区与文件：`read_file` / `write_file`、路径安全、原子写 + 单层 `.bak` |
| 5 | 已完成 | 贴纸：`stickers` 表、情绪匹配、冷却、出站媒体通道 |
| 6 | 已完成 | 记忆：分档窗口 + 字符预算、噪声标记、模板化摘要、FTS5 检索 |
| 7 | 已完成 | 沙箱 `run_code`：固定 argv、rootless Podman / Docker、Tier A/B、fail-closed；真机部署与验收已完成 |
| 8 | 已完成 | 权限/配额/运维：**群主命令最小闭环、群设定写入、日/月配额与运行指标**（`app/ops/admin.py` 管理员判定 + `/settings` 回显/写入 + `app/ops/quota.py` 配额判定 + `app/ops/metrics.py` `/stats` + `app/ops/health.py` `/health` 与 `storage/health.json` 同一状态，见 `docs/security.md` §2.1、`docs/token.md` §4.1、`docs/deployment.md` §7；F5.1/F5.2/F5.3/F5.4 + T12 + T15）；**F4.7 `host_info` 已实现**（`app/tools/builtin/host_info.py`，L4 + `allow_host_info` 默认关，见 `docs/tools.md` §host_info）；**token 四模式完整生效**（`app/modes.py` 唯一权威表：economy 10 条窗口 / 只 L0 / 256 输出 / 贴纸关；normal 意图分档 + 群开关；smart 50 条 + 额外 L0 只读；unrestricted 50 条 + 全部工具 + 输出不限；模式只由管理员 `/settings mode` 修改，见 `docs/token.md` §5、`docs/security.md` §2.2）；**`/clear` 已补做**（`8b14aab`：管理员限定、只删本群 `messages` 原文、摘要与用量保留，见 `docs/security.md` §2.1、`docs/database.md` §4）；**群级人设 Persona 已实现**（`c29ecac`：`/settings persona_override <文本>` 仅群主 `creator` 可写、普通管理员与成员拒绝、`app/ops/persona.py` 是唯一读取/清洗入口、优先级 本群 > 部署侧 `PERSONA` > 内置人格，见 `docs/persona.md` §2、`docs/security.md` §2.1）；**长期笔记 `/note` 已实现**（`495389b`：仅群主能列出/查看/记住/删除本群笔记，正文单行化 ≤500 字、名称 ≤50 字符、同名覆盖 `version` +1、删除同步清 `notes_fts`，见 `docs/memory.md` §6、`docs/security.md` §2.1） |
| 9 | 进行中（**最小生产闭环 + 备份/恢复 + 更新/回滚均已真机验证**） | 部署与 24/7：systemd **用户级单元** `groupbuddy.service`（`Restart=always`，开机自启，见 `docs/deployment.md` §12.9）、真实 `.env`（`600`）、启动时 migration（`user_version`=4）、`storage/health.json` 心跳、Telegram 真机收发、stop/start/restart 与 `SIGKILL` 自动重启均已实测通过（见 §4.3）；SQLite 冷备份 + 校验 + 保留（`scripts/backup_db.py`，`docs/database.md` §5）、恢复副本与线上一致性、更新成功与坏版本失败可检出、回滚恢复 `active` 且数据未丢（见 §4.4）；**剩**容器托管（可选路径）、程序内自动备份任务与 `BACKUP_*` 环境键、`PRAGMA optimize`/`VACUUM` |
| 10 | 未开始 | 控制面板与多实例（仅架构预留） |

## 3. 本机验证（Windows，开发环境）

- 解释器：Python 3.13.15（仓库内 `.venv`）；`openai 3.24.0`；**沙箱走 FakeBackend，不跑真实容器**。
- 命令：`python -m unittest discover -s tests -t .`
- 结果：`Ran 560 tests` / `OK (skipped=2)` / 退出码 0（293 原有 + 22 条 F5.2 + 11 条 F5.1 + 20 条 F5.3 + 32 条 F5.4 + 19 条 F4.7 + 19 条四模式 + 6 条阶段 9 备份 + 3 条真实使用修复 `bafe096` + 5 条 `/clear` `8b14aab` + 33 条 Persona `c29ecac`：`test_persona.py` 10 条（清洗/长度/清除值/三层优先级）+ `test_admins.py` 5 条（`getChatAdministrators` 里只有 `status == "creator"` 算群主、假对象与真实 aiogram 类型都覆盖、异常不吞）+ `test_commands.py` 17 条（群主可写且不回显正文、普通管理员与成员被拒且不泄露字段名、无 creator 时无人可写、多词/控制字符/`off` 清除/超长/缺文本/写库失败、`persona_override` 不是通用字段）+ `test_pipeline.py` 1 条端到端（群主写入后下一轮 system prompt 含该文本且不含内置人格；普通管理员改不动）+ 36 条长期笔记 `/note` `495389b`：`test_notes.py` 21 条（单行化、解析与保留字/上限、列表与查看文案、仓库同名覆盖 `version`=2 且旧 token 查不到新的、删除同步清 `notes_fts`、按群隔离与 `updated_at` 倒序）+ `test_commands.py` 14 条（群主列出/查看/记住/覆盖/删除全链路、普通管理员与成员被拒且不含笔记名、无 creator 群被拒、参数与超限不写库、写库失败只回固定短句）+ `test_pipeline.py` 1 条端到端（群主写 `/note` 后 0 token，之后一句回溯把 `[笔记:部署] …` 注入记忆块）；`allow_sticker` 关/开且库空/开且有贴纸三种下发组合（含 `check()` 契约不变）、空库时普通消息仍只调一轮模型且工具清单不含 `send_sticker`、库里有贴纸时重新下发；`/clear` 明细：管理员只清本群且摘要保留、空群回 0 条、非管理员被拒且不删、带参数只回用法、`clear_chat` 抛错只回固定短句且不泄露 SQLite 细节；F4.7 明细：`host_info` 冻结字段集与 schema、L4 默认关与群开关、不可得字段与 `/proc` 缺失回退、不泄露环境变量/主机名/路径；四模式明细：档位表逐列、economy/smart/unrestricted 的工具档位、模式窗口与 normal 意图分档、输出上限透传，含 3 条端到端（`/settings mode` 改完立即影响下一条消息的输出上限与工具清单、smart 解锁只读工具、economy 与 smart 的历史窗口差异体现在发给模型的上下文里）；阶段 9 备份明细：在线库生成已验证快照且源库不受影响、保留份数与 `removed`、`keep=0` 不清理、同分钟第二次快照加后缀、缺库时 CLI 退出码 2、CLI 输出含 `integrity=ok` 且不含凭据）；工具清单修复明细（`e1dcb6a`）：第 2 轮重新取清单、本轮被禁用的工具不再下发也不再被第二次执行（未修复时该用例 `spec_calls` 1≠2 失败）、`cooldown` 文案随 `BreakerConfig.round_failures` 变化而不是写死 2）；45 条 T25 关键路径补测（`6b93fd6`，只加测试、不改产品代码）：`test_logging.py` 10 条（`SecretFilter` 的 msg/tuple args/dict args 三条脱敏路径、空密钥不动、过滤器接在 handler 上时输出已脱敏；根 logger 两个 handler 都带过滤器、轮转文件写入且不含凭据、`LOG_LEVEL=DEBUG` 时噪声库仍为 WARNING、`get_logger`）+ `test_telegram_sender.py` 7 条（消息与贴纸的 `message_id`、不设 `parse_mode`、`TelegramRetryAfter` → `RateLimited`（含 `__cause__`）、`TelegramAPIError` → `SendFailed`）+ `test_handlers.py` 4 条（update → runner 字段映射、别名提及、无关 update 忽略、runner 异常被吞并记日志）+ `test_client.py` 13 条（默认/覆盖 payload、显式 `None` 不发送 `max_tokens`、`tools` + `tool_choice=auto`、usage 两种缓存字段与缺失回退、tool_calls 缺省值、空 choices 与底层异常翻译、`aclose`、未注入 client 时构造真实客户端）+ `test_main.py` 8 条（`SELECT 1` 探测可重复、工具失败留痕写入、`run_forever` 等待 `request_stop`、未 `start()` 的 `stop()` 取消任务、每小时清理过期行后退出、信号处理函数注册后直接调用会回调）+ `test_sandbox.py` 的 `CliBackendRunTests` 3 条（真实子进程退出码 0/3、超时杀进程并报 `timed_out=True`）；4 条 T7 验收脚本判定口径（`4ea2326`：`tests/offline/test_verify_sandbox.py` 用假后端跑 `scripts/verify_sandbox.py` 的 `main()` —— 全部符合时 `Tier A：PASS`/`Tier B：PASS`/`合计 13 项，失败 0 项` 且退出码 0；容器没起来时「无网络」「只读根」因缺探针标记与错误签名而 FAIL；单项「非 root」失败会翻转 `Tier A：FAIL`（修复前只聚合 1 项、会漏报）；`workspace_write=False` 时 fail-closed 项 PASS 且打印「Tier B：未启用（fail-closed 生效）」）；10 条 T9 事务边界（`1826d89`）：`tests/offline/test_transactions.py` 用 `SAVEPOINT` 语义验证 —— 最外层 `transaction()` 的写入对第二条连接可见（即 `RELEASE` 已提交，repo 无需自己 `commit()`）；块内抛错整体回滚，且随后另一个任务的正常写入不会把半成品顺带提交；嵌套时内层失败只回滚内层、外层继续提交；repo 回归用假 SQL 注入失败 —— `notes.upsert`（主表 + FTS）失败后正文与 `version` 仍是 v1、旧 token 仍可检索，`notes.delete`、`summaries.insert`、`summaries.prune`（3 条保留 1 条、首行即失败）失败后行与 FTS 条目全部保留；并断言 14 个写入入口在被 patch 成抛错的 `Connection.commit` 下仍能正常工作（repo 不再自己 commit）。
- 2 条 skip 为平台条件跳过（Windows 上软/硬链接相关用例，见 `TODO.md` T28）。
- 覆盖缺口：原先零覆盖的 `app/main.py`、`app/logging_setup.py`、`app/telegram/handlers.py`、`app/telegram/sender.py`、`CliBackend.run` 与 `DeepSeekClient` 已由 T25 补齐（`6b93fd6`，只加测试）；真机验收脚本 `scripts/verify_sandbox.py` 的判定逻辑由 `tests/offline/test_verify_sandbox.py` 离线覆盖（T7，`4ea2326`，脚本本身仍需真机执行）；仍未覆盖的是需要真实 Telegram/容器/真机的路径，由真机证据证明（见 §4）。

## 4. 真机验证（Linux VPS）

### 4.1 环境

| 项 | 值 |
|---|---|
| 主机 | Debian 12（VPS，主机名 `RainYun-e7lnBWeg`） |
| 运行用户 | `bot`（uid 1002），非 root，不在 `docker` 组 |
| 解释器 | Python 3.11.2（`/home/bot/app/.venv`）；`aiogram 3.31.0`、`openai 3.26.0`、`aiosqlite 0.22.1`、`sqlite 3.40.1` |
| 容器运行时 | rootless Podman 4.3.1，cgroup v2，driver `overlay`，runtime `crun` |
| 镜像 | 只有 `docker.io/library/python:3.12-slim`（digest `sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f`，124 MB，部署阶段预拉；验收期间未重新 pull） |

### 4.2 测试与验收

| 检查 | 命令 | 结果 |
|---|---|---|
| 全量离线测试 | `sudo -u bot bash -lc 'cd /home/bot/app && .venv/bin/python -m unittest discover -s tests -t .'` | **`Ran 416 tests` / `OK` / 退出码 0**（真机 checkout `88531d2`；Linux 上无 skip；`FAILED`/`ERROR:` 行 0 条，逐项无失败） |
| 全量离线测试（阶段 9 新版本） | 同上命令，真机 checkout `bc31c41` | **`Ran 422 tests` / `OK` / 退出码 0**（32.2s；`FAILED`/`ERROR:` 行 0 条、skip 0 条） |
| 沙箱真机验收 | `sudo -u bot bash -lc 'cd /home/bot/app && .venv/bin/python scripts/verify_sandbox.py'` | **13 项全 PASS，失败 0 项**，退出码 0；`Tier A：PASS`、`Tier B：PASS`；阶段 8 验收（`88531d2`）与阶段 9 演练后在 `bc31c41` 上复跑结果一致，与阶段 7 `3347301` 相比无回归 |
| migration 4 真机检查 | 临时库上 `apply_migrations` + `PRAGMA user_version` + `sqlite_master` | 加载/应用/`user_version` = 4；`tool_failures`、`idx_tool_failures_tool_time`、`idx_tool_failures_chat_time` 均存在；真机 `storage/bot.db` 尚未创建（Bot 未启动，属预期） |
| `host_info` Linux 实测 | bot 用户直调 `HostInfoTool`（默认全字段 + `fields` 选择） | cpu=2、memory=4105363456（= `/proc/meminfo` MemTotal）、disk_free=35596984320、python=`3.11.2`、uptime_s=68691（= `/proc/uptime`，非进程时长回退）；`fields` 选择生效；返回键恰为冻结五字段 |
| 证据日志 | 本机临时目录 `<本地临时目录>` 下的 `dsh_tests_vps_88531d2.log`（stdout）与 `dsh_verify_vps_88531d2.log`（13 项逐项输出）；VPS 上未落盘日志文件 | 验收执行后容器数 0、`storage/sandbox` 为空、`storage/workspaces` 仅 `999001`/`999002` |
| 环境复核 | `.venv/bin/python -V`；bot 用户 `podman images` | Python 3.11.2；镜像仍只有 `python:3.12-slim`（未重新 pull）；无 `bot` 用户 python 进程 |
| 历史记录（阶段 7） | 同上两条命令，真机 checkout `3347301` | `Ran 293 tests` / `OK`；沙箱 13 项全 PASS（保留在 git 历史中，判读口径相同） |
| 验收时间 | 2026-10-07（VPS 时间） | — |

Tier A 7/7：纯计算、非 root（UID 1002）、无网络、只读根、单文件大小上限（fsize 8388608）、资源上限（memory 268435456 / pids 64 / cpu 50000-100000）、超时被 kill 且容器已销毁。
Tier B 4/4：本群 workspace 读写（非 root）、宿主侧可见、其他群不可见、宿主目录不可见。收尾 2 项：执行后无残留容器、临时输出目录已清理。

**判读注意（技术债 T7 已于 `4ea2326` 修复；上表是该修复前的真机输出）**：修复前「无网络」「只读根」只看退出码非零，区分不出「容器没起来 / 解释器缺失」，且 `Tier A：PASS` 只聚合 1 项。修复后脚本要求探针标记（`PROBE net`/`PROBE rofs`）与预期错误签名同时出现，`Tier A`/`Tier B` 按显式 tier 归属聚合全部相关检查项（含 2 项全局清理检查），任一项 FAIL 都会翻转结论；逐项输出带 `[A]`/`[B]`/`[AB]` 标记。判定逻辑由 `tests/offline/test_verify_sandbox.py` 离线覆盖（见 `docs/deployment.md` §12.6）；**真机复跑安排在下一次部署/里程碑时**。

### 4.3 阶段 9 最小生产闭环（2026-10-07，真机实测）

运行方式：systemd **用户级**单元（不引入新组件、不开新端口、不动 root 级配置），单元路径、模板与命令见 `docs/deployment.md` §12.9；`is-enabled`=`enabled`、`loginctl show-user bot` 的 `Linger=yes`、`default.target.wants/groupbuddy.service` 符号链接存在 → VPS 重启后自动拉起。阶段 9 未改任何代码。

| 检查 | 命令/手段 | 结果 |
|---|---|---|
| 真实 `.env` | 部署阶段按白名单合并 `BOT_TOKEN`/`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`，临时凭据文件用后 `shred -u` | `-rw------- bot bot`（997 字节）、占位符 0 个；**本文档与所有文档不记录任何凭据值** |
| 启动核对 | 读取 `.env` → `get_me` → 沙箱探测 → 后台任务 | `配置加载完成`（`BOT_TOKEN=[redacted]`，SecretFilter 生效）→ `Bot 就绪 username=… bot_id=… model=deepseek-flash` → `沙箱后端就绪 backend=podman version=podman version 4.3.1 workspace=True` → `沙箱状态 {'backend': 'podman', 'available': 'True', 'workspace_write': 'True', 'image': 'python:3.12-slim', 'max_concurrent': '2'}` → `启动完成 data_dir=… db=…` |
| 启动时 migration | 启动后直接查 `storage/bot.db` | `user_version`=4；表 `chat_settings`/`messages`/`notes`(+fts)/`stickers`/`summaries`(+fts)/`tool_failures`/`updates`/`usage` 齐全 |
| health 心跳 | `storage/health.json` | `ok=true`、`db_ok=true`、`outbound_pending=0`、`instance=default`；`checked_at` 每 60 秒推进（实测 1791376036→1791376199、`uptime_s` 120.06）；重启后 `started_at` 重置、`uptime_s` 归零 |
| Telegram 真机收发 | 用户在测试群 @ Bot 发一条消息 | `updates`=2、`messages`=2（用户消息 + Bot 回复）、`usage`=2 行（`purpose=chat`：`model=deepseek-flash`、input 952 / output 44；静默 ≥120 秒后摘要任务按设计追加 `purpose=summary`：input 174 / output 109，东八区日键 `2026-10-07`）、`summaries`=1（`msg_from`=1 → `msg_to`=2，119 字）；`health.json` 的 `last_update_at` 由 `null` 变为非空；日志 `WARNING`/`ERROR`/`Traceback` 计数 0；`chat_settings`=0（`/settings` 回显不写库，符合设计）、`tool_failures`=0 |
| 管理员命令通路 | 真机 `get_chat_administrators` 探针 | 触发者确认为该群管理员（`is_admin=True`）→ `/settings` 走回显分支（成功回显不打日志、不写 `messages`/`chat_settings`）；非管理员拒绝分支与「不泄露内部信息」由离线测试覆盖（`tests/offline/test_commands.py`、`test_metrics.py`） |
| 优雅停止 | `systemctl --user stop groupbuddy.service` | 日志 `收到信号 signum=15` → `已关闭`，进程消失、`is-active`=`inactive`（走 SIGTERM，未 `kill -9`） |
| 重启恢复 | 随后 `start` / `restart` | 恢复 `active`，`Bot 就绪`/`启动完成` 重新打印；`bot.db` 保留（118784 字节、`user_version`=4），health 心跳恢复 |
| 异常自动重启 | `kill -9 <MainPID>` | `MainPID` 换新 PID、**`NRestarts` 0→1**、`ActiveState=active`，重新输出 `配置加载完成`/`Bot 就绪`/`启动完成`；日志仍无 `WARNING`/`ERROR`/`Traceback` |

排查注意：目标机用户级 `journalctl --user` 无 journal 文件（`No journal files were found`），运行日志以 `storage/logs/bot.log` 为准。`/settings` 的回显文案由用户目视确认（非阻塞项）。

本阶段明确未做：容器托管（`Dockerfile`/`compose.yaml`，可选路径）、正式远端（GitHub）、任何架构重构；T25 关键路径补测（`6b93fd6`）、T7 验收脚本判定口径（`4ea2326`）与 T9 repo 写入事务边界（`1826d89`）已在阶段 9 之后补做；备份/恢复与更新回滚演练已在同阶段补齐（见 §4.4）。

### 4.4 阶段 9 备份/恢复与更新/回滚演练（2026-10-07，真机实测）

演练在 Bot **在线**的情况下进行；备份与恢复都在副本上操作，现有 `storage/bot.db` 未被替换。演练用的坏版本是本地一次性分支 `stage9-broken-probe`（`7474c42`，只加 4 行「模拟新版本启动失败」，**永不合并进 `main`**），已随 bundle 传到真机以便复现。

| 检查 | 命令/手段 | 结果 |
|---|---|---|
| 在线备份 | `sudo -u bot bash -lc 'cd /home/bot/app && .venv/bin/python scripts/backup_db.py'`（Bot 未停机） | 快照 `storage/backups/bot.db.20261007-2051`（118784 字节）；输出 `user_version=4 integrity=ok chat_settings=0 messages=2 notes=0 stickers=0 summaries=1 tool_failures=0 updates=2 usage=2`；同目录另有 `bot.db.20261007-2046`；`sidecar_files=0`（快照是单文件，无 `-wal`/`-shm`） |
| 快照可重复 | 两轮备份后比对 SHA256 | 同一份快照两轮 `49735a608bd3f739bd028ad129a150546f9efcfaf9134f7c832b63606c6faef0` 一致 |
| 恢复出独立数据库 | 以 `bot` 复制快照到 `/tmp/dsh_restore_probe/bot.db`（118784，`bot:bot`；**必须以 bot 身份**，否则 WAL 切换报 `attempt to write a readonly database`） | 只读探针：`user_version`=4、8 表行数与线上逐项一致、`integrity`=ok、`first_user`/`last_assistant` 原文一致 → `IDENTICAL=yes`（与线上对照 diff 为空） |
| 恢复库可被应用层打开 | `PYTHONPATH=. DB_PATH=<副本> .venv/bin/python /tmp/dsh_appcheck.py`（走 `load_settings()`+`open_db`+`apply_migrations`） | `app_open_ok db_path=/tmp/dsh_restore_probe/bot.db migrations_version=4 messages=2` |
| 演练不影响运行中的 Bot | 演练前后 `systemctl --user show` 与 `health.json` | `MainPID=48310 NRestarts=0 active/running` 前后一致；`checked_at` 1791377465.213371 → 1791377525.241856（60 秒心跳继续推进，`uptime_s` 300.07→360.10）；日志 `warn_error_traceback=0` |
| 更新到新版本 | 按 `docs/deployment.md` §8.1 用 bundle 把 `88531d2`（上一可工作版本）更新到 `bc31c41` | HEAD `bc31c41`、`dirty=0`、跟踪文件 132→135；日志 `配置加载完成`→`Bot 就绪`→`沙箱状态`→`启动完成`；`MainPID=48310 NRestarts=0 ExecMainStatus=0 active/running`；`bot.db` 行数与演练前完全一致、`integrity`=ok；`workspaces/` 未变 |
| 坏版本启动失败可检出 | 部署 `7474c42`（见上行同流程） | `MainPID=0 Result=exit-code NRestarts=1 ExecMainStatus=1 ActiveState=activating SubState=auto-restart`；日志两条 `ERROR app.main 阶段 9 更新演练：模拟新版本启动失败`（发生在 `配置加载完成` 之后、`Bot 就绪` 之前）；无存活 `app.main` 进程；`Restart=always` 在自动重试 |
| 回滚到上一版本 | `stop` + `reset-failed` → `git checkout 88531d2` → `start` | `MainPID=48739 Result=success NRestarts=0 ExecMainStatus=0 active/running`；日志 `Bot 就绪`/`启动完成`；`user_version`=4、8 表行数与演练前完全一致、`integrity`=ok、`workspaces/` 仍为 `999001 999002` |
| 演练后回到好版本 | 再次按 §8.1 部署 `bc31c41` | HEAD `bc31c41`、`dirty=0`、跟踪文件 135；`MainPID=48814 NRestarts=0 ExecMainStatus=0 active/running`；`health.json` `ok=true`；`storage/backups/` 两份快照仍在；日志 `warn_error_traceback=2`（＝演练故意注入的 2 条 ERROR，属预期） |
| Telegram 连通性（演练后） | bot 用户 `Bot.get_me()`（只打印 username/id） | `getMe ok username=xiaoguNo1_bot id=8974124020` |
| 无 Secret 泄漏 | 对 `storage/logs/bot.log` 做形状扫描（只报计数） | `telegram_token_like=0`、`api_key_like=0`、`[redacted]` 标记 15 处；`.env` = `600 bot:bot` 997 字节，`git ls-files .env` 未跟踪 |
| bundle 持久化 | 把两个 bundle 复制到 Bot 用户持久目录并重指 `origin` | `/home/bot/bundles/dsh_deploy_88531d2.bundle`（334645 字节）、`dsh_deploy_bc31c41.bundle`（351723 字节）；`origin` = 后者，`git fetch origin` 成功、`git branch -r` 见 `origin/main` 与 `origin/stage9-broken-probe`；`git bundle verify` = `complete history` |

演练结论：备份可恢复、恢复库可读且与线上一致、更新成功、坏版本失败可检出并可回滚、回滚后 Bot 恢复 `active`、`bot.db` 与 workspace 全程未丢、日志与错误消息无 Secret。

### 4.5 首次真实使用观察与修复（2026-10-07，真机 `bc31c41`）

用户在真实群（`chat_id` `-1004487987492`）使用后按只读方式核对（Bot 未改动）：`updates` 30、`messages` 56（user 29 / assistant 27）、`usage` 32（chat 29 次 `43976 in / 4547 out`；summary 3 次 `2372 / 821`）、`summaries` 3、`chat_settings` 0、`stickers` **0**、`tool_failures` **2**；日志 WARNING/ERROR 仅上次演练故意注入的 2 条；`health.json` `ok=true`。

- **发现**：`tool_failures` 两条 `('send_sticker', -1004487987492, 'not_found')`。原因是 `allow_sticker` 默认开、而本群贴纸库为空 → `send_sticker` 每次匹配必然 `not_found`，模型想发表情就白花一轮工具调用，并污染 `/stats` 的错误率。
- **修复 `bafe096`**（独立 commit，5 个代码/测试文件 + `docs/security.md` + `docs/tools.md`）：`ToolContext` 新增 `stickers_available`（默认 `true`）；runner 每轮在 `profile.stickers` 为真时查一次本群贴纸（economy 短路不多查）；`Policy._advertised` 只从**下发清单**剔除 `send_sticker`——`check()`/执行路径的 `permission_denied`/`not_found` 契约不变（库为空时模型仍硬调依旧是 `not_found`）。不引入缓存/后台任务。
- **本机验证**：`Ran 425 tests` / `OK (skipped=2)` / 退出码 0；新增 3 条测试（三种下发组合 + 空库端到端只调一轮模型 + 有贴纸时重新下发）。
- **真机同步与复验（2026-10-07 22:07）**：按 `docs/deployment.md` §8.1 用 bundle 把真机从 `bc31c41` 更新到 `26e946d`（代码内容 = `bafe096`），停机 ≈8 秒（`收到信号` 22:07:23 → `启动完成` 22:07:31），`dirty=0`、跟踪文件 135、`origin` 重指 `/home/bot/bundles/dsh_deploy_bafe096.bundle`、`.env` 的 sha256 前后一致（未改真实凭据、未改 systemd/DB 结构/备份策略），`MainPID=50510 NRestarts=0 ExecMainStatus=0 active/running`。真机复验（真实代码路径 + 生产库）：生产库 + 真实群（`stickers` 0 行）时 `allowed_names`/`api_tools` 均无 `send_sticker`（`calc`/`read_file`）且 `check()` 仍为 `None`（执行契约未破）；线上库副本注册 1 张贴纸后 `send_sticker` 重新出现在两处清单；副本 `allow_sticker=0` 时不下发且 `check()`=`permission_denied`。真机直接相关测试 `Ran 65 tests` / OK（`test_policy`/`test_pipeline`/`test_modes`）。`tool_failures` 仍只有修复前 2 条 `send_sticker/not_found`（无新增）、`bot.log` 无新 WARNING/ERROR（`warn_error_traceback=2` 为阶段 9 演练故意注入）、`health.json` `ok=true`/`db_ok=true`/`outbound_pending=0`、无沙箱容器残留。**真实消息复验（2026-10-07 22:19）**：用户在真实群发一条消息（`messages.id=59`）→ Bot 22:19:34 回复（`messages.id=60`），`usage` 第 35 行 `purpose=chat`（input 1451 / output 214）**`tool_calls=0`**，即模型没有再白花一轮贴纸调用；`tool_failures` 仍是修复前那 2 条（无新增 `send_sticker/not_found`），`health.json.last_update_at` 由 `null` 推进为非空，`bot.log` 无新 WARNING/ERROR。

## 5. 尚未做 / 尚未上线（重要）

- **Bot 已在真机 24/7 运行**：systemd 用户级单元 `groupbuddy.service`（`Restart=always`、`RestartSec=5`，配合 `Linger=yes` 开机自启），真机证据见 §4.3，部署契约见 `docs/deployment.md` §12.9。
- **真实 `.env` 已就位**：`/home/bot/app/.env`（`600`、`bot:bot`，只写覆盖项，绝对路径）；仓库内仍只有 `.env.example`，本文件与所有文档都不记录任何凭据值。
- **未配置正式远端**：代码同步通过 git bundle + SSH 完成；bundle 已从 `/tmp` 移到 Bot 用户持久目录（真机 `origin` = `/home/bot/bundles/dsh_deploy_bafe096.bundle`），仍未建 GitHub remote、未 push。
- 备份/恢复与更新/回滚演练已完成（见 §4.4）；**仍未实现**：程序内自动备份任务与 `BACKUP_INTERVAL_SECONDS`/`BACKUP_KEEP` 环境键（当前只能手工跑 `scripts/backup_db.py`）、`PRAGMA optimize` / `VACUUM`、容器托管（`Dockerfile`/`compose.yaml`，可选路径）。
- 阶段 8 内明确留到后续的项：链 3 的工具轮次按意图分档（`TOOL_MAX_ROUNDS` 仍为全局 2）、模型档位路由（未决问题 #2）。原留后项 `/clear` 已补做（`8b14aab`，本机；真机尚未同步），群级人设 Persona 已实现（`c29ecac`，本机；真机尚未同步），长期笔记 `/note` 已实现（`495389b`，本机；真机尚未同步；记忆体验优化的第一项，见 `docs/memory.md` §6），工具体验优化修复 T31（`e1dcb6a`，本机；真机尚未同步：工具清单逐轮重取，本轮被禁用的工具不再下发给模型），关键路径补测 T25（`6b93fd6`，本机；真机尚未同步：只新增测试与文档，不改运行期行为，因此不影响真机运行），验收脚本判定口径 T7（`4ea2326`，本机；真机尚未同步：只改 `scripts/verify_sandbox.py` 的判定与 4 条离线测试 + 文档，不影响 Bot 运行期行为；真机复跑安排在下一次部署/里程碑），repo 写入事务边界 T9（`1826d89`，本机；真机尚未同步：**这条改变了运行期写入路径**（repo 不再自己 `commit()`，改由 `app/storage/tx.py` 的 SAVEPOINT 事务提交），因此下一次真机部署必须连同一次真实收发冒烟一起复验，并按 `docs/deployment.md` §8.1 备好回滚）。
- **模型档位路由与链 3 轮次分档：已评估为暂不做（2026-10-07）**：真实使用成本 < $0.01（§4.5：29 次 chat 调用 ≈ 44k 输入 / 4.5k 输出、观察到的轮次 `tool_calls=0`），没有复杂轮次质量不足的证据；唯一可用方向是把复杂轮次升级到 `deepseek-v4-pro`（提高花费换质量），其价格与可得性未核实，属部署决策；轮次分档的「闲聊=0 轮」会连贴纸工具一起关掉，与贴纸功能冲突。评估结论见 `docs/requirements.md` 未决问题 #2、`docs/token.md` §3/§5。
- 未引入 CI、lint、类型检查、锁文件（见 `TODO.md` T27）。

## 6. 技术债摘要

完整清单（T1–T31，含等级与 `文件:行号`）在 `TODO.md` §技术债与已知缺陷。`f7f34b5` 已修复其中 3 条，阶段 8 F5.2（`7382639`）追加修复 1 条，F5.4（`101c26c`）追加修复 1 条，工具体验优化（`e1dcb6a`）追加修复 1 条（T31），关键路径补测（`6b93fd6`）补上 1 条（T25，只加测试），验收脚本判定口径（`4ea2326`）修复 1 条（T7），repo 写入事务边界（`1826d89`）修复 1 条（T9）：

- **T1（P0，已修复）**：摘要「静默 ≥120 秒」触发恒不成立（`time.monotonic()` 与 Unix 秒比较）——记忆能力静默退化。
- **T2（P0，已修复）**：迁移无事务 + `ALTER TABLE` 不幂等——迁移中途失败会让 Bot **永久无法启动**。
- **T3（P1，已修复）**：本轮消息在超出字符预算时被 history 裁剪丢弃。
- **T12（P1，已修复，`7382639`）**：`chat_settings.upsert` 先读再写，并发下会丢更新（群主命令即将把设置写入变成热路径）——改为单条原子 `INSERT … ON CONFLICT DO UPDATE`，只写调用方给出的列；离线测试用 `mock` 断言 upsert 不再读取当前设置。
- **T15（P1，已修复，`101c26c`）**：`tool_failures` 表缺失，`/stats` 无失败数据源——migration 4 建表 + 两个索引，计入熔断的失败（超时 / 工具错误 / 未预期异常）经 `failure_recorder` 留痕，启动时与每小时清理 7 天前的行；调用前拒绝（`permission_denied` / `invalid_arguments` / `cooldown`）不入表。
- **T31（P1，已修复，`e1dcb6a`）**：工具清单在本轮内被快照（`app/llm/loop.py:89`）——第 1 轮取一次后，后续轮次仍下发「本轮已禁用/已熔断」的工具，模型可能再次调用只可能返回 `cooldown` 的工具，白花一整轮模型调用与 token；与 `docs/tools.md` §1、`docs/security.md` §9 的「本轮从可用清单移除」及 F4.8 验收「失败工具不再重复调用」不符。修复：每一轮重新取清单（清单为空即不带工具、强制给答案），`cooldown` 文案改用 `BreakerConfig.round_failures` 而不是写死 2。发现路径：工具体验优化（代码 + 契约证据；同类浪费在真实使用中已由 `send_sticker` 空库双失败暴露过一次）。
- **T9（P1，已修复，`1826d89`）**：各 repo 自己 `commit()`、无 `rollback`（`summaries.py:65,136`、`notes.py:48`、`stickers.py:73,90` 等 14 处），主表 + FTS 的多语句写可能半提交，或被执行其他任务的写入时顺带提交。修法：新增 `app/storage/tx.py` 的 `transaction()`（`SAVEPOINT` … `RELEASE` / `ROLLBACK TO`，因为整进程共享一条连接、`BEGIN` 会与之冲突），14 个写入入口全部改为在事务内完成并去掉自己的 `commit()`；主表与 FTS 要么一起生效要么一起回滚。离线回归 10 条（见 §3），契约同步 `docs/database.md` §6 与 `docs/architecture.md` 模块表。**注意：这条改变了运行期写入路径**，真机需随下一次部署复验。
- **T25（P1，已补测，`6b93fd6`）**：`app/main.py`、`app/logging_setup.py`、`app/telegram/handlers.py`、`app/telegram/sender.py` 零测试，`CliBackend.run` 与 `DeepSeekClient` 类体从未执行，`SecretFilter` 无测试——A1–A3 修复期间正是这个缺口让 `app/main.py` 缺 `import time` 的装配缺陷躲过全部离线测试。补法：只加测试（45 条，见 §3），不改产品代码；契约文档同步 `docs/architecture.md` §8 与 `docs/decisions/0006-credentials-not-in-git.md`。

当前最严重的是尚未修复的 B 组：CLI 非零退出不映射 `execution_failed`（T4）。（关键路径零覆盖 T25 已于 `6b93fd6` 补测：`app/main.py`、`app/logging_setup.py`、`app/telegram/handlers.py`、`app/telegram/sender.py`、`CliBackend.run` 与 `DeepSeekClient`；验收脚本判定口径 T7 已于 `4ea2326` 修复：负向断言要求探针标记与错误签名，`Tier A`/`Tier B` 按显式归属聚合；repo 层无事务边界 T9 已于 `1826d89` 修复：写入统一走 `app/storage/tx.py`，失败整体回滚，不再有半提交。）

其余分类：安全与沙箱（T4–T8）、数据与记忆（T9–T16）、工具契约（T17–T20）、代码质量（T21–T24）、测试与工程（T25–T30）。

## 7. 下一步

0. **当前批处理路线（用户 2026-10-07 指定，按序推进）**：真实使用反馈 → `/clear`（已完成，`8b14aab`）→ Persona（群级配置，**已完成，`c29ecac`**）→ **记忆体验优化（里程碑 B，进行中：第一项长期笔记 `/note` 已补做 `495389b`——填上 `docs/memory.md` §6 一直标注「尚未实现」的写入路径；其余候选按真实使用证据再评估）** → 工具体验优化（**已完成，`e1dcb6a`**：修复 T31 工具清单逐轮重取；其余候选（工具数量、新基础设施）无真实证据，未自造）→ 模型档位路由（**已评估，暂不做**）→ 链式工具轮次优化（**已评估，暂不做**：闲聊=0 轮会关掉贴纸工具，需产品决策）→ Stage 10.0 服务层接口预留（`docs/domain.md`/`docs/architecture.md` §10 已预留，无冻结接口规格，属产品设计）→ B 组技术债（T25 关键路径补测已完成 `6b93fd6`，只加测试；T7 验收脚本判定口径已修 `4ea2326`，含 4 条离线测试与文档；T9 repo 写入事务边界已修 `1826d89`，含 10 条离线测试与契约同步）→ 阶段 9 小优化（`PRAGMA optimize`；`BACKUP_*` 属部署契约变化、正式 remote 需用户确认）→ **下一项**。原则：已有真实反馈优先处理，无真实证据的新需求不自造；低风险可回滚的决定自行完成并记录。里程碑 A（`/clear` + Persona）已完成；该路线的模块形态统一为「Telegram adapter → `app/ops/` 规则入口 → repo」，Persona 与 `/note` 都按此落地，后续工具 UX 沿用同一形态。
1. **阶段 8 已全部完成并通过真机验收**（真机 `88531d2`：416 条全量 OK、沙箱 13 项全 PASS、migration 4 与 `host_info` Linux 行为符合契约）：F5.2（管理员判定 + 命令通道 + T12）、F5.1（`/settings <字段> <值>` 写入、即时生效）、F5.3（日/月配额）、F5.4（`/stats` + `/health`，`tool_failures` 留痕与 7 天清理，与 `storage/health.json` 同一内部状态）、F4.7（`host_info`：`cpu`/`memory`/`disk_free`/`python`/`uptime_s`，L4 + `allow_host_info` 默认关）与四模式（`78ae9cf`：窗口 / 输出上限 / 工具档位，`docs/token.md` §5）。阶段 8 内明确留到后续的只有链 3 轮次分档、模型档位路由（`/clear` 已于 `8b14aab` 补做，群级人设 Persona 已由 `c29ecac` 补做）。
2. **阶段 9（部署与 24/7）进行中**：最小生产闭环已完成并真机验证（systemd 用户级单元、真实 `.env`、启动时 migration、health 心跳、Telegram 真机收发、stop/start/restart 与 `SIGKILL` 自动重启，见 §4.3）；备份/恢复与更新/回滚演练已通过（`scripts/backup_db.py`、`docs/deployment.md` §8.1，证据见 §4.4），真机当前跑 `26e946d`（= `bafe096`，真机直接相关测试 65 条 OK）。首次真实使用发现的空贴纸库问题已在真机同步并复验（见 §4.5）。阶段 9 未完成部分：程序内自动备份任务与 `BACKUP_*` 环境键、`PRAGMA optimize`/`VACUUM`、容器托管（可选路径）。
3. 是否立项修 B 组技术债（`TODO.md` T4 / T6 / T10 等；T1–T3 已随 `f7f34b5`、T12 已随 `7382639`、T15 已随 `101c26c`、T25 已随 `6b93fd6`、T7 已随 `4ea2326`、T9 已随 `1826d89` 修复）。
4. 是否配置正式远端（GitHub），以便后续换 Agent 维护。

## 8. 如何重新生成这些证据

```bash
# 本机（Windows，仓库根）
python -m unittest discover -s tests -t .

# 真机（Linux VPS，bot 用户；注意用单引号包住 bash -lc 的内容）
sudo -u bot bash -lc 'cd /home/bot/app && .venv/bin/python -m unittest discover -s tests -t .'
sudo -u bot bash -lc 'cd /home/bot/app && .venv/bin/python scripts/verify_sandbox.py'   # 需要容器运行时
```

生产托管（阶段 9，systemd 用户级单元；root 操作 bot 的 `--user` 实例必须显式给 `XDG_RUNTIME_DIR`）：

```bash
U=bot; R=/run/user/$(id -u "$U")
sudo -u "$U" env XDG_RUNTIME_DIR=$R systemctl --user is-enabled groupbuddy.service
sudo -u "$U" env XDG_RUNTIME_DIR=$R systemctl --user show -p MainPID -p NRestarts -p ActiveState -p ExecMainStartTimestamp groupbuddy.service
sudo -u "$U" env XDG_RUNTIME_DIR=$R systemctl --user start|stop|restart groupbuddy.service
cat /home/bot/app/storage/health.json          # checked_at 每 60 秒推进
tail -n 20 /home/bot/app/storage/logs/bot.log # 用户级 journalctl 在目标机无 journal 文件
```

代码同步（无正式远端时的临时通道，替换 `<sha>`）：

```bash
# 本机（部署用私钥与本地临时目录不入文档）
git bundle create <本地临时目录>/dsh_deploy_<sha>.bundle main
scp -i <部署用私钥> <本地临时目录>/dsh_deploy_<sha>.bundle root@<vps>:/tmp/

# 真机：确认 sha256 一致后
sha256sum /tmp/dsh_deploy_<sha>.bundle
sudo -u bot bash -lc 'cd /home/bot/app && git bundle verify /tmp/dsh_deploy_<sha>.bundle \
  && git fetch /tmp/dsh_deploy_<sha>.bundle main:refs/remotes/origin/main \
  && git remote set-url origin /tmp/dsh_deploy_<sha>.bundle && git checkout <sha>'
```

备份与恢复（阶段 9；`<快照>` 取 `storage/backups/` 下最新一份）：

```bash
# 在线备份（Bot 不停机），输出 path/bytes/user_version/integrity/各表行数
sudo -u bot bash -lc 'cd /home/bot/app && .venv/bin/python scripts/backup_db.py'

# 恢复演练：必须以 bot 身份复制（否则 WAL 切换报 attempt to write a readonly database），
# 且只对副本操作，不替换线上 bot.db
sudo -u bot mkdir -p /tmp/dsh_restore_probe
sudo -u bot cp /home/bot/app/storage/backups/<快照> /tmp/dsh_restore_probe/bot.db
# 校验副本：用现有脚本对副本再做一次快照，输出的 bytes/user_version/integrity/各表行数即为副本实况
sudo -u bot bash -lc 'cd /home/bot/app && .venv/bin/python scripts/backup_db.py --db /tmp/dsh_restore_probe/bot.db --dest /tmp/dsh_restore_probe/verify'
```

副本与线上逐项对照（`user_version`、8 表行数、`first_user`/`last_assistant` 片段）应完全一致（`IDENTICAL=yes`）；
应用层可读性用临时探针验证：`load_settings()` → `open_db()` → `apply_migrations()`（阶段 9 实测 `migrations_version=4`、`messages=2`），
探针脚本属一次性产物，不入库。

更新与回滚按 `docs/deployment.md` §8.1 五步执行；bundle 传到 `/tmp` 后建议复制到 Bot 用户持久目录并把 `origin` 指过去
（真机当前为 `/home/bot/bundles/dsh_deploy_bc31c41.bundle`），这样后续 `git fetch` 不依赖 `/tmp`。

约束：`/home/bot/app` 属主是 `bot`，root 直接执行 git 会报 `dubious ownership`，所有 git 操作必须经 `sudo -u bot bash -lc '…'`；
`podman images` / `podman ps` 必须在 `bot` 用户可读的目录（如 `/home/bot/app`）里执行，否则会因 `cannot chdir to /root` 而失败；
**`bash -lc` 的内容必须用单引号，不要用双引号**：双引号会让外层 shell 先展开 `$(…)` / `$?` / `$HOME`，实测导致 `cd` 未生效（留在 `/root`，报 `.venv/bin/python: No such file or directory`）且重定向文件变成 root 所有（`bot` 再写就 `Permission denied`）；
`systemctl --user` 在 root 会话下必须带 `XDG_RUNTIME_DIR=/run/user/<uid>`（否则 `Failed to connect to bus: No medium found`），且**必须给单元名**（`systemctl --user is-active` 不带名字会报 `Too few arguments.`）。