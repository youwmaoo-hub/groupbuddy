# 当前状态（唯一事实来源）

负责：**当前基线**——commit、已完成阶段与能力、本机与真机测试结果、真机验收证据、技术债摘要、下一步。
上游：`docs/README.md` §2 路由表。
改动影响：本文件不是契约，只记录事实。契约在 `docs/requirements.md`、`docs/architecture.md`、`docs/security.md`、`docs/tools.md`、`docs/database.md`、`docs/deployment.md`。**每次提交、每次验收、每次阶段结束都要更新本文件**；其他文档不再各自维护「当前状态/进度/测试数字」，只指向这里（`AGENTS.md` §7、`TODO.md` §当前状态）。

## 1. 当前基线

| 项 | 值 |
|---|---|
| 代码 commit | `30cc3fe69a0a5693138a550e5836566878ec7767`（短 `30cc3fe`，分支 `main`；阶段 9 之后的真实使用修复 `bafe096` + 其基线记录、阶段 8 留后项 `/clear` `8b14aab`、群级人设 Persona `c29ecac`、长期笔记 `/note` `495389b`、工具清单逐轮重取 `e1dcb6a`、关键路径补测 T25 `6b93fd6`、验收脚本判定口径 T7 `4ea2326`、repo 写入事务边界 T9 `1826d89`、`PRAGMA optimize` 例行化 `29f6687`、容器运行时保留退出码 T4 `d59a703`、验收脚本能力/提权检查与贴纸时间口径 T6/T10 `b41bff4`、模型档位路由 `e26ea3c`、链式工具轮次分档 `a5bf651`、群宠体验升级 `ba7afe1`、贴纸 catalog 对齐公开包 `deepseek_whale_girl`（104 槽）`30cc3fe`、真实使用反馈修正 `172ab6b6e814eca3fc9fcf582bc6743c48f7dd42`、回复目标唯一修复 `50b4159de81dc87b40ea5711a068d98ee4035878`、开源配套与标识占位符化 `92755c3646981c0181b0d7bec2f630ef51ee115c`、开源化推送确认 `5b14ab064166cd62dd808b2657474f5f59cbdc73`、默认接话改造 `39687b4` + 其基线记录（本文件所在提交），见 §4.5–§4.11、§5、§6） |
| 跟踪文件数 | 166（`git ls-files`；开源配套新增 10 个：`README.md`、`LICENSE`、`CONTRIBUTING.md`、`SECURITY.md`、`CHANGELOG.md`、`.github/workflows/tests.yml`、`.github/ISSUE_TEMPLATE/`（3 个）、`.github/PULL_REQUEST_TEMPLATE.md`；Persona 新增 `app/ops/persona.py`、`tests/offline/test_persona.py`、`tests/offline/test_admins.py`；长期笔记新增 `app/ops/notes.py`、`app/ops/text.py`、`tests/offline/test_notes.py`；T25 新增 `tests/offline/test_logging.py`、`test_telegram_sender.py`、`test_handlers.py`、`test_client.py`、`test_main.py`；T7 新增 `tests/offline/test_verify_sandbox.py`；T9 新增 `app/storage/tx.py`、`tests/offline/test_transactions.py`；模型档位路由新增 `app/llm/routing.py`、`tests/offline/test_routing.py`；群宠体验升级新增 `app/ops/sticker_catalog.py`、`scripts/import_sticker_set.py`、`tests/offline/test_sticker_catalog.py`、`deploy/stickers/catalog.json`、`deploy/stickers/README.md`） |
| 提交数 | 73（阶段提交 + 文档治理 `b529741` + A1–A3 修复 `f7f34b5` + 文档同步 `3347301` + 部署记录 + 阶段 8 F5.2 `7382639` + F5.1 `c49fdc5` + F5.3 `1d649b8` + F5.4 `101c26c` + 基线 `ad560f4` + F4.7 `de73b57` + 四模式 `78ae9cf` + 四模式基线 `88531d2` + 真机验收记录 `d5e48f0` + 阶段 9 托管文档 `5a5b6d5` + 阶段 9 基线 `cb30c10` + 备份与校验 `bc31c41` + 阶段 9 演练记录 `bed250b` + 真实使用修复 `bafe096` + 其基线记录 + 真机同步与复验记录 `a4e1afc` + `/clear` `8b14aab` + 其基线记录 + 群级人设 Persona `c29ecac` + 其基线记录 + 长期笔记 `/note` `495389b` + 其基线记录 + 工具清单逐轮重取 `e1dcb6a` + 其基线记录 + 模型档位路由与轮次分档评估 + 关键路径补测 T25 `6b93fd6` + 其基线记录 + 验收脚本判定口径 T7 `4ea2326` + 其基线记录 + repo 写入事务边界 T9 `1826d89` + 其基线记录 + `PRAGMA optimize` 例行化 `29f6687` + 其基线记录 + 容器运行时保留退出码 T4 `d59a703` + 其基线记录 + 验收脚本能力/提权检查与贴纸 Unix 秒 T6/T10 `b41bff4` + 其基线记录 + 模型档位路由 `e26ea3c` + 其基线记录 + 链式工具轮次分档 `a5bf651` + 其基线记录 + 真机仓库行注修正 + 群宠体验升级 `ba7afe1` + 其基线记录 + 贴纸 catalog 对齐 104 槽 `30cc3fe` + 其基线记录 + 群宠体验升级真机上线与验收记录 + 其基线记录 + 真实使用反馈修正 `172ab6b` + 其基线记录 + 回复目标唯一修复 `50b4159` + 其基线记录 + 开源配套（README / LICENSE / CONTRIBUTING / SECURITY / CHANGELOG / GitHub Actions / Issue 与 PR 模板）与标识占位符化 `92755c3` + 开源化推送确认 `5b14ab0` + 默认接话改造 `39687b4` + 其基线记录（本文件所在提交）） |
| 本机工作树 | 干净（`git status --porcelain` 无输出）；真机 @ `50b4159`（群宠体验升级那一批的代码提交），本机 `main` 在其上多 5 条提交（回复目标唯一修复的基线记录 `387467d`、开源配套 `92755c3`、开源化推送确认 `5b14ab0`、默认接话改造 `39687b4`、本文件基线提交），差异里没有未提交改动；`origin` = GitHub 公开仓库 `youwmaoo-hub/groupbuddy`（`main` 已推送，见 §4.10） |
| 真机仓库 | `<bot-home>/app` = detached HEAD @ 本批部署提交（回复目标唯一修复 `50b4159`：每轮只回应当前触发消息、被跳过的消息不再补答；部署记录见 §4.8），工作树干净，属主 `bot:bot`，跟踪文件 156；**Bot 已在真机运行**：systemd 用户级单元 `groupbuddy.service`（`ActiveState=active`、`Restart=always`，见 §4.3、§4.6、§4.7、§4.8） |
| 真机远端 | `origin` = VPS `<bot-home>/bundles/dsh_deploy_<部署提交短哈希>.bundle`（每次部署按该次提交短哈希命名；本批依次为 `dsh_deploy_1a723fa.bundle` → `dsh_deploy_30cc3fe.bundle` → 最后一次文档基线，见 §4.6；真实使用反馈修正批为 `dsh_deploy_172ab6b.bundle`，见 §4.7；回复目标唯一修复批为 `dsh_deploy_50b4159.bundle`，见 §4.8）。Bot 用户持久目录，`/tmp` 会被清理；bundle 含 `refs/heads/main`，可 `git fetch`。**项目正式远端已改为 GitHub 公开仓库 `youwmaoo-hub/groupbuddy`**（本机 `origin`，长期使用；真机侧 `<bot-home>/.ssh` 不存在、无 GitHub 凭据，故真机 `origin` 仍是持久 bundle，待配置部署密钥后再切到 GitHub） |
| 项目远端 | GitHub 公开仓库 `youwmaoo-hub/groupbuddy`（本机 `origin`，`main` 已推送且与本机基线一致；仓库已公开，topics、简介与 CI 首跑结果见 §4.9、§4.10） |
| 许可证 | MIT（`LICENSE`，© 2026 youwmaoo-hub；2026-10-08 起仓库公开，见 §4.9） |
| 运行时目录 | 真机 `storage/`：`bot.db`（118784 字节，`user_version`=4，另有 WAL 的 `-wal`/`-shm`）、存储日志 `logs/bot.log`、`health.json`（60 秒心跳）、`sandbox/`、`workspaces/`、`backups/`（两份已验证快照，见 §4.4），属主 `bot:bot`；真实 `.env` 在 `<bot-home>/app/.env`（`600`、`bot:bot`，**内容与凭据值一律不记录**） |

## 2. 已完成阶段与能力

| 阶段 | 状态 | 能力 |
|---|---|---|
| 0 | 已完成 | 文档骨架 + 部署约束 |
| 1 | 已完成 | 最小闭环：long polling、入站过滤、落库、幂等、debounce、per-chat 串行、出站队列与限速、4096 分段、私聊默认静默、本轮消息边界 |
| 2 | 已完成 | 发言闸门：强触发 / **默认接话**（弱规则只标原因码，兜底 `general`）/ 冷却 20 秒 + 重复过滤 / `NO_REPLY` + 首轮追问一次（2026-10-08 调整，见 §4.11） |
| 3 | 已完成 | 工具主干：注册表、权限判定（唯一入口）、执行器、熔断 + `calc` + `search_web` 接口 |
| 4 | 已完成 | 工作区与文件：`read_file` / `write_file`、路径安全、原子写 + 单层 `.bak` |
| 5 | 已完成 | 贴纸：`stickers` 表、情绪匹配、冷却、出站媒体通道 |
| 6 | 已完成 | 记忆：分档窗口 + 字符预算、噪声标记、模板化摘要、FTS5 检索 |
| 7 | 已完成 | 沙箱 `run_code`：固定 argv、rootless Podman / Docker、Tier A/B、fail-closed；真机部署与验收已完成 |
| 8 | 已完成 | 权限/配额/运维：**群主命令最小闭环、群设定写入、日/月配额与运行指标**（`app/ops/admin.py` 管理员判定 + `/settings` 回显/写入 + `app/ops/quota.py` 配额判定 + `app/ops/metrics.py` `/stats` + `app/ops/health.py` `/health` 与 `storage/health.json` 同一状态，见 `docs/security.md` §2.1、`docs/token.md` §4.1、`docs/deployment.md` §7；F5.1/F5.2/F5.3/F5.4 + T12 + T15）；**F4.7 `host_info` 已实现**（`app/tools/builtin/host_info.py`，L4 + `allow_host_info` 默认关，见 `docs/tools.md` §host_info）；**token 四模式完整生效**（`app/modes.py` 唯一权威表：economy 10 条窗口 / 只 L0 / 256 输出 / 贴纸关；normal 意图分档 + 群开关；smart 50 条 + 额外 L0 只读；unrestricted 50 条 + 全部工具 + 输出不限；模式只由管理员 `/settings mode` 修改，见 `docs/token.md` §5、`docs/security.md` §2.2）；**`/clear` 已补做**（`8b14aab`：管理员限定、只删本群 `messages` 原文、摘要与用量保留，见 `docs/security.md` §2.1、`docs/database.md` §4）；**群级人设 Persona 已实现**（`c29ecac`：`/settings persona_override <文本>` 仅群主 `creator` 可写、普通管理员与成员拒绝、`app/ops/persona.py` 是唯一读取/清洗入口、优先级 本群 > 部署侧 `PERSONA` > 内置人格，见 `docs/persona.md` §2、`docs/security.md` §2.1）；**长期笔记 `/note` 已实现**（`495389b`：仅群主能列出/查看/记住/删除本群笔记，正文单行化 ≤500 字、名称 ≤50 字符、同名覆盖 `version` +1、删除同步清 `notes_fts`，见 `docs/memory.md` §6、`docs/security.md` §2.1） |
| 9 | 进行中（**最小生产闭环 + 备份/恢复 + 更新/回滚均已真机验证**） | 部署与 24/7：systemd **用户级单元** `groupbuddy.service`（`Restart=always`，开机自启，见 `docs/deployment.md` §12.9）、真实 `.env`（`600`）、启动时 migration（`user_version`=4）、`storage/health.json` 心跳、Telegram 真机收发、stop/start/restart 与 `SIGKILL` 自动重启均已实测通过（见 §4.3）；SQLite 冷备份 + 校验 + 保留（`scripts/backup_db.py`，`docs/database.md` §5）、恢复副本与线上一致性、更新成功与坏版本失败可检出、回滚恢复 `active` 且数据未丢（见 §4.4）；**剩**容器托管（可选路径）、程序内自动备份任务与 `BACKUP_*` 环境键、体积膨胀时的 `VACUUM`（离线手工；`PRAGMA optimize` 已随 `29f6687` 例行化） |
| 10 | 未开始 | 控制面板与多实例（仅架构预留） |

