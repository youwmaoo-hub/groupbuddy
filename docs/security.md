# 安全边界

负责：信任边界、权限判定、路径/沙箱/网络/密钥/日志边界、429 与洪泛处置、租户隔离。
上游：`docs/requirements.md`；工具字段见 `docs/tools.md`。
改动影响：等级映射或沙箱参数变更属契约变更（见 `AGENTS.md` §5），需同步 `docs/tools.md`。

## 1. 信任边界

- **不可信**：群消息文本、用户提供的路径与文件内容、模型输出（含工具参数）、工具返回内容、网络搜索结果。
- **可信**：程序自身代码、`.env` 配置、SQLite 中的群设置、出站限速器。
- 结论：一切"是否允许"的判断都在程序内完成；模型只能提出请求。
- 生产部署后，**群里任何人都能通过 Bot 间接影响服务器**（群里任何人 → Bot → 模型 → 服务器）。
  因此权限、路径、沙箱、网络四道边界不得因为"人少、信任群成员"而放松。

## 2. 权限模型（唯一判定入口 `app/tools/policy.py`）

| 等级 | 工具 | 说明 |
|---|---|---|
| L0 | `calc`, `search_web` | 无副作用或只读外部公开信息 |
| L1 | `read_file` | 只读本群 workspace |
| L2 | `write_file`, `send_sticker` | 写本群 workspace / 向群里发内容 |
| L3 | `run_code` | 沙箱执行 |
| L4 | `host_info`、高权限联网 | 默认关闭 |

判定顺序（任一不通过即拒绝，返回 `permission_denied`）：
1. 工具是否在注册表中；
2. 该工具等级在**本群**是否开启（`chat_settings`）；
3. 触发者身份是否满足该等级要求（管理员/普通成员）；
4. 参数是否通过 schema 校验；
5. 进入执行（必要时含沙箱）。

等级 → 群开关（`chat_settings` 列；`calc` 无开关，始终可用）：

| 工具 | `calc` | `search_web` | `read_file` | `write_file` | `send_sticker` | `run_code` | `host_info` |
|---|---|---|---|---|---|---|---|
| 开关列 | — | `allow_search` | `allow_read` | `allow_write` | `allow_sticker` | `allow_code` | `allow_host_info` |

工具可用 = 已注册 ∩ 本群开关；未注册、或注册但未登记等级的工单一律拒绝（fail-closed）。第 3 步身份判定随阶段 8 的群主命令落地：阶段 3 只有 L0 工具。

系统提示（System3）只能注入**已裁剪**的工具清单；模型永远不能提升自己的权限。
- **授权只由后端判定**：前端隐藏按钮、前端参数、面板传入的身份都不构成授权；面板改设置走同一条判定（`docs/domain.md` §3）。

## 3. 工作区与路径

- 根目录：`storage/workspaces/<chat_id>/`（每群一个，绝不复用）。
- 解析规则：
  ```python
  base = Path("storage/workspaces") / str(chat_id)
  base.mkdir(parents=True, exist_ok=True)
  base = base.resolve()
  target = (base / user_path).resolve()
  if not target.is_relative_to(base): reject("path_outside_workspace")
  ```
- 拒绝符号链接与非常规文件（`is_symlink()`、非普通文件）；拒绝绝对路径、盘符、反斜杠与 `..`；硬链接（`st_nlink > 1`）一律拒绝。
- 模型只看得到 workspace 相对路径；日志、错误消息、上下文里都不出现宿主机绝对路径。
- 写入：存在则先复制为 `<name>.bak`（只保留一层，再次覆盖时更新它，不做历史版本链）；写临时文件 → `flush`+`fsync` → `os.replace` 原子替换；读、写单文件上限各 1 MB。
- 只处理 UTF-8 文本文件；解码失败按 `invalid_arguments` 拒绝，不处理二进制。
- 隔离要求：任何查询/写入都必须带 `chat_id` 条件或本群路径；跨群读取一律拒绝。

## 4. 沙箱（`run_code`）

容器运行时：Podman（rootless 优先）/ Docker，一次性容器，执行后销毁。实现在 `app/sandbox/`：
`spec.py` 是 argv 白名单的唯一拼装点，`backends.py` 只用 CLI（无 shell）调用运行时，
`runner.py` 是 `run_code` 的唯一执行入口，`preflight.py` 只做提示。
`SANDBOX_BACKEND=auto` 只在**启动阶段**探测一次并固定后端，运行期不再探测。固定参数：

