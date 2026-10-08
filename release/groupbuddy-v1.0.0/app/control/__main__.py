"""面板进程入口：`python -m app.control`（装配根，允许 import storage 与 uvicorn）。

与机器人进程的关系：**独立进程、共用同一个 SQLite 库**（WAL + `busy_timeout=5000`，
见 `app/storage/db.py`）。因此面板随时可以重启，而机器人继续在跑；面板改完凭据只提示
"重启机器人后生效"，绝不代替操作者去重启另一个进程。
"""

from __future__ import annotations

import asyncio
import sys

import uvicorn

from app.config import Settings, load_settings
from app.control.app import create_app
from app.control.auth import PanelAuth
from app.logging_setup import setup_logging
from app.services.context import ServiceContext
from app.storage.db import close_db, open_db


def _panel_auth(settings: Settings) -> PanelAuth:
    return PanelAuth(
        admin_token=settings.panel_token,
        readonly_token=settings.panel_readonly_token,
    )


def _refuse(reason: str) -> int:
    print(f"面板未启动：{reason}", file=sys.stderr)
    return 2


async def _serve(settings: Settings) -> None:
    connection = await open_db(settings)
    try:
        context = ServiceContext.build(connection, settings)
        app = create_app(context, auth=_panel_auth(settings))
        config = uvicorn.Config(
            app,
            host=settings.panel_host,
            port=settings.panel_port,
            log_level=settings.log_level.lower(),
            # 用项目自己的日志（含脱敏过滤器）；关掉访问日志，避免任何凭据经 URL 落盘。
            log_config=None,
            access_log=False,
            server_header=False,
        )
        await uvicorn.Server(config).serve()
    finally:
        await close_db(connection)


def main() -> int:
    """启动面板；配置不合法时给出可操作的中文提示并以退出码 2 结束。"""
    try:
        settings = load_settings()
    except Exception as error:  # pydantic ValidationError 不在此 import 以免多一层依赖
        print(f"配置无效：{error}", file=sys.stderr)
        return 2
    if not settings.panel_enabled:
        return _refuse("配置项 PANEL_ENABLED 不是 true（默认关闭）。")
    if not settings.panel_token and not settings.panel_readonly_token:
        return _refuse("没有配置 PANEL_TOKEN 或 PANEL_READONLY_TOKEN，拒绝在无口令下开放面板。")
    setup_logging(settings)
    asyncio.run(_serve(settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
