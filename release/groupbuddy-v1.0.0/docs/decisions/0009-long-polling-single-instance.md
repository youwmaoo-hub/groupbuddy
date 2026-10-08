# ADR 0009：long polling + 单实例（一个 Token 一个进程）

状态：已接受
负责：为什么用 long polling 且只允许单实例。
上游：`docs/architecture.md` §5/§10、`docs/deployment.md` §6。
改动影响：推翻本决策时新增 ADR；同步 `docs/architecture.md` §5、`docs/deployment.md`。

## 背景

- Telegram 收更新只有两种方式：webhook 或 long polling；同一个 Token 同一时刻只能有一个 polling 消费者。
- 真机是单台 VPS，没有反向代理/证书配置（宝塔面板存在但未给本项目配置入口）。

## 决策

- 用 long polling（aiogram `start_polling`），一个 Token 一个进程（`app/main.py` 是唯一装配点）。
- 优雅关闭顺序固定：停止轮询 → 关闭出站队列 → 关闭数据库连接。
- 幂等靠数据库：`updates` 表去重 + `messages(chat_id, message_id)` 唯一键，重复投递不会产生重复回复。
- 实例生命周期交给部署（阶段 9 的 systemd / restart 策略），进程内不做自愈。

## 备选与放弃原因

- **Webhook 入站**：需要公网 HTTPS 端点、证书与鉴权，且与阶段 10 控制面耦合；当前没有收益（见 ADR 0008）。
- **多实例共享 Token**：会重复消费更新、重复回复，直接否决。

## 后果

- 不能水平扩展；升级 = 重启（期间不回复，符合验收预期）。
- 重启丢进程内状态：冷却、熔断、情绪（`MoodTracker`）；持久化语义只在数据库里。
- 单点故障：进程挂了就停止响应，需要阶段 9 的进程托管。

## 验证方式

- `tests/offline/` 中的入站幂等、去重与「本轮只处理开始时已入库的消息」用例。
- 真机：单进程运行，无 systemd 单元（阶段 7 只验收沙箱能力，未上线，见 `docs/status.md` §5）。