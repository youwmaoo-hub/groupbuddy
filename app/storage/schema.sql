-- 表结构：唯一权威是 docs/database.md §2。本文件按阶段追加迁移，不改已发布的迁移块。
-- 每条语句以分号结尾；列定义用逗号分隔。
-- ===== migration 1 =====

-- updates：批次级去重（update_id 主键）
CREATE TABLE IF NOT EXISTS updates (
    update_id   INTEGER PRIMARY KEY,
    chat_id     INTEGER NOT NULL,
    received_at INTEGER NOT NULL
);

-- messages：每个群的消息原文（原文存储 ≠ 模型上下文）
CREATE TABLE IF NOT EXISTS messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id             INTEGER NOT NULL,
    message_id          INTEGER NOT NULL,
    thread_id           INTEGER,
    user_id             INTEGER NOT NULL,
    role                TEXT NOT NULL,
    text                TEXT NOT NULL,
    reply_to_message_id INTEGER,
    noise               INTEGER NOT NULL DEFAULT 0,
    created_at          INTEGER NOT NULL,
    UNIQUE (chat_id, message_id)
);

-- 窗口查询索引：按群 + 时间取最近 N 条
CREATE INDEX IF NOT EXISTS idx_messages_chat_time ON messages (chat_id, created_at);

-- chat_settings：每个群的设置（阶段 1 只用到默认值）
CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id          INTEGER PRIMARY KEY,
    mode             TEXT NOT NULL DEFAULT 'normal',
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

-- usage：运行侧 token 记账（开发侧不计入）
CREATE TABLE IF NOT EXISTS usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id       INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    day           TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    tool_calls    INTEGER NOT NULL DEFAULT 0,
    tool_ms       INTEGER NOT NULL DEFAULT 0,
    created_at    INTEGER NOT NULL
);

-- 记账查询索引：按群 + 天聚合
CREATE INDEX IF NOT EXISTS idx_usage_chat_day ON usage (chat_id, day);

-- ===== migration 2 =====

-- stickers：每群登记的贴纸（file_id 与 Bot 身份绑定，换 Token 后需重新登记；阶段 5）
CREATE TABLE IF NOT EXISTS stickers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id        INTEGER NOT NULL,
    file_id        TEXT NOT NULL,
    file_unique_id TEXT NOT NULL,
    valence        REAL,
    arousal        REAL,
    tags           TEXT,
    last_used_at   INTEGER,
    created_at     INTEGER NOT NULL,
    UNIQUE (chat_id, file_unique_id)
);

-- ===== migration 3 =====

-- 用途维度：chat=回复调用，summary=摘要调用（老行由默认值补 'chat'，旧行为不变）
ALTER TABLE usage ADD COLUMN purpose TEXT NOT NULL DEFAULT 'chat';

-- 滚动摘要（阶段 6）：text=展示原文，tokens=检索分词串（中文双字 bigram）
CREATE TABLE IF NOT EXISTS summaries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    thread_id  INTEGER,
    text       TEXT NOT NULL,
    tokens     TEXT NOT NULL,
    msg_from   INTEGER,
    msg_to     INTEGER,
    created_at INTEGER NOT NULL
);

-- 摘要查询索引：按群取最新
CREATE INDEX IF NOT EXISTS idx_summaries_chat ON summaries (chat_id, created_at DESC);

-- 长期笔记（阶段 6）：同名覆盖，version 递增
CREATE TABLE IF NOT EXISTS notes (
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

CREATE INDEX IF NOT EXISTS idx_notes_chat ON notes (chat_id, name);

-- FTS：external content，索引 tokens 列；内容同步由 repo 显式维护（不用 trigger）
CREATE VIRTUAL TABLE IF NOT EXISTS summaries_fts USING fts5(tokens, content='summaries', content_rowid='id');
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(tokens, content='notes', content_rowid='id');