## 3. 本机验证（Windows，开发环境）

- 解释器：Python 3.13.15（仓库内 `.venv`）；`openai 3.24.0`；**沙箱走 FakeBackend，不跑真实容器**。
- 命令：`python -m unittest discover -s tests -t .`
- 结果：`Ran 656 tests` / `OK (skipped=2)` / 退出码 0（= 上面分项 624 + 真实使用反馈修正新增 19 + 回复目标唯一修复新增 4 + 默认接话改造新增 9（新增 15 条、改写 6 条：`test_limits.py` 冷却 4 + 重复过滤 4、`test_gate.py` 重复过滤与兜底 `general` 与"每条各自成批"、`test_prompts.py` 接话口径 3、`test_pipeline.py` 首轮 `NO_REPLY` 追问 1），见下一条；293 原有 + 22 条 F5.2 + 11 条 F5.1 + 20 条 F5.3 + 32 条 F5.4 + 19 条 F4.7 + 19 条四模式 + 6 条阶段 9 备份 + 3 条真实使用修复 `bafe096` + 5 条 `/clear` `8b14aab` + 33 条 Persona `c29ecac`：`test_persona.py` 10 条（清洗/长度/清除值/三层优先级）+ `test_admins.py` 5 条（`getChatAdministrators` 里只有 `status == "creator"` 算群主、假对象与真实 aiogram 类型都覆盖、异常不吞）+ `test_commands.py` 17 条（群主可写且不回显正文、普通管理员与成员被拒且不泄露字段名、无 creator 时无人可写、多词/控制字符/`off` 清除/超长/缺文本/写库失败、`persona_override` 不是通用字段）+ `test_pipeline.py` 1 条端到端（群主写入后下一轮 system prompt 含该文本且不含内置人格；普通管理员改不动）+ 36 条长期笔记 `/note` `495389b`：`test_notes.py` 21 条（单行化、解析与保留字/上限、列表与查看文案、仓库同名覆盖 `version`=2 且旧 token 查不到新的、删除同步清 `notes_fts`、按群隔离与 `updated_at` 倒序）+ `test_commands.py` 14 条（群主列出/查看/记住/覆盖/删除全链路、普通管理员与成员被拒且不含笔记名、无 creator 群被拒、参数与超限不写库、写库失败只回固定短句）+ `test_pipeline.py` 1 条端到端（群主写 `/note` 后 0 token，之后一句回溯把 `[笔记:部署] …` 注入记忆块）；`allow_sticker` 关/开且库空/开且有贴纸三种下发组合（含 `check()` 契约不变）、空库时普通消息仍只调一轮模型且工具清单不含 `send_sticker`、库里有贴纸时重新下发；`/clear` 明细：管理员只清本群且摘要保留、空群回 0 条、非管理员被拒且不删、带参数只回用法、`clear_chat` 抛错只回固定短句且不泄露 SQLite 细节；F4.7 明细：`host_info` 冻结字段集与 schema、L4 默认关与群开关、不可得字段与 `/proc` 缺失回退、不泄露环境变量/主机名/路径；四模式明细：档位表逐列、economy/smart/unrestricted 的工具档位、模式窗口与 normal 意图分档、输出上限透传，含 3 条端到端（`/settings mode` 改完立即影响下一条消息的输出上限与工具清单、smart 解锁只读工具、economy 与 smart 的历史窗口差异体现在发给模型的上下文里）；阶段 9 备份明细：在线库生成已验证快照且源库不受影响、保留份数与 `removed`、`keep=0` 不清理、同分钟第二次快照加后缀、缺库时 CLI 退出码 2、CLI 输出含 `integrity=ok` 且不含凭据）；工具清单修复明细（`e1dcb6a`）：第 2 轮重新取清单、本轮被禁用的工具不再下发也不再被第二次执行（未修复时该用例 `spec_calls` 1≠2 失败）、`cooldown` 文案随 `BreakerConfig.round_failures` 变化而不是写死 2）；45 条 T25 关键路径补测（`6b93fd6`，只加测试、不改产品代码）：`test_logging.py` 10 条（`SecretFilter` 的 msg/tuple args/dict args 三条脱敏路径、空密钥不动、过滤器接在 handler 上时输出已脱敏；根 logger 两个 handler 都带过滤器、轮转文件写入且不含凭据、`LOG_LEVEL=DEBUG` 时噪声库仍为 WARNING、`get_logger`）+ `test_telegram_sender.py` 7 条（消息与贴纸的 `message_id`、不设 `parse_mode`、`TelegramRetryAfter` → `RateLimited`（含 `__cause__`）、`TelegramAPIError` → `SendFailed`）+ `test_handlers.py` 4 条（update → runner 字段映射、别名提及、无关 update 忽略、runner 异常被吞并记日志）+ `test_client.py` 13 条（默认/覆盖 payload、显式 `None` 不发送 `max_tokens`、`tools` + `tool_choice=auto`、usage 两种缓存字段与缺失回退、tool_calls 缺省值、空 choices 与底层异常翻译、`aclose`、未注入 client 时构造真实客户端）+ `test_main.py` 8 条（`SELECT 1` 探测可重复、工具失败留痕写入、`run_forever` 等待 `request_stop`、未 `start()` 的 `stop()` 取消任务、每小时清理过期行后退出、信号处理函数注册后直接调用会回调）+ `test_sandbox.py` 的 `CliBackendRunTests` 3 条（真实子进程退出码 0/3、超时杀进程并报 `timed_out=True`）；4 条 T7 验收脚本判定口径（`4ea2326`：`tests/offline/test_verify_sandbox.py` 用假后端跑 `scripts/verify_sandbox.py` 的 `main()` —— 全部符合时 `Tier A：PASS`/`Tier B：PASS`/`合计 13 项，失败 0 项` 且退出码 0；容器没起来时「无网络」「只读根」因缺探针标记与错误签名而 FAIL；单项「非 root」失败会翻转 `Tier A：FAIL`（修复前只聚合 1 项、会漏报）；`workspace_write=False` 时 fail-closed 项 PASS 且打印「Tier B：未启用（fail-closed 生效）」）；10 条 T9 事务边界（`1826d89`）：`tests/offline/test_transactions.py` 用 `SAVEPOINT` 语义验证 —— 最外层 `transaction()` 的写入对第二条连接可见（即 `RELEASE` 已提交，repo 无需自己 `commit()`）；块内抛错整体回滚，且随后另一个任务的正常写入不会把半成品顺带提交；嵌套时内层失败只回滚内层、外层继续提交；repo 回归用假 SQL 注入失败 —— `notes.upsert`（主表 + FTS）失败后正文与 `version` 仍是 v1、旧 token 仍可检索，`notes.delete`、`summaries.insert`、`summaries.prune`（3 条保留 1 条、首行即失败）失败后行与 FTS 条目全部保留；并断言 14 个写入入口在被 patch 成抛错的 `Connection.commit` 下仍能正常工作（repo 不再自己 commit）；4 条阶段 9 维护（`29f6687`）：`optimize()` 只发出 `PRAGMA optimize` 一条语句、在真实迁移库上可重复执行，housekeeping 跑过 ≥4 轮清理仍只优化一次（7 天门槛），`optimize` 抛错时记 `后台清理失败` 且下一轮会重试；2 条 T4 容器运行时保留退出码（`d59a703`）：`tests/offline/test_sandbox.py` 的 `RunnerTests` 对 125/126/127 逐个断言映射为 `SandboxError("execution_failed")`（消息含该码、容器被销毁、临时文件清空），其他非零码（1/2/124/128/255）仍原样把 `exit_code` 与 stdout 返回给模型。
- 回复目标唯一修复明细（`50b4159`，643 → 647）：`tests/offline/test_prompts.py` 新增 `ReplyTargetTests` 3 条（输出规则段同时含「本轮只回应当前触发你的那条消息」与「视为已经跳过」；该句在 `NO_REPLY` 指令之前出现（`reply_limit=280` 下按字符串下标比较）；`build_system_prompt(persona=…)` 覆盖群级人设时该句仍存在）+ `tests/offline/test_pipeline.py` 端到端 1 条（先发 4 字、非噪声但触发不了弱触发的旧消息 → `ignore` 且 `llm.calls == []`，随后 `@bot` 触发 → 本轮批次只含新消息、旧消息只作为背景出现在 payload、只出站 1 条且 `reply_to_message_id` = 本轮最新消息）。
- 2 条 skip 为平台条件跳过（Windows 上软/硬链接相关用例，见 `TODO.md` T28）。
- T6/T10 明细（`b41bff4`，566 → 568）：`tests/offline/test_stickers.py` 新增 1 条（冷却时钟仍是 1000.0 时，落库值必须是 Unix 秒且不等于进程相对秒）并更新 1 条断言（`mark_used` 收到 `1_700_000_000`）；`tests/offline/test_verify_sandbox.py` 新增 1 条负路径（容器仍带能力位 / 仍允许提权 → 两项 FAIL 且 `Tier A：FAIL`）并扩充全绿用例（`合计 15 项` + 两项 `PASS [A]` 断言）。
- 模型档位路由明细（`e26ea3c`，568 → 585）：`tests/offline/test_routing.py` 12 条（默认档与闲聊档 → `LLM_MODEL`、复杂任务且有强模型 → 强模型、无强模型回退、未知意图回退、`purpose=summary` 保持默认档、强模型与默认同名视为未配置、模型名去空格、两档跟随配置、`_decide` 抛错时 fail-safe 回默认档；以及 `ContextBuilder.intent` 的代码块/长文本/链接/指代 → 复杂、短闲聊 → 闲聊、普通句与提问 → 默认、空批 → 默认）+ `tests/offline/test_pipeline.py` 5 条端到端（复杂任务升级且 `usage` 记最终 model + `purpose=chat`、普通任务仍是默认档、无强模型回退默认档、配额先于路由（超额时 0 次模型调用）、economy 模式下升级不改模式语义（输出上限与工具清单仍按 economy））。
- 工具轮次分档明细（`a5bf651`，585 → 594）：`tests/offline/test_routing.py` 新增 `ToolRoundTests` 5 条（闲聊 → 1 轮、default/complex → 全局上限 2、`TOOL_MAX_ROUNDS=4` 时 complex → 4 而闲聊仍 1、未知意图回全局上限、`TOOL_MAX_ROUNDS=0/1` 时 `min` 不突破上限）+ `tests/offline/test_pipeline.py` 4 条端到端（闲聊第 2 次调用不再下发工具且只记 1 次 `tool_calls`、闲聊仍下发 `send_sticker` 且贴纸真的发出、普通任务仍允许 2 轮工具且记 2 次、`TOOL_MAX_ROUNDS=3` 时复杂任务连做 3 轮工具）。
- 群宠体验升级明细（`ba7afe1`，594 → 624）：`tests/offline/test_gate.py` 新增 7 条（Bot 作者即使被点名也永不回复、话题延续命中与超窗/只共享停用词、情绪反应词、久静后开场与「≥6 字」信息量门槛、新弱触发仍被冷却压住；原 `test_followup_outside_window_is_ignored` 更名 `test_followup_outside_window_is_not_a_followup` 并只断言 gap 0/6，因为「从未发言」现在走 `quiet_open`）+ `tests/offline/test_pipeline.py` 4 条端到端（未被点名的信息量消息真的触发主动回复并计入额度、纯噪声 0 次模型调用、主动回复后 20 秒冷却压住下一条、其他 Bot 的消息不进批次也不调用模型）+ `tests/offline/test_sticker_catalog.py` 19 条（manifest 文件/目录与非法 JSON/缺字段/未知字段/tags 空/valence 越界/key 重复一律拒绝、素材名与 `resolve_asset` 的路径穿越拒绝、按 emoji 匹配 Telegram 贴纸包并报未匹配与未使用、幂等 UPSERT（`created_at` 不被覆盖）与 `--dry-run` 不写库、`chat_id=0` 与未绑定条目报错）+ `tests/offline/test_prompts.py` 的 `test_runtime_persona_matches_document` 校验新 `GLOBAL_PERSONA` 与 `docs/persona.md` §4 逐字一致。
- 贴纸 catalog 对齐明细（`30cc3fe`，104 槽，2026-10-08）：`deploy/stickers/catalog.json` 改为按 Telegram 公开包 `deepseek_whale_girl` 的包内顺序生成 104 条（`getStickerSet` 顺序 = GitHub 仓库 `DejavuMoe/deepseek_wale_girl` 文件顺序前移一位，用逐张 `file_size` 相等证明），每条 `key` 取对齐后的仓库文件名；`tests/offline/test_sticker_catalog.py` 19 条仍全绿（测试全部使用临时 manifest，不依赖仓库 catalog 的槽位数），`load_manifest('deploy/stickers/catalog.json')` → 104 条 / 104 个唯一 key，`match_sticker_set(包内 emoji 列表, entries)` → 匹配 104 / 未使用 0；真机导入与实发见 §4.6。
- 真实使用反馈修正明细（`172ab6b`，624 → 643）：`tests/offline/test_prompts.py` 新增 `ReplyLengthTests` 7 条（280 字约束出现在输出规则段且位于 `NO_REPLY` 句之前、`limit=0` 不限、短文本不动、超长按句末裁剪保留完整句、无句末时硬截加 `…` 且总长 ≤ limit、过早句末不采用而回退硬截）；`tests/offline/test_gate.py` 5 条（解析：回复本 Bot → `reply_to_bot=True`/`reply_to_other_bot=False`、回复别的 Bot → 反向、回复人类 → 两皆 False；触发：回复别的 Bot 且无点名 → `ignore/other_bot_reply`、点名/叫别名 → 仍 `respond`）；`tests/offline/test_commands.py` 5 条（`/help` 公开且列全 6 个指令与字段名与权限字样、不泄露本群设置值（`mode=economy` 时 `"模式："`/`"economy"`/`"write_file：开"`/`"贴纸冷却："` 均不出现）、`/settings` 无参末行以「指令：/help 查看全部指令」结尾、无 Telegram 管理员数据时 `/help` 仍可用、成员发 `/help` 有回复且 `llm.calls == []` 不写 `messages`）；`tests/offline/test_config.py` 1 条（`REPLY_MAX_CHARS` 默认 280、`0` 与 `120` 覆盖）；`tests/offline/test_pipeline.py` 2 条端到端（模型长回复 → 出站文本与 `messages.recent` 末条同为裁剪结果；`reply_to_other_bot=True` 的人类消息 → 无批次、0 次模型调用、无出站，但照常入库 1 条）。
- 覆盖缺口：原先零覆盖的 `app/main.py`、`app/logging_setup.py`、`app/telegram/handlers.py`、`app/telegram/sender.py`、`CliBackend.run` 与 `DeepSeekClient` 已由 T25 补齐（`6b93fd6`，只加测试）；真机验收脚本 `scripts/verify_sandbox.py` 的判定逻辑由 `tests/offline/test_verify_sandbox.py` 离线覆盖（T7，`4ea2326`，脚本本身仍需真机执行）；仍未覆盖的是需要真实 Telegram/容器/真机的路径，由真机证据证明（见 §4）。

