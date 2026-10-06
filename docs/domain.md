# 领域对象与身份

负责：对象模型（User / BotInstance / Chat / ChatSettings / Credential / Persona / ToolPolicy / Memory / Workspace / Usage / SystemStatus / Voice*）、身份类型、租户键与隔离口径。
上游：`docs/requirements.md`（F6.x 决定对象范围）。
改动影响：对象或租户键变化需同步 `docs/database.md`（表与键）、`docs/architecture.md` §2/§10、`docs/security.md` §6/§11。

## 1. 对象模型

| 对象 | 唯一键 | 归属 | 现在（阶段 1–9） | 阶段 |
|---|---|---|---|---|
| TelegramActor | `telegram_user_id` | 平台 | `IncomingMessage.user_id` | 现有 |
| WebUser | `user_id` | 控制面 | 不存在（预留） | 10 |
| Principal | `(actor_type, actor_id, bot_instance_id[, chat_id])` | 服务层入参 | 不存在（预留） | 10 |
| BotInstance | `instance_id` | 控制面 | `Settings.bot_instance()`（进程内一个，默认 `default`） | 已定义对象 |
| Credential | `(bot_instance_id, kind)` | BotInstance | `.env` → `BotInstance.bot_token` / `BotInstance.llm` | 10（由面板写入） |
| Chat | `(bot_instance_id, chat_id)` | BotInstance | `chat_id` | 现有（单实例） |
| ChatSettings | `(bot_instance_id, chat_id)` | Chat | `chat_settings` 表 | 阶段 3 起使用 |
| Persona | 全局 / 每实例 / 每群 | 全局 → 实例 → 群 | 代码常量 → `PERSONA` → `chat_settings.persona_override` | 8 / 10 |
| ToolPolicy | `(bot_instance_id, chat_id)` | Chat | `chat_settings.allow_*` + `app/tools/policy.py` | 3 |
| Memory | `(bot_instance_id, chat_id)` | Chat | `messages` / `summaries` / `notes` | 6 |
| Workspace | `(bot_instance_id, chat_id)` | Chat | `<WORKSPACE_ROOT>/<chat_id>/` | 4 |
| Usage | `(bot_instance_id, chat_id, day)` | Chat + 实例汇总 | `usage` 表 | 8 / 10 |
| SystemStatus | `bot_instance_id` | 实例 | `storage/health.json` 心跳 + 阶段 8 `/health` | 8 / 9 |
| VoiceProvider / VoiceProfile / VoiceSettings | provider 名 / `bot_instance_id` / `(bot_instance_id, chat_id)` | 服务层 | 不存在（仅预留，见 §5） | 11+ |

## 2. 租户键与隔离

- 租户键顺序固定为 `(bot_instance_id, chat_id)`；阶段 1–9 只有一个实例，`bot_instance_id="default"`，等价于现状的 `chat_id` 单键。
- 实例隔离靠"每实例一份存储根"：每个实例注入自己的 `DATA_DIR` / `DB_PATH` / `WORKSPACE_ROOT`（`docs/deployment.md` §3）。因此现有表**不加** `bot_instance_id` 列，已发布迁移不改；多实例 = 多目录 + 多进程。
- 记忆、workspace、配额、群设定、工具权限一律按 `chat_id` 隔离，跨群读取属缺陷（`docs/security.md` §11）；跨实例读取同样一律拒绝。
- 同一实例内 `chat_id` 与 `thread_id`（论坛主题）的预留关系见 `docs/database.md` §3。

## 3. 身份

- 三种身份不复用：Telegram 用户（`TelegramActor`）、Web 面板用户（`WebUser`）、运行期请求主体（`Principal`）。**Web 用户与 Telegram 用户不得简单视为同一种身份。**
- 服务层接收 `Principal`（含 `actor_type` / `actor_id` / `bot_instance_id` / 可选 `chat_id`），据此判定授权；适配器只提供身份事实，不做判定。
- 阶段 1–9 只有 Telegram 侧身份：`user_id` 与 `chat_settings.owner_user_id`；面板身份在阶段 10 引入。
- 审计：改设置、改权限、改凭据必须留下"谁改了什么"的记录（阶段 10 建 `audit_log`，见 `docs/database.md` §7）。

## 4. 凭据（Credential）

- 凭据在概念上归属 `BotInstance`；阶段 1–9 的唯一出口是 `Settings.bot_instance()` → `BotInstance.bot_token` / `BotInstance.llm`（`LLMCredentials`）。业务代码不得各自读全局 `BOT_TOKEN` / `LLM_API_KEY`。
- 凭据只写不读：任何面向面板/前端的接口都不得返回明文，只能写入、掩码读取、替换、删除。
- 新增任何凭据字段必须同时注册进日志脱敏集合（`Settings.secrets` → `BotInstance.secret_values()`），否则视为缺陷。
- 加密存储与主密钥托管属阶段 10 决策；规则细节见 `docs/security.md` §6。

## 5. 语音（预留，不实现）

- 对象：`VoiceProvider`（供应商）、`VoiceProfile`（音色，归实例）、`VoiceSettings`（开关与参数，归群）。
- 输入插入点：走工具层（需要权限等级与文件大小/时长限制，`docs/tools.md` §1），不新增旁路。
- 输出插入点：`app/outbound/queue.py` **新增媒体发送方法**（不改 `Sender.send_message` 签名），仍受同一限速与 429 退避约束。
- 阶段 11+ 才实现（F6.6）。

## 6. 现在不做（阶段 1–9）

- 不建控制面表（`bot_instances` / `users` / `credentials` / `audit_log`），不加 `bot_instance_id` 列（见 `docs/database.md` §7）。
- 不引入 `app/control/`、`app/services/`、`app/voice/` 目录与占位文件；不引入 Web 框架与前端依赖。
- 不做实例热加载、不做多实例共享运行态（队列/限速器/去重都是进程内状态）。
