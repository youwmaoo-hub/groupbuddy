# 当前状态（唯一事实来源）

负责：**当前基线**——commit、已完成阶段与能力、本机与真机测试结果、真机验收证据、技术债摘要、下一步。
上游：`docs/README.md` §2 路由表。
改动影响：本文件不是契约，只记录事实。契约在 `docs/requirements.md`、`docs/architecture.md`、`docs/security.md`、`docs/tools.md`、`docs/database.md`、`docs/deployment.md`。**每次提交、每次验收、每次阶段结束都要更新本文件**；其他文档不再各自维护「当前状态/进度/测试数字」，只指向这里（`AGENTS.md` §7、`TODO.md` §当前状态）。

## 1. 当前基线

| 项 | 值 |
|---|---|
| 代码 commit | `1d649b8b41d99c357e224245355496e1b8da55d4`（短 `1d649b8`，分支 `main`；阶段 8 F5.3 代码 + 契约文档） |
| 跟踪文件数 | 123（`git ls-files`） |
| 提交数 | 21（阶段提交 + 文档治理 `b529741` + A1–A3 修复 `f7f34b5` + 文档同步 `3347301` + 部署记录 + 阶段 8 F5.2 `7382639` + F5.1 `c49fdc5` + F5.3 `1d649b8` + 本次状态更新） |
| 本机工作树 | 干净（`git status --porcelain` 无输出） |
| 真机仓库 | `/home/bot/app` = detached HEAD @ `3347301`，工作树干净，属主 `bot:bot`；**代码基线落后于本机**：本机其后的 `07a9288`（部署记录，纯文档）与阶段 8 F5.2 提交均未上真机 |
| 真机远端 | `origin` = VPS `/tmp/dsh_deploy_3347301.bundle`（文件存在，可 `git fetch`；仍未配置正式远端，未建 GitHub remote、未 push） |
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
| 8 | 进行中 | 权限/配额/运维：**已完成群主命令最小闭环、群设定写入与日/月配额**（`app/ops/admin.py` 管理员判定 + `/settings` 回显/写入 + `app/ops/quota.py` 配额判定，见 `docs/security.md` §2.1 与 `docs/token.md` §4.1；F5.1/F5.2/F5.3 + T12）；`/stats`、`/health` + `health.json`、`host_info`、token 四模式生效待做 |
| 9 / 10 | 未开始 | 部署与 24/7；控制面板与多实例（仅架构预留） |

## 3. 本机验证（Windows，开发环境）

- 解释器：Python 3.13.15（仓库内 `.venv`）；`openai 3.24.0`；**沙箱走 FakeBackend，不跑真实容器**。
- 命令：`python -m unittest discover -s tests -t .`
- 结果：`Ran 346 tests` / `OK (skipped=2)` / 退出码 0（293 原有 + 22 条 F5.2 + 11 条 F5.1 + 20 条 F5.3：配额统计口径与拒绝边界、超额不调模型不记账、命令不消耗配额）。
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
| 全量离线测试 | `sudo -u bot bash -lc "cd /home/bot/app && .venv/bin/python -m unittest discover -s tests -t ."` | `Ran 293 tests` / `OK` / 退出码 0（Linux 上无 skip；对应真机 checkout `3347301`，含 A1–A3 的 10 条回归） |
| 沙箱真机验收 | `sudo -u bot bash -lc "cd /home/bot/app && .venv/bin/python scripts/verify_sandbox.py"` | **13 项全 PASS，失败 0 项**，退出码 0；`Tier A：PASS`、`Tier B：PASS`（对应真机 checkout `3347301`） |
| 证据日志 | 保留在 VPS `/tmp/dsh_tests_3347301.log`（43 行）、`/tmp/dsh_verify_3347301.log`（26 行） | 验收执行后容器数 0；`storage/sandbox` 与 `storage/workspaces/{999001,999002}` 已清空 |
| 环境复核 | `.venv/bin/python -V` | Python 3.11.2；`podman images` 只有 `python:3.12-slim`（未重新 pull） |
| 验收时间 | 2026-10-07（VPS 时间） | — |

Tier A 7/7：纯计算、非 root（UID 1002）、无网络、只读根、单文件大小上限（fsize 8388608）、资源上限（memory 268435456 / pids 64 / cpu 50000-100000）、超时被 kill 且容器已销毁。
Tier B 4/4：本群 workspace 读写（非 root）、宿主侧可见、其他群不可见、宿主目录不可见。收尾 2 项：执行后无残留容器、临时输出目录已清理。

**判读注意（重要）**：`verify_sandbox.py` 的「无网络」「只读根」是期望非零退出的负向断言，任何非零退出都算 PASS，区分不出「容器没启动」；脚本正文的 `Tier A：PASS` 汇总只聚合 1 项。判读时必须看逐项输出与「合计 N 项，失败 M 项」（见 `docs/deployment.md` §12.6、`TODO.md` T7）。

