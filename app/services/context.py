"""服务层上下文：一次装配里传下去的东西（连接、配置、路径）。

`app/control/__main__.py` 构造它，`app/control/app.py` 只把它转交给服务层函数；
面板自身不持有 SQL、不 import `app.storage.*`（tests/offline/test_layering.py 会检查）。

凭据不在这里：需要用到凭据的地方一律经 `Settings.bot_instance()`（docs/domain.md §4）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from app.config import Settings
from app.ops.health import HEALTH_FILENAME


@dataclass(frozen=True, slots=True)
class ServiceContext:
    """服务层调用所需的全部依赖。

    `health_path` 指向机器人进程写出的心跳文件（docs/deployment.md §7）：面板读它来判断
    「机器人还在不在」，而不是自己造一份健康状态——两个进程各写一份心跳只会互相矛盾。
    """

    connection: aiosqlite.Connection
    settings: Settings
    env_path: Path
    health_path: Path

    @classmethod
    def build(
        cls,
        connection: aiosqlite.Connection,
        settings: Settings,
        *,
        env_path: Path | None = None,
        health_path: Path | None = None,
    ) -> ServiceContext:
        """从配置推导路径：`.env` 位置与心跳位置各自只有一个来源，不在这里重复硬编码。

        两个路径都允许显式覆盖（测试用临时目录，或部署时把 `.env` 放在别处）。
        """
        env_file = str(settings.model_config.get("env_file", ".env"))
        return cls(
            connection=connection,
            settings=settings,
            env_path=Path(env_file) if env_path is None else env_path,
            health_path=(settings.data_dir / HEALTH_FILENAME) if health_path is None else health_path,
        )
