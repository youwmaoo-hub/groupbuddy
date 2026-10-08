# ADR 0006：凭据不进 Git、不进日志

状态：已接受
负责：凭据为什么不进 Git、不进日志。
上游：`docs/security.md` §6、`docs/deployment.md` §12。
改动影响：推翻本决策时新增 ADR；同步 `docs/security.md` §6 与 `.env.example`。

## 背景

- `.env` 里有 `BOT_TOKEN` 与 `LLM_API_KEY`；仓库需要跨机器传输（离线 bundle → VPS），将来可能同步到 GitHub。
- 日志、错误消息、模型上下文都可能把凭据泄漏出去。

## 决策

- `.env` 永不入库（`.gitignore` 第一行），仓库只提供 `.env.example`（值全是占位符）。
- 凭据只经 `Settings.bot_instance()` / `Credential` 读取；任何接口不得返回明文；新增凭据必须登记进日志脱敏集合（`AGENTS.md` §3.16）。
- 日志与错误消息脱敏（`SecretFilter`）；文档、汇报、测试夹具一律不写真实值；Agent 不读取也不输出 `.env` 内容。
- 产品数据（消息、摘要、笔记）按正常数据路径入库，与凭据分开对待（`AGENTS.md` §3.11）。

## 备选与放弃原因

- **只用系统环境变量**：凭据仍进进程环境与子进程白名单，还需要额外清理逻辑，收益不明显。
- **密钥管理服务 / 面板下发**：属阶段 10 控制面，当前不引入（ADR 0008）。

## 后果

- 部署必须手工创建 `.env`；缺必填键时启动即 fail-closed 报错。
- 现场排查不能直接打印配置对象（要经脱敏），排障手段变少但可接受。
- `SecretFilter` 已有专门测试（`tests/offline/test_logging.py`：msg / tuple args / dict args 三条脱敏路径，以及根 logger 装配后写进轮转文件的内容确实不含凭据；技术债 T25 已补）。

## 验证方式

- `git check-ignore -v .env` 命中 `.gitignore`；`git ls-files` 中不存在 `.env`。
- 启动校验：缺 `BOT_TOKEN` / `LLM_API_KEY` 时启动失败并给出键名（不含值）。