| 项 | 取值 |
|---|---|
| 网络 | `--network=none` |
| 根文件系统 | `--read-only`；`--tmpfs /tmp:rw,noexec,nosuid,size=16m` 提供可写临时目录 |
| 用户 | 非 root：Tier A `--user 65534:65534`；Tier B `--userns=keep-id --user <宿主 uid>:<gid>` |
| 挂载 | Tier A 不挂载任何宿主目录；Tier B 只挂 `storage/workspaces/<chat_id>` → `/workspace:rw` |
| 禁止 | docker/podman socket、宿主目录、宿主环境变量、密钥（子进程环境是白名单拷贝） |
| 限制 | `--memory 256m --memory-swap 256m --cpus 0.5 --pids-limit 64 --ulimit nofile=64:64 --ulimit fsize=8388608:8388608` |
| 时间 | 默认 15s、上限 30s（`SANDBOX_TIMEOUT_DEFAULT` / `SANDBOX_TIMEOUT_MAX`） |
| 并发 | `SANDBOX_MAX_CONCURRENT=2`（进程内信号量，超出排队） |
| 输出 | stdout/stderr 各 8 KB，超出即截断并追加 `[output truncated: N bytes]` |
| 镜像/执行 | `python:3.12-slim`（只能部署阶段预拉取）→ `python -I -c <code>`，code 作为单个 argv 参数 |
| 超时 | kill 进程并销毁容器（`--rm` 兜底 + 显式 kill/rm） |

- Tier A（默认）：纯计算，无挂载、无网络、非 root、一次一销毁。
- Tier B（workspace 写入）：只在 rootless Podman + `SANDBOX_TIER_B=auto` 时启用，用 user namespace `keep-id`
  把宿主用户映射进容器，容器内仍是非 root 用户；Docker 与 rootful Podman 一律不启用，
  `workspace=true` 直接返回 `sandbox_unavailable`（不为了兼容放宽权限）。
- 无可用运行时 → 直接拒绝（`sandbox_unavailable`），禁止退化为宿主机执行。
- 模型不能指定镜像、挂载、工作目录或任何 runtime 参数；容器 argv 全部由 `app/sandbox/spec.py` 生成。
- 临时输出目录 `storage/sandbox/`：正常、异常、超时、取消、Bot 关停都立即删除；
  启动时清理带 `groupbuddy=1` 标签的残留容器（上次进程被强杀留下的）。
- 代码扫描（`app/sandbox/preflight.py`：`os.system`/`subprocess`/`eval`/`__import__`/网络/写入…）只作 **preflight 提示**（只记日志），不作为安全边界。
- 真实验收：在目标机（Linux + rootless Podman）由**运行 Bot 的同一用户**执行 `scripts/verify_sandbox.py`，逐项验证无网络、非 root、
  只读根、fsize 上限、cgroup 资源上限（256 MB / 0.5 CPU / 64 PIDs）、超时销毁、无残留容器、临时目录已清理、
  其他群 workspace 不可见、宿主目录不可见。上线清单与 Tier A/B 判读见 `docs/deployment.md` §12；
  Tier B 任一项不 PASS 就把 `SANDBOX_TIER_B=off` 只保留 Tier A。
- **红线：禁止挂载 docker/podman socket**（等价于宿主机 root 权限），**禁止 privileged / host network / 宿主目录挂载**。
- 若确需调用容器运行时，只允许由权限受限的独立组件用固定模板调用（白名单参数）；模型无法影响镜像、参数与宿主路径。
- 不使用 microVM/Kata/gVisor（阶段 1–8）；确有高风险需求时再评估。

## 5. 网络

- Bot 进程默认不发起出网请求；唯一出口是 `search_web`（以及后续显式批准的工具）。
- `search_web` 只上行查询串；禁止把 workspace 内容、文件正文、环境变量、密钥、完整对话拼进请求。
- URL/域名白名单：只允许已登记域名；拒绝 `file://`、内网地址、云元数据地址（SSRF 防护）。
- 用户说"访问这个链接"不等于获得出网授权；由程序判定。

## 6. 密钥与敏感信息

- 唯一来源：`.env`（不在版本库）。`.env.example` 只放键名与占位符。阶段 10 起由控制面安全存储注入，读取路径不变（`Settings.bot_instance()`）。
- 密钥禁止出现在：代码、日志、数据库、错误消息、工具输出、模型上下文、容器内环境变量。
- 日志写入前做形态遮蔽（`sk-`、`<数字>:<字母数字串>` 等）；发现疑似凭据即替换为 `[redacted]`。
- 出错时只输出分类与短句，不输出堆栈、路径、配置内容。
- 生产环境默认无调试模式；调试开关只能由 `.env` 显式配置，且不得改变本节的遮蔽规则与 §7 的日志过滤规则。
- 凭据生命周期：**只写不读**（接口只能掩码显示，永不返回明文）、可替换、可删除，每次变更留审计记录（阶段 10 建 `audit_log`）。
- 凭据按实例归属（`BotInstance` / `Credential`，见 `docs/domain.md` §1、§4）；一个实例的凭据不出现在另一个实例的配置、日志或上下文里。
- 新增任何凭据字段必须同时注册进日志脱敏集合（`Settings.secrets` → `BotInstance.secret_values()`），否则视为缺陷。

