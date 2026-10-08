# 文档入口

负责：文档入口、阅读顺序、改动路由表、文档元数据约定。
上游：无。
改动影响：新增/重命名文档时更新本文件。

## 1. 默认阅读顺序（按需停止）

0. 从 GitHub 第一次进来先读仓库根目录的 `README.md`（项目定位、快速开始、离线测试、目录结构），再回到本文件的路由表。
1. `AGENTS.md` — 怎么干活（每个任务都先读）。
2. `docs/requirements.md` — 要做什么、优先级、验收标准。
3. 目标的**归属文档**（见下表）→ 然后才看代码。
4. 需要排期或确认阶段边界时读 `TODO.md`；与部署、VPS 运维、持久化相关时读 `docs/deployment.md`。

不要为了"了解全貌"通读全部文档；按任务只读 1–3 个。

## 2. 改动路由表（"要改 X → 读哪个文件"）

| 要改 / 要查的东西 | 读这个 | 不要读 |
|---|---|---|
| 开发方式、任务边界、完成标准 | `AGENTS.md` | 其他文档 |
| 分层、模块职责、数据流、并发、恢复、扩展预留 | `docs/architecture.md` | requirements |
| 需求条目、行为规则、优先级、验收标准、未决问题 | `docs/requirements.md` | architecture |
| 什么时候说话、判定顺序、原因码、冷却与重复过滤 | `docs/requirements.md` §2.1 | 其他文档（只引用） |
| 人格、语气、情绪、人设边界 | `docs/persona.md` | 其他文档（只引用） |
| 对象、身份、租户键、凭据归属、控制面板边界 | `docs/domain.md` | 其他文档（只引用） |
| 某个工具的输入/输出/等级/超时/错误码 | `docs/tools.md` | security（只引用） |
| 权限、路径、沙箱、网络、密钥、日志、429 | `docs/security.md` | tools（只引用） |
| 上下文窗口、摘要模板、FTS 检索 | `docs/memory.md` | database |
| 表结构、索引、迁移、保留清理 | `docs/database.md` | memory |
| Token/成本优化（开发侧 + 运行侧） | `docs/token.md` | 其他 |
| 阶段划分与阶段验收标准 | `TODO.md` | docs/（细节） |
| 当前 commit、阶段进度、测试数字、真机验收证据、技术债摘要 | `docs/status.md` | 其他文档（只引用） |
| 某个设计为什么这样定、放弃过哪些方案 | `docs/decisions/` | 其他文档（只引用） |
| 运行环境、Docker/systemd、持久化目录、备份恢复、健康检查、优雅关闭、换机迁移、VPS 上线准备（rootless Podman / subuid-subgid / 预拉镜像 / 沙箱验收） | `docs/deployment.md` | architecture（只引用） |
| 控制面板怎么开、怎么用、怎么关、改了什么什么时候生效 | `docs/deployment.md` §13（可选进程与运维） | 其他文档（只引用） |
| 控制面板为什么用 FastAPI、为什么不用 Cookie、为什么默认关闭 | `docs/decisions/0011-control-panel-fastapi.md` | 其他文档（只引用） |

## 3. 文件清单与唯一职责

| 文件 | 唯一负责 |
|---|---|
| `AGENTS.md` | 开发规则与工作方式 |
| `docs/README.md` | 入口与路由（本文件） |
| `docs/architecture.md` | 架构、模块边界、数据流、并发 |
| `docs/requirements.md` | 需求与验收 |
| `docs/persona.md` | 全局人格与三层人设分离 |
| `docs/domain.md` | 领域对象、身份模型、租户键与面板边界 |
| `docs/tools.md` | 工具契约 |
| `docs/security.md` | 安全边界与权限 |
| `docs/memory.md` | 记忆与检索策略 |
| `docs/database.md` | 数据模型与迁移 |
| `docs/token.md` | Token/成本策略 |
| `TODO.md` | 阶段路线图、阶段验收标准与技术债登记 |
| `docs/status.md` | 当前基线、测试与验收证据、技术债摘要（唯一事实来源） |
| `docs/decisions/` | 已接受的设计决策（ADR）与被放弃的方案 |
| `docs/deployment.md` | 运行环境契约与部署运维（唯一权威） |

## 4. 元数据约定（每个文档头部必须有三行）

```
负责：<本文件回答的唯一问题>
上游：<改本文件前必须先看什么>
改动影响：<改本文件需要同步更新哪些文件/位置>
```

## 5. 引用约定

- 引用具体条目用锚点式写法：`见 docs/tools.md §run_code`。
- 规则只在归属文件里写完整内容；其他文件只允许一句话引用。
- 术语以本目录为准：`chat_id`（群）、`thread_id`（论坛主题，预留）、
  `workspace`（每群工作区）、`Trigger`（发言闸门）、`Policy`（程序侧权限判定）、
  `OutboundQueue`（出站队列）、L0–L4（工具等级）、
  `BotInstance`（实例，租户键第一段）、`Credential`（凭据，归属实例）、
  `Principal`（运行期请求主体，Web 用户与 Telegram 用户不复用）、控制面板（Control API，阶段 10 已实施：
  独立进程 `python -m app.control`，见 `docs/deployment.md` §13 与 ADR 0011）、
  本轮（round，一次回复任务的边界：只处理开始时已入库的消息）、情绪（mood，动态段末条的可选语气状态）。
