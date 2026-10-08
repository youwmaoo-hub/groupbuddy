# ADR 0001：用 SQLite 作为唯一存储

状态：已接受
负责：为什么用 SQLite 单文件而不是外部数据库。
上游：`docs/requirements.md` §3、`docs/database.md`。
改动影响：推翻本决策时新增 ADR 并把本文件标 `被取代`；同步 `docs/architecture.md` §3、`docs/database.md`、`docs/deployment.md`。

## 背景

- 形态是单进程、单 Bot Token（见 ADR 0009），数据按群隔离：消息、群设置、用量、贴纸、摘要、笔记。
- 真机（Debian 12）上虽然有 MySQL（宝塔面板自带），但那是其他服务的库；为这个 Bot 再引入数据库服务会带来新凭据、新网络依赖与新运维面。
- 检索需要中文全文搜索（见 ADR 0010），需要的是「库内建 FTS」而不是「独立检索服务」。

## 决策

- 唯一存储是 SQLite 单文件 `storage/bot.db`，经 `aiosqlite` 单连接访问（`app/storage/db.py`）。
- 连接参数：`journal_mode=WAL`、`synchronous=NORMAL`、`foreign_keys=ON`、`busy_timeout=5000`。
- 迁移用 `PRAGMA user_version` + `app/storage/schema.sql` 里的 `-- ===== migration N =====` 块；只追加新块，不改写已应用的块。
- 表结构、索引与清理策略的唯一权威是 `docs/database.md`。

## 备选与放弃原因

- **MySQL / PostgreSQL**：需要新服务、新账号、网络与备份流程；单进程用不上并发写能力。
- **JSON / 文本文件**：没有事务、没有查询与排序，用不上 FTS5 的 bm25 排序。
- **Redis 作为主存**：见 ADR 0008（暂不引入），持久化语义与备份都不如单文件清晰。

## 后果

- 单写者语义：所有写都排在同一条连接上；运维脚本另开同步连接，靠 `busy_timeout` 争锁，锁超过 5 秒会报 `database is locked`（`app/` 内没有重试）。
- 不能多实例共享同一份库（与 ADR 0009 一致）；备份只能是冷快照（阶段 9 才做）。
- 迁移是「一次成功」模型：没有事务包裹，失败后 `user_version` 与结构可能不一致（已知技术债 T2，见 `TODO.md`）。
  **更新（commit `f7f34b5`）**：迁移块已改为显式事务（`BEGIN IMMEDIATE` … `commit`，失败 `rollback` 且不推进 `user_version`），并对 `usage.purpose` 的历史半升级状态做严格限定的兼容；本决策本身未变，其余后果与选型仍成立。
- 换来的好处：部署零依赖、离线测试可以用内存库、FTS5 直接可用。

## 验证方式

- `tests/offline/test_storage.py`、迁移相关用例（3 个块、6/1/7 条语句）。
- 真机：`sqlite 3.40.1` 上跑通全部 283 个测试；`load_migrations() = 3`（见 `docs/status.md` §4）。