## 7. 日志

| 记录 | 不记录 |
|---|---|
| 时间、`chat_id`、`user_id`、trigger 判定、模型名 | API Key、Bot Token |
| 工具名、状态、耗时、token 用量、错误码 | 文件全文、原始工具参数、完整 URL query |
| | 环境变量、消息全文（除调试模式且本地运行） |

`search_web`/`run_code`/`write_file` 的参数最容易带隐私，默认只记工具名与状态；贴纸只记内部 `sticker_id` 与状态，不记 `file_id`；摘要与检索只记条数/耗时，不记消息全文。
心跳与健康检查日志与常规日志同级脱敏：不记录状态文件内容或其中的密钥。

## 8. Telegram 限速与 429

- 出站限速（初值，可配）：单聊天 ≤1 条/秒；群 ≤15 条/分钟；贴纸 ≤1 条/20 秒（贴纸与文本是两条独立通道，实现见 `app/outbound/ratelimit.py`）。
- 收到 429 时：只让**该群队列**按 `retry_after` 退避（含抖动），其他群继续；
  连续失败按指数退避，上限 60 秒。
- 状态消息（"正在搜索…"）与最终回复一样走队列，否则自己制造洪泛。
- 长文本按 §10 分段后**逐条**限速发送，不并发轰炸。

## 9. 工具熔断

- 同一工具在一轮内失败 2 次 → 本轮从可用清单移除。
- 5 分钟内失败 8 次 → 临时熔断 30 秒，期间调用返回 `cooldown`。
- 阶段 3 的失败计数与熔断状态在进程内存（重启归零）；写入 `tool_failures` 表供 `/stats` 查看属阶段 8。

## 10. 长消息与特殊内容

- `sendMessage` 上限 4096 字符（实体解析后）。按段落 → 代码块 → 句子 → 字符逐级切分；
  不切断代码块（必要时补 fence），不产生非法实体。
- 分段发送之间走同一限速器，避免突发。

## 11. 租户隔离检查清单（测试必覆盖）

1. A 群上下文不出现 B 群消息、摘要、笔记、贴纸。
2. 路径逃逸：`../../.env`、`..\\..\\x`、绝对路径、符号链接、硬链接指向外部 → 全部拒绝。
3. `write_file` 覆盖已有文件后，`.bak` 存在且内容为旧版本。
4. 越权调用（未开启的等级、非管理员）→ `permission_denied`，且不泄露内部信息。
5. 自身消息与其他 Bot 消息不触发回复（产品规则，见 §12）。
6. 429 场景下其他群消息仍能正常发送。
7. 长回复分段后顺序正确、无内容丢失。
8. 跨实例读取（另一个 `bot_instance_id` 的记忆、workspace、配额、群设定）一律拒绝。
9. 凭据按实例归属：本实例的 Bot Token / LLM Key 不泄漏到其他实例与任何接口返回体。
10. FTS 检索必须带 `chat_id`（`JOIN` 主表 + `WHERE chat_id = ?`）：跨群召回属于缺陷。

## 12. 关于其他 Bot 的消息

Telegram 目前允许 Bot 之间互相通信，"收不到其他 Bot 消息"不是平台事实。
本项目把它作为**产品规则**：默认忽略其他 Bot 的消息（避免两个 Bot 互相刷屏）。
实现方式：入站按"是否为自己/已登记的 Bot"过滤，本地回环测试时尤其不能只按 `is_bot` 过滤。

## 13. 部署检查清单（上线 / 换机 / 更新后逐条确认）

1. 容器与宿主机上都不存在挂进 Bot 的 docker/podman socket，也未使用 privileged / host network。
2. Bot 以非 root 专用用户运行，且不属于 `docker` 组。
3. 沙箱只能看到本群 workspace（挂载表与路径校验同时确认）。
4. 进程按 24/7 方式托管（systemd 或容器 restart policy），且同一 Bot Token 只有一个 polling 进程。
5. LLM、工具、沙箱、出站、数据库全部有超时，无无限等待路径。
6. 发送 SIGTERM 后进程能优雅退出（排空队列并关闭数据库与 HTTP 连接）。
7. 日志与错误消息不含 Secret、Token、文件正文、环境变量。
8. 必需配置缺失或持久目录不可写时拒绝启动（fail-closed），不带默认密钥跑起来。

部署形态与目录约定见 `docs/deployment.md`。
