"""面板 HTTP 契约（唯一权威说明：docs/requirements.md F6）。

测试用手写的最小 ASGI 客户端：项目未安装 httpx，`fastapi.testclient` 依赖它，
而为一个测试引入新依赖不值得（AGENTS.md §3.1）。这里只发一次请求、收一次响应，
足够覆盖鉴权、读写与脱敏。
"""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from typing import Any

from app.control.app import MAX_LOG_LINES, create_app
from app.control.auth import PanelAuth
from app.ops.health import write_snapshot
from app.services.context import ServiceContext
from app.storage.repo import chat_settings, messages
from tests.offline.helpers import DbTestCase

ADMIN = "admin-token-123456"
READONLY = "readonly-token-1234"
SECRET_VALUE = "sk-panel-secret-0123456789"


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    data: Any
    text: str
    headers: dict[str, str]

    @property
    def error_code(self) -> str:
        return str(self.data["error"]["code"]) if isinstance(self.data, dict) and "error" in self.data else ""


class AsgiClient:
    """最小 ASGI 客户端：够用就好，不引入 httpx。"""

    def __init__(self, application: Any) -> None:
        self._application = application

    async def request(
        self,
        method: str,
        path: str,
        *,
        token: str = "",
        body: object | None = None,
        query: str = "",
    ) -> Response:
        raw = b"" if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = [(b"host", b"panel.test")]
        if body is not None:
            headers.append((b"content-type", b"application/json"))
        if token:
            headers.append((b"authorization", f"Bearer {token}".encode("utf-8")))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query.encode("utf-8"),
            "root_path": "",
            "headers": headers,
            "client": ("127.0.0.1", 41234),
            "server": ("panel.test", 80),
        }
        sent: list[dict[str, Any]] = []
        request_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": raw, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        try:
            await self._application(scope, receive, send)
        except Exception:
            # starlette 的 ServerErrorMiddleware 发完 500 响应后仍会把异常重新抛出
            # （真实服务器同样只在日志里记录）。响应已经发出时按真实行为忽略。
            if not any(message["type"] == "http.response.start" for message in sent):
                raise

        status = 200
        out_headers: dict[str, str] = {}
        payload = b""
        for message in sent:
            if message["type"] == "http.response.start":
                status = int(message["status"])
                out_headers = {
                    key.decode("latin-1").lower(): value.decode("latin-1")
                    for key, value in message.get("headers", [])
                }
            elif message["type"] == "http.response.body":
                payload += message.get("body", b"")

        text = payload.decode("utf-8", errors="replace")
        try:
            data: Any = json.loads(text) if text else None
        except ValueError:
            data = None
        return Response(status=status, data=data, text=text, headers=out_headers)


