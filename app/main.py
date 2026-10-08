"""进程入口：装配各层、启动长轮询、优雅关闭（docs/deployment.md §5、§6）。"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Callable

import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from pydantic import ValidationError

from app.config import Settings, load_settings
from app.gate.debounce import Debouncer, run_debounce_loop
from app.gate.dedupe import UpdateDeduplicator
from app.gate.limits import ProactiveLimiter, RepeatGuard
from app.gate.queue import ChatQueue
from app.gate.trigger import TriggerDetector
from app.llm.client import DeepSeekClient
from app.llm.loop import Responder
from app.logging_setup import setup_logging
from app.ops.admin import AdminRegistry
from app.ops.commands import BOT_COMMANDS, CommandService
from app.ops.health import HEALTH_FILENAME, HEALTH_INTERVAL_SECONDS, HealthState, health_loop
from app.ops.quota import QuotaGuard
from app.outbound.queue import OutboundQueue
from app.outbound.ratelimit import RateLimiter
from app.sandbox.backends import build_backend
from app.sandbox.runner import SandboxRunner
from app.session.context import ContextBuilder
from app.session.mood import MoodTracker
from app.session.runner import SessionRunner
from app.session.summary import SummaryScheduler, SummaryService
from app.storage.db import apply_migrations, close_db, open_db, optimize
from app.storage.repo import tool_failures, updates
from app.storage.repo.stickers import DbStickerStore
from app.telegram.admins import AiogramAdminSource
from app.telegram.handlers import build_router
from app.telegram.sender import AiogramSender
from app.tools.builtin import build_registry
from app.tools.executor import ToolExecutor
from app.tools.policy import Policy

logger = logging.getLogger("app.main")

HOUSEKEEPING_INTERVAL_SECONDS = 3600.0
OPTIMIZE_INTERVAL_SECONDS = 7 * 24 * 3600.0
SHUTDOWN_DRAIN_SECONDS = 10.0


async def _database_readable(connection: aiosqlite.Connection) -> bool:
    """健康检查用的最小只读探测：连接可用即视为数据库可读（docs/deployment.md §7）。"""
    cursor = await connection.execute("SELECT 1")
    try:
        return await cursor.fetchone() is not None
    finally:
        await cursor.close()


def _tool_failure_recorder(connection: aiosqlite.Connection):
    """把计入熔断的工具失败写进 `tool_failures`，供 `/stats` 统计（阶段 8 F5.4）。"""

    async def record(tool: str, chat_id: int, error_code: str) -> None:
        await tool_failures.record(connection, tool=tool, chat_id=chat_id, error_code=error_code)

    return record


class Application:
    """把组件装起来；装配顺序与依赖方向一致（docs/architecture.md §2）。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stop = asyncio.Event()
        self._connection: aiosqlite.Connection | None = None
        self._bot: Bot | None = None
        self._dispatcher: Dispatcher | None = None
        self._llm: DeepSeekClient | None = None
        self._outbound: OutboundQueue | None = None
        self._chat_queue: ChatQueue | None = None
        self._sandbox: SandboxRunner | None = None
        self._tasks: list[asyncio.Task[None]] = []

    def request_stop(self) -> None:
        self._stop.set()

    async def start(self) -> None:
        settings = self._settings
        connection = await open_db(settings)
        await apply_migrations(connection)
        self._connection = connection
        await updates.purge_old(connection)
        await tool_failures.purge_old(connection)

        instance = settings.bot_instance()
        self._llm = DeepSeekClient(instance.llm)

        bot = Bot(instance.bot_token)
        me = await bot.get_me()
        self._bot = bot
        logger.info(
            "Bot 就绪 username=%s bot_id=%s model=%s",
            me.username,
            me.id,
            settings.llm_model,
        )
        # 指令菜单：让群里的人知道有哪些命令可用（可发现性，docs/requirements.md §2.3）；
        # 失败只降级成没有菜单，绝不挡住启动。
        try:
            await bot.set_my_commands(
                [BotCommand(command=name, description=desc) for name, desc in BOT_COMMANDS]
            )
        except Exception:
            logger.warning("设置指令菜单失败", exc_info=True)

        limiter = RateLimiter(
            group_per_minute=settings.send_rate_group_per_minute,
            private_per_second=settings.send_rate_private_per_second,
            sticker_per_second=settings.send_rate_sticker_per_second,
            max_backoff=settings.send_backoff_max_seconds,
        )
        outbound = OutboundQueue(AiogramSender(bot), limiter)
        self._outbound = outbound

        # 健康状态：health.json 心跳与 /health 命令共用同一个实例（docs/deployment.md §7）
        health = HealthState(
            instance_id=settings.instance_id,
            db_check=lambda: _database_readable(connection),
            pending=lambda: outbound.pending,
        )

        # 群主命令：管理员只认 Telegram 返回的管理员，查询失败按拒绝处理（docs/security.md §2）
        commands = CommandService(
            connection,
            AdminRegistry(AiogramAdminSource(bot)),
            settings=settings,
            health=health,
        )

        # 配额：调用模型前按 chat_id 检查日/月用量，0 或未配置 = 不限额（docs/token.md §4.1）
        quota = QuotaGuard(connection, settings)

        # 沙箱：启动时探测一次并固定后端（docs/security.md §4），运行期不再探测
        sandbox = SandboxRunner(build_backend(settings), settings)
        self._sandbox = sandbox
        try:
            await sandbox.cleanup_stale()
        except Exception:
            logger.warning("清理残留沙箱容器失败", exc_info=True)
        logger.info("沙箱状态 %s", sandbox.describe())

        mood = MoodTracker()
        registry = build_registry(
            settings,
            store=DbStickerStore(connection),
            outbound=outbound,
            mood=mood,
            sandbox=sandbox,
        )
        policy = Policy(registry)
        tools = ToolExecutor(registry, policy, failure_recorder=_tool_failure_recorder(connection))
        responder = Responder(self._llm, settings, tools)

        debouncer = Debouncer(
            quiet_seconds=settings.debounce_seconds,
            max_messages=settings.debounce_max_messages,
        )
        proactive = ProactiveLimiter(cooldown_seconds=settings.proactive_cooldown_seconds)
        repeats = RepeatGuard(window_seconds=settings.duplicate_window_seconds)
        runner = SessionRunner(
            settings=settings,
            connection=connection,
            deduplicator=UpdateDeduplicator(connection),
            detector=TriggerDetector(settings, proactive, repeats),
            limiter=proactive,
            debouncer=debouncer,
            context_builder=ContextBuilder(connection, settings),
            responder=responder,
            outbound=outbound,
            tools=tools,
            mood=mood,
            commands=commands,
            quota=quota,
            health=health,
            bot_username=me.username or "",
        )
        chat_queue = ChatQueue(runner.handle_batch, max_batch_messages=settings.debounce_max_messages)
        self._chat_queue = chat_queue

        dispatcher = Dispatcher()
        dispatcher.include_router(
            build_router(
                runner=runner,
                bot_id=int(me.id),
                bot_username=me.username or "",
                aliases=settings.aliases,
            )
        )
        self._dispatcher = dispatcher

        # 信号由本进程统一处理，aiogram 不再自己处理
        self._tasks = [
            asyncio.create_task(
                dispatcher.start_polling(bot, handle_signals=False, close_bot_session=False),
                name="telegram-polling",
            ),
            asyncio.create_task(
                run_debounce_loop(debouncer, chat_queue.submit, stop=self._stop),
                name="debounce-loop",
            ),
            asyncio.create_task(self._housekeeping_loop(), name="housekeeping"),
            asyncio.create_task(self._summary_loop(connection), name="summary-scheduler"),
            asyncio.create_task(
                health_loop(
                    health,
                    settings.data_dir / HEALTH_FILENAME,
                    stop=self._stop,
                    interval=HEALTH_INTERVAL_SECONDS,
                ),
                name="health-heartbeat",
            ),
        ]
        logger.info("启动完成 data_dir=%s db=%s", settings.data_dir, settings.db_path)

    async def _summary_loop(self, connection: aiosqlite.Connection) -> None:
        """后台摘要：异步、按群串行、可优雅停止，不阻塞回复（docs/memory.md §4）。"""
        service = SummaryService(connection, self._llm, self._settings)
        scheduler = SummaryScheduler(
            service,
            connection,
            poll_seconds=self._settings.summary_poll_seconds,
            stop=self._stop,
        )
        await scheduler.run()

    async def run_forever(self) -> None:
        await self._stop.wait()

    async def stop(self) -> None:
        """停止接收新更新 → 限时排空 → 关闭资源（未发送的消息不重试）。"""
        self._stop.set()
        if self._dispatcher is not None:
            await self._dispatcher.stop_polling()
        if self._sandbox is not None:
            await self._sandbox.shutdown()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._sandbox is not None:
            await self._sandbox.shutdown()

        if self._chat_queue is not None:
            await self._chat_queue.drain(SHUTDOWN_DRAIN_SECONDS)
            await self._chat_queue.stop()
        if self._outbound is not None:
            await self._outbound.drain(SHUTDOWN_DRAIN_SECONDS)
            await self._outbound.stop()
        if self._llm is not None:
            await self._llm.aclose()
        if self._connection is not None:
            await close_db(self._connection)
        if self._bot is not None:
            await self._bot.session.close()
        logger.info("已关闭")

    async def _housekeeping_loop(self) -> None:
        """定期清理过期 update_id 与过期工具失败记录（docs/database.md §4），并按周刷新统计信息（§5）。"""
        connection = self._connection
        last_optimize: float | None = None
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=HOUSEKEEPING_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set() or connection is None:
                return
            try:
                removed = await updates.purge_old(connection)
                if removed:
                    logger.info("清理过期 update 记录 rows=%s", removed)
                purged = await tool_failures.purge_old(connection)
                if purged:
                    logger.info("清理过期工具失败记录 rows=%s", purged)
                now = asyncio.get_running_loop().time()
                if last_optimize is None or now - last_optimize >= OPTIMIZE_INTERVAL_SECONDS:
                    await optimize(connection)
                    last_optimize = now
                    logger.info("数据库统计信息已刷新")
            except Exception:
                logger.exception("后台清理失败")


def _install_signal_handlers(callback: Callable[[], None]) -> None:
    """SIGTERM/SIGINT → 优雅关闭；Windows 上只保证 SIGINT 真正到达。"""
    loop = asyncio.get_running_loop()

    def _handle(signum: int, _frame: object) -> None:
        logger.info("收到信号 signum=%s", signum)
        loop.call_soon_threadsafe(callback)

    for name in ("SIGINT", "SIGTERM"):
        value = getattr(signal, name, None)
        if value is None:
            continue
        try:
            signal.signal(value, _handle)
        except (OSError, ValueError):
            logger.warning("无法注册信号处理 signal=%s", name)


async def _run() -> None:
    try:
        settings = load_settings()
    except ValidationError as error:
        raise SystemExit("配置无效：请按 .env.example 填写 .env 后重试。\n" + str(error)) from error
    setup_logging(settings)
    settings.ensure_directories()

    application = Application(settings)
    _install_signal_handlers(application.request_stop)
    await application.start()
    try:
        await application.run_forever()
    finally:
        await application.stop()


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