## 4. 真机验证（Linux VPS）

### 4.1 环境

| 项 | 值 |
|---|---|
| 主机 | Debian 12（VPS，主机名 `<vps-host>`） |
| 运行用户 | `bot`（uid 1002），非 root，不在 `docker` 组 |
| 解释器 | Python 3.11.2（`<bot-home>/app/.venv`）；`aiogram 3.31.0`、`openai 3.26.0`、`aiosqlite 0.22.1`、`sqlite 3.40.1` |
| 容器运行时 | rootless Podman 4.3.1，cgroup v2，driver `overlay`，runtime `crun` |
| 镜像 | 只有 `docker.io/library/python:3.12-slim`（digest `sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f`，124 MB，部署阶段预拉；验收期间未重新 pull） |

### 4.2 测试与验收

| 检查 | 命令 | 结果 |
|---|---|---|
| 全量离线测试 | `sudo -u bot bash -lc 'cd <bot-home>/app && .venv/bin/python -m unittest discover -s tests -t .'` | **`Ran 416 tests` / `OK` / 退出码 0**（真机 checkout `88531d2`；Linux 上无 skip；`FAILED`/`ERROR:` 行 0 条，逐项无失败） |
| 全量离线测试（阶段 9 新版本） | 同上命令，真机 checkout `bc31c41` | **`Ran 422 tests` / `OK` / 退出码 0**（32.2s；`FAILED`/`ERROR:` 行 0 条、skip 0 条） |
| 沙箱真机验收 | `sudo -u bot bash -lc 'cd <bot-home>/app && .venv/bin/python scripts/verify_sandbox.py'` | **13 项全 PASS，失败 0 项**，退出码 0；`Tier A：PASS`、`Tier B：PASS`；阶段 8 验收（`88531d2`）与阶段 9 演练后在 `bc31c41` 上复跑结果一致，与阶段 7 `3347301` 相比无回归（该输出是 T6 之前的 13 项；in-tree 脚本自 `b41bff4` 起为 15 项，下次部署复跑对齐） |
| migration 4 真机检查 | 临时库上 `apply_migrations` + `PRAGMA user_version` + `sqlite_master` | 加载/应用/`user_version` = 4；`tool_failures`、`idx_tool_failures_tool_time`、`idx_tool_failures_chat_time` 均存在；真机 `storage/bot.db` 尚未创建（Bot 未启动，属预期） |
| `host_info` Linux 实测 | bot 用户直调 `HostInfoTool`（默认全字段 + `fields` 选择） | cpu=2、memory=4105363456（= `/proc/meminfo` MemTotal）、disk_free=35596984320、python=`3.11.2`、uptime_s=68691（= `/proc/uptime`，非进程时长回退）；`fields` 选择生效；返回键恰为冻结五字段 |
| 证据日志 | 本机临时目录 `<本地临时目录>` 下的 `dsh_tests_vps_88531d2.log`（stdout）与 `dsh_verify_vps_88531d2.log`（13 项逐项输出）；VPS 上未落盘日志文件 | 验收执行后容器数 0、`storage/sandbox` 为空、`storage/workspaces` 仅 `999001`/`999002` |
| 环境复核 | `.venv/bin/python -V`；bot 用户 `podman images` | Python 3.11.2；镜像仍只有 `python:3.12-slim`（未重新 pull）；无 `bot` 用户 python 进程 |
| 历史记录（阶段 7） | 同上两条命令，真机 checkout `3347301` | `Ran 293 tests` / `OK`；沙箱 13 项全 PASS（保留在 git 历史中，判读口径相同） |
| 验收时间 | 2026-10-07（VPS 时间） | — |

Tier A 7/7：纯计算、非 root（UID 1002）、无网络、只读根、单文件大小上限（fsize 8388608）、资源上限（memory 268435456 / pids 64 / cpu 50000-100000）、超时被 kill 且容器已销毁。
Tier B 4/4：本群 workspace 读写（非 root）、宿主侧可见、其他群不可见、宿主目录不可见。收尾 2 项：执行后无残留容器、临时输出目录已清理。

**判读注意（技术债 T7 已于 `4ea2326` 修复；上表是该修复前的真机输出）**：修复前「无网络」「只读根」只看退出码非零，区分不出「容器没起来 / 解释器缺失」，且 `Tier A：PASS` 只聚合 1 项。修复后脚本要求探针标记（`PROBE net`/`PROBE rofs`）与预期错误签名同时出现，`Tier A`/`Tier B` 按显式 tier 归属聚合全部相关检查项（含 2 项全局清理检查），任一项 FAIL 都会翻转结论；逐项输出带 `[A]`/`[B]`/`[AB]` 标记。判定逻辑由 `tests/offline/test_verify_sandbox.py` 离线覆盖（见 `docs/deployment.md` §12.6）；**真机复跑安排在下一次部署/里程碑时**（届时脚本为 T6 之后的 15 项：新增能力集 `CapBnd`=0 与提权位 `NoNewPrivs`=1 两项检查）。

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

本阶段明确未做：容器托管（`Dockerfile`/`compose.yaml`，可选路径）、正式远端（GitHub）、任何架构重构；T25 关键路径补测（`6b93fd6`）、T7 验收脚本判定口径（`4ea2326`）与 T9 repo 写入事务边界（`1826d89`）、T4 容器运行时退出码（`d59a703`）已在阶段 9 之后补做；备份/恢复与更新回滚演练已在同阶段补齐（见 §4.4）。

### 4.4 阶段 9 备份/恢复与更新/回滚演练（2026-10-07，真机实测）

演练在 Bot **在线**的情况下进行；备份与恢复都在副本上操作，现有 `storage/bot.db` 未被替换。演练用的坏版本是本地一次性分支 `stage9-broken-probe`（`7474c42`，只加 4 行「模拟新版本启动失败」，**永不合并进 `main`**），已随 bundle 传到真机以便复现。

| 检查 | 命令/手段 | 结果 |
|---|---|---|
| 在线备份 | `sudo -u bot bash -lc 'cd <bot-home>/app && .venv/bin/python scripts/backup_db.py'`（Bot 未停机） | 快照 `storage/backups/bot.db.20261007-2051`（118784 字节）；输出 `user_version=4 integrity=ok chat_settings=0 messages=2 notes=0 stickers=0 summaries=1 tool_failures=0 updates=2 usage=2`；同目录另有 `bot.db.20261007-2046`；`sidecar_files=0`（快照是单文件，无 `-wal`/`-shm`） |
| 快照可重复 | 两轮备份后比对 SHA256 | 同一份快照两轮 `49735a608bd3f739bd028ad129a150546f9efcfaf9134f7c832b63606c6faef0` 一致 |
| 恢复出独立数据库 | 以 `bot` 复制快照到 `/tmp/dsh_restore_probe/bot.db`（118784，`bot:bot`；**必须以 bot 身份**，否则 WAL 切换报 `attempt to write a readonly database`） | 只读探针：`user_version`=4、8 表行数与线上逐项一致、`integrity`=ok、`first_user`/`last_assistant` 原文一致 → `IDENTICAL=yes`（与线上对照 diff 为空） |
| 恢复库可被应用层打开 | `PYTHONPATH=. DB_PATH=<副本> .venv/bin/python /tmp/dsh_appcheck.py`（走 `load_settings()`+`open_db`+`apply_migrations`） | `app_open_ok db_path=/tmp/dsh_restore_probe/bot.db migrations_version=4 messages=2` |
| 演练不影响运行中的 Bot | 演练前后 `systemctl --user show` 与 `health.json` | `MainPID=48310 NRestarts=0 active/running` 前后一致；`checked_at` 1791377465.213371 → 1791377525.241856（60 秒心跳继续推进，`uptime_s` 300.07→360.10）；日志 `warn_error_traceback=0` |
| 更新到新版本 | 按 `docs/deployment.md` §8.1 用 bundle 把 `88531d2`（上一可工作版本）更新到 `bc31c41` | HEAD `bc31c41`、`dirty=0`、跟踪文件 132→135；日志 `配置加载完成`→`Bot 就绪`→`沙箱状态`→`启动完成`；`MainPID=48310 NRestarts=0 ExecMainStatus=0 active/running`；`bot.db` 行数与演练前完全一致、`integrity`=ok；`workspaces/` 未变 |
| 坏版本启动失败可检出 | 部署 `7474c42`（见上行同流程） | `MainPID=0 Result=exit-code NRestarts=1 ExecMainStatus=1 ActiveState=activating SubState=auto-restart`；日志两条 `ERROR app.main 阶段 9 更新演练：模拟新版本启动失败`（发生在 `配置加载完成` 之后、`Bot 就绪` 之前）；无存活 `app.main` 进程；`Restart=always` 在自动重试 |
| 回滚到上一版本 | `stop` + `reset-failed` → `git checkout 88531d2` → `start` | `MainPID=48739 Result=success NRestarts=0 ExecMainStatus=0 active/running`；日志 `Bot 就绪`/`启动完成`；`user_version`=4、8 表行数与演练前完全一致、`integrity`=ok、`workspaces/` 仍为 `999001 999002` |
| 演练后回到好版本 | 再次按 §8.1 部署 `bc31c41` | HEAD `bc31c41`、`dirty=0`、跟踪文件 135；`MainPID=48814 NRestarts=0 ExecMainStatus=0 active/running`；`health.json` `ok=true`；`storage/backups/` 两份快照仍在；日志 `warn_error_traceback=2`（＝演练故意注入的 2 条 ERROR，属预期） |
| Telegram 连通性（演练后） | bot 用户 `Bot.get_me()`（只打印 username/id） | `getMe ok username=<bot-username> id=<bot-id>` |
| 无 Secret 泄漏 | 对 `storage/logs/bot.log` 做形状扫描（只报计数） | `telegram_token_like=0`、`api_key_like=0`、`[redacted]` 标记 15 处；`.env` = `600 bot:bot` 997 字节，`git ls-files .env` 未跟踪 |
| bundle 持久化 | 把两个 bundle 复制到 Bot 用户持久目录并重指 `origin` | `<bot-home>/bundles/dsh_deploy_88531d2.bundle`（334645 字节）、`dsh_deploy_bc31c41.bundle`（351723 字节）；`origin` = 后者，`git fetch origin` 成功、`git branch -r` 见 `origin/main` 与 `origin/stage9-broken-probe`；`git bundle verify` = `complete history` |

