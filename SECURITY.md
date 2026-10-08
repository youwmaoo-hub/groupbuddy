# 安全策略（SECURITY）

## 支持范围

| 版本 | 支持 |
|---|---|
| `main`（最新提交） | ✅ |
| 更早的提交 | ❌（请先更新到 `main`） |

本项目是自托管软件：安全边界由程序实现（权限判定、路径校验、沙箱调用都不交给模型），
但**部署环境本身的加固由部署者负责**（系统账号、防火墙、SSH 密钥、`.env` 文件权限等）。

## 报告漏洞

请不要为安全漏洞开公开 issue。请用 GitHub 的私密渠道：

**仓库 → Security → Advisories → Report a vulnerability**
（即 <https://github.com/youwmaoo-hub/groupbuddy/security/advisories/new>）

如果无法使用该入口，可以开一个**不含任何细节**的 issue 说明「需要私下联系渠道」。
报告中请包含：受影响的提交/文件、复现步骤（尽量最小）、影响（能做什么、需要什么前置条件）、
以及你建议的修复方向。**不要在报告里粘贴真实 Token、API Key 或群聊数据。**

我们尽力在 7 天内首次回复，并在修复发布后再公开细节（会署名，除非你要求匿名）。

## 在范围内

- 权限或沙箱逃逸：`run_code` 之外的宿主机执行、容器参数可被模型影响、路径穿越出
  `storage/workspaces/<chat_id>/`、只读根/无网络/非 root 等不变量被绕过。
- 凭据泄漏：Token/API Key 进入日志、数据库、错误消息、出站消息或版本库；日志脱敏集合漏项。
- 未授权的出站：绕过 `app/outbound/queue.py` 直发 Telegram、突破限速/退避/配额。
- 越权操作：非群管理员触发管理员命令、群级设置或人设覆盖被非授权者改写。
- 依赖或构建链问题（`requirements.txt`）。

## 不在范围内

- 需要持有有效 Bot Token、LLM Key 或管理员账号才能触发的「正常功能」。
- Telegram、DeepSeek/OpenAI 等上游服务自身的行为与可用性。
- 自托管环境加固（防火墙、SSH 配置、系统补丁、`.env` 权限）与硬件/平台问题。
- 社会工程、DoS 压测、以及模型输出内容的偏好问题（人格与语气不是安全边界）。

## 部署者须知

- 凭据只放在 `.env`（建议 `600`、属主为运行 Bot 的系统用户），永不入库；仓库里只有
  `.env.example` 的占位值。详见 `docs/security.md` §6。
- 不要公开运行数据库、`storage/`、备份与贴纸素材；`.gitignore` 已覆盖这些路径。
- `SANDBOX_BACKEND=auto` 在探测不到可用后端时会**拒绝执行**（fail-closed），不要为了「让它跑起来」
  改成宿主机执行。
- 生产实例建议只跑一个进程（长轮询 + 单 Bot Token），并按 `docs/deployment.md` 做备份与健康检查。
