"""运行指标：`/stats` 与 `/health` 的文本渲染（阶段 8 F5.4，docs/requirements.md F5.4）。

统计口径全部复用现有数据源 —— `usage`（token 与工具调用）与 `tool_failures`（工具失败），
本模块只做聚合读取与文案，不新建第二套统计体系（docs/database.md §3、§4）。
文案里只出现计数、时长与上限：不含文件路径、异常堆栈、环境变量、凭据或原始工具参数。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiosqlite

from app.config import Settings, today_in_timezone
from app.storage.repo import tool_failures, usage

logger = logging.getLogger(__name__)

STATS_FAILED_TEXT = "统计暂时不可用，请稍后重试。"
NO_QUOTA_TEXT = "未设置限额"
UNLIMITED_TEXT = "不限额"

WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def day_bounds(settings: Settings, *, now: datetime | None = None) -> tuple[int, int]:
    """按 `TIMEZONE` 的自然日算 `(起点, 终点)` 的 Unix 秒（左闭右开）。

    `usage.day` 是日期字符串（可 `LIKE` 前缀查），而 `tool_failures` 只有时间戳，需要区间。
    """
    moment = now or datetime.now(tz=timezone.utc)
    try:
        zone = ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = moment.astimezone().tzinfo or timezone.utc
    local = moment.astimezone(zone)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


async def render_stats(
    connection: aiosqlite.Connection,
    settings: Settings,
    *,
    chat_id: int,
    now: datetime | None = None,
) -> str:
    """本群当日运行统计：token 用量、工具调用与失败（错误率）、配额余量。"""
    try:
        day = today_in_timezone(settings, now)
        totals = await usage.summary_for_day(connection, day, chat_id)
        start, end = day_bounds(settings, now=now)
        failures = await tool_failures.count(connection, chat_id=chat_id, since=start, until=end)
        day_used = await usage.tokens_used(connection, chat_id=chat_id, day_prefix=day)
        month_used = await usage.tokens_used(connection, chat_id=chat_id, day_prefix=day[:7])
    except Exception:
        logger.exception("统计读取失败 chat_id=%s", chat_id)
        return STATS_FAILED_TEXT

    calls = int(totals["calls"])
    tool_calls = int(totals["tool_calls"])
    lines = [
        f"本群运行统计（{day} {WEEKDAY_NAMES[_weekday_index(day)]}）",
        f"模型调用：{calls} 次",
        "Token：输入 {input}（缓存 {cached}）/ 输出 {output}，合计 {total}".format(
            input=int(totals["input_tokens"]),
            cached=int(totals["cached_tokens"]),
            output=int(totals["output_tokens"]),
            total=int(totals["input_tokens"]) + int(totals["output_tokens"]),
        ),
        f"工具调用：{tool_calls} 次，{_failure_text(failures, tool_calls)}",
        _quota_line(settings, day_used=day_used, month_used=month_used),
    ]
    return "\n".join(lines)


def render_health(snapshot: dict[str, object]) -> str:
    """`/health` 的简短回显；状态异常时给可操作提示，不带路径与堆栈。"""
    ok = bool(snapshot.get("ok"))
    pending = snapshot.get("outbound_pending")
    lines = [
        f"状态：{'正常' if ok else '异常'}",
        f"实例：{snapshot.get('instance') or 'default'}",
        f"运行时长：{_duration(snapshot.get('uptime_s'))}",
        f"最后处理更新：{_since(snapshot.get('last_update_at'), snapshot.get('checked_at'))}",
        f"数据库：{'可读' if snapshot.get('db_ok') else '不可读'}",
        f"出站队列：{'未知' if pending is None else str(int(pending)) + ' 条待发'}",
    ]
    if not ok:
        lines.append("请检查服务日志后重试。")
    return "\n".join(lines)


def _weekday_index(day: str) -> int:
    try:
        return datetime.strptime(day, "%Y-%m-%d").weekday()
    except ValueError:
        return 0


def _failure_text(failures: int, tool_calls: int) -> str:
    """错误率 = 失败次数 / 工具调用次数；没有调用时不报比率，避免除零与误导。"""
    if tool_calls <= 0:
        return f"失败 {failures} 次"
    return f"失败 {failures} 次（错误率 {failures * 100.0 / tool_calls:.1f}%）"


def _quota_line(settings: Settings, *, day_used: int, month_used: int) -> str:
    if settings.quota_daily_tokens <= 0 and settings.quota_monthly_tokens <= 0:
        return f"配额：{NO_QUOTA_TEXT}（0 或未配置 = {UNLIMITED_TEXT}）"
    return (
        f"配额：今日已用 {day_used} / {_limit(settings.quota_daily_tokens)}，"
        f"本月已用 {month_used} / {_limit(settings.quota_monthly_tokens)}"
    )


def _limit(value: int) -> str:
    return UNLIMITED_TEXT if value <= 0 else str(value)


def _duration(seconds: object) -> str:
    total = max(0, int(float(seconds or 0)))
    if total < 60:
        return f"{total} 秒"
    minutes, _ = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} 分钟"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} 小时 {minutes} 分钟"
    days, hours = divmod(hours, 24)
    return f"{days} 天 {hours} 小时"


def _since(last_update_at: object, checked_at: object) -> str:
    if last_update_at is None:
        return "暂无"
    try:
        delta = max(0, int(float(checked_at or 0)) - int(float(last_update_at)))
    except (TypeError, ValueError):
        return "暂无"
    return f"{_duration(delta)}前"