class PanelApiTests(DbTestCase):
    SETTINGS_OVERRIDES = {"PANEL_TOKEN": ADMIN, "PANEL_READONLY_TOKEN": READONLY}

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.env_path = self.tmp / ".env"
        self.env_path.write_text("BOT_TOKEN=test-token\nLLM_API_KEY=test-key\n", encoding="utf-8")
        self.health_path = self.settings.data_dir / "health.json"
        context = ServiceContext(
            connection=self.connection,
            settings=self.settings,
            env_path=self.env_path,
            health_path=self.health_path,
        )
        self.client = AsgiClient(
            create_app(context, auth=PanelAuth(admin_token=ADMIN, readonly_token=READONLY))
        )

    async def _get(self, path: str, *, token: str = ADMIN, query: str = "") -> Response:
        return await self.client.request("GET", path, token=token, query=query)

    async def _put(self, path: str, body: object, *, token: str = ADMIN) -> Response:
        return await self.client.request("PUT", path, token=token, body=body)

    # --- 鉴权 ---

    async def test_requires_token(self) -> None:
        for token in ("", "wrong-token-12345678"):
            with self.subTest(token=token):
                response = await self._get("/api/overview", token=token)
                self.assertEqual(401, response.status)
                self.assertEqual("unauthorized", response.error_code)

    async def test_readonly_token_can_read(self) -> None:
        response = await self._get("/api/overview", token=READONLY)
        self.assertEqual(200, response.status)

    async def test_session_reports_level_and_fields(self) -> None:
        admin = await self._get("/api/session")
        self.assertEqual("admin", admin.data["level"])
        self.assertFalse(admin.data["readonly"])
        names = [field["name"] for field in admin.data["fields"]]
        self.assertIn("mode", names)
        self.assertIn("write_file", names)  # 工具开关用工具名（与 /settings 一致）
        self.assertIn("persona_override", names)
        persona = next(field for field in admin.data["fields"] if field["name"] == "persona_override")
        self.assertTrue(persona["owner_only"])

        viewer = await self._get("/api/session", token=READONLY)
        self.assertEqual("viewer", viewer.data["level"])
        self.assertTrue(viewer.data["readonly"])

    async def test_readonly_cannot_write_anything(self) -> None:
        blocked = await self._put(
            "/api/groups/100/settings", {"field": "allow_write", "value": "on"}, token=READONLY
        )
        self.assertEqual(403, blocked.status)
        self.assertEqual("forbidden", blocked.error_code)
        row = await chat_settings.get(self.connection, 100)
        self.assertEqual(0, row["allow_write"])

        self.assertEqual(403, (await self._get("/api/credentials", token=READONLY)).status)
        self.assertEqual(
            403,
            (await self._put("/api/credentials/LLM_API_KEY", {"value": SECRET_VALUE}, token=READONLY)).status,
        )

    # --- 群设置：与 /settings 同一条路径 ---

    async def test_admin_updates_single_field(self) -> None:
        await chat_settings.upsert(self.connection, 100, mode="smart")
        response = await self._put("/api/groups/100/settings", {"field": "allow_write", "value": "on"})
        self.assertEqual(200, response.status)
        self.assertTrue(response.data["group"]["toggles"]["write_file"])  # toggles 的键是工具名
        row = await chat_settings.get(self.connection, 100)
        self.assertEqual(1, row["allow_write"])
        self.assertEqual("smart", row["mode"])  # 单字段写入不影响其它字段

    async def test_invalid_field_and_value_are_rejected_in_chinese(self) -> None:
        for field, value in (("nope", "on"), ("allow_write", "yes"), ("sticker_cooldown", "99999")):
            with self.subTest(field=field, value=value):
                response = await self._put(
                    f"/api/groups/100/settings", {"field": field, "value": value}
                )
                self.assertEqual(400, response.status)
                self.assertEqual("invalid_setting", response.error_code)

    async def test_malformed_body_is_rejected(self) -> None:
        response = await self._put("/api/groups/100/settings", {"field": "mode"})
        self.assertEqual(400, response.status)
        self.assertEqual("bad_request", response.error_code)

    async def test_persona_is_written_and_cleared(self) -> None:
        written = await self._put(
            "/api/groups/100/settings", {"field": "persona_override", "value": "  面板人设  "}
        )
        self.assertEqual(200, written.status)
        self.assertEqual("面板人设", written.data["group"]["persona_override"])

        cleared = await self._put("/api/groups/100/settings", {"field": "persona_override", "value": "off"})
        self.assertEqual(200, cleared.status)
        self.assertEqual("", cleared.data["group"]["persona_override"])

    # --- 群列表与概览 ---

    async def test_group_list_covers_configured_and_active_chats(self) -> None:
        await chat_settings.upsert(self.connection, 100, mode="economy")
        await messages.insert(
            self.connection, chat_id=200, message_id=1, user_id=7, role="user", text="hi"
        )
        response = await self._get("/api/groups")
        self.assertEqual(200, response.status)
        by_id = {group["chat_id"]: group for group in response.data["groups"]}
        self.assertEqual({"100", "200"}, set(map(str, by_id)))
        self.assertEqual("economy", by_id[100]["mode"])
        self.assertEqual(1, by_id[200]["messages"])
        self.assertNotIn("hi", response.text)  # 面板不给聊天原文

    async def test_overview_reports_missing_heartbeat_then_reads_it(self) -> None:
        empty = await self._get("/api/overview")
        self.assertEqual(200, empty.status)
        self.assertIsNone(empty.data["health_ok"])
        self.assertIsNone(empty.data["heartbeat_at"])
        self.assertTrue(empty.data["db_ok"])

        write_snapshot(
            self.health_path,
            {"instance": "default", "ok": True, "checked_at": 1000.0, "uptime_s": 60.0},
        )
        filled = await self._get("/api/overview")
        self.assertTrue(filled.data["health_ok"])
        self.assertEqual("default", filled.data["instance"])
        self.assertEqual(1000.0, filled.data["heartbeat_at"])

    # --- 凭据：只写不读 ---

    async def test_credential_write_never_echoes_value(self) -> None:
        response = await self._put("/api/credentials/LLM_API_KEY", {"value": SECRET_VALUE})
        self.assertEqual(200, response.status)
        self.assertNotIn(SECRET_VALUE, response.text)
        self.assertTrue(response.data["restart_required"])
        entry = next(item for item in response.data["credentials"] if item["name"] == "LLM_API_KEY")
        self.assertTrue(entry["configured"])
        self.assertEqual(".env", entry["source"])

        stored = self.env_path.read_text(encoding="utf-8")
        self.assertIn(SECRET_VALUE, stored)
        self.assertEqual(1, stored.count("LLM_API_KEY="))

        status = await self._get("/api/credentials")
        self.assertNotIn(SECRET_VALUE, status.text)
        self.assertEqual(".env", status.data["env_file"])

    async def test_credential_delete_and_unknown_name(self) -> None:
        await self._put("/api/credentials/LLM_API_KEY", {"value": SECRET_VALUE})
        removed = await self.client.request("DELETE", "/api/credentials/LLM_API_KEY", token=ADMIN)
        self.assertEqual(200, removed.status)
        self.assertNotIn(SECRET_VALUE, self.env_path.read_text(encoding="utf-8"))

        unknown = await self.client.request("DELETE", "/api/credentials/PATH", token=ADMIN)
        self.assertEqual(400, unknown.status)
        self.assertEqual("invalid_credential", unknown.error_code)

    async def test_credential_value_with_newline_is_rejected(self) -> None:
        response = await self._put(
            "/api/credentials/LLM_API_KEY", {"value": "sk-abc\nLLM_BASE_URL=http://evil"}
        )
        self.assertEqual(400, response.status)
        self.assertNotIn("evil", self.env_path.read_text(encoding="utf-8"))

    # --- 日志 ---

    async def test_logs_are_redacted_and_bounded(self) -> None:
        log_path = self.settings.log_dir / self.settings.log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "\n".join(
                [
                    f"2026-10-08 INFO app 配置 {self.settings.bot_token}",
                    f"2026-10-08 INFO app 面板口令 {ADMIN}",
                    "2026-10-08 INFO app 普通一行",
                ]
            ),
            encoding="utf-8",
        )
        response = await self._get("/api/logs", query="lines=2")
        self.assertEqual(200, response.status)
        self.assertEqual(2, len(response.data["lines"]))
        self.assertNotIn(self.settings.bot_token, response.text)
        self.assertNotIn(ADMIN, response.text)
        self.assertIn("[redacted]", response.text)

        too_many = await self._get("/api/logs", query=f"lines={MAX_LOG_LINES + 1}")
        self.assertEqual(400, too_many.status)

    # --- 静态壳与安全响应头 ---

    async def test_static_shell_has_no_inline_code(self) -> None:
        shell = await self._get("/")
        self.assertEqual(200, shell.status)
        self.assertIn("控制面板", shell.text)
        self.assertNotIn("<script>", shell.text)  # CSP 禁止内联脚本，全部走 /static/app.js

    async def test_security_headers_are_set(self) -> None:
        response = await self._get("/api/overview")
        self.assertIn("default-src 'none'", response.headers.get("content-security-policy", ""))
        self.assertEqual("no-store", response.headers.get("cache-control"))
        self.assertEqual("nosniff", response.headers.get("x-content-type-options"))

    async def test_unexpected_errors_do_not_leak_details(self) -> None:
        from unittest import mock

        from app.services import settings as group_settings

        with mock.patch.object(
            group_settings.messages, "chat_activity", side_effect=RuntimeError("内部细节不该外泄")
        ):
            response = await self._get("/api/groups")
        self.assertEqual(500, response.status)
        self.assertEqual("internal", response.error_code)
        self.assertNotIn("内部细节不该外泄", response.text)


class PanelStartupTests(unittest.TestCase):
    def test_create_app_refuses_without_tokens(self) -> None:
        with self.assertRaises(ValueError):
            create_app(object(), auth=PanelAuth())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