演练结论：备份可恢复、恢复库可读且与线上一致、更新成功、坏版本失败可检出并可回滚、回滚后 Bot 恢复 `active`、`bot.db` 与 workspace 全程未丢、日志与错误消息无 Secret。

### 4.5 首次真实使用观察与修复（2026-10-07，真机 `bc31c41`）

用户在真实群（`chat_id` `<group-chat-id>`）使用后按只读方式核对（Bot 未改动）：`updates` 30、`messages` 56（user 29 / assistant 27）、`usage` 32（chat 29 次 `43976 in / 4547 out`；summary 3 次 `2372 / 821`）、`summaries` 3、`chat_settings` 0、`stickers` **0**、`tool_failures` **2**；日志 WARNING/ERROR 仅上次演练故意注入的 2 条；`health.json` `ok=true`。

- **发现**：`tool_failures` 两条 `('send_sticker', <group-chat-id>, 'not_found')`。原因是 `allow_sticker` 默认开、而本群贴纸库为空 → `send_sticker` 每次匹配必然 `not_found`，模型想发表情就白花一轮工具调用，并污染 `/stats` 的错误率。
- **修复 `bafe096`**（独立 commit，5 个代码/测试文件 + `docs/security.md` + `docs/tools.md`）：`ToolContext` 新增 `stickers_available`（默认 `true`）；runner 每轮在 `profile.stickers` 为真时查一次本群贴纸（economy 短路不多查）；`Policy._advertised` 只从**下发清单**剔除 `send_sticker`——`check()`/执行路径的 `permission_denied`/`not_found` 契约不变（库为空时模型仍硬调依旧是 `not_found`）。不引入缓存/后台任务。
- **本机验证**：`Ran 425 tests` / `OK (skipped=2)` / 退出码 0；新增 3 条测试（三种下发组合 + 空库端到端只调一轮模型 + 有贴纸时重新下发）。
- **真机同步与复验（2026-10-07 22:07）**：按 `docs/deployment.md` §8.1 用 bundle 把真机从 `bc31c41` 更新到 `26e946d`（代码内容 = `bafe096`），停机 ≈8 秒（`收到信号` 22:07:23 → `启动完成` 22:07:31），`dirty=0`、跟踪文件 135、`origin` 重指 `<bot-home>/bundles/dsh_deploy_bafe096.bundle`、`.env` 的 sha256 前后一致（未改真实凭据、未改 systemd/DB 结构/备份策略），`MainPID=50510 NRestarts=0 ExecMainStatus=0 active/running`。真机复验（真实代码路径 + 生产库）：生产库 + 真实群（`stickers` 0 行）时 `allowed_names`/`api_tools` 均无 `send_sticker`（`calc`/`read_file`）且 `check()` 仍为 `None`（执行契约未破）；线上库副本注册 1 张贴纸后 `send_sticker` 重新出现在两处清单；副本 `allow_sticker=0` 时不下发且 `check()`=`permission_denied`。真机直接相关测试 `Ran 65 tests` / OK（`test_policy`/`test_pipeline`/`test_modes`）。`tool_failures` 仍只有修复前 2 条 `send_sticker/not_found`（无新增）、`bot.log` 无新 WARNING/ERROR（`warn_error_traceback=2` 为阶段 9 演练故意注入）、`health.json` `ok=true`/`db_ok=true`/`outbound_pending=0`、无沙箱容器残留。**真实消息复验（2026-10-07 22:19）**：用户在真实群发一条消息（`messages.id=59`）→ Bot 22:19:34 回复（`messages.id=60`），`usage` 第 35 行 `purpose=chat`（input 1451 / output 214）**`tool_calls=0`**，即模型没有再白花一轮贴纸调用；`tool_failures` 仍是修复前那 2 条（无新增 `send_sticker/not_found`），`health.json.last_update_at` 由 `null` 推进为非空，`bot.log` 无新 WARNING/ERROR。

### 4.6 群宠体验升级真机上线与验收（2026-10-08，真机 `30cc3fe`）

**范围**：主动接话（三条弱触发 + 人类中心）、DeepSeek 大肥鱼 Persona、多 Bot 同群防误触、贴纸 catalog 与 104 张完整导入、`/clear`、群级人设覆盖、`/note`、模型档位路由、链式工具轮次分档等本机已封板内容一次性上线；未改 systemd 结构、未改 DB 结构（`user_version` 仍 4）、未改真实 `.env` 中任何已有 Secret。

- **部署**：按 `docs/deployment.md` §8.1 的 bundle + SSH 流程。第一次部署 `1a723fa`（群宠体验升级 + 其基线记录），第二次部署 `30cc3fe`（104 槽 catalog + 文档），第三次部署本批文档基线提交（本节上线与验收记录；bundle 按该次提交短哈希命名）。前两次之后均未重启进程（后两次只含运维数据与文档），因此 `MainPID` 与 `started_at` 保持不变。部署前保留回滚点 `<bot-home>/rollback-26e946d/`（旧版本 `bot.db` 副本 + `HEAD.txt` = `26e946d`）；真机 `origin` 重指本批 bundle；`.env` 只补 `BOT_ALIASES=DeepSeek,大肥鱼,深蓝大肥鱼,鲸鱼娘`、`PROACTIVE_TOPIC_MAX_MESSAGES=8`、`PROACTIVE_QUIET_MESSAGES=20`（键数 22，仍 `600`/`bot:bot`，原有 19 个键的值未被读取、未被改写）。
- **重启与运行状态**（2026-10-08 01:01:08）：`ActiveState=active`、`SubState=running`、`NRestarts=0`、`ExecMainStatus=0`；`storage/health.json` `ok=true`/`db_ok=true`/`outbound_pending=0`；`bot.log` = `配置加载完成` → `Bot 就绪 username=<bot-username> bot_id=<bot-id> model=deepseek-flash` → `沙箱后端就绪 backend=podman version=podman version 4.3.1 workspace=True keep_id=True` → `启动完成`，无 `ERROR`/`Traceback`；部署后 `bot.db` 行数与 sha256 与部署前一致（部署本身未触碰数据）。**文档基线部署后复查**：`MainPID=52755` 未变（`started_at` 仍为 01:01:08，即未重启）、`NRestarts=0`、`health.json` `ok=true`/`db_ok=true`/`outbound_pending=0`/`uptime_s≈1800`，真机 `git rev-parse HEAD` 等于该次 bundle 提交、`git status --porcelain` 为空、跟踪文件 156、提交数 66。
- **群消息接收前提**：`getChatMember(chat_id, bot_id)` 返回 `status=administrator` ⇒ 走「Bot 是群管理员」这条路径，普通群消息会到达进程；未关 Privacy Mode、未用代码绕过接收限制。
- **贴纸完整导入**：来源为公开 Telegram 包 `deepseek_whale_girl`（与 GitHub `DejavuMoe/deepseek_wale_girl` 同源，MIT © 2026 Dejavu Moe，104 张 512×512 透明 VP9 WebM），因此**无需下载与重新上传素材**，`deploy/stickers/assets/` 保持为空且仍被 `.gitignore`。真机先 `--dry-run`（`贴纸包 deepseek_whale_girl：共 104 张，匹配 104 个槽位，包内未使用 0 张`、`[dry-run] 未写库`）再正式导入：`已登记 chat_id=<group-chat-id> 条目=104 新增=104 更新=0`；第二次导入 `新增=0 更新=104` ⇒ **幂等**。导入后 `stickers` = 104 行 / 104 个 `file_unique_id` / 104 个 `file_id`，`tags` 无空值、`valence ∈ (-0.8, 0.9)`、`arousal ∈ (0.1, 0.9)`，`last_used_at` 全为 NULL（尚未发出）；导入过程不写 `messages`（行数未变）。**被排除的素材**：候选的其它社区来源因「许可未核实」未被采用（未下载、未入库），无来源不明/许可不清/损坏/格式不符的素材进入生产库。
- **真实发送（不允许只看数据库）**：在真机上跑真实组件图（receive → gate → debounce → agent loop → outbound，真实生产库 + 真实 Telegram API）：点名轮「大肥鱼，发个贴纸给我看看」真实发出贴纸并投递文本；随后 6 种情绪逐个真实投递成功（`开心得意`→id 88、`难过哭`→79、`生气`→5、`可爱抱抱`→19、`疑惑`→83、`困`→10；两两之间真等 31 秒以尊重真实 30 秒群内冷却，不注入时钟），加上此前两轮共 8 张贴纸被真实使用；全程无 `not_found`、无新的 `tool_failures`（仍为 2 条，即 `bafe096` 之前空贴纸库遗留的 `send_sticker/not_found`）。
- **主动接话真实结果**：未被点名的 `刚上线就崩了，我破防了` → `TriggerDecision(verdict='respond', reason='emotion', proactive=True)` → 真实投递回复（`摸鱼这块本大肥鱼有发言权——摸得过分不算事……不过上线就崩那是真难受，抱一下。`）；紧接其后的 `今天摸鱼摸得有点过分`（在 20 秒冷却内）→ `wait/cooldown`，**批次为空、不回复**；纯噪声 `哈哈哈哈` → 不回复（0 次模型调用）。
- **多 Bot 防误触**：`is_bot_author=True` 且被点名的消息 → `ignore/bot_author`，既不入批次、不进模型、也不占主动冷却额度；人类消息随后仍能正常触发（上一行已证明），Bot 不会因为别的 Bot 说话而永久沉默。
- **Persona 真实表现**：真机部署版 `GLOBAL_PERSONA` 与 `docs/persona.md` §4 逐字一致（8 行，含「知道自己是 AI」「不把自己当成真实的鱼」）。真机提问「大肥鱼，你是不是真的鱼？你是不是 AI 呀？」→ 真实回复：`不是真鱼，是 AI。这点我从来不装——大肥鱼这个蓝圆球只是网友给我画的皮，里面是 DeepSeek 家的。所以你对着我许愿要吃鱼是不会成的，但算个数、翻个文件、陪你唠两句还是排得上的。` —— 自我定位、蓝圆球是二创形象、能力边界（工具/权限）都没有被人设带偏。
- **工具与权限边界**：同一脚本打印 `allowed_names`：库中有贴纸时 = `('calc', 'read_file', 'send_sticker')`，库为空时 = `('calc', 'read_file')` ⇒ 「空库不下发 `send_sticker`」的修复在真机仍然成立；群设置 `allow_sticker=1`、`allow_write=0`、`allow_code=0`、`sticker_cooldown=30` 与回显一致；`send_sticker` 的匹配/冷却/`mark_used` 核心逻辑未改。
- **基础回归（真实命令通道，真实群主 `<owner-user-id>`）**：`/health` → `状态：正常 / 实例：default / 数据库：可读 / 出站队列：0 条待发`；`/stats` → `模型调用：9 次 / Token：22254 / 工具调用 3 次、失败 0 次 / 配额：未设置限额`；`/settings` → 模式 `normal` + 七个工具开关 + `贴纸冷却：30 秒` + `人设覆盖：未设置`（三条命令的回复都真实投递到群里）。数据库 `user_version=4`、`chat_settings`/`messages`/`notes`(+fts)/`stickers`/`summaries`(+fts)/`tool_failures`/`updates`/`usage` 齐全，`summaries=5`、`notes=0` ⇒ 记忆/摘要通路未被本批改动破坏；`health.json` `ok=true`/`db_ok=true`。
- **验证方法的边界（如实记录）**：真机验证用真实组件图 + 合成 `IncomingMessage`（因为无法向已运行进程注入更新），除「消息如何进入」之外全部走生产代码与生产库；所有回复与贴纸都是真实 Telegram 消息。验证过程中出现的两次失败都是探针自身的问题（`debouncer.pending_chats` 被当作方法调用、合成 `message_id` 不是真实消息导致 Telegram 拒绝对该消息回复），**不是产品缺陷**，修的是探针。
- **结论**：本批升级在真机可用，`tool_failures` 无新增、`health` 正常、无发现真实缺陷，因此**未改任何产品代码**（本批对仓库的改动只有贴纸 catalog 数据与文档）。

