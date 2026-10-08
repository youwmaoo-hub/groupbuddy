# 领域对象与身份

负责：对象模型（User / BotInstance / Chat / ChatSettings / Credential / Persona / ToolPolicy / Memory / Workspace / Usage / SystemStatus / Voice*）、身份类型、租户键与隔离口径。
上游：`docs/requirements.md`（F6.x 决定对象范围）。
改动影响：对象或租户键变化需同步 `docs/database.md`（表与键）、`docs/architecture.md` §2/§10、`docs/security.md` §6/§11。

## 1. 对象模型

| 对象 | 唯一键 | 归属 | 现在（阶段 1–9 + 阶段 10 面板） | 阶段 |
|---|---|---|---|---|
| TelegramActor | `telegram_user_id` | 平台 | `IncomingMessage.user_id` | 现有 |
| WebUser | `user_id` | 控制面 | 不存在（预留）：面板只有部署者口令两级，没有用户对象 | 10（未实施） |
| Principal | `(actor_type, actor_id, bot_instance_id[, chat_id])` | 服务层入参 | 不存在（预留）：服务层目前直接收 `connection` + `Settings` | 10（未实施） |
| BotInstance | `instance_id` | 控制面 | `Settings.bot_instance()`（进程内一个，默认 `default`） | 已定义对象 |
| Credential | `(bot_instance_id, kind)` | BotInstance | `.env` → `BotInstance.bot_token` / `BotInstance.llm`；**面板可写入/替换/删除**（`app/services/credentials.py`） | 10（写入已实施） |
| Chat | `(bot_instance_id, chat_id)` | BotInstance | `chat_id` | 现有（单实例） |
| ChatSettings | `(bot_instance_id, chat_id)` | Chat | `chat_settings` 表 | 阶段 3 起使用 |
| Persona | 全局 / 每实例 / 每群 | 全局 → 实例 → 群 | 代码常量 → `PERSONA` → `chat_settings.persona_override`（面板可写群覆盖） | 8 / 10（写已实施） |
| ToolPolicy | `(bot_instance_id, chat_id)` | Chat | `chat_settings.allow_*` + `app/tools/policy.py` | 3 |
| Memory | `(bot_instance_id, chat_id)` | Chat | `messages` / `summaries` / `notes` | 6 |
| Workspace | `(bot_instance_id, chat_id)` | Chat | `<WORKSPACE_ROOT>/<chat_id>/` | 4 |
| Usage | `(bot_instance_id, chat_id, day)` | Chat + 实例汇总 | `usage` 表（面板只读展示当日用量） | 8 / 10（实例汇总未实施） |
| SystemStatus | `bot_instance_id` | 实例 | `storage/health.json` 心跳 + `/health` 命令 + 面板概览（`app/services/overview.py`） | 8 / 9 / 10 |
| VoiceProvider / VoiceProfile / VoiceSettings | provider 名 / `bot_instance_id` / `(bot_instance_id, chat_id)` | 服务层 | 不存在（仅预留，见 §5） | 11+ |

## 2. 租户键与隔离

- 租户键顺序固定为 `(bot_instance_id, chat_id)`；阶段 1–9 只有一个实例，`bot_instance_id="default"`，等价于现状的 `chat_id` 单键。
- 实例隔离靠"每实例一份存储根"：每个实例注入自己的 `DATA_DIR` / `DB_PATH` / `WORKSPACE_ROOT`（`docs/deployment.md` §3）。因此现有表**不加** `bot_instance_id` 列，已发布迁移不改；多实例 = 多目录 + 多进程。
- 记忆、workspace、配额、群设定、工具权限一律按 `chat_id` 隔离，跨群读取属缺陷（`docs/security.md` §11）；跨实例读取同样一律拒绝。
- 同一实例内 `chat_id` 与 `thread_id`（论坛主题）的预留关系见 `docs/database.md` §3。

## 3. 身份

- 三种身份不复用：Telegram 用户（`TelegramActor`）、Web 面板用户（`WebUser`）、运行期请求主体（`Principal`）。**Web 用户与 Telegram 用户不得简单视为同一种身份。**
- 服务层接收 `Principal`（含 `actor_type` / `actor_id` / `bot_instance_id` / 可选 `chat_id`），据此判定授权；适配器只提供身份事实，不做判定。
- 阶段 1–9 只有 Telegram 侧身份：`user_id` 与 `chat_settings.owner_user_id`；面板身份在阶段 10 引入**面板口令两级**（`PANEL_TOKEN`=ADMIN / `PANEL_READONLY_TOKEN`=VIEWER，`app/control/auth.py`），`WebUser` 与 `Principal` 对象仍未实施——面板的"管理员"语义是"部署者本人"，不等价于任何 Telegram 用户。
- 审计：改设置、改权限、改凭据必须留下"谁改了什么"的记录（阶段 10 建 `audit_log`，见 `docs/database.md` §7）。**现状：`audit_log` 未建**，面板的写入只落服务日志（含脱敏），这是已知缺口。

## 4. 凭据（Credential）

- 凭据在概念上归属 `BotInstance`；唯一出口是 `Settings.bot_instance()` → `BotInstance.bot_token` / `BotInstance.llm`（`LLMCredentials`）。业务代码不得各自读全局 `BOT_TOKEN` / `LLM_API_KEY`。
- 凭据只写不读：任何面向面板/前端的接口都不得返回明文，只能写入、替换、删除；状态查询只回"配没配 + 来源"（`app/services/credentials.py`，`GET /api/credentials` 连掩码都不回）。
- 面板写入按 name 精确改 `.env` 行（同目录临时文件 + `chmod 0600` + `os.replace`），写完后机器人需重启才生效（面板只回 `restart_required: true`，不代替操作者重启进程）。
- 新增任何凭据字段必须同时注册进日志脱敏集合（`Settings.secrets` → `BotInstance.secret_values()`；面板口令走 `Settings.panel_tokens`），否则视为缺陷。
- 加密存储与主密钥托管仍未实施（当前明文 `.env`，不在版本库、权限 0600）；规则细节见 `docs/security.md` §6。

## 5. 语音（预留，不实现）

- 对象：`VoiceProvider`（供应商）、`VoiceProfile`（音色，归实例）、`VoiceSettings`（开关与参数，归群）。
- 输入插入点：走工具层（需要权限等级与文件大小/时长限制，`docs/tools.md` §1），不新增旁路。
- 输出插入点：`app/outbound/queue.py` **新增媒体发送方法**（不改 `Sender.send_message` 签名），仍受同一限速与 429 退避约束。
- 阶段 11+ 才实现（F6.6）。

## 6. 现在不做

- 不建控制面表（`bot_instances` / `users` / `credentials` / `audit_log`），不加 `bot_instance_id` 列（见 `docs/database.md` §7）。
- `app/control/`、`app/services/` **已在本版实施**（阶段 10 面板，ADR 0011）；`app/voice/` 仍不引入。Web 框架（FastAPI）与前端依赖**只允许出现在 `app/control/`**，且是可选依赖（`tests/offline/test_layering.py` 锁死）；`app/services/` 不得 import Web 框架与 aiogram。
- 不做实例热加载、不做多实例共享运行态（队列/限速器/去重都是进程内状态）；面板是独立进程但**不共享运行态**，只共享同一个 SQLite 库。
