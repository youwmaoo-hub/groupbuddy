"""离线测试共用的假实现：无网络、无凭据文件、无真实时钟。"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.llm.client import LLMError, LLMReply
from app.outbound.queue import RateLimited, SendFailed
from app.storage.db import apply_migrations, close_db, open_db
from app.telegram.parse import IncomingMessage


class FakeClock:
    """可控时钟：让 debounce/限速测试不需要真的等待。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSleep:
    """替代 asyncio.sleep：只推进时钟并让出执行权。"""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.total = 0.0

    async def __call__(self, seconds: float) -> None:
        self.total += seconds
        self._clock.advance(seconds)
        await asyncio.sleep(0)


class FakeLLMClient:
    """记录每次请求；按脚本返回文本，可模拟失败。"""

    def __init__(self, *replies: str, fail: bool = False) -> None:
        self.calls: list[list[dict[str, str]]] = []
        self.models: list[str] = []
        self._replies = list(replies) or ["好的"]
        self._fail = fail

    async def complete(self, messages, *, model=None, temperature=None, max_tokens=None) -> LLMReply:
        self.calls.append(messages)
        self.models.append(model or "")
        if self._fail:
            raise LLMError("模拟失败")
        if len(self._replies) > 1:
            text = self._replies.pop(0)
        else:
            text = self._replies[0]
        return LLMReply(text=text, model=model or "fake", input_tokens=10, cached_tokens=8, output_tokens=5)


class FakeSender:
    """实现 outbound.queue 的 Sender 协议。"""

    def __init__(self, *, rate_limited_times: int = 0, fail_times: int = 0) -> None:
        self.sent: list[dict[str, object]] = []
        self.rate_limited_times = rate_limited_times
        self.fail_times = fail_times
        self._next_id = 1000

    async def send_message(self, *, chat_id: int, text: str, reply_to_message_id: int | None = None) -> int:
        if self.rate_limited_times > 0:
            self.rate_limited_times -= 1
            raise RateLimited(0.0)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise SendFailed("模拟发送失败")
        self.sent.append({"chat_id": chat_id, "text": text, "reply_to_message_id": reply_to_message_id})
        self._next_id += 1
        return self._next_id


class DbTestCase(unittest.IsolatedAsyncioTestCase):
    """带临时数据库的测试基类：不触碰项目 storage/。"""

    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.settings = make_settings(self.tmp)
        self.connection = await open_db(self.settings)
        await apply_migrations(self.connection)

    async def asyncTearDown(self) -> None:
        await close_db(self.connection)
        self._tmp.cleanup()


def make_settings(tmp: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "BOT_TOKEN": "test-token",
        "LLM_API_KEY": "test-key",
        "DATA_DIR": str(tmp / "storage"),
        "DB_PATH": str(tmp / "storage" / "bot.db"),
        "WORKSPACE_ROOT": str(tmp / "storage" / "workspaces"),
        "LOG_DIR": str(tmp / "storage" / "logs"),
        "SEND_RATE_GROUP_PER_MINUTE": 1000,
        "SEND_RATE_PRIVATE_PER_SECOND": 1000.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_incoming(
    *,
    update_id: int,
    chat_id: int,
    message_id: int,
    text: str,
    **overrides: object,
) -> IncomingMessage:
    values: dict[str, object] = {
        "update_id": update_id,
        "chat_id": chat_id,
        "chat_type": "supergroup",
        "message_id": message_id,
        "user_id": 42,
        "text": text,
        "thread_id": None,
        "is_bot_author": False,
        "reply_to_bot": False,
        "mentions_bot": True,
    }
    values.update(overrides)
    return IncomingMessage(**values)  # type: ignore[arg-type]