### 4.7 真实使用反馈修正（2026-10-08，真机 `172ab6b`）

**范围**：按用户本轮 5 条反馈修正——① 清污生产库（删探针合成行）、② 群回复长度上限 ≈280 字、③ 用户操作别的 Bot 时本 Bot 不插嘴（含不发贴纸）、④ 指令可发现（`/help` + 菜单）、⑤ 人设自我认识（知道自己的感知边界与「谁能操作我」）；**未批准**把被回复消息原文喂给模型（用户答复「先看我前一个」）。未改 systemd 结构、未改 DB 结构（`user_version` 仍 4）、未改真实 `.env` 中任何已有 Secret（`REPLY_MAX_CHARS` 未配置，走默认 280）。

- **生产库清污**（方案 1；备份 `storage/backup/bot.db.bak-20261008-014850`，用 `sqlite3.Connection.backup` 做的一致性快照）：BEFORE `messages=89`（其中探针合成 `user_id=42` 14 行）/ `updates=65` / `usage=47`（探针 5 行）/ `summaries=5`（含被摘要器吃进去的探针原文）/ `stickers=104` / `tool_failures=2` → AFTER `messages=75`（全为真实群主 `<owner-user-id>`，`probe42=0`）/ `updates=51`（全真实）/ `usage=42` / `summaries=0`（按真实消息重新生成，重启前已自增到 1 行）/ `stickers=104` / `tool_failures=2`（保留，未删）。**过程中发生的错误与修复（如实记录）**：删除探针 update 的条件写成 `update_id>=900000`，而真实 Telegram `update_id` 是 9 位数（`457943832`–`457943882`），结果把 51 条真实行一起删了；随即用上述备份按 `update_id > 1000000` 复原（`REAL_ROWS 51`、`PROBE_ROWS 14`、`PROBE_IDS (900001, 930012)`、`LIVE_UPDATES 51`、`LIVE_PROBE_LEFT 0`）。教训：按数值区间删行前必须先看 `MIN`/`MAX` 分布；`updates` 只是 48 小时去重缓存，清空只影响 Telegram 重放保护，不影响业务数据。
- **代码改动**（`172ab6b6e814eca3fc9fcf582bc6743c48f7dd42`，67 提交 / 跟踪文件 156 / 工作树干净）：`app/config.py` 新增 `REPLY_MAX_CHARS`（默认 280，0 = 不限）→ `app/llm/prompts.py` 的 `length_rule()` + `fit_reply()` 把约束写进输出规则段并在超长时按句末裁剪 → `app/session/context.py`/`runner.py` 让提示词、出站消息、入库文本用同一份裁剪结果；`app/telegram/parse.py` 新增 `reply_to_other_bot`（`IncomingMessage` 不携带被回复正文，只看作者是不是 Bot）→ `app/gate/trigger.py` 对「人类回复另一个 Bot」默认 `ignore/other_bot_reply`，只有强触发（@ / 回复本 Bot / 叫别名）才回应；`app/ops/commands.py` 新增公开 `/help` 与 `BOT_COMMANDS`，`/settings` 无参末尾提示「指令：/help 查看全部指令」；`app/main.py` 启动时 `set_my_commands` 注册菜单（失败只降级为没有菜单，不挡启动）；`GLOBAL_PERSONA` 重写为 10 行（感知边界 + 谁能操作我 + 群主/管理员权限边界）。
- **部署**：按 `docs/deployment.md` §8.1 的 bundle 流程。bundle `dsh_deploy_172ab6b.bundle`（sha256 `b08be1c55f2c6181401dd90661c96edb7f1b62db8fd440ff82b5e301e209c78a`，两端 `sha256sum` 一致），真机 `git bundle verify` 通过 → `git fetch` → `git remote set-url origin <bot-home>/bundles/dsh_deploy_172ab6b.bundle` → `git checkout 172ab6b`；真机 `git rev-parse HEAD` = 该提交、`git status --porcelain` 为空、提交数 67、跟踪文件 156。**本次含产品代码改动，因此按要求重启**：`2026-10-08 01:58:02` 收到 SIGTERM（`收到信号 signum=15` → `已关闭`）→ `01:58:08` `启动完成`，停机约 6 秒。
- **重启后运行状态**：`ActiveState=active`、`SubState=running`、`MainPID=54668`、`NRestarts=0`、`ExecMainStatus=0`；`storage/health.json` `ok=true`/`db_ok=true`/`outbound_pending=0`；`bot.log` 启动序列 `配置加载完成`（已含新配置项，`BOT_TOKEN`/`LLM_API_KEY` 仍被脱敏）→ `Bot 就绪 username=<bot-username> bot_id=<bot-id> model=deepseek-flash` → `沙箱后端就绪` → `启动完成`，无 `Traceback`；全文 `WARNING|ERROR` 仍只有阶段 9 演练故意注入的 2 条（第 48、50 行），**无新增**。
- **数据不动**：重启前后 `user_version=4`、`messages=75`、`updates=51`、`usage=43`、`summaries=1`、`stickers=104`、`tool_failures=2`（仍是修复前那两条 `send_sticker/not_found` `1791380630`/`1791380646`，无新增）、`probe42=0`；`chat_settings` 为空表 ⇒ 该群走 schema 默认值（`mode=normal`、`allow_sticker=1`、`sticker_cooldown=30`、写/代码/主机信息默认关），与 §4.6 观测一致。真实 `messages` 作者只有群主 `<owner-user-id>`（75 条）⇒ 探针污染已清除干净。
- **真机验证（真实 API + 真实代码 + 生产库只读）**：① `getMyCommands` 真实 Telegram API 返回 6 条菜单 `help/settings/note/stats/health/clear`，描述与本机 `BOT_COMMANDS` 逐字一致；② 用真机 venv（`<bot-home>/app/.venv/bin/python`）加载真实 `.env` 跑部署版代码：`reply_max_chars=280`、输出规则段含「280 字以内」、`fit_reply("甲"*200+"。"+"乙"*200)` → 201 字且以 `。` 结尾、`GLOBAL_PERSONA` 10 行、`help_text()` 覆盖全部 6 个指令；③ 真机定向离线测试 `python -m unittest tests.offline.test_gate tests.offline.test_prompts tests.offline.test_commands tests.offline.test_pipeline` → `Ran 188 tests` / `OK`；④ 全过程只读生产库（查询以 `file:…?mode=ro` 打开，回放类检查用副本，**未再向生产库写入任何合成行**）。
- **验证方法的边界（如实记录）**：真机无法向已运行进程注入真实 Telegram 更新，因此「人类回复另一个 Bot → `ignore/other_bot_reply`」这条规则由离线测试（新增 5 条，含端到端 1 条：不调用模型、不出站、照常入库）与真机定向测试共同证明，尚未在真实群里由真人回复别的 Bot 覆核；`/help` 的群内真实回执由用户下一条消息自然触发（菜单已注册、进程已带新代码）。
- **结论**：5 条反馈对应的改动已上线真机并验证通过，无发现真实缺陷；`tool_failures` 无新增、`health` 正常、数据未被本次操作弄丢（含一次误删后的完整复原）。

### 4.8 回复目标唯一修复（2026-10-08，真机 `50b4159`）

**范围**：用户要求「每次回复只响应当前触发消息；被跳过的消息视为已跳过，之后不补答，也不一次回好几条旧消息」。程序侧原本已满足（出站 `reply_to_message_id` 恒为本轮批次最后一条，`app/session/runner.py`），缺口是模型侧没有该约束，故本批只改提示词与文档，**无契约变更**（未动工具 schema / DB / 权限表 / 出站限流），也未改 `GLOBAL_PERSONA`（`docs/persona.md` §4 与该常量有逐字一致断言）。

- **代码与文档**（`50b4159de81dc87b40ea5711a068d98ee4035878`，68 提交 / 跟踪文件 156）：`app/llm/prompts.py` 的 `OUTPUT_RULES` 新增两句（只回应当前触发消息、历史只用于理解语义、跳过即 pass、不补答/不顺带回答/不一次回多条，连发只挑一条、通常最后一条），位置在「插不上话就不要说话」句与 `NO_REPLY` 句之间；`docs/requirements.md` §2.1 新增第 9–13 条（含「今天天气不错（未回）→ 你在干嘛？（触发）→ 只回你在干嘛？」正反例）、判定顺序与 F 表新增 `F2.13`（P1）。
- **测试**：本机 `Ran 647 tests` / `OK (skipped=2)` / 退出码 0（643 → 647，新增 4 条，明细见 §3）；定向 `tests.offline.test_prompts tests.offline.test_pipeline` → `Ran 80 tests` / `OK`。
- **部署**：按 `docs/deployment.md` §8.1 的 bundle 流程。bundle `dsh_deploy_50b4159.bundle`（sha256 `8f034527772f5ac49a04420e1686307442f4ab160ec2a00eccfb371094ba2194`，两端 `sha256sum` 一致），真机 `git bundle verify` 通过 → `git fetch … main:refs/remotes/origin/main` → `git remote set-url origin <bot-home>/bundles/dsh_deploy_50b4159.bundle` → `git checkout 50b4159`；真机 `git rev-parse --short HEAD` = `50b4159`、`git status --porcelain` 为空、跟踪文件 156。**本次含产品代码（提示词）改动，因此按要求重启**：`2026-10-08 17:13:46` 收到 SIGTERM（`收到信号 signum=15` → `已关闭`）→ `17:13:52` `启动完成`，停机约 6 秒。
- **重启后运行状态**：`ActiveState=active`、`SubState=running`、`MainPID=64443`、`NRestarts=0`、`ExecMainStatus=0`；`storage/health.json` `ok=true`/`db_ok=true`/`outbound_pending=0`；`bot.log` 启动序列 `配置加载完成`（`BOT_TOKEN`/`LLM_API_KEY` 仍被脱敏）→ `Bot 就绪 username=<bot-username> bot_id=<bot-id> model=deepseek-flash` → `沙箱后端就绪 backend=podman version=4.3.1 workspace=True keep_id=True` → `启动完成`，重启后无新增 `Traceback`/`WARNING`/`ERROR`（日志全文 179 行，4 处 `Traceback` 位于第 106/122/131/147 行，均早于本次启动序列）。
- **数据不动**：重启前后 `user_version=4`、`messages=159`、`updates=231`、`usage=81`、`summaries=8`、`stickers=104` 完全一致（生产库以 `file:…?mode=ro` 只读打开，未写入任何合成行）。
- **真机定向验证**：用真机 venv 跑部署版代码 `python -m unittest tests.offline.test_prompts tests.offline.test_pipeline` → `Ran 80 tests` / `OK`；`app.llm.prompts.OUTPUT_RULES` 含「当前触发你的那条消息」（`rule_present=ok`）。
- **GitHub 远端**：本批起项目正式远端为 GitHub 公开仓库 `youwmaoo-hub/groupbuddy`（本机 `origin`，`main` 已推送且与本机基线一致）；真机侧暂无 GitHub 凭据（`<bot-home>/.ssh` 不存在），真机 `origin` 仍是 Bot 用户持久目录里的 bundle，待配置部署密钥后再切换。
- **验证方法的边界（如实记录）**：真机无法向已运行进程注入真实 Telegram 更新，「跳过的消息不再补答」在真实群里的观感需用户后续自然对话确认；本批已由离线端到端用例（旧消息只作背景、`reply_to_message_id` = 本轮最新消息）与真机定向测试共同证明。
- **结论**：修复已上线真机并验证通过，`health` 正常、数据前后一致、无新增错误。

### 4.9 开源化（2026-10-08，`92755c3`）

**范围**：按用户要求把项目转为开源——仓库由私有改为公开、补齐开源必需文件、把文档里的实例标识换成占位符、删除账号下另外两个公共仓库。**不改运行期行为**（只动文档、模板与占位符；`scripts/backup_db.py` 只改了 docstring 里的示例路径）。

