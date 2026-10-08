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

#: 面板访问口令的最短长度：太短的口令会被 `redact()` 误伤日志里的无关文本。
MIN_PANEL_TOKEN_CHARS = 12

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
    #: 更强模型（可选）：留空 = 未配置，复杂任务也走 `llm_model`（docs/token.md §5）。
    llm_model_strong: str = Field(default="", alias="LLM_MODEL_STRONG")
    llm_timeout_seconds: float = Field(default=60.0, alias="LLM_TIMEOUT_SECONDS")
    llm_temperature: float = Field(default=0.7, alias="LLM_TEMPERATURE")
    llm_max_output_tokens: int = Field(default=1024, alias="LLM_MAX_OUTPUT_TOKENS")
    #: 群回复字数上限：提示词按此约束，超长再按句末裁一刀（0 = 不限；docs/token.md §5）。
    reply_max_chars: int = Field(default=280, ge=0, alias="REPLY_MAX_CHARS")

    # --- 路径 ---
    data_dir: Path = Field(default=Path("storage"), alias="DATA_DIR")
    db_path: Path = Field(default=Path("storage/bot.db"), alias="DB_PATH")
    workspace_root: Path = Field(default=Path("storage/workspaces"), alias="WORKSPACE_ROOT")

    # --- 发言闸门 ---
    bot_aliases: str = Field(default="", alias="BOT_ALIASES")
    # 关掉合并：每条消息各自成批（0 秒静默期 + 每批 1 条）；>0/>=2 时恢复连发合并
    debounce_seconds: float = Field(default=0.0, alias="DEBOUNCE_SECONDS")
    debounce_max_messages: int = Field(default=1, alias="DEBOUNCE_MAX_MESSAGES")
    history_default: int = Field(default=20, alias="HISTORY_DEFAULT")
    history_complex: int = Field(default=50, alias="HISTORY_COMPLEX")
    history_chitchat: int = Field(default=10, alias="HISTORY_CHITCHAT")
    allow_private_chat: bool = Field(default=False, alias="ALLOW_PRIVATE_CHAT")
    # 主动接话闸门：F2.4 只保留冷却；重复消息过滤见 app/gate/limits.py::RepeatGuard
    followup_max_messages: int = Field(default=5, alias="FOLLOWUP_MAX_MESSAGES")
    proactive_cooldown_seconds: float = Field(default=20.0, alias="PROACTIVE_COOLDOWN_SECONDS")
    duplicate_window_seconds: float = Field(default=300.0, alias="DUPLICATE_WINDOW_SECONDS")
    # 群宠体验升级（阶段 8）：同话题窗口、久静后开口阈值（只用于标注内容原因码）
    proactive_topic_max_messages: int = Field(default=8, ge=1, alias="PROACTIVE_TOPIC_MAX_MESSAGES")
    proactive_quiet_messages: int = Field(default=20, ge=1, alias="PROACTIVE_QUIET_MESSAGES")

    # --- 记忆（阶段 6，docs/memory.md） ---
    history_budget_chars: int = Field(default=6000, alias="HISTORY_BUDGET_CHARS")
    summary_min_messages: int = Field(default=40, alias="SUMMARY_MIN_MESSAGES")
    summary_quiet_seconds: float = Field(default=120.0, alias="SUMMARY_QUIET_SECONDS")
    summary_max_chars: int = Field(default=300, alias="SUMMARY_MAX_CHARS")
    summary_max_output_tokens: int = Field(default=400, alias="SUMMARY_MAX_OUTPUT_TOKENS")
    summary_poll_seconds: float = Field(default=15.0, alias="SUMMARY_POLL_SECONDS")

    # --- 工具（阶段 3） ---
    tool_max_rounds: int = Field(default=2, ge=0, le=4, alias="TOOL_MAX_ROUNDS")
    # search_web 后端未定（docs/requirements.md §4 #1）：none = 不注册该工具
    search_backend: Literal["none", "fake"] = Field(default="none", alias="SEARCH_BACKEND")

    # --- 配额（阶段 8 F5.3，docs/token.md §4.1） ---
    # 0 或未配置 = 不限额（与 SEARCH_BACKEND=none / SANDBOX_BACKEND=none 的"关闭"写法一致）
    quota_daily_tokens: int = Field(default=0, ge=0, alias="QUOTA_DAILY_TOKENS")
    quota_monthly_tokens: int = Field(default=0, ge=0, alias="QUOTA_MONTHLY_TOKENS")

    # --- 沙箱（阶段 7，docs/security.md §4） ---
    sandbox_backend: Literal["auto", "podman", "docker", "none"] = Field(default="auto", alias="SANDBOX_BACKEND")
    sandbox_image: str = Field(default="python:3.12-slim", alias="SANDBOX_IMAGE")
    # auto=rootless Podman（keep-id 映射）允许 workspace 写入；off=关闭。Docker 一律不启用 Tier B
    sandbox_tier_b: Literal["auto", "off"] = Field(default="auto", alias="SANDBOX_TIER_B")
    sandbox_timeout_default: int = Field(default=15, ge=1, le=120, alias="SANDBOX_TIMEOUT_DEFAULT")
    sandbox_timeout_max: int = Field(default=30, ge=1, le=300, alias="SANDBOX_TIMEOUT_MAX")
    sandbox_memory_mb: int = Field(default=256, ge=32, alias="SANDBOX_MEMORY_MB")
    sandbox_cpus: float = Field(default=0.5, gt=0, alias="SANDBOX_CPUS")
    sandbox_pids: int = Field(default=64, ge=8, alias="SANDBOX_PIDS")
    sandbox_max_concurrent: int = Field(default=2, ge=1, le=8, alias="SANDBOX_MAX_CONCURRENT")
    sandbox_output_kb: int = Field(default=8, ge=1, le=1024, alias="SANDBOX_OUTPUT_KB")
    sandbox_temp_dir: Path = Field(default=Path("storage/sandbox"), alias="SANDBOX_TEMP_DIR")

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

    # --- 控制面板（阶段 10，docs/requirements.md F6） ---
    # 默认关闭：不配置就完全不开放任何端口（安全默认值，见 docs/security.md §2）。
    panel_enabled: bool = Field(default=False, alias="PANEL_ENABLED")
    # 默认只监听本机：要对外开放必须显式改 PANEL_HOST，并自行置于反向代理/防火墙之后。
    panel_host: str = Field(default="127.0.0.1", alias="PANEL_HOST")
    panel_port: int = Field(default=8787, ge=1, le=65535, alias="PANEL_PORT")
    #: 可写凭据；面板用它判定"管理员级"请求（Authorization: Bearer）。
    panel_token: str = Field(default="", alias="PANEL_TOKEN")
    #: 只读凭据：只能看概览/群设置/日志，不能改任何东西。
    panel_readonly_token: str = Field(default="", alias="PANEL_READONLY_TOKEN")

    @field_validator("panel_token", "panel_readonly_token", mode="after")
    @classmethod
    def _check_panel_token(cls, value: str) -> str:
        """空 = 未配置；非空则必须够长，否则 short token 会被日志脱敏误伤无关文本。"""
        token = value.strip()
        if token and len(token) < MIN_PANEL_TOKEN_CHARS:
            raise ValueError(f"面板访问口令至少 {MIN_PANEL_TOKEN_CHARS} 个字符（或留空表示未配置）")
        return token

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
        """必须脱敏的字符串；日志过滤器用它做替换。

        Bot Token / API Key 来自 `BotInstance`（docs/domain.md §4）；面板口令同样必须脱敏，
        否则一次异常堆栈或访问日志就能把面板口令写进日志文件。
        """
        return (*self.bot_instance().secret_values(), *self.panel_tokens)

    @property
    def panel_tokens(self) -> tuple[str, ...]:
        """已配置的面板口令（含只读口令）；供脱敏使用，不做任何形式的展示。"""
        return tuple(token for token in (self.panel_token, self.panel_readonly_token) if token)

    def describe(self) -> str:
        """启动时打印配置摘要；凭据一律遮蔽。"""
        items = {
            "BOT_INSTANCE_ID": self.instance_id,
            "LLM_BASE_URL": self.llm_base_url,
            "LLM_MODEL": self.llm_model,
            "LLM_MODEL_STRONG": self.llm_model_strong or "(未配置)",
            "LLM_TIMEOUT_SECONDS": self.llm_timeout_seconds,
            "DB_PATH": str(self.db_path),
            "WORKSPACE_ROOT": str(self.workspace_root),
            "BOT_ALIASES": ",".join(self.aliases),
            "DEBOUNCE_SECONDS": self.debounce_seconds,
            "DEBOUNCE_MAX_MESSAGES": self.debounce_max_messages,
            "HISTORY_DEFAULT": self.history_default,
            "HISTORY_COMPLEX": self.history_complex,
            "HISTORY_CHITCHAT": self.history_chitchat,
            "HISTORY_BUDGET_CHARS": self.history_budget_chars,
            "SUMMARY_MIN_MESSAGES": self.summary_min_messages,
            "SUMMARY_QUIET_SECONDS": self.summary_quiet_seconds,
            "SUMMARY_MAX_CHARS": self.summary_max_chars,
            "SUMMARY_MAX_OUTPUT_TOKENS": self.summary_max_output_tokens,
            "SUMMARY_POLL_SECONDS": self.summary_poll_seconds,
            "ALLOW_PRIVATE_CHAT": self.allow_private_chat,
            "FOLLOWUP_MAX_MESSAGES": self.followup_max_messages,
            "PROACTIVE_COOLDOWN_SECONDS": self.proactive_cooldown_seconds,
            "DUPLICATE_WINDOW_SECONDS": self.duplicate_window_seconds,
            "PROACTIVE_TOPIC_MAX_MESSAGES": self.proactive_topic_max_messages,
            "PROACTIVE_QUIET_MESSAGES": self.proactive_quiet_messages,
            "TOOL_MAX_ROUNDS": self.tool_max_rounds,
            "SEARCH_BACKEND": self.search_backend,
            "QUOTA_DAILY_TOKENS": self.quota_daily_tokens,
            "QUOTA_MONTHLY_TOKENS": self.quota_monthly_tokens,
            "SANDBOX_BACKEND": self.sandbox_backend,
            "SANDBOX_IMAGE": self.sandbox_image,
            "SANDBOX_TIER_B": self.sandbox_tier_b,
            "SANDBOX_TIMEOUT_DEFAULT": self.sandbox_timeout_default,
            "SANDBOX_TIMEOUT_MAX": self.sandbox_timeout_max,
            "SANDBOX_MEMORY_MB": self.sandbox_memory_mb,
            "SANDBOX_CPUS": self.sandbox_cpus,
            "SANDBOX_PIDS": self.sandbox_pids,
            "SANDBOX_MAX_CONCURRENT": self.sandbox_max_concurrent,
            "SANDBOX_OUTPUT_KB": self.sandbox_output_kb,
            "TIMEZONE": self.timezone,
            "LOG_LEVEL": self.log_level,
            "PANEL_ENABLED": self.panel_enabled,
            "PANEL_HOST": self.panel_host,
            "PANEL_PORT": self.panel_port,
            "BOT_TOKEN": REDACTED,
            "LLM_API_KEY": REDACTED,
            "PANEL_TOKEN": REDACTED if self.panel_token else "(未配置)",
            "PANEL_READONLY_TOKEN": REDACTED if self.panel_readonly_token else "(未配置)",
        }
        return " ".join(f"{key}={value}" for key, value in items.items())

    def subprocess_env(self) -> dict[str, str]:
        """给沙箱 CLI 子进程的最小环境：白名单拷贝，绝不含凭据（docs/security.md §4）。

        只有本模块可以读环境变量（AGENTS.md §3 规则 11 + 分层测试）。
        """
        allowed = (
            "PATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "TMPDIR",
            "XDG_RUNTIME_DIR",
            "XDG_DATA_HOME",
            "DBUS_SESSION_BUS_ADDRESS",
            "CONTAINER_HOST",
        )
        return {name: os.environ[name] for name in allowed if os.environ.get(name)}

    def ensure_directories(self) -> None:
        """创建持久化目录；容器部署时这些目录由 volume 挂载。"""
        for path in (self.data_dir, self.db_path.parent, self.workspace_root, self.log_dir, self.sandbox_temp_dir):
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
