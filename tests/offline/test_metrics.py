"""运行指标：健康状态、health.json 心跳、/stats 与 /health 文案（阶段 8 F5.4）。"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest import mock

import aiosqlite

from app.config import today_in_timezone
from app.ops.admin import AdminRegistry, ChatRoles
from app.ops.commands import DENIED_TEXT, Command, CommandService
from app.ops.health import HealthState, health_loop, write_snapshot
from app.ops.metrics import STATS_FAILED_TEXT, day_bounds, render_health, render_stats
from app.storage.repo import tool_failures, usage
from tests.offline.helpers import DbTestCase, FakeClock


def _state(**overrides: object) -> HealthState:
    values: dict[str, object] = {
        "instance_id": "bot-1",
        "started_at": 1000.0,
        "clock": FakeClock(start=1000.0).monotonic,
    }
    values.update(overrides)
    return HealthState(**values)  # type: ignore[arg-type]


class HealthStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_without_probes_is_ok(self) -> None:
        snapshot = await _state().snapshot()

        self.assertTrue(snapshot["ok"])
        self.assertTrue(snapshot["db_ok"])
        self.assertIsNone(snapshot["last_update_at"])
        self.assertIsNone(snapshot["outbound_pending"])

    async def test_mark_update_records_the_time(self) -> None:
        clock = FakeClock(start=1000.0)
        state = _state(clock=clock.monotonic)
        clock.advance(30.0)
        state.mark_update()

        snapshot = await state.snapshot()
        self.assertEqual(snapshot["last_update_at"], 1030.0)
        self.assertEqual(snapshot["uptime_s"], 30.0)

    async def test_database_failure_degrades_to_unreadable(self) -> None:
        async def boom() -> bool:
            raise RuntimeError("database is locked")

        snapshot = await _state(db_check=boom).snapshot()

        self.assertFalse(snapshot["ok"])
        self.assertFalse(snapshot["db_ok"])
        self.assertNotIn("locked", json.dumps(snapshot, ensure_ascii=False))

    async def test_pending_failure_is_reported_as_unknown(self) -> None:
        def boom() -> int:
            raise RuntimeError("队列读取失败")

        snapshot = await _state(pending=boom).snapshot()

        self.assertIsNone(snapshot["outbound_pending"])
        self.assertTrue(snapshot["ok"])

    async def test_pending_count_is_included(self) -> None:
        snapshot = await _state(pending=lambda: 3).snapshot()
        self.assertEqual(snapshot["outbound_pending"], 3)


class HealthSnapshotFileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.path = self.tmp / "health.json"

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def test_write_snapshot_is_atomic_valid_json_without_secrets(self) -> None:
        snapshot = {"instance": "bot-1", "ok": True, "db_ok": True, "outbound_pending": 0}
        write_snapshot(self.path, snapshot)

        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), snapshot)
        self.assertFalse(self.tmp.joinpath("health.json.tmp").exists())
        self.assertNotIn("token", self.path.read_text(encoding="utf-8"))

    async def test_health_loop_writes_then_stops(self) -> None:
        stop = asyncio.Event()
        state = _state()
        task = asyncio.create_task(health_loop(state, self.path, stop=stop, interval=0.01))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=1.0)

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["instance"], "bot-1")


class RenderHealthTests(unittest.TestCase):
    def test_healthy_snapshot_is_short_and_positive(self) -> None:
        text = render_health(
            {
                "instance": "bot-1",
                "ok": True,
                "db_ok": True,
                "uptime_s": 120.0,
                "last_update_at": 1000.0,
                "checked_at": 1060.0,
                "outbound_pending": 2,
            }
        )

        self.assertIn("状态：正常", text)
        self.assertIn("数据库：可读", text)
        self.assertIn("出站队列：2 条待发", text)
        self.assertIn("最后处理更新：1 分钟前", text)
        self.assertNotIn("请检查服务日志", text)

    def test_unhealthy_snapshot_is_actionable_without_internals(self) -> None:
        text = render_health(
            {
                "instance": "bot-1",
                "ok": False,
                "db_ok": False,
                "uptime_s": 5.0,
                "last_update_at": None,
                "checked_at": 1005.0,
                "outbound_pending": None,
            }
        )

        self.assertIn("状态：异常", text)
        self.assertIn("数据库：不可读", text)
        self.assertIn("最后处理更新：暂无", text)
        self.assertIn("出站队列：未知", text)
        self.assertIn("请检查服务日志后重试。", text)
        self.assertNotIn("/", text)  # 不含路径
        self.assertNotIn("Traceback", text)


class RenderStatsTests(DbTestCase):
    async def test_tokens_tool_calls_and_failures(self) -> None:
        day = today_in_timezone(self.settings)
        start, _ = day_bounds(self.settings)
        await usage.record(
            self.connection,
            chat_id=1,
            user_id=42,
            day=day,
            model="fake",
            input_tokens=100,
            cached_tokens=80,
            output_tokens=50,
            tool_calls=4,
            tool_ms=120,
        )
        for _ in range(2):
            await tool_failures.record(
                self.connection,
                tool="read_file",
                chat_id=1,
                error_code="timeout",
                created_at=start + 10,
            )
        # 别的群的数据不得混入
        await usage.record(
            self.connection, chat_id=2, user_id=43, day=day, model="fake", input_tokens=999, output_tokens=999
        )

        text = await render_stats(self.connection, self.settings, chat_id=1)

        self.assertIn(f"本群运行统计（{day} ", text)
        self.assertIn("模型调用：1 次", text)
        self.assertIn("Token：输入 100（缓存 80）/ 输出 50，合计 150", text)
        self.assertIn("工具调用：4 次，失败 2 次（错误率 50.0%）", text)
        self.assertNotIn("999", text)

    async def test_without_tool_calls_no_error_rate(self) -> None:
        await usage.record(
            self.connection,
            chat_id=1,
            user_id=42,
            day=today_in_timezone(self.settings),
            model="fake",
            input_tokens=10,
            output_tokens=5,
        )

        text = await render_stats(self.connection, self.settings, chat_id=1)

        self.assertIn("工具调用：0 次，失败 0 次", text)
        self.assertNotIn("错误率", text)

    async def test_failures_outside_today_are_excluded(self) -> None:
        start, _ = day_bounds(self.settings)
        await tool_failures.record(
            self.connection, tool="calc", chat_id=1, error_code="timeout", created_at=start - 1
        )

        text = await render_stats(self.connection, self.settings, chat_id=1)

        self.assertIn("失败 0 次", text)

    async def test_quota_line_when_configured(self) -> None:
        from tests.offline.helpers import make_settings

        settings = make_settings(self.tmp, QUOTA_DAILY_TOKENS=200)
        await usage.record(
            self.connection,
            chat_id=1,
            user_id=42,
            day=today_in_timezone(settings),
            model="fake",
            input_tokens=30,
            output_tokens=20,
        )

        text = await render_stats(self.connection, settings, chat_id=1)

        self.assertIn("配额：今日已用 50 / 200，本月已用 50 / 不限额", text)

    async def test_quota_line_when_unconfigured(self) -> None:
        text = await render_stats(self.connection, self.settings, chat_id=1)
        self.assertIn("配额：未设置限额（0 或未配置 = 不限额）", text)

    async def test_read_failure_returns_safe_text(self) -> None:
        with mock.patch.object(usage, "summary_for_day", side_effect=aiosqlite.Error("database is locked")):
            text = await render_stats(self.connection, self.settings, chat_id=1)

        self.assertEqual(text, STATS_FAILED_TEXT)
        self.assertNotIn("locked", text)
        self.assertNotIn("aiosqlite", text)


class CommandMetricsTests(DbTestCase):
    """`/stats` 与 `/health` 走既有命令通道：管理员可见、非管理员拒绝、0 token。"""

    def _service(self, *, admins=(42,), owner=None, **kwargs: object) -> CommandService:
        async def fetch(_chat_id: int) -> ChatRoles:
            return ChatRoles(admins=frozenset(admins), owner_id=owner)

        return CommandService(self.connection, AdminRegistry(fetch), **kwargs)  # type: ignore[arg-type]

    def _command(self, name: str) -> Command:
        return Command(name=name, args=(), mention="")

    async def test_stats_is_visible_to_admins(self) -> None:
        service = self._service(settings=self.settings, health=_state())

        text = await service.reply_text(chat_id=1, user_id=42, command=self._command("stats"))

        self.assertIsNotNone(text)
        self.assertIn("本群运行统计", text or "")

    async def test_health_is_visible_to_admins(self) -> None:
        service = self._service(settings=self.settings, health=_state())

        text = await service.reply_text(chat_id=1, user_id=42, command=self._command("health"))

        self.assertEqual(text, render_health(await _state().snapshot()))
        self.assertIn("状态：正常", text or "")

    async def test_non_admin_is_denied_without_details(self) -> None:
        service = self._service(admins=(7,), settings=self.settings, health=_state())

        for name in ("stats", "health"):
            text = await service.reply_text(chat_id=1, user_id=42, command=self._command(name))
            self.assertEqual(text, DENIED_TEXT)
            self.assertNotIn("统计", text or "")
            self.assertNotIn("状态", text or "")

    async def test_unwired_sources_are_silent(self) -> None:
        service = self._service()

        for name in ("stats", "health"):
            self.assertIsNone(await service.reply_text(chat_id=1, user_id=42, command=self._command(name)))


if __name__ == "__main__":
    unittest.main()