- **许可**：`LICENSE` = MIT，© 2026 youwmaoo-hub（用户选定）。
- **新增文件（10 个）**：`README.md`（定位、能力、快速开始、离线测试、部署、目录结构、文档地图、安全与隐私、许可）、`CONTRIBUTING.md`（`AGENTS.md` 摘要：开工顺序、硬规则、测试纪律、文档纪律、PR 要求、许可）、`SECURITY.md`（支持范围、GitHub 私密漏洞报告入口、在/不在范围内、部署者须知）、`CHANGELOG.md`（Keep a Changelog 形式，按阶段与提交汇总到 0.1.0）、`.github/workflows/tests.yml`（ubuntu-latest + Python 3.13：装依赖 → `compileall` → `unittest discover` → 校验 `.env`/数据库/素材未入库）、`.github/ISSUE_TEMPLATE/{bug_report.yml,feature_request.yml,config.yml}`、`.github/PULL_REQUEST_TEMPLATE.md`（要求写清验证命令、证据来源、契约与文档同步、脱敏确认）。
- **标识占位符化**（`git grep` 复核后 tracked 文件里已无真实标识）：`docs/status.md` 中 bot 用户名 ×4 → `<bot-username>`、bot id ×4 → `<bot-id>`、真实群主 user id ×3 → `<owner-user-id>`、真实群 id ×3 → `<group-chat-id>`、VPS 主机名 ×1 → `<vps-host>`、`/home/bot` ×29 → `<bot-home>`；`TODO.md` ×2、`docs/deployment.md` ×1、`scripts/backup_db.py`（docstring 示例）×2 同样替换；`GitHub 私有仓库` ×5 → `GitHub 公开仓库`。**未改动两份原始需求文件** `优化与前言.txt`、`流程与要求.txt`（`AGENTS.md` §14 禁止修改；已检查其中只有 `chat_id` 语义说明与 `-100123456` 这类示例 id，无真实凭据与真实 id）。
- **仓库设置与清理**：`gh repo edit` 更新简介并加 topics（telegram-bot / telegram / aiogram / python / llm / sqlite / sqlite-fts5 / podman / sandbox / self-hosted / chatbot）、可见性由 private 改为 public；删除账号下另外两个公共仓库 `tideline-gesture-field`（自建）与 `hypit`（fork）。（推送后确认：`gh repo view` → `visibility=PUBLIC`、`licenseInfo=MIT License`、11 个 topics、简介生效；`gh repo list youwmaoo-hub` 只剩 `groupbuddy`，两个删除命令均 exit 0，见 §4.10。）
- **验证**：本机 `Ran 647 tests` / `OK (skipped=2)`（本批只有文档与模板，测试数字不变）；tracked 文件中无真实用户名/id/群 id/主机名/`/home/bot`，也无 `.env`、`storage/`、`*.db`、贴纸素材。本机无法执行 GitHub Actions，CI 首次运行结果见 §4.10。
- **边界**：本批不改 `app/` 行为、**未上真机**，真机仍 @ `50b4159`（见 §4.8）——与本机在这一批上不是同一棵树，差异只有文档/模板/占位符；真机要跟进需按 `docs/deployment.md` §8.1 再走一次部署。

### 4.10 开源化推送确认（2026-10-08，本文件所在提交）

**范围**：把 §4.9 的开源化改动推送到 GitHub 并确认仓库设置生效；**不改代码、不动真机**。

- **推送**：`git push origin main` → `387467d..92755c3  main -> main`（exit 0）；`git ls-remote origin refs/heads/main` = `92755c3646981c0181b0d7bec2f630ef51ee115c` = 本地 `git rev-parse HEAD`；本机 `git status --porcelain` 为空，跟踪文件 166、提交数 71。
- **仓库设置**：`gh repo edit youwmaoo-hub/groupbuddy --visibility public --accept-visibility-change-consequences` + 简介 + 11 个 topics（exit 0）；`gh repo view --json visibility,licenseInfo,repositoryTopics,description` → `visibility=PUBLIC`、`licenseInfo=MIT License`、topics 11 个、简介生效。
- **旧仓库清理**：`gh repo delete youwmaoo-hub/tideline-gesture-field --yes` 与 `gh repo delete youwmaoo-hub/hypit --yes` 均 exit 0；`gh repo list youwmaoo-hub --json name,visibility,isFork` 现只剩 `groupbuddy`（PUBLIC、`isFork=false`）。
- **CI 首次运行**：`.github/workflows/tests.yml` 在 `92755c3` 上跑通——`gh run list` → `tests | completed | success`，run `37760925291`（`https://github.com/youwmaoo-hub/groupbuddy/actions/runs/37760925291`）；步骤为 ubuntu-latest + Python 3.13：依赖安装 → `compileall` → `unittest discover` 全绿。本机无法执行 Actions，故此为唯一来源。
- **真机状态（未动，只读复查）**：`groupbuddy.service` `ActiveState=active`、`SubState=running`、`MainPID=64443`、`NRestarts=0`、`ExecMainStatus=0`；`storage/health.json` → `ok=true`、`db_ok=true`、`outbound_pending=0`、`uptime_s≈3000`；`<bot-home>/app` 侧 `HEAD=50b4159`、`dirty=0`、`origin=<bot-home>/bundles/dsh_deploy_50b4159.bundle`。本批只改文档与模板，未重新部署，故真机仍停在 `50b4159`。
- **边界**：不改 `app/` 运行期行为；真机与本机在文档/模板层面相差两个提交（`92755c3` 与本次确认提交），功能代码完全一致。真机要切到 GitHub 远端仍需先配只读部署密钥（见 §4.8、§5）。

### 4.11 默认接话改造（2026-10-08，本机；真机未部署）

- **范围**：用户要求"群里大部分能接话的消息都回"，同时保留限制。改动只动发言判定、合并与输出规则，不新增依赖、不改数据库、不改权限与出站契约。
- **代码**：
  - `app/gate/trigger.py`：强触发（`mention`/`reply_to_bot`/`alias`）之后依次过重复过滤与冷却，通过即 RESPOND；弱规则（疑问/报错/资源/追问/话题/情绪/安静后开场）只决定原因码，都没命中落新增的 `general` 兜底；删除"沉默词表"`not_addressed` 与 `quota`。
  - `app/gate/limits.py`：`ProactiveLimiter` 只保留冷却（默认 20 秒）；新增 `RepeatGuard`（同一人同一句话在 `DUPLICATE_WINDOW_SECONDS` 默认 300 秒内只接第一次，去空白 + 大小写归一），原因码 `repeat`。
  - `app/config.py`：`DEBOUNCE_SECONDS`/`DEBOUNCE_MAX_MESSAGES` 默认改为 `0`/`1`（连发不合并）；删除 `PROACTIVE_WINDOW_SECONDS`、`PROACTIVE_MAX_PER_WINDOW`；新增 `DUPLICATE_WINDOW_SECONDS`。
  - `app/llm/prompts.py` + `app/session/runner.py`：输出规则写明"这条消息已经通过筛选、轮到你了：默认就接一句"，`NO_REPLY` 收窄到纯符号/纯链接/纯转发媒体；首轮 `NO_REPLY` 时追加一句"必须回"的追问重跑一次（只多一次调用，仍记 usage）。
  - 人设（`GLOBAL_PERSONA` 与 `docs/persona.md` §4 逐字一致）：去掉"没人点名你、你也插不上话时就不说话"，改为"接话自然一点，别硬凑话题、也别句句卖萌"。
- **测试（本机 Windows + `.venv` Python 3.13 + 离线 FakeBackend）**：`Ran 656 tests` / `OK (skipped=2)`（647 → 656，新增 15 条、改写 6 条，明细见 §3）；定向 `tests.offline.test_pipeline/test_prompts/test_gate/test_limits` → `Ran 136 tests` / `OK`。
- **文档**：`docs/requirements.md` §2.1（规则 2/3/8/10/13 + 判定顺序表 13 行 + 三条闸门说明）、F2.2–F2.11 验收口径；`docs/architecture.md` §2 表格与运行期行为；`docs/token.md` §3 链 1；`docs/deployment.md` §3 主动接话；`docs/persona.md` §3/§4/§5；`docs/security.md` §12；`README.md`、`docs/README.md` 路由表、`TODO.md` 阶段 2、`CHANGELOG.md`（Unreleased）、`.env.example`。
- **兼容性**：`.env` 里保留已删除的 `PROACTIVE_WINDOW_SECONDS`/`PROACTIVE_MAX_PER_WINDOW` 会被静默忽略（未知键走默认值），真机 `.env` 不需要改也能启动；反之不设 `DUPLICATE_WINDOW_SECONDS` 走默认 300 秒。
- **边界（必须如实区分）**：**只在真机之外验证**——本机 Windows、离线 fake 模型与 fake 发送器；**未部署真机**，真机仍停在 `50b4159`，所以"是否过于话痨""真实群里的观感"这类结论暂无真机证据；改的是运行期行为（发言判定与 prompt），下一次真机部署必须连同一次真实收发冒烟，并按 `docs/deployment.md` §8.1 备好回滚。
- **结论**：默认接话已在本机实现并全绿；是否上线、要不要顺手把真机切到 GitHub 远端，留给用户决定（见 §5）。

## 5. 尚未做 / 尚未上线（重要）

- **默认接话改造已完成、未上真机（2026-10-08，`39687b4` + 本文件所在提交）**：发言策略、重复过滤、合并默认关闭、输出规则与人设措辞都已改完并本机全绿（见 §4.11）；真机仍 @ `50b4159`，部署后需在真实群里看清观感再决定是否调 `PROACTIVE_COOLDOWN_SECONDS`/`DUPLICATE_WINDOW_SECONDS`。
- **开源化已完成（2026-10-08，`5b14ab0`）**：仓库公开（`youwmaoo-hub/groupbuddy`，MIT）、开源文件与 CI/Issue/PR 模板就位、文档标识已占位符化、两个旧公共仓库已删除（见 §4.9）；遗留：GitHub Actions 首次运行已通过（`92755c3`，run `37760925291`，见 §4.10）；真机仍在 `50b4159`（差异仅文档与模板，不影响运行）。
- **回复目标唯一修复已上线真机（2026-10-08，`50b4159`）**：每轮只响应当前触发消息、被跳过的消息不再补答已部署并验证（见 §4.8）；本机 `main` 与真机同一棵树（本机多一条本文件基线提交）。
- **真实使用反馈修正已上线真机（2026-10-08，`172ab6b`）**：回复长度上限、别人的 Bot 对话不插嘴、`/help` 与指令菜单、人设自我认识均已部署并验证（见 §4.7）；本机 `main` 与真机为同一棵树。
- **群宠体验升级已上线真机（2026-10-08，`30cc3fe`）**：主动接话 / Persona / 多 Bot 防误触 / 104 槽贴纸 catalog 与完整导入均已部署并真机验收（证据见 §4.6），本机 `main` 与真机现为同一棵树；本批未改产品代码。

