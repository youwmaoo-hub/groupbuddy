"""host_info：冻结字段集、L4 默认关、不泄露环境信息（docs/tools.md §host_info）。"""

from __future__ import annotations

import json
import os
import platform
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic import ValidationError

from app.tools.builtin import build_registry
from app.tools.builtin import host_info as host_info_module
from app.tools.builtin.host_info import FIELDS, HostInfoArgs, HostInfoTool
from app.tools.executor import ToolExecutor
from app.tools.policy import Policy
from app.tools.registry import ToolContext, ToolRegistry
from tests.offline.helpers import FakeClock, make_settings


def _executor() -> ToolExecutor:
    registry = ToolRegistry()
    registry.register(HostInfoTool())
    return ToolExecutor(registry, Policy(registry), clock=FakeClock().monotonic)


def _ctx(allow_host_info: int = 0, chat_id: int = 1) -> ToolContext:
    return ToolContext(chat_id=chat_id, user_id=42, group={"allow_host_info": allow_host_info})


async def _run(arguments: str = "{}", allow_host_info: int = 1) -> dict[str, object]:
    return await _executor().execute(_ctx(allow_host_info), "host_info", arguments)


class SpecTests(unittest.TestCase):
    def test_spec_is_l4_with_only_the_frozen_fields(self) -> None:
        self.assertEqual(FIELDS, ("cpu", "memory", "disk_free", "python", "uptime_s"))
        self.assertEqual(HostInfoTool.spec.name, "host_info")
        self.assertEqual(HostInfoTool.spec.level, "L4")
        self.assertEqual(HostInfoTool.spec.timeout_seconds, 2.0)

    def test_schema_is_strict_and_title_free(self) -> None:
        parameters = HostInfoTool.spec.parameters
        self.assertFalse(parameters["additionalProperties"])
        self.assertIn("fields", parameters["properties"])
        self.assertNotIn("title", json.dumps(parameters))


class ArgsTests(unittest.TestCase):
    def test_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            HostInfoArgs.model_validate({"fields": ["env"]})

    def test_duplicates_are_removed_and_order_kept(self) -> None:
        args = HostInfoArgs.model_validate({"fields": ["python", "cpu", "python"]})
        self.assertEqual(args.fields, ["python", "cpu"])

    def test_extra_arguments_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            HostInfoArgs.model_validate({"paths": ["/etc/passwd"]})

    def test_field_count_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            HostInfoArgs.model_validate({"fields": ["cpu"] * (len(FIELDS) + 1)})


class RunTests(unittest.IsolatedAsyncioTestCase):
    async def test_defaults_return_all_five_fields(self) -> None:
        payload = await _run()
        self.assertEqual(list(payload), list(FIELDS))
        self.assertIsInstance(payload["python"], str)
        self.assertIsInstance(payload["uptime_s"], int)
        self.assertGreaterEqual(payload["uptime_s"], 0)
        self.assertIsInstance(payload["disk_free"], int)

    async def test_selected_fields_only(self) -> None:
        payload = await _run('{"fields": ["python", "cpu"]}')
        self.assertEqual(list(payload), ["python", "cpu"])

    async def test_unavailable_values_are_none_not_errors(self) -> None:
        with (
            mock.patch.object(host_info_module, "_cpu_count", return_value=None),
            mock.patch.object(host_info_module, "_memory_total", return_value=None),
            mock.patch.object(host_info_module, "_disk_free", return_value=None),
        ):
            payload = await _run()
        self.assertIsNone(payload["cpu"])
        self.assertIsNone(payload["memory"])
        self.assertIsNone(payload["disk_free"])

    async def test_memory_total_reads_no_environment(self) -> None:
        with mock.patch.dict(os.environ, {"SC_PHYS_PAGES": "not-a-number"}):
            value = host_info_module._memory_total()
        self.assertTrue(value is None or value > 0)

    def test_uptime_falls_back_to_process_time_without_proc(self) -> None:
        with (
            mock.patch("builtins.open", side_effect=OSError("no /proc")),
            mock.patch.object(host_info_module, "_PROCESS_START", 100.0),
        ):
            self.assertEqual(host_info_module._uptime_seconds(142.9), 42)

    def test_uptime_reads_proc_when_available(self) -> None:
        with mock.patch("builtins.open", mock.mock_open(read_data="12345.67 98765.43\n")):
            self.assertEqual(host_info_module._uptime_seconds(999.0), 12345)


class PolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_by_default(self) -> None:
        payload = await _run(allow_host_info=0)
        self.assertEqual(payload["error"], "permission_denied")

    async def test_group_switch_enables_the_tool(self) -> None:
        payload = await _run(allow_host_info=1)
        self.assertNotIn("error", payload)
        self.assertEqual(list(payload), list(FIELDS))

    async def test_unknown_field_is_invalid_arguments_without_echoing_it(self) -> None:
        payload = await _run('{"fields": ["env"]}')
        self.assertEqual(payload["error"], "invalid_arguments")
        self.assertNotIn("env", str(payload["message"]))

    def test_specs_for_respects_the_switch(self) -> None:
        executor = _executor()
        self.assertEqual(executor.specs_for(_ctx(0)), [])
        names = [spec["function"]["name"] for spec in executor.specs_for(_ctx(1))]  # type: ignore[index]
        self.assertEqual(names, ["host_info"])

    def test_policy_denies_unregistered_host_info(self) -> None:
        empty = ToolRegistry()
        self.assertEqual(Policy(empty).check("host_info", _ctx(1)), "permission_denied")


class LeakTests(unittest.IsolatedAsyncioTestCase):
    async def test_payload_has_no_environment_or_host_identity(self) -> None:
        with mock.patch.dict(os.environ, {"DSH_HOST_INFO_SECRET": "s3cr3t-value"}):
            payload = await _run(allow_host_info=1)
        text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("s3cr3t-value", text)
        if platform.node():
            self.assertNotIn(platform.node(), text)
        if socket.gethostname():
            self.assertNotIn(socket.gethostname(), text)
        self.assertNotIn(str(Path.cwd()), text)
        self.assertEqual(set(payload) - set(FIELDS), set())
        self.assertEqual(set(payload) & {"env", "environ", "hostname", "user", "ip", "net", "pid"}, set())


class RegistryTests(unittest.TestCase):
    def test_build_registry_includes_host_info(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        settings = make_settings(Path(tmp.name))
        registry = build_registry(settings, store=object(), outbound=object(), mood=object())
        self.assertIn("host_info", registry.names())


if __name__ == "__main__":
    unittest.main()
