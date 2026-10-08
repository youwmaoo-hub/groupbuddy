"""四模式档位（docs/token.md §5）：窗口 / 输出上限 / 工具档位 / 贴纸。"""

from __future__ import annotations

import unittest

from pydantic import BaseModel, ConfigDict

from app import modes
from app.gate.debounce import Batch
from app.llm.loop import Responder
from app.ops import commands
from app.session.context import ContextBuilder
from app.tools.builtin.calc import CalcTool
from app.tools.builtin.search_web import FakeSearchBackend, SearchWebTool
from app.tools.policy import Policy
from app.tools.registry import ToolContext, ToolRegistry, ToolSpec
from tests.offline.helpers import DbTestCase, FakeLLMClient, make_incoming

FENCE = chr(96) * 3


class _Settings:
    """只提供 Responder 需要的配置字段。"""

    llm_max_output_tokens = 1024
    llm_model = "fake"
    tool_max_rounds = 2


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = ""


class _LevelTool:
    """按指定等级注册的测试工具；不会被真正执行。"""

    def __init__(self, name: str, level: str) -> None:
        self.spec = ToolSpec(name=name, level=level, description="测试用", args_model=_Args, timeout_seconds=1.0)

    async def run(self, args: BaseModel, context: ToolContext) -> dict[str, object]:
        return {}


def _registry() -> ToolRegistry:
    """覆盖 L0–L4 的注册表：calc/search_web 是 L0，其余按等级造替身。"""
    registry = ToolRegistry()
    registry.register(CalcTool())
    registry.register(SearchWebTool(FakeSearchBackend()))
    registry.register(_LevelTool("read_file", "L1"))
    registry.register(_LevelTool("send_sticker", "L2"))
    registry.register(_LevelTool("run_code", "L3"))
    registry.register(_LevelTool("host_info", "L4"))
    return registry


def _ctx(chat_id: int = 1, **group: object) -> ToolContext:
    return ToolContext(chat_id=chat_id, user_id=42, group=group)


class ProfileTests(unittest.TestCase):
    def test_contract_table_matches_token_md_section_5(self) -> None:
        economy = modes.PROFILES[modes.ECONOMY]
        normal = modes.PROFILES[modes.NORMAL]
        smart = modes.PROFILES[modes.SMART]
        unrestricted = modes.PROFILES[modes.UNRESTRICTED]

        self.assertEqual(modes.MODES, ("economy", "normal", "smart", "unrestricted"))
        # 窗口：最小 10 / 默认（按意图分档）/ 最长 50 / 最长 50
        self.assertEqual([economy.window, normal.window, smart.window, unrestricted.window], [10, None, 50, 50])
        # 输出上限：短 / 正常 / 正常 / 不限
        self.assertEqual(
            [economy.output, normal.output, smart.output, unrestricted.output],
            [modes.SHORT, modes.CONFIGURED, modes.CONFIGURED, modes.UNLIMITED],
        )
        # 工具：L0 只读 / 群设定允许的等级 / 允许的等级 + 更多工具 / 全部
        self.assertEqual(economy.levels, frozenset({"L0"}))
        self.assertIsNone(normal.levels)
        self.assertIsNone(smart.levels)
        self.assertIsNone(unrestricted.levels)
        self.assertFalse(economy.readonly_regardless_of_switch)
        self.assertTrue(smart.readonly_regardless_of_switch)
        self.assertTrue(unrestricted.ignore_switches)
        # 贴纸：只有 economy 关
        self.assertEqual([economy.stickers, normal.stickers, smart.stickers, unrestricted.stickers], [False, True, True, True])

    def test_mode_names_have_a_single_source(self) -> None:
        self.assertIs(commands.MODES, modes.MODES)
        for name in modes.MODES:
            field, value = commands.resolve_setting(("mode", name))  # type: ignore[misc]
            self.assertEqual((field.name, value), ("mode", name))

    def test_unknown_or_missing_mode_falls_back_to_normal(self) -> None:
        for raw in (None, "", "weird", 0, {"mode": "nope"}):
            self.assertEqual(modes.normalize(raw), modes.NORMAL)
        self.assertEqual(modes.profile_for({}).name, modes.NORMAL)
        self.assertEqual(modes.profile_for({"mode": "SMART"}).name, modes.SMART)
        self.assertEqual(modes.profile_for("economy").name, modes.ECONOMY)

    def test_output_limit_per_mode(self) -> None:
        settings = _Settings()
        self.assertEqual(modes.output_limit(modes.PROFILES[modes.ECONOMY], settings), modes.ECONOMY_MAX_OUTPUT_TOKENS)  # type: ignore[arg-type]
        for name in (modes.NORMAL, modes.SMART):
            self.assertEqual(modes.output_limit(modes.PROFILES[name], settings), 1024)  # type: ignore[arg-type]
        self.assertIsNone(modes.output_limit(modes.PROFILES[modes.UNRESTRICTED], settings))  # type: ignore[arg-type]