- **Bot 已在真机 24/7 运行**：systemd 用户级单元 `groupbuddy.service`（`Restart=always`、`RestartSec=5`，配合 `Linger=yes` 开机自启），真机证据见 §4.3，部署契约见 `docs/deployment.md` §12.9。
- **真实 `.env` 已就位**：`<bot-home>/app/.env`（`600`、`bot:bot`，只写覆盖项，绝对路径）；仓库内仍只有 `.env.example`，本文件与所有文档都不记录任何凭据值。
- **正式远端已配置（2026-10-08）**：项目 `origin` = GitHub 公开仓库 `youwmaoo-hub/groupbuddy`，`main` 已推送且与本机基线一致（见 §4.8）；真机侧仍通过 git bundle + SSH 同步（bundle 在 Bot 用户持久目录，真机 `origin` = `<bot-home>/bundles/dsh_deploy_50b4159.bundle`），真机暂无 GitHub 凭据（`<bot-home>/.ssh` 不存在），待配置部署密钥后再把真机 `origin` 切到 GitHub。
- 备份/恢复与更新/回滚演练已完成（见 §4.4）；**仍未实现**：程序内自动备份任务与 `BACKUP_INTERVAL_SECONDS`/`BACKUP_KEEP` 环境键（当前只能手工跑 `scripts/backup_db.py`）、体积膨胀时的 `VACUUM`（离线手工）、容器托管（`Dockerfile`/`compose.yaml`，可选路径）。`PRAGMA optimize` 已例行化（`29f6687`：每 7 天一次，契约见 `docs/database.md` §5、`docs/architecture.md` §5）。
- 阶段 8 内明确留到后续的项：**均已实施**——链 3 的工具轮次按意图分档（已于 `a5bf651` 实施：闲聊 1 轮、其余沿用全局 `TOOL_MAX_ROUNDS`，见 §3 与 `docs/token.md` §5.2）、模型档位路由（已于 `e26ea3c` 实施，见 §3 与 `docs/token.md` §5.1）。原留后项 `/clear` 已补做（`8b14aab`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）），群级人设 Persona 已实现（`c29ecac`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）），长期笔记 `/note` 已实现（`495389b`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）；记忆体验优化的第一项，见 `docs/memory.md` §6），工具体验优化修复 T31（`e1dcb6a`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）：工具清单逐轮重取，本轮被禁用的工具不再下发给模型），关键路径补测 T25（`6b93fd6`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）：只新增测试与文档，不改运行期行为，因此不影响真机运行），验收脚本判定口径 T7（`4ea2326`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）：只改 `scripts/verify_sandbox.py` 的判定与 4 条离线测试 + 文档，不影响 Bot 运行期行为；真机复跑安排在下一次部署/里程碑），repo 写入事务边界 T9（`1826d89`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）：**这条改变了运行期写入路径**（repo 不再自己 `commit()`，改由 `app/storage/tx.py` 的 SAVEPOINT 事务提交），因此下一次真机部署必须连同一次真实收发冒烟一起复验，并按 `docs/deployment.md` §8.1 备好回滚），阶段 9 小优化 `PRAGMA optimize`（`29f6687`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）：housekeeping 每 7 天多执行一条 `PRAGMA optimize`，失败只记日志不影响循环；随下一次批量部署一起上），容器运行时保留退出码 T4（`d59a703`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）：**这条改变了运行期行为**——容器以 125/126/127 退出时不再把 argv 结果当工具结果返回，而是回 `execution_failed` 并销毁容器，部署后建议真机补一次 `run_code` 冒烟；随下一次批量部署一起上），验收脚本能力/提权覆盖 T6 与贴纸时间口径 T10（`b41bff4`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）：T6 只改 `scripts/verify_sandbox.py` 与离线测试、不影响运行期行为，按 §4.2 下次部署复跑 15 项；**T10 改运行期写入值**——`stickers.last_used_at` 由进程相对秒改为 Unix 秒（冷却仍用 `time.monotonic`），部署后首次 `send_sticker` 即写入 Unix 秒；两项随下一次批量部署一起上），模型档位路由（`e26ea3c`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）：新增配置键 `LLM_MODEL_STRONG` 与 `app/llm/routing.py`，**该键留空时行为与成本与升级前完全一致**——真机 `.env` 现在没有这个键，所以不同步也不会改变真机运行期行为；要启用需在真机 `.env` 增键，属部署决策，随下一次批量部署一起上），群宠体验升级（`ba7afe1`，本机；已随本批部署同步真机（2026-10-08，见 §4.6）：**这条改变了运行期行为与提示词**——主动接话新增三条弱触发（同话题 / 情绪反应 / 久静后开场，冷却 20 秒与每 300 秒 3 次的上限不变，全部纯规则 0 token）、内置 Persona 换成「DeepSeek 大肥鱼」群宠定位、其他 Bot 的消息在判定入口直接 `ignore` 且不占冷却与额度；贴纸 catalog 与两个导入脚本属运维侧、不改运行期执行路径，但真机要按情绪取到贴纸仍需先按 `deploy/stickers/README.md` 导入素材（空库时 `send_sticker` 仍不下发，`bafe096` 语义不变）。部署时另注意两点：①真机 `.env` 的 `BOT_ALIASES` 建议显式配置（如 `DeepSeek,大肥鱼,深蓝大肥鱼,鲸鱼娘`），不要写 `bot` 这类通用词，否则 `@其他bot` 会被当成叫本 Bot；②Telegram 侧需关掉 Privacy Mode 或把 Bot 设为群管理员，否则普通群消息根本到不了进程、主动接话不生效（`docs/deployment.md` §12.10）。随下一次批量部署一起上）。
- **模型档位路由：已实施（`e26ea3c`，2026-10-07）**：唯一入口 `app/llm/routing.py::ModelRouter.choose(*, intent, purpose)`——默认档 = `LLM_MODEL`（现为 `deepseek-flash`），升级档 = `LLM_MODEL_STRONG`（留空或与默认同名即视为未配置，不改路由），只有 `purpose=chat` 且 `intent=complex` 且有升级档时才换模型；summary / 后台任务继续走默认档且 purpose 不变；复杂判定仍沿用既有的纯规则（代码块 / 单条 ≥400 字 / 链接 / 指代检索需求），不新增独立分类器、不增加额外一次 LLM 判断、不引入依赖；选择过程抛错即 fail-safe 回默认档；路由发生在配额判定之后，不绕过 quota / tool policy / sandbox / 权限；`usage` 记最终实际使用的 model（`purpose=chat`）。成本影响：`LLM_MODEL_STRONG` 留空时与升级前完全一致；填了之后只有复杂轮换模型，且缓存按模型隔离，升级轮可能按未命中价计费。评估背景（2026-10-07）：真实使用成本 < $0.01（§4.5：29 次 chat 调用 ≈ 44k 输入 / 4.5k 输出、观察到的轮次 `tool_calls=0`），没有复杂轮次质量不足的证据，所以默认不配置升级档；唯一可用方向是把复杂轮次升级到 `deepseek-v4-pro`（提高花费换质量），其价格与可得性未核实，属部署决策。**链 3 轮次分档：已实施（`a5bf651`，2026-10-07）**——同一入口 `app/llm/routing.py::tool_round_limit(intent, settings)`：只把全局 `TOOL_MAX_ROUNDS`（默认 2，可选 0–4）调低，闲聊 1 轮（原表写 0 轮，但 0 轮会连贴纸工具一起关掉，故取 1 轮）、复杂任务与无法判断仍用全局上限（部署方设 4 即对应表里的「代码调试 4 轮」）；未登记意图与异常输入一律回全局上限，分档不会突破部署方设置。契约与评估结论见 `docs/requirements.md` 未决问题 #2、`docs/token.md` §5/§5.1/§5.2、`docs/architecture.md` §3/§7。
- 未引入 CI、lint、类型检查、锁文件（见 `TODO.md` T27）。

## 6. 技术债摘要

完整清单（T1–T31，含等级与 `文件:行号`）在 `TODO.md` §技术债与已知缺陷。`f7f34b5` 已修复其中 3 条，阶段 8 F5.2（`7382639`）追加修复 1 条，F5.4（`101c26c`）追加修复 1 条，工具体验优化（`e1dcb6a`）追加修复 1 条（T31），关键路径补测（`6b93fd6`）补上 1 条（T25，只加测试），验收脚本判定口径（`4ea2326`）修复 1 条（T7），repo 写入事务边界（`1826d89`）修复 1 条（T9），容器运行时保留退出码（`d59a703`）修复 1 条（T4）：

- **T1（P0，已修复）**：摘要「静默 ≥120 秒」触发恒不成立（`time.monotonic()` 与 Unix 秒比较）——记忆能力静默退化。
- **T2（P0，已修复）**：迁移无事务 + `ALTER TABLE` 不幂等——迁移中途失败会让 Bot **永久无法启动**。
- **T3（P1，已修复）**：本轮消息在超出字符预算时被 history 裁剪丢弃。
- **T12（P1，已修复，`7382639`）**：`chat_settings.upsert` 先读再写，并发下会丢更新（群主命令即将把设置写入变成热路径）——改为单条原子 `INSERT … ON CONFLICT DO UPDATE`，只写调用方给出的列；离线测试用 `mock` 断言 upsert 不再读取当前设置。
- **T15（P1，已修复，`101c26c`）**：`tool_failures` 表缺失，`/stats` 无失败数据源——migration 4 建表 + 两个索引，计入熔断的失败（超时 / 工具错误 / 未预期异常）经 `failure_recorder` 留痕，启动时与每小时清理 7 天前的行；调用前拒绝（`permission_denied` / `invalid_arguments` / `cooldown`）不入表。
- **T31（P1，已修复，`e1dcb6a`）**：工具清单在本轮内被快照（`app/llm/loop.py:89`）——第 1 轮取一次后，后续轮次仍下发「本轮已禁用/已熔断」的工具，模型可能再次调用只可能返回 `cooldown` 的工具，白花一整轮模型调用与 token；与 `docs/tools.md` §1、`docs/security.md` §9 的「本轮从可用清单移除」及 F4.8 验收「失败工具不再重复调用」不符。修复：每一轮重新取清单（清单为空即不带工具、强制给答案），`cooldown` 文案改用 `BreakerConfig.round_failures` 而不是写死 2。发现路径：工具体验优化（代码 + 契约证据；同类浪费在真实使用中已由 `send_sticker` 空库双失败暴露过一次）。
- **T4（P1，已修复，`d59a703`）**：容器运行时以保留退出码 125/126/127（CLI 自身失败 / 容器内命令不可执行 / 命令不存在）退出时，`runner.py` 原样把 argv 的退出码当工具结果返回，「容器没起来」与「程序正常失败」不可区分（阶段 7 首次真机验收的 `--workdir /workspace` 事故正是由此漏报）。修法：`app/sandbox/backends.py` 新增 `CLI_FAILURE_EXIT_CODES = frozenset({125, 126, 127})`，`runner.py` 在超时判定之后、读输出之前按该集合抛 `SandboxError("execution_failed", …)` 并销毁容器；这三个码由 podman/docker 保留、无法与「程序自己 `exit 125/126/127`」区分，属已知取舍（错误文案提示改用其他退出码）。离线回归 2 条（见 §3），契约同步 `docs/tools.md` §2 `run_code` 与 §3 错误码表。**注意：这条改变了运行期行为**，真机需随下一次部署复验。
- **T9（P1，已修复，`1826d89`）**：各 repo 自己 `commit()`、无 `rollback`（`summaries.py:65,136`、`notes.py:48`、`stickers.py:73,90` 等 14 处），主表 + FTS 的多语句写可能半提交，或被执行其他任务的写入时顺带提交。修法：新增 `app/storage/tx.py` 的 `transaction()`（`SAVEPOINT` … `RELEASE` / `ROLLBACK TO`，因为整进程共享一条连接、`BEGIN` 会与之冲突），14 个写入入口全部改为在事务内完成并去掉自己的 `commit()`；主表与 FTS 要么一起生效要么一起回滚。离线回归 10 条（见 §3），契约同步 `docs/database.md` §6 与 `docs/architecture.md` 模块表。**注意：这条改变了运行期写入路径**，真机需随下一次部署复验。
- **T25（P1，已补测，`6b93fd6`）**：`app/main.py`、`app/logging_setup.py`、`app/telegram/handlers.py`、`app/telegram/sender.py` 零测试，`CliBackend.run` 与 `DeepSeekClient` 类体从未执行，`SecretFilter` 无测试——A1–A3 修复期间正是这个缺口让 `app/main.py` 缺 `import time` 的装配缺陷躲过全部离线测试。补法：只加测试（45 条，见 §3），不改产品代码；契约文档同步 `docs/architecture.md` §8 与 `docs/decisions/0006-credentials-not-in-git.md`。

