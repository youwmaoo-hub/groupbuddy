# 当前状态（唯一事实来源）

负责：**当前基线**——commit、已完成阶段与能力、本机与真机测试结果、真机验收证据、技术债摘要、下一步。
上游：`docs/README.md` §2 路由表。
改动影响：本文件不是契约，只记录事实。契约在 `docs/requirements.md`、`docs/architecture.md`、`docs/security.md`、`docs/tools.md`、`docs/database.md`、`docs/deployment.md`。**每次提交、每次验收、每次阶段结束都要更新本文件**；其他文档不再各自维护「当前状态/进度/测试数字」，只指向这里（`AGENTS.md` §7、`TODO.md` §当前状态）。

## 1. 当前基线

| 项 | 值 |
|---|---|
| 代码 commit | `78ae9cff6f733f87ab5b0c63d6cc8d1294ff3b4e`（短 `78ae9cf`，分支 `main`；阶段 8 四模式代码 + 契约文档） |
| 跟踪文件数 | 132（`git ls-files`） |
| 提交数 | 28（阶段提交 + 文档治理 `b529741` + A1–A3 修复 `f7f34b5` + 文档同步 `3347301` + 部署记录 + 阶段 8 F5.2 `7382639` + F5.1 `c49fdc5` + F5.3 `1d649b8` + F5.4 `101c26c` + 基线 `ad560f4` + F4.7 `de73b57` + 四模式 `78ae9cf` + 四模式基线 `88531d2` + 本次真机验收记录） |
| 本机工作树 | 干净（`git status --porcelain` 无输出）；本机 `main` HEAD 在此验收之后只有一个纯文档记录提交（本次 `docs:` 提交），代码内容与真机 `88531d2` 一致 |
| 真机仓库 | `/home/bot/app` = detached HEAD @ `88531d2`（本次验收实际运行的 checkout；**代码内容 = 本机 `78ae9cf`**，与本机一致），工作树干净，属主 `bot:bot`，跟踪文件 132 |
| 真机远端 | `origin` = VPS `/tmp/dsh_deploy_88531d2.bundle`（文件存在，可 `git fetch`；仍未配置正式远端，未建 GitHub remote、未 push） |
| 运行时目录 | 真机 `storage/` 存在（本轮沙箱验收自动创建）：`logs/`、`sandbox/`、`workspaces/{999001,999002}` 均为空目录，属主 `bot:bot` |

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
| 8 | 已完成 | 权限/配额/运维：**群主命令最小闭环、群设定写入、日/月配额与运行指标**（`app/ops/admin.py` 管理员判定 + `/settings` 回显/写入 + `app/ops/quota.py` 配额判定 + `app/ops/metrics.py` `/stats` + `app/ops/health.py` `/health` 与 `storage/health.json` 同一状态，见 `docs/security.md` §2.1、`docs/token.md` §4.1、`docs/deployment.md` §7；F5.1/F5.2/F5.3/F5.4 + T12 + T15）；**F4.7 `host_info` 已实现**（`app/tools/builtin/host_info.py`，L4 + `allow_host_info` 默认关，见 `docs/tools.md` §host_info）；**token 四模式完整生效**（`app/modes.py` 唯一权威表：economy 10 条窗口 / 只 L0 / 256 输出 / 贴纸关；normal 意图分档 + 群开关；smart 50 条 + 额外 L0 只读；unrestricted 50 条 + 全部工具 + 输出不限；模式只由管理员 `/settings mode` 修改，见 `docs/token.md` §5、`docs/security.md` §2.2） |
| 9 / 10 | 未开始 | 部署与 24/7；控制面板与多实例（仅架构预留） |

## 3. 本机验证（Windows，开发环境）

