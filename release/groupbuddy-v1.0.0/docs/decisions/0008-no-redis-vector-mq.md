# ADR 0008：暂不引入 Redis / 容器化部署 / Webhook 入站 / 向量库 / MQ

状态：已接受
负责：为什么暂不引入 Redis/容器化/Webhook/向量库/MQ，以及何时重新评估。
上游：`docs/requirements.md` §3（已否定方案）、`docs/architecture.md` §1。
改动影响：重新评估前必须新增 ADR 说明触发条件与影响面；`AGENTS.md` §3.21 已把这一类改动定为必须先评审。

## 背景

- 需求 `docs/requirements.md` §3 明确否定这些方案；当前形态是单机、单进程、单 Token、群数量级很小。
- 每引入一个基础设施，都会同时增加：新依赖、新凭据、新网络面、新部署步骤与新故障模式。

## 决策

保持「单进程 + SQLite + 进程内状态」：

- 入站用 long polling（ADR 0009）；不引入 MQ，任务直接在进程内 `asyncio` 调度。
- 限速、冷却、熔断、情绪都在进程内；跨重启的幂等依赖 `updates` 与 `messages` 表的唯一键。
- 检索用 SQLite FTS5（ADR 0010），不引入向量库或嵌入服务。
- 部署按「宿主直跑 + 系统依赖（Podman）」设计，不把 Bot 打进容器（沙箱本身需要宿主 runtime）。

## 备选与放弃原因

- **Redis**：能做跨进程队列/限速/缓存，但当前只有一个进程，收益为零，成本是运维与一致性。
- **MQ（RabbitMQ 等）**：解耦多消费者，当前没有第二个消费者。
- **Webhook 入站**：需要公网 HTTPS、证书、鉴权与防重放，且天然属于「控制面」（阶段 10）一起评估。
- **向量库 / 嵌入检索**：见 ADR 0010。

## 后果

- 单实例上限：不能多机 HA，重启会丢进程内状态（冷却、熔断、情绪）。
- 换来的好处：部署面最小、离线可测、没有额外凭据与网络入口。

## 重新评估条件（满足任一才重启讨论，并新增 ADR）

1. 需要多实例或多机部署（同一 Token 或多 Token 池）。
2. 需要跨进程共享限速/队列/去重状态。
3. 需要实时推送能力（Webhook 或长连接），或控制面板需要主动下发。
4. 检索质量被证明不足（词面召回漏掉关键历史）且 FTS5 调优已到上限。
5. 单机资源（CPU/内存/磁盘/Token 成本）成为瓶颈。

## 验证方式

- `requirements.txt` 中只有 `aiogram / openai / pydantic / pydantic-settings / aiosqlite / tzdata / aiohttp / httpx`，无 Redis/MQ/向量库依赖。
- `docs/architecture.md` §5 描述的调度与恢复完全在进程内。