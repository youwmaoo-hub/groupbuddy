"""进程入口离线测试：数据库探测、工具失败留痕、关闭路径与信号注册（app/main.py、T25）。

不启动真实 Bot/网络：只覆盖无需 Telegram 的关键函数与 Application 的生命周期收尾。
"""

from __future__ import annotations

import asyncio
import signal
import unittest
from unittest import mock

from app.main import Application, _database_readable, _install_signal_handlers, _tool_failure_recorder
from tests.offline.helpers import DbTestCase


class DatabaseProbeTests(DbTestCase):
    async def test_open_connection_is_readable(self) -> None:
        self.assertTrue(await _database_readable(self.connection))

    async def test_probe_can_be_repeated(self) -> None:
        self.assertTrue(await _database_readable(self.connection))
        self.assertTrue(await _database_readable(self.connection))


class ToolFailureRecorderTests(DbTestCase):
    async def test_recorded_failure_is_written_with_its_error_code(self) -> None:
        recorder = _tool_failure_recorder(self.connection)

        await recorder("read_file", -100, "timeout")

        cursor = await self.connection.execute("SELECT tool, chat_id, error_code FROM tool_failures")
        try:
            rows = await cursor.fetchall()
        finally:
            await cursor.close()
        self.assertEqual([("read_file", -100, "timeout")], [tuple(row) for row in rows])


class ApplicationLifecycleTests(DbTestCase):
    async def test_run_forever_waits_until_stop_is_requested(self) -> None:
        application = Application(self.settings)
        waiter = asyncio.create_task(application.run_forever())
        await asyncio.sleep(0)
        self.assertFalse(waiter.done())

        application.request_stop()

        await asyncio.wait_for(waiter, 1.0)

    async def test_stop_without_start_is_safe_and_cancels_tasks(self) -> None:
        application = Application(self.settings)

        async def forever() -> None:
            await asyncio.sleep(3600)

        task = asyncio.create_task(forever())
        application._tasks.append(task)

        await application.stop()

        self.assertTrue(task.cancelled())


class HousekeepingTests(DbTestCase):
    async def test_expired_rows_are_purged_and_the_loop_stops(self) -> None:
        application = Application(self.settings)
        application._connection = self.connection
        await self.connection.execute(
            "INSERT INTO tool_failures (tool, chat_id, error_code, created_at) VALUES ('calc', 1, 'timeout', 1)"
        )
        await self.connection.commit()

        with mock.patch("app.main.HOUSEKEEPING_INTERVAL_SECONDS", 0.01):
            task = asyncio.create_task(application._housekeeping_loop())
            await asyncio.sleep(0.05)
            application.request_stop()
            await asyncio.wait_for(task, 1.0)

        cursor = await self.connection.execute("SELECT COUNT(*) FROM tool_failures")
        try:
            remaining = await cursor.fetchone()
        finally:
            await cursor.close()
        self.assertEqual(0, remaining[0])

    async def test_loop_returns_immediately_after_stop(self) -> None:
        application = Application(self.settings)
        application.request_stop()

        await asyncio.wait_for(application._housekeeping_loop(), 1.0)


class SignalHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_registered_handler_schedules_the_callback(self) -> None:
        names = ("SIGINT", "SIGTERM")
        saved = {name: signal.getsignal(getattr(signal, name)) for name in names}
        called: list[bool] = []
        try:
            _install_signal_handlers(lambda: called.append(True))

            handler = signal.getsignal(signal.SIGINT)
            self.assertIsNot(saved["SIGINT"], handler)
            self.assertTrue(callable(handler))

            handler(signal.SIGINT, None)  # 直接调用注册的处理函数，不真的发信号
            await asyncio.sleep(0)
            self.assertEqual([True], called)
        finally:
            for name, previous in saved.items():
                signal.signal(getattr(signal, name), previous)
