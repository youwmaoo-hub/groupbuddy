"""健康状态：`storage/health.json` 心跳与 `/health` 命令共用的唯一状态（docs/deployment.md §7）。

只读轻量：进程存活（心跳新鲜度）、最后一次成功处理的更新时间、数据库可读、出站队列深度。
不调用模型、不产生 token 成本；快照只含计数与时间戳，不含路径、异常堆栈、环境变量或凭据。
心跳写失败只告警，不自动重启（避免重启风暴，docs/deployment.md §7）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

#: 心跳文件名（`<DATA_DIR>/health.json`）。
HEALTH_FILENAME = "health.json"

#: 心跳周期（秒）：足够新鲜，又不产生可感知的写放大。
HEALTH_INTERVAL_SECONDS = 60.0


class HealthState:
    """健康判定与快照；探测回调由装配方注入，本模块不依赖上层。"""

    def __init__(
        self,
        *,
        instance_id: str,
        db_check: Callable[[], Awaitable[bool]] | None = None,
        pending: Callable[[], int] | None = None,
        started_at: float | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._instance_id = instance_id
        self._db_check = db_check
        self._pending = pending
        self._clock = clock
        self._started_at = clock() if started_at is None else started_at
        self._last_update_at: float | None = None

    def mark_update(self, now: float | None = None) -> None:
        """记下最近一次成功处理的更新（由接收路径调用，无 IO）。"""
        self._last_update_at = self._clock() if now is None else now

    async def snapshot(self) -> dict[str, object]:
        """生成状态快照；任何探测异常都降级为"不可读"，绝不抛出、不泄露细节。"""
        db_ok = False
        if self._db_check is not None:
            try:
                db_ok = bool(await self._db_check())
            except Exception:
                logger.warning("健康检查：数据库探测失败", exc_info=True)
        else:
            db_ok = True

        pending: int | None = None
        if self._pending is not None:
            try:
                pending = int(self._pending())
            except Exception:
                logger.warning("健康检查：出站队列深度读取失败", exc_info=True)

        now = self._clock()
        return {
            "instance": self._instance_id,
            "ok": db_ok,
            "started_at": self._started_at,
            "checked_at": now,
            "uptime_s": max(0.0, now - self._started_at),
            "last_update_at": self._last_update_at,
            "db_ok": db_ok,
            "outbound_pending": pending,
        }


def write_snapshot(path: Path, snapshot: dict[str, object]) -> None:
    """原子写心跳文件（同目录临时文件 + `os.replace`），读方永远看不到半截 JSON。"""
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def read_snapshot(path: Path) -> dict[str, object] | None:
    """读心跳文件：面板判断机器人是否在运行的唯一依据。

    文件不存在、不可读或内容损坏时一律返回 None——面板据此显示"没有心跳"，
    而不是把异常渲染成"运行正常"（docs/deployment.md §7）。
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        logger.warning("健康心跳读取失败 path=%s", path, exc_info=True)
        return None
    return parse_snapshot(raw)


def parse_snapshot(raw: str) -> dict[str, object] | None:
    """解析心跳 JSON；坏数据按"没有心跳"处理，不让面板接口 500。"""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("健康心跳内容无法解析")
        return None
    return data if isinstance(data, dict) else None


async def health_loop(
    state: HealthState,
    path: Path,
    *,
    stop: asyncio.Event,
    interval: float = HEALTH_INTERVAL_SECONDS,
) -> None:
    """先写一次心跳，再按周期重写；写失败只告警（docs/deployment.md §7）。"""
    while not stop.is_set():
        try:
            write_snapshot(path, await state.snapshot())
        except Exception:
            logger.warning("健康心跳写入失败", exc_info=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
        return
