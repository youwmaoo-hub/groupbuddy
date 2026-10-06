"""集中配置：项目内唯一允许读取环境变量的模块（AGENTS.md 硬规则 11）。"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.bot_instance import BotInstance, LLMCredentials

REDACTED = "[redacted]"

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """全部运行配置。除本文件外，其他模块一律不得调用 os.environ。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- 实例身份与凭据（凭据概念上归属 BotInstance，见 docs/domain.md §1、§4） ---
    instance_id: str = Field(default="default", alias="BOT_INSTANCE_ID")
    bot_token: str = Field(alias="BOT_TOKEN")
    llm_api_key: str = Field(alias="LLM_API_KEY")

    # --- 模型 ---
    llm_base_url: str = Field(default="https://api.deepseek.com", alias="LLM_BASE_URL")
    llm_model: str = Field(default="deepseek-flash", alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_temperature: float = Field(default=0.7, alias="LLM_TEMPERATURE")
    llm_max_output_tokens: int = Field(default=1024, alias="LLM_MAX_OUTPUT_TOKENS")

    # --- 路径 ---
    data_dir: Path = Field(default=Path("storage"), alias="DATA_DIR")
    db_path: Path = Field(default=Path("storage/bot.db"), alias="DB_PATH")
    workspace_root: Path = Field(default=Path("storage/workspaces"), alias="WORKSPACE_ROOT")

    # --- 发言闸门 ---
    bot_aliases: str = Field(default="", alias="BOT_ALIASES")
    debounce_seconds: float = Field(default=1.2, alias="DEBOUNCE_SECONDS")
    debounce_max_messages: int = Field(default=5, alias="DEBOUNCE_MAX_MESSAGES")
    history_default: int = Field(default=20, alias="HISTORY_DEFAULT")
    history_complex: int = Field(default=50, alias="HISTORY_COMPLEX")
    history_chitchat: int = Field(default=10, alias="HISTORY_CHITCHAT")
    allow_private_chat: bool = Field(default=False, alias="ALLOW_PRIVATE_CHAT")
    # 主动回复（弱触发）闸门：F2.3 追问窗口、F2.4 冷却与每窗口上限
    followup_max_messages: int = Field(default=5, alias="FOLLOWUP_MAX_MESSAGES")
    proactive_cooldown_seconds: float = Field(default=20.0, alias="PROACTIVE_COOLDOWN_SECONDS")
    proactive_window_seconds: float = Field(default=300.0, alias="PROACTIVE_WINDOW_SECONDS")
    proactive_max_per_window: int = Field(default=3, alias="PROACTIVE_MAX_PER_WINDOW")

    # --- 全局人格（System1，见 docs/persona.md） ---
    persona: str = Field(default="", alias="PERSONA")

    # --- 时区与时钟 ---
    timezone: str = Field(default="Asia/Shanghai", alias="TIMEZONE")

    # --- 出站限速 ---
    send_rate_group_per_minute: int = Field(default=15, alias="SEND_RATE_GROUP_PER_MINUTE")
    send_rate_private_per_second: float = Field(default=1.0, alias="SEND_RATE_PRIVATE_PER_SECOND")
    send_rate_sticker_per_second: float = Field(default=1.0 / 20.0, alias="SEND_RATE_STICKER_PER_SECOND")
    send_backoff_max_seconds: float = Field(default=60.0, alias="SEND_BACKOFF_MAX_SECONDS")

    # --- 日志 ---
    log_level: LogLevel = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: Path = Field(default=Path("storage/logs"), alias="LOG_DIR")
    log_file: str = Field(default="bot.log", alias="LOG_FILE")

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @property
    def aliases(self) -> tuple[str, ...]:
        """Bot 昵称/别名，用于强触发判定。"""
        raw = self.bot_aliases.replace("，", ",")
        return tuple(part.strip() for part in raw.split(",") if part.strip())

    def bot_instance(self) -> BotInstance:
        """凭据的唯一出口；业务代码不直接读 bot_token/llm_api_key（docs/domain.md §4）。"""
        return BotInstance(
            instance_id=self.instance_id,
            bot_token=self.bot_token,
            llm=LLMCredentials(
                base_url=self.llm_base_url,
                api_key=self.llm_api_key,
                timeout_seconds=self.llm_timeout_seconds,
                model=self.llm_model,
                temperature=self.llm_temperature,
                max_output_tokens=self.llm_max_output_tokens,
            ),
        )

    @property
    def secrets(self) -> tuple[str, ...]:
        """必须脱敏的字符串；日志过滤器用它做替换。"""
        return self.bot_instance().secret_values()

    def describe(self) -> str:
        """启动时打印配置摘要；凭据一律遮蔽。"""
        items = {
            "BOT_INSTANCE_ID": self.instance_id,
            "LLM_BASE_URL": self.llm_base_url,
            "LLM_MODEL": self.llm_model,
            "LLM_TIMEOUT_SECONDS": self.llm_timeout_seconds,
            "DB_PATH": str(self.db_path),
            "WORKSPACE_ROOT": str(self.workspace_root),
            "BOT_ALIASES": ",".join(self.aliases),
            "DEBOUNCE_SECONDS": self.debounce_seconds,
            "DEBOUNCE_MAX_MESSAGES": self.debounce_max_messages,
            "HISTORY_DEFAULT": self.history_default,
            "HISTORY_COMPLEX": self.history_complex,
            "HISTORY_CHITCHAT": self.history_chitchat,
            "ALLOW_PRIVATE_CHAT": self.allow_private_chat,
            "FOLLOWUP_MAX_MESSAGES": self.followup_max_messages,
            "PROACTIVE_COOLDOWN_SECONDS": self.proactive_cooldown_seconds,
            "PROACTIVE_WINDOW_SECONDS": self.proactive_window_seconds,
            "PROACTIVE_MAX_PER_WINDOW": self.proactive_max_per_window,
            "TIMEZONE": self.timezone,
            "LOG_LEVEL": self.log_level,
            "BOT_TOKEN": REDACTED,
            "LLM_API_KEY": REDACTED,
        }
        return " ".join(f"{key}={value}" for key, value in items.items())

    def ensure_directories(self) -> None:
        """创建持久化目录；容器部署时这些目录由 volume 挂载。"""
        for path in (self.data_dir, self.db_path.parent, self.workspace_root, self.log_dir):
            path.mkdir(parents=True, exist_ok=True)


_CACHED: Settings | None = None


def load_settings() -> Settings:
    """读取 .env + 环境变量，返回不可变配置对象（进程内缓存一次）。"""
    global _CACHED
    if _CACHED is None:
        _CACHED = Settings()  # type: ignore[call-arg]
    return _CACHED


def redact(text: str, secrets: tuple[str, ...]) -> str:
    """把已知凭据替换为 [redacted]；日志与错误消息统一出口。"""
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, REDACTED)
    return text


def today_in_timezone(settings: Settings, now: datetime | None = None) -> str:
    """usage.day 与展示按 TIMEZONE 归属；缺失时退回本机时区（不静默用 UTC 冒充）。"""
    moment = now or datetime.now(tz=ZoneInfo("UTC"))
    try:
        zone = ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return moment.astimezone().strftime("%Y-%m-%d")
    return moment.astimezone(zone).strftime("%Y-%m-%d")


def env_present(name: str) -> bool:
    """供测试/诊断使用，返回值是否存在，不暴露值本身。"""
    return bool(os.environ.get(name))
