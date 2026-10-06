"""日志：统一入口，写入前强制脱敏（AGENTS.md 硬规则 11）。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config import Settings, redact

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class SecretFilter(logging.Filter):
    """在日志落盘/落终端之前替换凭据，兜底任何位置的意外输出。"""

    def __init__(self, secrets: tuple[str, ...]) -> None:
        super().__init__()
        self._secrets = secrets

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg), self._secrets)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {key: redact(str(value), self._secrets) for key, value in record.args.items()}
            else:
                record.args = tuple(redact(str(value), self._secrets) for value in record.args)
        return True


def setup_logging(settings: Settings) -> logging.Logger:
    """配置根 logger：终端 + 轮转文件，两者都带脱敏过滤器。"""
    settings.ensure_directories()
    level = getattr(logging, settings.log_level)

    formatter = logging.Formatter(LOG_FORMAT)
    secret_filter = SecretFilter(settings.secrets)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(secret_filter)

    file_handler = RotatingFileHandler(
        settings.log_dir / settings.log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(secret_filter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(stream)
    root.addHandler(file_handler)

    # 第三方库降噪：只保留告警以上
    for noisy in ("aiogram", "httpx", "httpcore", "openai"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    logger = logging.getLogger("app")
    logger.info("配置加载完成 %s", settings.describe())
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
