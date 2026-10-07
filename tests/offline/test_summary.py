"""摘要：触发、模板、滚动、失败恢复与用途记账（F3.3）。"""

from __future__ import annotations

import time
import unittest

from app.config import today_in_timezone
from app.session.summary import (
    SUMMARY_FIELDS,
    SummaryScheduler,
    SummaryService,
    build_summary_prompt,
    clean_summary,
)
from app.storage.repo import messages as messages_repo
from app.storage.repo import summaries as summaries_repo
from app.storage.repo import usage as usage_repo
from app.storage.repo_models import PendingSummary, StoredMessage
from tests.offline.helpers import DbTestCase, FakeClock, FakeLLMClient, make_settings


def _row(row_id: int, text: str, *, role: str = "user", chat_id: int = 1, noise: bool = False) -> StoredMessage:
    return StoredMessage(
        id=row_id,
        chat_id=chat_id,
        message_id=row_id,
        thread_id=None,
        user_id=42,
        role=role,
        text=text,
        reply_to_message_id=None,
        noise=noise,
        created_at=1000 + row_id,
    )


class PromptTests(unittest.TestCase):
    def test_template_fields_present(self) -> None:
        prompt = build_summary_prompt(None, [_row(1, "我们在改部署脚本")])
        self.assertEqual(prompt[0]["role"], "system")
        for field in SUMMARY_FIELDS:
            self.assertIn(field, prompt[1]["content"])
        self.assertIn("我们在改部署脚本", prompt[1]["content"])

    def test_previous_summary_is_included(self) -> None:
        prompt = build_summary_prompt("上次的摘要", [_row(1, "新消息")])
        self.assertIn("上次的摘要", prompt[1]["content"])

    def test_messages_keep_chronological_order(self) -> None:
        prompt = build_summary_prompt(None, [_row(1, "第一条"), _row(2, "第二条")])
        body = prompt[1]["content"]
        self.assertLess(body.index("第一条"), body.index("第二条"))

    def test_clean_summary_strips_blank_lines(self) -> None:
        self.assertEqual(clean_summary("  a \n\n b  \n"), "a\nb")


class TriggerTests(DbTestCase):
    def _service(self, **overrides: object) -> SummaryService:
        self.clock = FakeClock()
        self.settings = make_settings(self.tmp, **overrides)
        self.llm = FakeLLMClient("摘要")
        return SummaryService(self.connection, self.llm, self.settings, clock=self.clock.monotonic)

    def test_count_trigger(self) -> None:
        service = self._service(SUMMARY_MIN_MESSAGES=2)
        self.assertTrue(service.should_summarize(PendingSummary(messages=2, chars=10, last_at=1000)))
        self.assertFalse(service.should_summarize(PendingSummary(messages=0, chars=0, last_at=0)))

    def test_char_trigger_needs_volume(self) -> None:
        service = self._service(HISTORY_BUDGET_CHARS=100)
        self.assertTrue(service.should_summarize(PendingSummary(messages=10, chars=100, last_at=0)))
        self.assertFalse(service.should_summarize(PendingSummary(messages=3, chars=100, last_at=0)))

    def test_quiet_trigger(self) -> None:
        service = self._service(SUMMARY_MIN_MESSAGES=99, SUMMARY_QUIET_SECONDS=60.0)
        self.clock.now = 1000.0
        self.assertTrue(service.should_summarize(PendingSummary(messages=1, chars=5, last_at=900)))
        self.assertFalse(service.should_summarize(PendingSummary(messages=1, chars=5, last_at=990)))


class ClockDomainTests(DbTestCase):
    """静默触发必须与 last_at 同域：库里是 Unix 秒，服务默认时钟也必须是 Unix 秒。"""

    async def test_quiet_trigger_uses_real_unix_seconds(self) -> None:
        settings = make_settings(self.tmp, SUMMARY_MIN_MESSAGES=99, SUMMARY_QUIET_SECONDS=120.0)
        service = SummaryService(self.connection, FakeLLMClient("摘要"), settings)  # 不注入假时钟
        now = time.time()
        # 旧实现默认单调时钟（约 1e4），与 Unix 秒相减恒为负 → 这里必然 False
        self.assertTrue(service.should_summarize(PendingSummary(messages=1, chars=5, last_at=now - 121)))
        self.assertFalse(service.should_summarize(PendingSummary(messages=1, chars=5, last_at=now)))

    async def test_quiet_trigger_consumes_repo_timestamp(self) -> None:
        settings = make_settings(self.tmp, SUMMARY_MIN_MESSAGES=99, SUMMARY_QUIET_SECONDS=120.0)
        service = SummaryService(self.connection, FakeLLMClient("摘要"), settings)
        inserted_at = int(time.time()) - 121
        await messages_repo.insert(
            self.connection,
            chat_id=1,
            message_id=500,
            user_id=42,
            role="user",
            text="静默后的一条",
            created_at=inserted_at,
        )
        pending = await service.pending(1)
        self.assertEqual(pending.messages, 1)
        self.assertEqual(pending.last_at, inserted_at)  # repo 写入的是 Unix 秒
        self.assertTrue(service.should_summarize(pending))