- 解释器：Python 3.13.15（仓库内 `.venv`）；`openai 3.24.0`；**沙箱走 FakeBackend，不跑真实容器**。
- 命令：`python -m unittest discover -s tests -t .`
- 结果：`Ran 416 tests` / `OK (skipped=2)` / 退出码 0（293 原有 + 22 条 F5.2 + 11 条 F5.1 + 20 条 F5.3 + 32 条 F5.4 + 19 条 F4.7：`host_info` 冻结字段集与 schema、L4 默认关与群开关、不可得字段与 `/proc` 缺失回退、不泄露环境变量/主机名/路径；19 条四模式：档位表逐列、economy/smart/unrestricted 的工具档位、模式窗口与 normal 意图分档、输出上限透传，含 3 条端到端：`/settings mode` 改完立即影响下一条消息的输出上限与工具清单、smart 解锁只读工具、economy 与 smart 的历史窗口差异体现在发给模型的上下文里）。
- 2 条 skip 为平台条件跳过（Windows 上软/硬链接相关用例，见 `TODO.md` T28）。
- 覆盖缺口（已知）：`app/main.py`、`app/logging_setup.py`、`app/telegram/handlers.py`、`app/telegram/sender.py` 无测试（见 `TODO.md` T25）。

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
| 沙箱真机验收 | `sudo -u bot bash -lc 'cd /home/bot/app && .venv/bin/python scripts/verify_sandbox.py'` | **13 项全 PASS，失败 0 项**，退出码 0；`Tier A：PASS`、`Tier B：PASS`（`88531d2`；与阶段 7 `3347301` 相比无回归） |
| migration 4 真机检查 | 临时库上 `apply_migrations` + `PRAGMA user_version` + `sqlite_master` | 加载/应用/`user_version` = 4；`tool_failures`、`idx_tool_failures_tool_time`、`idx_tool_failures_chat_time` 均存在；真机 `storage/bot.db` 尚未创建（Bot 未启动，属预期） |
| `host_info` Linux 实测 | bot 用户直调 `HostInfoTool`（默认全字段 + `fields` 选择） | cpu=2、memory=4105363456（= `/proc/meminfo` MemTotal）、disk_free=35596984320、python=`3.11.2`、uptime_s=68691（= `/proc/uptime`，非进程时长回退）；`fields` 选择生效；返回键恰为冻结五字段 |
| 证据日志 | 本机临时目录 `<本地临时目录>` 下的 `dsh_tests_vps_88531d2.log`（stdout）与 `dsh_verify_vps_88531d2.log`（13 项逐项输出）；VPS 上未落盘日志文件 | 验收执行后容器数 0、`storage/sandbox` 为空、`storage/workspaces` 仅 `999001`/`999002` |
| 环境复核 | `.venv/bin/python -V`；bot 用户 `podman images` | Python 3.11.2；镜像仍只有 `python:3.12-slim`（未重新 pull）；无 `bot` 用户 python 进程 |
| 历史记录（阶段 7） | 同上两条命令，真机 checkout `3347301` | `Ran 293 tests` / `OK`；沙箱 13 项全 PASS（保留在 git 历史中，判读口径相同） |
| 验收时间 | 2026-10-07（VPS 时间） | — |

Tier A 7/7：纯计算、非 root（UID 1002）、无网络、只读根、单文件大小上限（fsize 8388608）、资源上限（memory 268435456 / pids 64 / cpu 50000-100000）、超时被 kill 且容器已销毁。
Tier B 4/4：本群 workspace 读写（非 root）、宿主侧可见、其他群不可见、宿主目录不可见。收尾 2 项：执行后无残留容器、临时输出目录已清理。

**判读注意（重要）**：`verify_sandbox.py` 的「无网络」「只读根」是期望非零退出的负向断言，任何非零退出都算 PASS，区分不出「容器没启动」；脚本正文的 `Tier A：PASS` 汇总只聚合 1 项。判读时必须看逐项输出与「合计 N 项，失败 M 项」（见 `docs/deployment.md` §12.6、`TODO.md` T7）。

## 5. 尚未做 / 尚未上线（重要）

- **Bot 未启动**：真机没有 `app.main` 进程、没有 systemd 单元、没有容器；阶段 7 只到「沙箱能力验收」。
- **没有真实 `.env`**：仓库只有 `.env.example`；本文件与所有文档都不记录任何凭据值。
- **未配置正式远端**：代码同步通过临时 git bundle + SSH 完成，`origin` 不可用。
- 备份/恢复任务、`PRAGMA optimize` / `VACUUM`、人群托管（systemd/容器 restart）：属阶段 8/9，尚未实现（阶段 8 已完成群主命令、群设定写入、配额、运行指标 `/stats`/`/health`、`host_info` 与四模式生效，见 §2）。
- 阶段 8 内明确留到后续的项：`/clear`（群主清理本群消息原文）、链 3 的工具轮次按意图分档（`TOOL_MAX_ROUNDS` 仍为全局 2）、模型档位路由（未决问题 #2）。
- 未引入 CI、lint、类型检查、锁文件（见 `TODO.md` T27）。

## 6. 技术债摘要

