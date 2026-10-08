# ADR 0011：控制面板用 FastAPI + 零构建静态页，独立进程只经服务层

状态：已接受
负责：为什么引入 FastAPI/uvicorn、面板为什么是独立进程、面板的授权与凭据边界怎么定。
上游：`docs/requirements.md` F6、`docs/architecture.md` §2/§10、`docs/domain.md` §3/§4、`docs/security.md` §2/§6、ADR 0007、ADR 0009。
改动影响：`requirements.txt` 新增可选依赖；新增 `app/control/`（HTTP 适配器）与 `app/services/`（业务入口）；`docs/deployment.md` 新增面板部署与运维章节；`docs/architecture.md` §2/§3/§7/§10、`docs/domain.md` §1/§6、`docs/security.md` §6、`docs/status.md` §2/§7 同步。

## 背景

- 阶段 10 之前，所有运维都靠 Telegram 命令（`/settings`、`/stats`、`/health`）加 SSH 改 `.env`；`docs/status.md` §5 记录的凭据轮换、群设置巡检、日志查看都需要登机器。
- `docs/architecture.md` §2 早已定下「适配器 → 服务 → 领域/存储」三层，并把 `app/control/` 与 `app/services/` 写成阶段 10 的预留；`docs/domain.md` §6 当时明确「不引入 Web 框架与前端依赖」。
- `AGENTS.md` §3.21 把引入 Web 框架定为必须先出方案确认的改动；用户在本轮明确选择「Web 面板 + 引入 FastAPI/前端栈」。

## 决策

1. **框架**：后端用 FastAPI + uvicorn，作为**可选依赖**写在 `requirements.txt` 末尾，只允许 `app/control/` import；不装这两个包时机器人进程完全不受影响。前端是 `app/control/static/` 里的原生 HTML/CSS/JS，**没有构建步骤、没有 npm、没有前端依赖**。
2. **进程形态**：面板是**独立进程** `python -m app.control`，与机器人**共用同一个 SQLite 库**（WAL + `busy_timeout=5000`，见 `app/storage/db.py`）。面板随时可重启，机器人继续跑；面板不代替操作者去重启另一个进程，改完凭据只回 `restart_required: true`。
3. **分层**：`app/control/` 只做鉴权、解析请求、调服务层、转 JSON——不写 SQL、不碰文件、不读环境变量、不 import aiogram。业务判断全在 `app/services/`（`context` / `settings` / `overview` / `credentials`），与 Telegram 适配器共用同一条写路径与同一套校验（`app/ops/commands.py` 的 `resolve_setting` / `resolve_persona_setting`）。
4. **授权只由后端判定**：口令走 `Authorization: Bearer <token>` 头，服务端用 `hmac.compare_digest` 比对，`PANEL_TOKEN` → ADMIN、`PANEL_READONLY_TOKEN` → VIEWER，其余 401/403。不用 Cookie、不进 URL，因此没有 CSRF 面，也不会把口令写进访问日志。前端隐藏按钮只是界面礼貌。
5. **凭据只写不读**：`GET /api/credentials` 只返回「配没配 + 来源」，永不返回明文或掩码；写入走 `PUT /api/credentials/{name}`，按 name 精确改 `.env` 行（同目录临时文件 + `chmod 0600` + `os.replace`），删除走 `DELETE`（幂等）。
6. **默认关闭**：`PANEL_ENABLED=false`、默认只监听 `127.0.0.1:8787`、没有口令时**拒绝启动**，不提供「无鉴权模式」。

## 备选与放弃原因

- **面板直连 SQLite / 自己写 SQL**：最省事，但会长出第二套校验与授权规则，Telegram 侧和面板侧的群设置可能不一致；`docs/requirements.md` §3 已把这条列为否定方案。
- **前端框架 + 构建链（React/Vue/Vite）**：对「看状态、改开关、轮换凭据」这点规模，构建链带来的依赖与维护成本远超收益，违反 `AGENTS.md` §3.1「引入新依赖需先确认」。
- **Cookie/Session 登录页**：需要会话存储、CSRF 防护与「多用户身份」模型（`docs/domain.md` §3 的 `Principal`），而面板目前只有「部署者本人」一个使用者，用 Bearer 头即可。
- **面板内嵌进机器人进程**：省一个进程，但面板的依赖与生命周期会绑住消息主循环；面板自身崩溃不该影响回复。
- **面板代管机器人进程（启动/停止/重启）**：跨进程生命周期管理要额外的权限与故障面，交给部署层（systemd 用户级单元）负责。
- **用 Webhook 入站替代 long polling**：仍见 ADR 0008；面板不解决入站问题。

## 后果

- 依赖面增加 `fastapi` / `uvicorn` 两个可选包；不部署面板的实例不装也不影响。
- 面板与机器人**同时只读**同一库没问题，但两者都会写：面板写 `chat_settings` 与 `.env`，机器人写消息/用量等表；`AGENTS.md` §3.11 不变——凭据不进代码、日志、DB、测试。
- 群设置改完**下一轮消息即生效**（`app/session/runner.py:173` 每轮读 `chat_settings.get`），凭据改完需要重启机器人后生效。
- 面板只监听回环地址；要远程访问必须由部署者自己加 SSH 隧道或反向代理，本项目不提供公网暴露方案（`docs/deployment.md` §13）。

## 验证方式

- `tests/offline/test_control_auth.py`：口令 → 级别、空白与错误口令一律 NONE/BEARER 头解析 fail-closed。
- `tests/offline/test_control_api.py`：只读口令写设置 403、无口令 401、错误详情不外泄、凭据写入不回显明文、日志尾部脱敏且有行数上限、安全响应头与静态壳无内联代码、心跳缺失时概览降级。
- `tests/offline/test_control_auth.py`：口令 → 级别、空白与错误口令一律 NONE、`Authorization` 头解析 fail-closed、`describe()` 永不打印口令。
- `tests/offline/test_layering.py`：`fastapi/starlette/uvicorn` 只能出现在 `app/control/`；`app/services/` 不 import Web 框架与 aiogram。
- `tests/offline/test_control_api.py` 的 `PanelApiTests` 同时覆盖服务层（`app/services/settings.py` 的字段校验、`overview.py` 的降级、`credentials.py` 的写入与状态）。
