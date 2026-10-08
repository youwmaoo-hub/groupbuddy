"""tool_failures：工具失败留痕、统计与 7 天清理（阶段 8 F5.4，T15）。"""

from __future__ import annotations

import asyncio
import unittest

from pydantic import BaseModel, ConfigDict

from app.storage.repo import tool_failures
from app.tools.executor import ToolExecutor
from app.tools.policy import Policy
from app.tools.registry import ToolContext, ToolError, ToolRegistry, ToolSpec
from tests.offline.helpers import DbTestCase, FakeClock


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""


class _FailingTool:
    """工具自身报错：计入熔断，也应留痕。"""

    spec = ToolSpec(name="read_file", level="L1", description="失败", args_model=_Args, timeout_seconds=1.0)

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        raise ToolError("execution_failed", "炸了")


class _SlowTool:
    spec = ToolSpec(name="read_file", level="L1", description="很慢", args_model=_Args, timeout_seconds=0.01)

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        await asyncio.sleep(0.05)
        return {}


def _ctx(chat_id: int = 1, **group: object) -> ToolContext:
    values: dict[str, object] = {"allow_read": 1}
    values.update(group)
    return ToolContext(chat_id=chat_id, user_id=42, group=values)


class ToolFailuresRepoTests(DbTestCase):
    async def test_records_are_counted_per_chat(self) -> None:
        await tool_failures.record(self.connection, tool="read_file", chat_id=1, error_code="execution_failed")
        await tool_failures.record(self.connection, tool="read_file", chat_id=1, error_code="timeout")
        await tool_failures.record(self.connection, tool="run_code", chat_id=2, error_code="internal_error")

        self.assertEqual(await tool_failures.count(self.connection, chat_id=1), 2)
        self.assertEqual(await tool_failures.count(self.connection, chat_id=2), 1)
        self.assertEqual(await tool_failures.count(self.connection, chat_id=999), 0)

    async def test_error_code_is_stored_verbatim(self) -> None:
        await tool_failures.record(self.connection, tool="calc", chat_id=7, error_code="timeout")

        cursor = await self.connection.execute(
            "SELECT tool, error_code FROM tool_failures WHERE chat_id = ?", (7,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        self.assertEqual(tuple(row), ("calc", "timeout"))

    async def test_count_uses_half_open_bounds(self) -> None:
        for created_at in (100, 200, 300):
            await tool_failures.record(
                self.connection, tool="calc", chat_id=1, error_code="timeout", created_at=created_at
            )

        # 左闭右开：100 被排除，200 计入，300 被排除
        self.assertEqual(
            await tool_failures.count(self.connection, chat_id=1, since=200, until=300), 1
        )
        self.assertEqual(await tool_failures.count(self.connection, chat_id=1, since=100), 3)

    async def test_purge_old_removes_only_expired_records(self) -> None:
        now = 1_700_000_000
        await tool_failures.record(
            self.connection, tool="calc", chat_id=1, error_code="timeout", created_at=now - 8 * 86400
        )
        await tool_failures.record(
            self.connection, tool="calc", chat_id=1, error_code="timeout", created_at=now - 1 * 86400
        )

        self.assertEqual(await tool_failures.purge_old(self.connection, now=now), 1)
        self.assertEqual(await tool_failures.count(self.connection, chat_id=1), 1)

    async def test_purge_old_keeps_the_boundary_record(self) -> None:
        now = 1_700_000_000
        cutoff = now - tool_failures.RETENTION_DAYS * 86400
        await tool_failures.record(
            self.connection, tool="calc", chat_id=1, error_code="timeout", created_at=cutoff
        )

        self.assertEqual(await tool_failures.purge_old(self.connection, now=now), 0)
        self.assertEqual(await tool_failures.count(self.connection, chat_id=1), 1)


class ToolFailureRecordingTests(DbTestCase):
    """executor → tool_failures 的接线：只记计入熔断的失败。"""

    def _build(self, tool: object, *, recorder=None) -> ToolExecutor:
        registry = ToolRegistry()
        registry.register(tool)  # type: ignore[arg-type]
        return ToolExecutor(
            registry,
            Policy(registry),
            clock=FakeClock().monotonic,
            failure_recorder=recorder,
        )

    async def test_tool_error_is_recorded(self) -> None:
        recorded: list[tuple[str, int, str]] = []

        async def recorder(tool: str, chat_id: int, error_code: str) -> None:
            recorded.append((tool, chat_id, error_code))

        executor = self._build(_FailingTool(), recorder=recorder)
        payload = await executor.execute(_ctx(chat_id=5), "read_file", "{}")

        self.assertEqual(payload["error"], "execution_failed")
        self.assertEqual(recorded, [("read_file", 5, "execution_failed")])

    async def test_timeout_is_recorded(self) -> None:
        recorded: list[tuple[str, int, str]] = []

        async def recorder(tool: str, chat_id: int, error_code: str) -> None:
            recorded.append((tool, chat_id, error_code))

        executor = self._build(_SlowTool(), recorder=recorder)
        payload = await executor.execute(_ctx(), "read_file", "{}")

        self.assertEqual(payload["error"], "timeout")
        self.assertEqual(recorded, [("read_file", 1, "timeout")])

    async def test_call_time_rejection_is_not_recorded(self) -> None:
        recorded: list[tuple[str, int, str]] = []

        async def recorder(tool: str, chat_id: int, error_code: str) -> None:
            recorded.append((tool, chat_id, error_code))

        # 未登记的 read_file 在权限层就被拒（调用前拒绝，不计熔断、不留痕）
        registry = ToolRegistry()
        executor = ToolExecutor(registry, Policy(registry), failure_recorder=recorder)
        payload = await executor.execute(_ctx(), "read_file", "{}")

        self.assertEqual(payload["error"], "permission_denied")
        self.assertEqual(recorded, [])

        # 参数非法同样属于调用前拒绝
        executor = self._build(_FailingTool(), recorder=recorder)
        payload = await executor.execute(_ctx(), "read_file", "not json")
        self.assertEqual(payload["error"], "invalid_arguments")
        self.assertEqual(recorded, [])

    async def test_recorder_failure_does_not_change_the_result(self) -> None:
        async def recorder(tool: str, chat_id: int, error_code: str) -> None:
            raise RuntimeError("数据库锁住了")

        executor = self._build(_FailingTool(), recorder=recorder)
        payload = await executor.execute(_ctx(), "read_file", "{}")

        self.assertEqual(payload["error"], "execution_failed")
        self.assertEqual(payload["tool"], "read_file")

    async def test_no_recorder_is_allowed(self) -> None:
        executor = self._build(_FailingTool())
        payload = await executor.execute(_ctx(), "read_file", "{}")
        self.assertEqual(payload["error"], "execution_failed")


if __name__ == "__main__":
    unittest.main()
