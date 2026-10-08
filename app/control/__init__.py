"""控制面板适配器（阶段 10，docs/architecture.md §10）。

分层（`tests/offline/test_layering.py` 有对应不变量）：
- 本目录是唯一允许出现 Web 框架（fastapi / starlette / uvicorn）的地方；
- `auth.py`、`app.py` 不得直接 import `app.storage.*`、不得 import aiogram，
  也不得读环境变量——所有数据一律经 `app/services/` 取，凭据一律经 `Settings` 取；
- `__main__.py` 是本目录的装配根（建库连接、起 uvicorn），因此它允许 import
  `app.storage.db` 与 uvicorn。

Web 访问者不是 Telegram 用户（docs/requirements.md F6.6）：面板只认自己的口令，
绝不接受来自前端的 Telegram 身份声明。
"""
