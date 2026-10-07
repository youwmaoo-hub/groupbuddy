# 数据库

负责：表结构、索引、迁移、保留清理、写入与幂等规则。
上游：`docs/requirements.md`；检索策略见 `docs/memory.md`（本文件不重复）。
改动影响：加表/改列属契约变更（见 `AGENTS.md` §5），需同步 `docs/architecture.md` 模块地图。

## 1. 选型与设置

- SQLite（`aiosqlite`），文件：`storage/bot.db`。
- 连接 PRAGMA：`journal_mode=WAL`、`synchronous=NORMAL`、`foreign_keys=ON`、`busy_timeout=5000`。
- 时间统一存 Unix 秒（`INTEGER`），不存本地时间字符串。
- 时钟口径：`stickers.last_used_at` 也写 Unix 秒（`app/tools/builtin/send_sticker.py` 落库用 `time.time`；同一工具的群内冷却仍用 `time.monotonic`，那是进程相对秒、不落库）。修复前的进程相对秒只会残留在本机开发库（真机 `stickers` 为 0 行），残留值比 Unix 秒小，仍会被当作「很久没用过」，不会反转 tie-break（T10 已修）。
- 时间语义：内部一律 UTC；展示与"按天"归集再按 `TIMEZONE` 配置转换（默认 `Asia/Shanghai`，见 `docs/deployment.md` §4）。
- 迁移：使用 `PRAGMA user_version` + 代码内有序迁移列表（`app/storage/db.py`）；
  每次启动比对版本并逐条应用，迁移脚本只追加不修改。
- **每个迁移块在显式事务中应用**（`BEGIN IMMEDIATE` … `commit()`）：块内任一句失败即 `rollback`，`user_version` 不推进；对历史半升级形态（`usage.purpose` 列已存在但版本未推进）做**严格限定**的兼容跳过，其他重复 `ADD COLUMN` / `CREATE TABLE` 仍按真实错误抛出。

## 2. 表结构

```sql
-- 幂等来源
updates (
  update_id   INTEGER PRIMARY KEY,
  chat_id     INTEGER NOT NULL,  -- 私聊/无 chat 的更新由 repo 归一为 0
  received_at INTEGER NOT NULL
);

-- 消息原文（模型上下文按需取子集，见 memory.md）
messages (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id             INTEGER NOT NULL,
  message_id          INTEGER NOT NULL,
  thread_id           INTEGER,             -- 论坛主题，预留
  user_id             INTEGER NOT NULL,    -- 负数=频道/匿名管理员
  role                TEXT NOT NULL,       -- 'user' | 'assistant'
  text                TEXT NOT NULL,
  reply_to_message_id INTEGER,
  noise               INTEGER NOT NULL DEFAULT 0,
  created_at          INTEGER NOT NULL,
  UNIQUE (chat_id, message_id)
);
CREATE INDEX idx_messages_chat_time ON messages (chat_id, created_at);  -- 实际定义无 DESC

-- 滚动摘要（阶段 6 / migration 3）：tokens 是检索用分词串（中文双字 bigram + 拉丁词）
summaries (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id    INTEGER NOT NULL,
  thread_id  INTEGER,
  text       TEXT NOT NULL,
  tokens     TEXT NOT NULL,
  msg_from   INTEGER, msg_to INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_summaries_chat ON summaries (chat_id, created_at DESC);

-- 长期笔记（阶段 6 / migration 3）：同名覆盖，version 递增
notes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id    INTEGER NOT NULL,
  name       TEXT NOT NULL,
  text       TEXT NOT NULL,
  tokens     TEXT NOT NULL,
  version    INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE (chat_id, name)
);
CREATE INDEX idx_notes_chat ON notes (chat_id, name);  -- 与 UNIQUE 自动索引重复，保留为显式声明

-- 每群设定（工具开关 + 模式 + 冷却；等级映射见 security.md）
chat_settings (
  chat_id          INTEGER PRIMARY KEY,
  mode             TEXT NOT NULL DEFAULT 'normal',  -- economy|normal|smart|unrestricted
  allow_search     INTEGER NOT NULL DEFAULT 1,
  allow_read       INTEGER NOT NULL DEFAULT 1,
  allow_write      INTEGER NOT NULL DEFAULT 0,
  allow_code       INTEGER NOT NULL DEFAULT 0,
  allow_sticker    INTEGER NOT NULL DEFAULT 1,
  allow_host_info  INTEGER NOT NULL DEFAULT 0,
  sticker_cooldown INTEGER NOT NULL DEFAULT 30,
  persona_override TEXT,
  owner_user_id    INTEGER,
  updated_at       INTEGER NOT NULL
);

-- 贴纸（阶段 5 / migration 2 加入；file_id 与 Bot 身份绑定，换 Token 后需重新登记；按群规模小，不额外建索引）
stickers (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id      INTEGER NOT NULL,
  file_id      TEXT NOT NULL,
  file_unique_id TEXT NOT NULL,
  valence      REAL, arousal REAL, tags TEXT,
  last_used_at INTEGER,
  created_at   INTEGER NOT NULL,
  UNIQUE (chat_id, file_unique_id)
);

-- 调用记账
usage (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id        INTEGER NOT NULL,
  user_id        INTEGER NOT NULL,  -- 摘要调用记 0
  day            TEXT NOT NULL,            -- YYYY-MM-DD（按 TIMEZONE 配置归属，默认 Asia/Shanghai）
  model          TEXT NOT NULL,
  input_tokens   INTEGER NOT NULL DEFAULT 0,
  cached_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens  INTEGER NOT NULL DEFAULT 0,
  tool_calls     INTEGER NOT NULL DEFAULT 0,
  tool_ms        INTEGER NOT NULL DEFAULT 0,
  purpose        TEXT NOT NULL DEFAULT 'chat',  -- chat=回复调用；summary=摘要调用（阶段 6）
  created_at     INTEGER NOT NULL
);
CREATE INDEX idx_usage_chat_day ON usage (chat_id, day);

-- 工具失败与熔断依据（migration 4 / 阶段 8 F5.4；阶段 3 的熔断计数仍在进程内存，见 docs/security.md §9）
tool_failures (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tool       TEXT NOT NULL,
  chat_id    INTEGER NOT NULL,
  error_code TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_tool_failures_tool_time ON tool_failures (tool, created_at DESC);
CREATE INDEX idx_tool_failures_chat_time ON tool_failures (chat_id, created_at);  -- /stats 按群查当日失败

-- FTS（阶段 6 / migration 3；索引 tokens 列，内容同步由 repo 显式维护，不用 trigger）
CREATE VIRTUAL TABLE summaries_fts USING fts5(tokens, content='summaries', content_rowid='id');
CREATE VIRTUAL TABLE notes_fts     USING fts5(tokens, content='notes',     content_rowid='id');
```