- **T10（P1，已修复，`b41bff4`）**：`stickers.last_used_at` 写 `time.monotonic()`（进程相对秒），与 `docs/database.md` §1「统一 Unix 秒」冲突，重启后「优先未近期使用」的 tie-break 语义反转。修法：`SendStickerTool` 拆成两个时钟——群内冷却仍用 `time.monotonic`（不落库），落库改 `wall_clock`（默认 `time.time`）写 Unix 秒；`docs/database.md` §1 的偏差条移除（旧值只可能残留在本机开发库，数值比 Unix 秒小、仍被当作「很久没用过」）。离线回归 1 条 + 更新 1 条（见 §3）。**注意：这条改变了运行期写入值**，真机需随下一次部署复验。
- **T6（P2，已修复，`b41bff4`）**：`--cap-drop=ALL` 与 `no-new-privileges` 只有 `app/sandbox/spec.py:68-70` 的实现，`scripts/verify_sandbox.py` 没有任何验收项（安全契约只能靠人工读代码保证）。修法：新增两项 Tier A 检查，直接读容器内 `/proc/self/status`（不依赖 `capsh` 之类镜像里可能没有的工具）——`CapBnd`（bounding set）必须为 0（容器内是非 root，`CapEff` 本来就是 0，不作断言）、`NoNewPrivs` 必须为 1，字段缺失即 FAIL；脚本 13 → 15 项，判读口径同步 `docs/deployment.md` §12.6 与 `docs/security.md` §4，负路径由 `tests/offline/test_verify_sandbox.py` 覆盖。只改验收脚本与测试，不影响运行期行为；真机需在下一次部署时复跑对齐。
- B 组技术债当前没有未修复项：原先最严重的两项已于 `b41bff4` 一并修复（T6 验收覆盖、T10 时间口径，明细见上两条）。（关键路径零覆盖 T25 已于 `6b93fd6` 补测：`app/main.py`、`app/logging_setup.py`、`app/telegram/handlers.py`、`app/telegram/sender.py`、`CliBackend.run` 与 `DeepSeekClient`；验收脚本判定口径 T7 已于 `4ea2326` 修复：负向断言要求探针标记与错误签名，`Tier A`/`Tier B` 按显式归属聚合；repo 层无事务边界 T9 已于 `1826d89` 修复：写入统一走 `app/storage/tx.py`，失败整体回滚，不再有半提交；CLI 非零退出不映射 `execution_failed`（T4）已于 `d59a703` 修复：容器以 125/126/127 退出时回 `execution_failed` 并销毁容器；验收脚本 T6 于 `b41bff4` 加上能力集（`CapBnd`=0）与提权位（`NoNewPrivs`=1）两项检查（13 → 15 项）；贴纸 `last_used_at`（T10）于 `b41bff4` 改由 `wall_clock`（`time.time`）写 Unix 秒，冷却仍用 `time.monotonic`。）

其余分类：安全与沙箱（T4–T8）、数据与记忆（T9–T16）、工具契约（T17–T20）、代码质量（T21–T24）、测试与工程（T25–T30）。

## 7. 下一步

0. **当前批处理路线（用户 2026-10-07 指定，按序推进）**：真实使用反馈 → `/clear`（已完成，`8b14aab`）→ Persona（群级配置，**已完成，`c29ecac`**）→ **记忆体验优化（里程碑 B，进行中：第一项长期笔记 `/note` 已补做 `495389b`——填上 `docs/memory.md` §6 一直标注「尚未实现」的写入路径；其余候选按真实使用证据再评估）** → 工具体验优化（**已完成，`e1dcb6a`**：修复 T31 工具清单逐轮重取；其余候选（工具数量、新基础设施）无真实证据，未自造）→ 模型档位路由（**已完成，`e26ea3c`**：最小规则型路由，默认档 `LLM_MODEL`、可选升级档 `LLM_MODEL_STRONG`，见 `docs/token.md` §5.1）→ 链式工具轮次优化（**已完成，`a5bf651`**：按意图分档，闲聊 1 轮——原表 0 轮会连贴纸工具一起关掉，故取 1 轮；其余沿用全局上限 `TOOL_MAX_ROUNDS`，见 `docs/token.md` §5.2）→ Stage 10.0 服务层接口预留（`docs/domain.md`/`docs/architecture.md` §10 已预留，无冻结接口规格，属产品设计）→ B 组技术债（T25 关键路径补测已完成 `6b93fd6`，只加测试；T7 验收脚本判定口径已修 `4ea2326`，含 4 条离线测试与文档；T9 repo 写入事务边界已修 `1826d89`，含 10 条离线测试与契约同步；T4 容器运行时保留退出码已修 `d59a703`，含 2 条离线测试与 `docs/tools.md` 契约同步；T6 验收脚本能力/提权覆盖与 T10 贴纸 Unix 秒已修 `b41bff4`，含 1 + 1 条离线测试与 `docs/deployment.md`/`docs/security.md`/`docs/database.md` 契约同步）→ 阶段 9 小优化（`PRAGMA optimize` 已例行化 `29f6687`，含 4 条离线测试；`BACKUP_*` 属部署契约变化、正式 remote 需用户确认，未做）→ 群宠体验升级（**已完成并已真机上线，`ba7afe1` + 贴纸 catalog `30cc3fe`**：主动接话三条弱触发 + 人类中心、DeepSeek 大肥鱼 Persona、贴纸 catalog 与批量导入；契约见 `docs/requirements.md` §2.1 与 F2.8–F2.11、`docs/persona.md`、`deploy/stickers/README.md`）→ **下一项：Stage 10.0 服务层接口预留**（模型档位路由已由 `e26ea3c` 完成、链式工具轮次优化已由 `a5bf651` 完成、群宠体验升级已由 `ba7afe1` 完成；T10/T6 完成后不再自动寻找新技术债，按用户最近的批处理指令执行）。原则：已有真实反馈优先处理，无真实证据的新需求不自造；低风险可回滚的决定自行完成并记录。里程碑 A（`/clear` + Persona）已完成；该路线的模块形态统一为「Telegram adapter → `app/ops/` 规则入口 → repo」，Persona 与 `/note` 都按此落地，后续工具 UX 沿用同一形态。
1. **阶段 8 已全部完成并通过真机验收**（真机 `88531d2`：416 条全量 OK、沙箱 13 项全 PASS、migration 4 与 `host_info` Linux 行为符合契约）：F5.2（管理员判定 + 命令通道 + T12）、F5.1（`/settings <字段> <值>` 写入、即时生效）、F5.3（日/月配额）、F5.4（`/stats` + `/health`，`tool_failures` 留痕与 7 天清理，与 `storage/health.json` 同一内部状态）、F4.7（`host_info`：`cpu`/`memory`/`disk_free`/`python`/`uptime_s`，L4 + `allow_host_info` 默认关）与四模式（`78ae9cf`：窗口 / 输出上限 / 工具档位，`docs/token.md` §5）。阶段 8 内明确留到后续的**两项均已实施**：链 3 轮次分档（`a5bf651`）与模型档位路由（已于 `e26ea3c` 实施，见 `docs/token.md` §5.1/§5.2；`/clear` 已于 `8b14aab` 补做，群级人设 Persona 已由 `c29ecac` 补做）。
2. **阶段 9（部署与 24/7）进行中**：最小生产闭环已完成并真机验证（systemd 用户级单元、真实 `.env`、启动时 migration、health 心跳、Telegram 真机收发、stop/start/restart 与 `SIGKILL` 自动重启，见 §4.3）；备份/恢复与更新/回滚演练已通过（`scripts/backup_db.py`、`docs/deployment.md` §8.1，证据见 §4.4），真机当前已同步到本机 `main`（`30cc3fe` + 本批文档基线提交，群宠体验升级 + 104 槽贴纸已上线并真机验收，见 §4.6）。首次真实使用发现的空贴纸库问题已在真机同步并复验（见 §4.5）。阶段 9 未完成部分：程序内自动备份任务与 `BACKUP_*` 环境键、体积膨胀时的 `VACUUM`（离线手工）、容器托管（可选路径）；`PRAGMA optimize` 已在 `29f6687` 随 housekeeping 按周执行。
3. B 组技术债已全部修复，不再需要立项（T6 / T10 随 `b41bff4`；T1–T3 已随 `f7f34b5`、T12 已随 `7382639`、T15 已随 `101c26c`、T25 已随 `6b93fd6`、T7 已随 `4ea2326`、T9 已随 `1826d89`、T4 已随 `d59a703`）；剩余 P2 项（T5 stderr 清洗、T8 `resolve_path`、T11 迁移解析、T13 已由 `/note` 补上运行时写入路径、T14 `thread_id`、T16 纵深防御等）按真实证据再决定。
4. 是否配置正式远端（GitHub），以便后续换 Agent 维护。

## 8. 如何重新生成这些证据

```bash
# 本机（Windows，仓库根）
python -m unittest discover -s tests -t .

# 真机（Linux VPS，bot 用户；注意用单引号包住 bash -lc 的内容）
sudo -u bot bash -lc 'cd <bot-home>/app && .venv/bin/python -m unittest discover -s tests -t .'
sudo -u bot bash -lc 'cd <bot-home>/app && .venv/bin/python scripts/verify_sandbox.py'   # 需要容器运行时
```

生产托管（阶段 9，systemd 用户级单元；root 操作 bot 的 `--user` 实例必须显式给 `XDG_RUNTIME_DIR`）：

```bash
U=bot; R=/run/user/$(id -u "$U")
sudo -u "$U" env XDG_RUNTIME_DIR=$R systemctl --user is-enabled groupbuddy.service
sudo -u "$U" env XDG_RUNTIME_DIR=$R systemctl --user show -p MainPID -p NRestarts -p ActiveState -p ExecMainStartTimestamp groupbuddy.service
sudo -u "$U" env XDG_RUNTIME_DIR=$R systemctl --user start|stop|restart groupbuddy.service
cat <bot-home>/app/storage/health.json          # checked_at 每 60 秒推进
tail -n 20 <bot-home>/app/storage/logs/bot.log # 用户级 journalctl 在目标机无 journal 文件
```

代码同步（无正式远端时的临时通道，替换 `<sha>`）：

```bash
# 本机（部署用私钥与本地临时目录不入文档）
git bundle create <本地临时目录>/dsh_deploy_<sha>.bundle main
scp -i <部署用私钥> <本地临时目录>/dsh_deploy_<sha>.bundle root@<vps>:/tmp/

# 真机：确认 sha256 一致后
sha256sum /tmp/dsh_deploy_<sha>.bundle
sudo -u bot bash -lc 'cd <bot-home>/app && git bundle verify /tmp/dsh_deploy_<sha>.bundle \
  && git fetch /tmp/dsh_deploy_<sha>.bundle main:refs/remotes/origin/main \
  && git remote set-url origin /tmp/dsh_deploy_<sha>.bundle && git checkout <sha>'
```

备份与恢复（阶段 9；`<快照>` 取 `storage/backups/` 下最新一份）：

```bash
# 在线备份（Bot 不停机），输出 path/bytes/user_version/integrity/各表行数
sudo -u bot bash -lc 'cd <bot-home>/app && .venv/bin/python scripts/backup_db.py'

# 恢复演练：必须以 bot 身份复制（否则 WAL 切换报 attempt to write a readonly database），
# 且只对副本操作，不替换线上 bot.db
sudo -u bot mkdir -p /tmp/dsh_restore_probe
sudo -u bot cp <bot-home>/app/storage/backups/<快照> /tmp/dsh_restore_probe/bot.db
# 校验副本：用现有脚本对副本再做一次快照，输出的 bytes/user_version/integrity/各表行数即为副本实况
sudo -u bot bash -lc 'cd <bot-home>/app && .venv/bin/python scripts/backup_db.py --db /tmp/dsh_restore_probe/bot.db --dest /tmp/dsh_restore_probe/verify'
```

副本与线上逐项对照（`user_version`、8 表行数、`first_user`/`last_assistant` 片段）应完全一致（`IDENTICAL=yes`）；
应用层可读性用临时探针验证：`load_settings()` → `open_db()` → `apply_migrations()`（阶段 9 实测 `migrations_version=4`、`messages=2`），
探针脚本属一次性产物，不入库。

更新与回滚按 `docs/deployment.md` §8.1 五步执行；bundle 传到 `/tmp` 后建议复制到 Bot 用户持久目录并把 `origin` 指过去
（真机当前为 `<bot-home>/bundles/dsh_deploy_bc31c41.bundle`），这样后续 `git fetch` 不依赖 `/tmp`。

约束：`<bot-home>/app` 属主是 `bot`，root 直接执行 git 会报 `dubious ownership`，所有 git 操作必须经 `sudo -u bot bash -lc '…'`；
`podman images` / `podman ps` 必须在 `bot` 用户可读的目录（如 `<bot-home>/app`）里执行，否则会因 `cannot chdir to /root` 而失败；
**`bash -lc` 的内容必须用单引号，不要用双引号**：双引号会让外层 shell 先展开 `$(…)` / `$?` / `$HOME`，实测导致 `cd` 未生效（留在 `/root`，报 `.venv/bin/python: No such file or directory`）且重定向文件变成 root 所有（`bot` 再写就 `Permission denied`）；
`systemctl --user` 在 root 会话下必须带 `XDG_RUNTIME_DIR=/run/user/<uid>`（否则 `Failed to connect to bus: No medium found`），且**必须给单元名**（`systemctl --user is-active` 不带名字会报 `Too few arguments.`）。