完整清单（T1–T30，含等级与 `文件:行号`）在 `TODO.md` §技术债与已知缺陷。`f7f34b5` 已修复其中 3 条，阶段 8 F5.2（`7382639`）追加修复 1 条，F5.4（`101c26c`）追加修复 1 条：

- **T1（P0，已修复）**：摘要「静默 ≥120 秒」触发恒不成立（`time.monotonic()` 与 Unix 秒比较）——记忆能力静默退化。
- **T2（P0，已修复）**：迁移无事务 + `ALTER TABLE` 不幂等——迁移中途失败会让 Bot **永久无法启动**。
- **T3（P1，已修复）**：本轮消息在超出字符预算时被 history 裁剪丢弃。
- **T12（P1，已修复，`7382639`）**：`chat_settings.upsert` 先读再写，并发下会丢更新（群主命令即将把设置写入变成热路径）——改为单条原子 `INSERT … ON CONFLICT DO UPDATE`，只写调用方给出的列；离线测试用 `mock` 断言 upsert 不再读取当前设置。
- **T15（P1，已修复，`101c26c`）**：`tool_failures` 表缺失，`/stats` 无失败数据源——migration 4 建表 + 两个索引，计入熔断的失败（超时 / 工具错误 / 未预期异常）经 `failure_recorder` 留痕，启动时与每小时清理 7 天前的行；调用前拒绝（`permission_denied` / `invalid_arguments` / `cooldown`）不入表。

当前最严重的是尚未修复的 B 组：repo 层无 `rollback`（T9）、`verify_sandbox.py` 判定口径弱（T7）、CLI 非零退出不映射 `execution_failed`（T4）、关键路径零覆盖（T25；A1–A3 期间发现的 `app/main.py` 装配缺陷印证了它的价值）。

其余分类：安全与沙箱（T4–T8）、数据与记忆（T9–T16）、工具契约（T17–T20）、代码质量（T21–T24）、测试与工程（T25–T30）。

## 7. 下一步

1. **阶段 8 已全部完成并通过真机验收**（真机 `88531d2`：416 条全量 OK、沙箱 13 项全 PASS、migration 4 与 `host_info` Linux 行为符合契约）：F5.2（管理员判定 + 命令通道 + T12）、F5.1（`/settings <字段> <值>` 写入、即时生效）、F5.3（日/月配额）、F5.4（`/stats` + `/health`，`tool_failures` 留痕与 7 天清理，与 `storage/health.json` 同一内部状态）、F4.7（`host_info`：`cpu`/`memory`/`disk_free`/`python`/`uptime_s`，L4 + `allow_host_info` 默认关）与四模式（`78ae9cf`：窗口 / 输出上限 / 工具档位，`docs/token.md` §5）。阶段 8 内明确留到后续的只有 `/clear`、链 3 轮次分档、模型档位路由。
2. 阶段 9（部署与 24/7 运行：`BOT_TOKEN` 落 `.env`、systemd/容器托管、备份恢复）需用户授权后开工；真机当前仍无 `.env`、未启动 Bot、未配 systemd。
3. 是否立项修 B 组技术债（`TODO.md` T4 / T7 / T9 / T10 / T25 等；T1–T3 已随 `f7f34b5`、T12 已随 `7382639`、T15 已随 `101c26c` 修复）。
4. 是否配置正式远端（GitHub），以便后续换 Agent 维护。

## 8. 如何重新生成这些证据

```bash
# 本机（Windows，仓库根）
python -m unittest discover -s tests -t .

# 真机（Linux VPS，bot 用户；注意用单引号包住 bash -lc 的内容）
sudo -u bot bash -lc 'cd /home/bot/app && .venv/bin/python -m unittest discover -s tests -t .'
sudo -u bot bash -lc 'cd /home/bot/app && .venv/bin/python scripts/verify_sandbox.py'   # 需要容器运行时
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

约束：`/home/bot/app` 属主是 `bot`，root 直接执行 git 会报 `dubious ownership`，所有 git 操作必须经 `sudo -u bot bash -lc '…'`；
`podman images` / `podman ps` 必须在 `bot` 用户可读的目录（如 `/home/bot/app`）里执行，否则会因 `cannot chdir to /root` 而失败；
**`bash -lc` 的内容必须用单引号，不要用双引号**：双引号会让外层 shell 先展开 `$(…)` / `$?` / `$HOME`，实测导致 `cd` 未生效（留在 `/root`，报 `.venv/bin/python: No such file or directory`）且重定向文件变成 root 所有（`bot` 再写就 `Permission denied`）。