## 3. 关系与不变量

- `messages/summaries/notes/stickers/chat_settings/usage/tool_failures` 都以 `chat_id` 为租户键；跨群读取属于缺陷。
- `notes_fts` 是**外部内容表**（无触发器，由 repo 显式同步）：写入前先删旧 `tokens`，删除笔记时同步删（**已实现** `notes.delete`）；`tokens` 由 `term_tokens`（CJK bigram + 拉丁词）产生。
- `(chat_id, message_id)` 唯一：同一条 Telegram 消息即使重复 ingest 也只落一行。
- `update_id` 是主键：`INSERT OR IGNORE` 失败即视为重复，直接丢弃更新。
- `chat_settings` 缺失时按默认值处理（不强制预建行）。
- 私聊默认不处理：不写入 `messages`，只在 `updates` 留下 update_id/chat_id/received_at（见 `docs/requirements.md` §2.2）。
- 租户键口径：本文所有表的 `chat_id` 都是"实例内的群"；完整租户键是 `(bot_instance_id, chat_id)`，阶段 1–9 只有一个实例（`default`），因此不新增列（见 `docs/domain.md` §2）。

## 4. 保留与清理（启动时执行，低优先级后台任务）

| 数据 | 保留 | 动作 |
|---|---|---|
| `updates` | 48 小时 | 删除更早行（幂等只需覆盖重放窗口；**已实现** `updates.purge_old`，housekeeping 启动时执行） |
| `tool_failures` | 7 天 | 删除更早行（**已实现** `tool_failures.purge_old`，启动时与每小时 housekeeping 各执行一次） |
| `messages` | 默认全保留 | 群主 `/clear` 可按群清理；清理后摘要保留 |
| `notes` | 默认全保留 | 群主 `/note` 同名覆盖（`version` +1）或 `/note del <名称>` 删除（**已实现** `notes.delete`，同步清 `notes_fts`） |
| `summaries` | 每群保留最近 50 条 | 超出归档删除最旧（**已实现**：`SUMMARY_KEEP=50`，摘要写成功后立即 prune） |
| 维护 | 每周 | **已实现** `PRAGMA optimize`：每小时 housekeeping 里带时间门槛，每 7 天（`app/main.py` 的 `OPTIMIZE_INTERVAL_SECONDS`）执行一次，让 SQLite 只在其认为划算时刷新统计信息；体积明显膨胀时的 `VACUUM` 仍离线手工执行（不放进进程内）。 |

