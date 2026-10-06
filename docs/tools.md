# 工具契约

负责：工具的名称、等级、输入输出、超时、错误码、输出上限、熔断规则。
上游：`docs/requirements.md` F4；`docs/security.md`（等级与权限来源）。
改动影响：任一字段变更都属契约变更（见 `AGENTS.md` §5）。

## 1. 通用规则

- 工具清单由程序生成并按权限裁剪后注入 System3（见 `docs/security.md` §2）。
- 模型返回的 `arguments` 不保证是合法 JSON、也可能是未定义参数：一律经 Pydantic 校验，失败即拒绝。
- 执行顺序固定（判定顺序以 `docs/security.md` §2 为准）：**注册表 → 本群开关/身份 → 参数 schema → 执行 → 结构化结果**，任何一步失败都返回 §3 的错误码。
- 输出必须是短的结构化 JSON；超限即截断并标注（见 §4）。
- 同一工具在一轮内失败 2 次 → 本轮禁用；5 分钟内失败 8 次 → 临时熔断 30 秒（见 `docs/security.md` §9；阶段 3 熔断状态在进程内存）。

## 2. 冻结表

| 工具 | 等级 | 默认开关 | 输入 | 输出 | 超时 |
|---|---|---|---|---|---|
| `calc` | L0 | 开 | `expression: str` | `{value: str}` | 2s |
| `search_web` | L0 | 群开关（需配置后端，见下） | `query: str, top_k?: int=3` | `{results:[{title,url,snippet}]}` | 10s |
| `read_file` | L1 | 群开关 | `path: str, start_line?: int, end_line?: int, query?: str`（`query` 保留，传入即 `invalid_arguments`） | `{path,start_line,end_line,text,total_lines}` | 3s |
| `write_file` | L2 | 群开关 | `path: str, content: str` | `{path,bytes,backup?: str}` | 5s |
| `send_sticker` | L2 | 群开关 | `valence: float, arousal: float, tags?: [str]` | `{sent: bool, sticker_id: int}`；冷却中 `{sent: false, state: "cooldown", retry_after: N}` | 3s |
| `run_code` | L3 | 群开关（默认关） | `code: str, timeout_s?: int=15, workspace?: bool=false` | `{exit_code,stdout,stderr,truncated}` | 30s（ToolSpec 35s） |
| `host_info` | L4 | 默认关 | `fields?: [str]` | `{cpu,memory,disk_free,python,uptime_s}` | 2s |

### calc

- 只接受 `+ - * / % ** ( )`、数字、空白；通过 AST 解析求值。
- 禁止 `eval`/`exec`；出现名称、属性、调用、下标、推导式等一律拒绝（`invalid_expression`）。
- 表达式 ≤200 字符；指数绝对值 ≤100；结果绝对值 ≤10^100；除零同样返回 `invalid_expression`。
- 零文件、零网络、零 shell。

### search_web

- 后端未定（见 `docs/requirements.md` §4 #1）：接口已冻结。`SEARCH_BACKEND=none`（默认）时该工具不注册、不下发；`fake` 只用于离线测试与演示（结果标注为示例）；接真实后端只需实现 `SearchBackend`。
- 只允许查询串与 `top_k` 上行；不得携带 workspace 内容、环境变量、密钥、完整文件文本。
- 默认 `top_k=3`，上限 5；结果最多 5 条；`snippet` 截断到 500 字符、`title` 120、`url` 300；保留来源 URL 以便引用。

### read_file / write_file

- `path` 只能是 workspace 内 `/` 分隔的相对路径；解析与越界拒绝规则见 `docs/security.md` §3。
- `read_file` 只读 UTF-8 文本：无法按 UTF-8 解码返回 `invalid_arguments`；单文件超过 1 MB 直接 `too_large`，不能靠多次读取绕过。
- 行区间 1-based 且包含两端；省略 `start_line` 从第 1 行开始，省略 `end_line` 读到文件末尾；越界截断到实际范围，最终区间为空返回 `invalid_arguments`；单次最多 200 行。
- `query` 子串检索本阶段不实现：参数保留，传入即 `invalid_arguments`，将来由独立的文件检索/FTS 功能定义。
- `write_file` 单次写入 ≤1 MB；覆盖已存在文件前把旧内容复制为 `<name>.bak`（只保留一层，再次覆盖时更新它），用临时文件 + `fsync` + 原子替换；上级目录不存在返回 `not_found`。