class ServiceTests(DbTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.clock = FakeClock()
        self.settings = make_settings(self.tmp, SUMMARY_MIN_MESSAGES=2, SUMMARY_QUIET_SECONDS=10.0)

    def _service(self, *replies: str, fail: bool = False) -> SummaryService:
        self.llm = FakeLLMClient(*replies, fail=fail)
        return SummaryService(self.connection, self.llm, self.settings, clock=self.clock.monotonic)

    async def _seed(self, chat_id: int = 1, count: int = 3, *, noise: bool = False) -> None:
        for index in range(count):
            await messages_repo.insert(
                self.connection,
                chat_id=chat_id,
                message_id=100 + index,
                user_id=42,
                role="user",
                text=f"第{index}条：我们在改部署脚本",
                noise=noise,
            )

    async def test_summarize_writes_summary_fts_and_usage(self) -> None:
        await self._seed()
        service = self._service("当前话题：部署\n已完成：讨论")
        self.assertTrue(await service.summarize(1))

        latest = await summaries_repo.latest(self.connection, chat_id=1)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertIn("部署", latest.text)
        self.assertEqual(latest.msg_from, 1)
        self.assertEqual(latest.msg_to, 3)
        self.assertEqual(await summaries_repo.cursor(self.connection, chat_id=1), 3)
        self.assertEqual(self.llm.models[0], self.settings.llm_model)

        hits = await summaries_repo.search(self.connection, chat_id=1, match_query="部署", limit=3)
        self.assertEqual(len(hits), 1)

        day = today_in_timezone(self.settings)
        self.assertEqual((await usage_repo.summary_for_day(self.connection, day, purpose="summary"))["calls"], 1)
        self.assertEqual((await usage_repo.summary_for_day(self.connection, day, purpose="chat"))["calls"], 0)

    async def test_failure_does_not_write_or_advance(self) -> None:
        await self._seed()
        service = self._service(fail=True)
        self.assertFalse(await service.summarize(1))
        self.assertIsNone(await summaries_repo.latest(self.connection, chat_id=1))
        self.assertEqual(await summaries_repo.cursor(self.connection, chat_id=1), 0)

    async def test_overlong_summary_is_retried_once(self) -> None:
        await self._seed()
        service = self._service("长" * 400, "短摘要")
        self.assertTrue(await service.summarize(1))
        latest = await summaries_repo.latest(self.connection, chat_id=1)
        assert latest is not None
        self.assertEqual(latest.text, "短摘要")
        self.assertEqual(len(self.llm.calls), 2)

    async def test_still_overlong_is_dropped(self) -> None:
        await self._seed()
        service = self._service("长" * 400, "长" * 400)
        self.assertFalse(await service.summarize(1))
        self.assertIsNone(await summaries_repo.latest(self.connection, chat_id=1))

    async def test_second_run_without_new_messages_is_noop(self) -> None:
        await self._seed()
        service = self._service("第一版", "第二版")
        self.assertTrue(await service.summarize(1))
        self.assertFalse(await service.summarize(1))
        self.assertEqual(len(self.llm.calls), 1)

    async def test_incremental_input_only_contains_new_messages(self) -> None:
        await self._seed(count=2)
        service = self._service("第一版", "第二版")
        self.assertTrue(await service.summarize(1))
        await messages_repo.insert(
            self.connection, chat_id=1, message_id=200, user_id=42, role="user", text="新增的一条"
        )
        self.assertTrue(await service.summarize(1))
        second_prompt = self.llm.calls[1][1]["content"]
        self.assertIn("第一版", second_prompt)  # 上次摘要作为滚动输入
        self.assertIn("新增的一条", second_prompt)
        self.assertNotIn("第0条", second_prompt)

    async def test_chats_are_isolated(self) -> None:
        await self._seed(chat_id=1, count=2)
        await self._seed(chat_id=2, count=2)
        service = self._service("摘要")
        self.assertTrue(await service.summarize(1))
        self.assertIsNone(await summaries_repo.latest(self.connection, chat_id=2))
        self.assertEqual(await summaries_repo.cursor(self.connection, chat_id=2), 0)

    async def test_noise_messages_are_not_summarized(self) -> None:
        await self._seed(count=2, noise=True)
        service = self._service("摘要")
        self.assertFalse(await service.summarize(1))
        pending = await service.pending(1)
        self.assertEqual(pending.messages, 0)

    async def test_scheduler_only_summarizes_due_chats(self) -> None:
        await self._seed(chat_id=1, count=3)
        await messages_repo.insert(
            self.connection, chat_id=2, message_id=300, user_id=42, role="user", text="只有一条"
        )
        service = self._service("摘要")
        scheduler = SummaryScheduler(service, self.connection, poll_seconds=60.0, stop=None)  # type: ignore[arg-type]
        self.assertEqual(await scheduler.tick(), 1)
        self.assertIsNotNone(await summaries_repo.latest(self.connection, chat_id=1))
        self.assertIsNone(await summaries_repo.latest(self.connection, chat_id=2))


if __name__ == "__main__":
    unittest.main()
