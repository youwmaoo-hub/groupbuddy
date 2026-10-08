"""服务层：面板与 Telegram 通道共享的业务入口（唯一权威说明：docs/architecture.md §10）。

分层约定（`tests/offline/test_layering.py` 会检查）：
- 本层不 import 任何 Web 框架（fastapi / uvicorn / starlette）与 aiogram，也不读环境变量；
- 本层是唯一允许同时持有「数据库连接 + 业务规则」的地方，`app/control/` 只能调用本层，
  不得自己写 SQL，也不得直接触碰 `app/storage/`、工作区或沙箱。

分层带来的唯一好处写在 docs/security.md §2：面板与聊天指令走同一套校验与同一条写路径，
因此「面板能不能改、什么值合法」不会因为多了一个入口而出现第二个白名单。
"""