## 5. 尚未做 / 尚未上线（重要）

- **Bot 未启动**：真机没有 `app.main` 进程、没有 systemd 单元、没有容器；阶段 7 只到「沙箱能力验收」。
- **没有真实 `.env`**：仓库只有 `.env.example`；本文件与所有文档都不记录任何凭据值。
- **未配置正式远端**：代码同步通过临时 git bundle + SSH 完成，`origin` 不可用。
- 备份/恢复任务、`PRAGMA optimize` / `VACUUM`、`/stats`、`host_info`、健康检查 `/health` + `storage/health.json`、人群托管（systemd/容器 restart）：属阶段 8/9，尚未实现（阶段 8 已完成群主命令、群设定写入与配额，见 §2）。
- 未引入 CI、lint、类型检查、锁文件（见 `TODO.md` T27）。

## 6. 技术债摘要

完整清单（T1–T30，含等级与 `文件:行号`）在 `TODO.md` §技术债与已知缺陷。`f7f34b5` 已修复其中 3 条，阶段 8 F5.2（`7382639`）追加修复 1 条：

- **T1（P0，已修复）**：摘要「静默 ≥120 秒」触发恒不成立（`time.monotonic()` 与 Unix 秒比较）——记忆能力静默退化。
- **T2（P0，已修复）**：迁移无事务 + `ALTER TABLE` 不幂等——迁移中途失败会让 Bot **永久无法启动**。
- **T3（P1，已修复）**：本轮消息在超出字符预算时被 history 裁剪丢弃。
- **T12（P1，已修复，`7382639`）**：`chat_settings.upsert` 先读再写，并发下会丢更新（群主命令即将把设置写入变成热路径）——改为单条原子 `INSERT … ON CONFLICT DO UPDATE`，只写调用方给出的列；离线测试用 `mock` 断言 upsert 不再读取当前设置。

当前最严重的是尚未修复的 B 组：repo 层无 `rollback`（T9）、`verify_sandbox.py` 判定口径弱（T7）、CLI 非零退出不映射 `execution_failed`（T4）、关键路径零覆盖（T25；A1–A3 期间发现的 `app/main.py` 装配缺陷印证了它的价值）。

其余分类：安全与沙箱（T4–T8）、数据与记忆（T9–T16）、工具契约（T17–T20）、代码质量（T21–T24）、测试与工程（T25–T30）。

## 7. 下一步

1. **阶段 8（进行中）**：已完成 F5.2（管理员判定 + 命令通道 + T12）、F5.1（`/settings <字段> <值>` 写入、即时生效）与 F5.3（日/月配额：`QUOTA_DAILY_TOKENS` / `QUOTA_MONTHLY_TOKENS`，按 `chat_id` 统计，超额优雅拒绝）。下一项 = F5.4 `/stats` + `/health`（与 `storage/health.json` 同一内部状态）；随后 F4.7 `host_info`、`docs/token.md` §5 四模式（窗口/输出上限/工具档位的完整影响）。
2. 是否把阶段 8 提交（`7382639`、`c49fdc5`、`1d649b8`）同步到真机并在真机重跑测试（本机 346 条，真机仍为 `3347301` 的 293 条）。
3. 是否立项修 B 组技术债（`TODO.md` T4 / T7 / T9 / T10 / T25 等；T1–T3 已随 `f7f34b5`、T12 已随 `7382639` 修复）。
4. 是否配置正式远端（GitHub），以便后续换 Agent 维护。

## 8. 如何重新生成这些证据

```bash
# 本机（Windows，仓库根）
python -m unittest discover -s tests -t .

# 真机（Linux VPS，bot 用户）
sudo -u bot bash -lc "cd /home/bot/app && .venv/bin/python -m unittest discover -s tests -t ."
sudo -u bot bash -lc "cd /home/bot/app && .venv/bin/python scripts/verify_sandbox.py"   # 需要容器运行时
```

代码同步（无正式远端时的临时通道，替换 `<sha>`）：

```bash
# 本机（部署用私钥与本地临时目录不入文档）
git bundle create <本地临时目录>/dsh_deploy_<sha>.bundle main
scp -i <部署用私钥> <本地临时目录>/dsh_deploy_<sha>.bundle root@<vps>:/tmp/

# 真机：确认 sha256 一致后
sha256sum /tmp/dsh_deploy_<sha>.bundle
sudo -u bot bash -lc "cd /home/bot/app && git bundle verify /tmp/dsh_deploy_<sha>.bundle \
  && git fetch /tmp/dsh_deploy_<sha>.bundle main:refs/remotes/origin/main && git checkout <sha>"
```

约束：`/home/bot/app` 属主是 `bot`，root 直接执行 git 会报 `dubious ownership`，所有 git 操作必须经 `sudo -u bot bash -lc '…'`；
`podman images` / `podman ps` 必须在 `bot` 用户可读的目录（如 `/home/bot/app`）里执行，否则会因 `cannot chdir to /root` 而失败。