### send_sticker

- 模型只给情绪与标签；`file_id` 永不进入模型上下文、工具返回、日志与错误消息（只允许存在于 `stickers` 表与 Telegram 发送边界）。
- 匹配：valence/arousal 余弦相似度为主分 + tags 交集轻量加分（`TAG_BONUS=0.1`）；低于 `MIN_SCORE=0.6` 返回 `not_found`，不强行发不合适的贴纸；分数接近（差值 ≤ `TIE_EPSILON=0.05`）时取 `last_used_at` 更早的，尽量避免连续重复；严格按 `chat_id` 隔离。
- 冷却取群设置 `chat_settings.sticker_cooldown`（默认 30 秒）；冷却期内返回 `{"sent": false, "state": "cooldown", "retry_after": N}`，这是业务状态而不是错误。
- 成功后更新该贴纸 `last_used_at`，并把本次情绪写入进程内 mood（TTL 10 分钟，见 `docs/persona.md` §2）。
- 受出站限速约束：贴纸 1 条/20 秒，与同群文本发送串行（`app/outbound/queue.py`）。

### run_code

- 必须经 `app/sandbox/runner.py`；沙箱参数由程序固定（见 `docs/security.md` §4），模型看不到也改不了镜像、挂载与 runtime 参数。
- 权限：等级 L3 + 群开关 `allow_code`（默认关）；`workspace=true` 还需要本群 `allow_write`，否则 `permission_denied`。模型不能自行授予权限。
- 沙箱后端在**启动时探测一次**并固定（`SANDBOX_BACKEND=auto`：rootless Podman 优先、Docker 备选）；没有可用运行时就不执行。
- Tier B（`workspace=true`）只在 rootless Podman（`--userns=keep-id`）下可用；其他后端一律 `sandbox_unavailable`。
- 无容器运行时可用时一律 fail-closed 拒绝（`sandbox_unavailable`），不允许退化为宿主机执行。
- 默认 `timeout_s=15`，上限 30；超时即 kill 并销毁容器并返回 `timeout`。
- 错误映射：运行时不可用 / Tier B 未验证 → `sandbox_unavailable`；启动或执行失败 → `execution_failed`；workspace 越界 → `path_outside_workspace`。

### host_info

- 只允许 `cpu`、`memory`、`disk_free`、`python`、`uptime_s` 五个字段。
- 禁止环境变量、进程命令行、网络接口、主机名、用户目录、IP。

## 3. 错误码（统一格式）

```json
{"error": "<code>", "tool": "<name>", "message": "<短句，≤200 字符>"}
```

| code | 含义 |
|---|---|
| `permission_denied` | 权限/等级/群开关不允许 |
| `invalid_arguments` | schema 校验失败（含非法 JSON、未定义参数） |
| `invalid_expression` | `calc` 表达式含不允许的构造 |
| `not_found` | 路径不存在 |
| `path_outside_workspace` | 路径解析后不在本群 workspace 内 |
| `too_large` | 输入或输出超过上限 |
| `timeout` | 超时 |
| `sandbox_unavailable` | 容器运行时不可用（`run_code` 专用） |
| `execution_failed` | 目标程序非零退出且有 stderr |
| `cooldown` | 工具处于冷却/熔断 |
| `internal_error` | 未分类错误（消息只回一句，不泄露细节） |

错误对象直接返回给模型，由模型用一句话向用户解释；不把堆栈、路径、环境信息放进 message。

## 4. 输出上限与截断

| 位置 | 上限 | 超出表现 |
|---|---|---|
| `run_code` stdout / stderr | 各 8 KB | 末尾追加 `[output truncated: N bytes]` |
| `search_web` | 结果 ≤5 条，snippet ≤500 字符 | 多余结果丢弃并计入 `truncated` |
| `read_file` | 单次 ≤200 行且 ≤16 KB | 返回 `total_lines` 与 `end_line` 供模型续读 |
| 其他工具 | 4 KB JSON | 截断并标注 |

## 5. System3 注入格式

程序按当前群设置与用户身份生成，模型只能从这个列表里选：

```json
{"allowed_tools": ["calc", "search_web", "read_file"]}
```

未列出的工具不进入 `tools` 参数；模型若强行请求，由 `app/tools/policy.py` 二次拒绝。
