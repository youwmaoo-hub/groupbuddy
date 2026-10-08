"""面板 HTTP 路由（唯一 Web 入口）。

只做四件事：鉴权、解析请求、调用服务层、把结果转成 JSON。
**不写 SQL、不碰文件、不读环境变量、不 import aiogram**：所有业务判断都在 `app/services/`，
这样面板和 Telegram 通道不会长出两套规则（docs/architecture.md §10）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.control.auth import AUTH_HEADER, ApiError, Level, PanelAuth
from app.services import credentials as credential_service
from app.services import overview as overview_service
from app.services import settings as group_settings
from app.services.context import ServiceContext

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).with_name("static")

#: 接口返回的行数上限（与 `app/services/overview.py` 的预算一致，避免前端传个天文数字）。
MAX_LOG_LINES = overview_service.MAX_LOG_LINES


def create_app(context: ServiceContext, *, auth: PanelAuth) -> FastAPI:
    """装配面板应用；未配置任何口令时直接拒绝（不提供"无鉴权模式"）。"""
    if not auth.configured:
        raise ValueError("面板未配置访问口令，拒绝启动：请设置 PANEL_TOKEN（或 PANEL_READONLY_TOKEN）")

    app = FastAPI(
        title="GroupBuddy 控制面板",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # 具体异常只进日志（日志有脱敏过滤器），回给前端的是固定文案。
        logger.error("面板请求失败 path=%s error=%s", request.url.path, type(exc).__name__, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal", "message": "面板内部错误，请查看服务日志。"}},
        )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; "
            "img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def _level(request: Request) -> Level:
        level = auth.level_from_header(request.headers.get(AUTH_HEADER))
        if level is Level.NONE:
            raise ApiError(401, "unauthorized", "缺少或错误的面板口令。")
        return level

    def _admin(level: Level) -> None:
        if level < Level.ADMIN:
            raise ApiError(403, "forbidden", "当前口令是只读口令，不能修改任何设置。")

    async def _json_body(request: Request) -> dict[str, object]:
        try:
            payload = await request.json()
        except Exception as error:  # noqa: BLE001 - 任何解析失败都归为请求体不合法
            raise ApiError(400, "bad_json", "请求体不是合法 JSON。") from error
        if not isinstance(payload, dict):
            raise ApiError(400, "bad_json", "请求体必须是 JSON 对象。")
        return payload

    def _text_field(payload: dict[str, object], name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str):
            raise ApiError(400, "bad_request", f"字段 {name} 必须是字符串。")
        return value

    @app.get("/")
    async def index() -> FileResponse:
        # 静态壳不含任何数据；数据接口一律需要口令。
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/session")
    async def session(request: Request) -> dict[str, object]:
        level = _level(request)
        return {
            "level": level.name.lower(),
            "readonly": level < Level.ADMIN,
            "instance": context.settings.instance_id,
            "fields": group_settings.as_payload(group_settings.fields()),
            "max_log_lines": MAX_LOG_LINES,
        }

    @app.get("/api/overview")
    async def overview(request: Request) -> dict[str, object]:
        _level(request)
        data = await overview_service.build(
            context.connection, context.settings, health_path=context.health_path
        )
        return dict(group_settings.as_payload(data))

    @app.get("/api/groups")
    async def groups(request: Request) -> dict[str, object]:
        _level(request)
        rows = await group_settings.list_groups(context.connection)
        return {"groups": group_settings.as_payload(rows)}

    @app.get("/api/groups/{chat_id}")
    async def group_detail(chat_id: int, request: Request) -> dict[str, object]:
        _level(request)
        group = await group_settings.read_group(context.connection, chat_id)
        return {"group": group_settings.as_payload(group)}

    @app.put("/api/groups/{chat_id}/settings")
    async def update_group(chat_id: int, request: Request) -> dict[str, object]:
        _admin(_level(request))
        payload = await _json_body(request)
        field = _text_field(payload, "field")
        value = _text_field(payload, "value")
        try:
            # 面板管理员口令 = 部署者本人，等价于 Telegram 侧"群主"才有的权限位。
            group = await group_settings.update_group(
                context.connection, chat_id, field=field, value=value, allow_persona=True
            )
        except group_settings.SettingError as error:
            raise ApiError(400, "invalid_setting", str(error)) from error
        return {"group": group_settings.as_payload(group)}

    @app.get("/api/credentials")
    async def credentials(request: Request) -> dict[str, object]:
        # 凭据状态（有没有、来源）属于运维信息：只读口令连"配了哪些"都不该看到。
        _admin(_level(request))
        items = credential_service.status(context.settings, env_path=context.env_path)
        return {
            "env_file": context.env_path.name,
            "credentials": group_settings.as_payload(items),
        }

    @app.put("/api/credentials/{name}")
    async def write_credential(name: str, request: Request) -> dict[str, object]:
        _admin(_level(request))
        payload = await _json_body(request)
        value = _text_field(payload, "value")
        try:
            credential_service.write(env_path=context.env_path, name=name, value=value)
        except credential_service.CredentialError as error:
            raise ApiError(400, "invalid_credential", str(error)) from error
        return {
            "ok": True,
            "restart_required": True,
            "credentials": group_settings.as_payload(
                credential_service.status(context.settings, env_path=context.env_path)
            ),
        }

    @app.delete("/api/credentials/{name}")
    async def clear_credential(name: str, request: Request) -> dict[str, object]:
        _admin(_level(request))
        try:
            credential_service.clear(env_path=context.env_path, name=name)
        except credential_service.CredentialError as error:
            raise ApiError(400, "invalid_credential", str(error)) from error
        return {
            "ok": True,
            "restart_required": True,
            "credentials": group_settings.as_payload(
                credential_service.status(context.settings, env_path=context.env_path)
            ),
        }

    @app.get("/api/logs")
    async def logs(request: Request, lines: int = overview_service.DEFAULT_LOG_LINES) -> dict[str, object]:
        _level(request)
        if lines < 1 or lines > MAX_LOG_LINES:
            raise ApiError(400, "bad_request", f"lines 必须在 1 到 {MAX_LOG_LINES} 之间。")
        return {"lines": overview_service.tail_log(context.settings, lines=lines)}

    return app