## 5. 备份与恢复

- **状态：阶段 9 已实现**：`app/storage/backup.py`（能力）+ `scripts/backup_db.py`（运维入口）。
- 备份 = 冷快照：用标准库 `sqlite3` 以只读方式打开 `DB_PATH` 并调 `Connection.backup()` 写入
  `storage/backups/bot.db.YYYYMMDD-HHMM`（不走 `aiosqlite` 连接，避免与工作连接抢锁；同一分钟内重复执行追加 `-2`、`-3` 后缀）。
- 快照必须是**单个自洽文件**：源库是 WAL 时 `Connection.backup()` 会把 WAL 标志一起复制到目标，
  `copy_database()` 因此复制完成后把目标改回回滚日志模式并清掉残留 `-wal`/`-shm`（恢复时只需这一个文件）。
- 校验：写完立刻只读打开做 `PRAGMA integrity_check`，并统计 8 张关键表（`chat_settings`/`messages`/`notes`/`stickers`/
  `summaries`/`tool_failures`/`updates`/`usage`）的行数；`integrity != ok` 时脚本退出码 1。
- 保留：默认最近 7 份（`DEFAULT_KEEP=7`），更旧的删除；`--keep 0` 表示不清理。
- 触发方式：`python scripts/backup_db.py [--db storage/bot.db] [--dest storage/backups] [--keep 7]`；
  只读源库、不读 `.env`、不需要凭据，**可在 Bot 运行中执行**（不阻塞服务，不影响 polling 与健康心跳）。
- 恢复：停进程 → 用快照替换 `bot.db`（`cp storage/backups/bot.db.<时间戳> storage/bot.db`）→ 启动时自动跑迁移
  （旧版本由迁移升级，版本高于代码时拒绝启动）。演练时把快照复制到独立目录再打开，不动线上库。
- **未实现（阶段 9 明确未做）**：程序内每周自动备份任务与 `BACKUP_INTERVAL_SECONDS` / `BACKUP_KEEP` 环境键；
  当前由运维触发，复用同一份 `create_backup()`（新增配置键属部署契约变化，需要单独确认）。
- 逐步走：不做 WAL 增量归档、不做主从、不做跨机实时同步；需要异地容灾时再单独评估。

## 6. 写入规则

- 所有写入在事务中完成；同一事务内不做网络或工具调用。
  **实现（技术债 T9 已修）**：迁移按块原子（见 §1）；repo 层不再自己 `commit()`，每个写入路径都用 `app/storage/tx.py` 的 `transaction()`（`SAVEPOINT` … `RELEASE` / `ROLLBACK TO`）包住：成功由最外层 `RELEASE` 提交，任一句失败则整体回滚后抛出，半成品不会被后续别的写入顺带提交。用 `SAVEPOINT` 而不是 `BEGIN IMMEDIATE`，是因为整进程共享同一条连接，另一任务可能已经开着事务（savepoint 可安全嵌套）。覆盖：`messages`（insert/clear_chat）、`chat_settings.upsert`、`usage.record`、`updates`（mark_seen/purge_old）、`tool_failures`（record/purge_old）、`notes`（upsert/delete）、`summaries`（insert/prune）、`stickers`（register/mark_used）；离线回归见 `tests/offline/test_transactions.py`。
- 工具执行与 LLM 调用**不**持有数据库写锁（先算后写）。
- 记账失败不得影响回复；`usage` 写入异常只记日志。

## 7. 控制面预留（阶段 10，暂不建表）

面板使用**单独的控制库文件**，不放进实例的 `bot.db`；本轮不建表、不加列、不改已发布迁移。

| 候选表 | 唯一键 | 用途 |
|---|---|---|
| `bot_instances` | `instance_id` | 实例清单与状态（对应 `DATA_DIR`/`DB_PATH`/`WORKSPACE_ROOT`） |
| `users` | `user_id` | Web 面板用户（与 Telegram 用户不是同一身份，见 `docs/domain.md` §3） |
| `credentials` | `(bot_instance_id, kind)` | 凭据密文 + 掩码（只写不读，见 `docs/security.md` §6） |
| `audit_log` | `id` | 谁在何时改了哪个设置/权限/凭据 |
| `usage_rollup` | `(bot_instance_id, day)` | 实例级用量汇总（明细仍在实例库的 `usage`） |

规则：迁移只追加；凭据列只存密文与掩码；控制库不含任何群消息原文。