class PolicyModeTests(unittest.TestCase):
    def test_economy_only_offers_readonly_tools_and_no_stickers(self) -> None:
        policy = Policy(_registry())
        context = _ctx(
            mode="economy", allow_search=1, allow_read=1, allow_write=1, allow_code=1, allow_sticker=1, allow_host_info=1
        )
        self.assertEqual(policy.allowed_names(context), ("calc", "search_web"))
        for name in ("read_file", "write_file", "send_sticker", "run_code", "host_info"):
            self.assertEqual(policy.check(name, context), "permission_denied")

    def test_economy_still_respects_group_switches(self) -> None:
        policy = Policy(_registry())
        context = _ctx(mode="economy", allow_search=0, allow_read=1)
        self.assertEqual(policy.allowed_names(context), ("calc",))

    def test_normal_keeps_the_group_switches(self) -> None:
        policy = Policy(_registry())
        off = _ctx(mode="normal")
        self.assertEqual(policy.allowed_names(off), ("calc",))
        on = _ctx(mode="normal", allow_search=1, allow_read=1, allow_write=1, allow_code=1, allow_sticker=1, allow_host_info=1)
        self.assertEqual(
            policy.allowed_names(on),
            ("calc", "host_info", "read_file", "run_code", "search_web", "send_sticker"),
        )

    def test_smart_adds_readonly_tools_but_not_higher_levels(self) -> None:
        policy = Policy(_registry())
        context = _ctx(mode="smart", allow_search=0, allow_read=0, allow_host_info=0)
        self.assertEqual(policy.allowed_names(context), ("calc", "search_web"))
        self.assertEqual(policy.check("read_file", context), "permission_denied")
        self.assertEqual(policy.check("host_info", context), "permission_denied")

    def test_smart_still_honours_enabled_switches(self) -> None:
        policy = Policy(_registry())
        context = _ctx(mode="smart", allow_read=1, allow_code=1)
        self.assertEqual(policy.allowed_names(context), ("calc", "read_file", "run_code", "search_web"))

    def test_unrestricted_offers_every_registered_tool(self) -> None:
        policy = Policy(_registry())
        context = _ctx(mode="unrestricted")
        self.assertEqual(
            policy.allowed_names(context),
            ("calc", "host_info", "read_file", "run_code", "search_web", "send_sticker"),
        )
        self.assertIsNone(policy.check("host_info", context))

    def test_unknown_mode_behaves_like_normal(self) -> None:
        policy = Policy(_registry())
        context = _ctx(mode="weird", allow_search=1)
        self.assertEqual(policy.allowed_names(context), ("calc", "search_web"))


class WindowTests(DbTestCase):
    def _builder(self) -> ContextBuilder:
        return ContextBuilder(self.connection, self.settings)

    @staticmethod
    def _batch(*texts: str) -> Batch:
        items = [
            make_incoming(update_id=900 + index, chat_id=1, message_id=900 + index, text=text)
            for index, text in enumerate(texts)
        ]
        return Batch(chat_id=1, items=items, last_at=0.0, full=False)

    def test_each_mode_has_the_contract_window(self) -> None:
        builder = self._builder()
        chitchat = self._batch("哈哈")
        complex_one = self._batch(f"看代码 {FENCE}x{FENCE}")
        self.assertEqual(builder.window_size(chitchat, mode="economy"), 10)
        self.assertEqual(builder.window_size(complex_one, mode="smart"), 50)
        self.assertEqual(builder.window_size(chitchat, mode="unrestricted"), 50)
        self.assertEqual(builder.window_size(complex_one, mode="unrestricted"), 50)

    def test_normal_keeps_the_intent_tiers(self) -> None:
        builder = self._builder()
        self.assertEqual(builder.window_size(self._batch("哈哈")), self.settings.history_chitchat)
        self.assertEqual(builder.window_size(self._batch("这是一句普通的日常对话内容")), self.settings.history_default)
        self.assertEqual(builder.window_size(self._batch(f"看代码 {FENCE}x{FENCE}")), self.settings.history_complex)

    def test_unknown_mode_uses_the_normal_tiers(self) -> None:
        builder = self._builder()
        self.assertEqual(builder.window_size(self._batch("看代码 " + FENCE), mode="weird"), self.settings.history_complex)


class ResponderLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_limit_reaches_the_client(self) -> None:
        llm = FakeLLMClient("好")
        responder = Responder(llm, _Settings(), None)  # type: ignore[arg-type]
        await responder.reply([{"role": "user", "content": "你好"}], max_output_tokens=modes.ECONOMY_MAX_OUTPUT_TOKENS)
        self.assertEqual(llm.max_tokens, [modes.ECONOMY_MAX_OUTPUT_TOKENS])

    async def test_unlimited_omits_the_cap_and_default_uses_settings(self) -> None:
        llm = FakeLLMClient("好", "好")
        responder = Responder(llm, _Settings(), None)  # type: ignore[arg-type]
        await responder.reply([{"role": "user", "content": "你好"}], max_output_tokens=None)
        await responder.reply([{"role": "user", "content": "你好"}])
        self.assertEqual(llm.max_tokens, [None, _Settings.llm_max_output_tokens])


if __name__ == "__main__":
    unittest.main()
