# 数据库

负责：表结构、索引、迁移、保留清理、写入与幂等规则。
上游：`docs/requirements.md`；检索策略见 `docs/memory.md`（本文件不重复）。
改动影响：加表/改列属契约变更（见 `AGENTS.md` §5），需同步 `docs/architecture.md` 模块地图。

## 1. 选型与设置

- SQLite（`aiosqlite`），文件：`storage/bot.db`。
- 连接 PRAGMA：`journal_mode=WAL`、`synchronous=NORMAL`、`foreign_keys=ON`、`busy_timeout=5000`。
- 时间统一存 Unix 秒（`INTEGER`），不存本地时间字符串。
- 时间语义：内部一律 UTC；展示与"按天"归集再按 `TIMEZONE` 配置转换（默认 `Asia/Shanghai`，见 `docs/deployment.md` §4）。
- 迁移：使用 `PRAGMA user_version` + 代码内有序迁移列表（`app/storage/db.py`）；
  每次启动比对版本并逐条应用，迁移脚本只追加不修改。

## 2. 表结构

```sql
-- 幂等来源
updates (
  update_id   INTEGER PRIMARY KEY,
  chat_id     INTEGER,
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
CREATE INDEX idx_messages_chat_time ON messages (chat_id, created_at DESC);

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
  user_id        INTEGER,
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

-- 工具失败与熔断依据（阶段 8 建表：阶段 3 的失败计数与熔断在进程内存，见 docs/security.md §9）
tool_failures (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tool       TEXT NOT NULL,
  chat_id    INTEGER NOT NULL,
  error_code TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_tool_failures_tool_time ON tool_failures (tool, created_at DESC);

-- FTS（阶段 6 / migration 3；索引 tokens 列，内容同步由 repo 显式维护，不用 trigger）
CREATE VIRTUAL TABLE summaries_fts USING fts5(tokens, content='summaries', content_rowid='id');
CREATE VIRTUAL TABLE notes_fts     USING fts5(tokens, content='notes',     content_rowid='id');
```

## 3. 关系与不变量

- `messages/summaries/notes/stickers/chat_settings/usage` 都以 `chat_id` 为租户键；跨群读取属于缺陷。
- `(chat_id, message_id)` 唯一：同一条 Telegram 消息即使重复 ingest 也只落一行。
- `update_id` 是主键：`INSERT OR IGNORE` 失败即视为重复，直接丢弃更新。
- `chat_settings` 缺失时按默认值处理（不强制预建行）。
- 私聊默认不处理：不写入 `messages`，只在 `updates` 留下 update_id/chat_id/received_at（见 `docs/requirements.md` §2.2）。
- 租户键口径：本文所有表的 `chat_id` 都是"实例内的群"；完整租户键是 `(bot_instance_id, chat_id)`，阶段 1–9 只有一个实例（`default`），因此不新增列（见 `docs/domain.md` §2）。

## 4. 保留与清理（启动时执行，低优先级后台任务）

| 数据 | 保留 | 动作 |
|---|---|---|
| `updates` | 48 小时 | 删除更早行（幂等只需覆盖重放窗口） |
| `tool_failures` | 7 天 | 删除更早行 |
| `messages` | 默认全保留 | 群主 `/clear` 可按群清理；清理后摘要保留 |
| `summaries` | 每群保留最近 50 条 | 超出归档删除最旧 |
| 维护 | 每周 | `PRAGMA optimize`；体积明显膨胀时 `VACUUM`（离线执行） |

## 5. 备份与恢复

- 备份 = 冷快照：用标准库 `sqlite3` 打开 `DB_PATH` 并调 `Connection.backup()` 写入
  `storage/backups/bot.db.YYYYMMDD-HHMM`（不走 `aiosqlite` 连接，避免与工作连接抢锁）。
- 频率：程序内默认每周 1 次，保留最近 `BACKUP_KEEP`（默认 7）份，更旧的删除；失败只 `WARN`，不阻塞服务。
- 备份在低优先级后台任务中执行，必须有超时，且随关闭信号停止（见 `docs/deployment.md` §5）。
- 恢复：停进程 → 用快照替换 `bot.db` → 启动时自动跑迁移（旧版本由迁移升级，版本高于代码时拒绝启动）。
- 逐步走：不做 WAL 增量归档、不做主从、不做跨机实时同步；需要异地容灾时再单独评估。

## 6. 写入规则

- 所有写入在事务中完成；同一事务内不做网络或工具调用。
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
