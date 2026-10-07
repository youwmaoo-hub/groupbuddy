# 设计决策记录（ADR）

负责：这个项目**为什么**这样设计、放弃过哪些方案、什么条件下重新评估。
上游：`docs/README.md` §2 路由表、`docs/requirements.md` §3（已否定方案）。
改动影响：只追加新 ADR；新增/取代 ADR 时更新本文件 §3 索引表；推翻旧决策时把旧文件标 `被取代`，不删除。

## 1. 什么时候写 ADR

- 架构变化（`AGENTS.md` §8 级别 3）：分层、模块边界、装配与关闭、引入或移除基础设施。
- 明确否决过某个方案（尤其是反复被提出的：Redis、向量库、DinD、Webhook 入站、多实例）。
- 安全与部署上的不可逆取舍（沙箱档位、不挂容器 socket、不进 Git 的凭据、单实例形态）。
- 已经造成过事故或返工、需要留下「为什么不能改回去」的记录。

不写 ADR：普通 bug fix、性能优化、纯实现细节、进度与测试数字（进 `docs/status.md`）。

## 2. 写法与状态

- 文件命名 `NNNN-短标题.md`，编号连续递增，不回收、不重排。
- 状态只有三种：`已接受`、`已否决`、`被取代（见 ADR NNNN）`。
- **只追加，不改写历史**：推翻旧决策时新增一个 ADR，并在旧文件顶部加一行 `被取代：见 ADR NNNN`。
- ADR 只回答「为什么」；契约细节（表结构、工具 schema、权限、部署步骤）写在 `docs/security.md`、`docs/tools.md`、`docs/database.md`、`docs/deployment.md`，ADR 只引用不复制。

## 3. 索引

| 编号 | 决策 | 状态 |
|---|---|---|
| [0001](0001-sqlite.md) | 用 SQLite 作为唯一存储（单进程 + WAL + `user_version` 迁移） | 已接受 |
| [0002](0002-bot-sandbox-separation.md) | Bot 进程与沙箱分离：不挂容器 socket，用固定 argv 调 CLI | 已接受 |
| [0003](0003-rootless-podman.md) | 沙箱优选 rootless Podman，Docker 只作 Tier A 备选 | 已接受 |
| [0004](0004-tier-a-b.md) | 沙箱分 Tier A / Tier B 两档 | 已接受 |
| [0005](0005-windows-fake-backend.md) | Windows 开发用 FakeBackend，真实容器只在 Linux 验证 | 已接受 |
| [0006](0006-credentials-not-in-git.md) | 凭据不进 Git、不进日志 | 已接受 |
| [0007](0007-storage-source-vs-runtime.md) | 只忽略仓库根 `/storage/`；`app/storage/` 是源码必须入库 | 已接受 |
| [0008](0008-no-redis-vector-mq.md) | 暂不引入 Redis / 容器化部署 / Webhook 入站 / 向量库 / MQ | 已接受 |
| [0009](0009-long-polling-single-instance.md) | long polling + 单实例（一个 Token 一个进程） | 已接受 |
| [0010](0010-fts5-not-vector.md) | 检索用 FTS5（双字 bigram + bm25），不用向量库 | 已接受 |

## 4. 模板

```
# ADR NNNN：一句话决策

状态：已接受
负责：<本决策回答的唯一问题>
上游：<相关需求/文档>
改动影响：<推翻时新增 ADR + 需要同步的文档>

## 背景        —— 当时面对什么约束与问题
## 决策        —— 选了什么，边界到哪里
## 备选与放弃原因 —— 试过/考虑过什么，为什么不选
## 后果        —— 换来了什么，付出了什么代价，什么条件要重新评估
## 验证方式    —— 哪些测试/真机检查证明它现在成立
```