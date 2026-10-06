"""BotInstance 与 Credential：凭据的归属（唯一权威说明见 docs/domain.md §1、§4）。

纯数据结构，只依赖标准库；不 import app.*，也不 import aiogram/openai/aiosqlite
（tests/offline/test_layering.py 会检查）。凭据只允许从这里读取，任何接口不得返回明文。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LLMCredentials:
    """一个实例的 LLM 接入凭据与模型档位。api_key 永不写入日志/DB/错误消息/模型上下文。"""

    base_url: str
    api_key: str
    timeout_seconds: float = 60.0
    model: str = "deepseek-flash"
    temperature: float = 0.7
    max_output_tokens: int = 1024

    def secret_values(self) -> tuple[str, ...]:
        """必须脱敏的字符串（空值不参与替换）。"""
        return tuple(value for value in (self.api_key,) if value)


@dataclass(frozen=True, slots=True)
class BotInstance:
    """一个 Telegram Bot 的运行身份。

    现在是进程内唯一实例（instance_id 默认 "default"，等价于单 Token 现状）；
    将来一个用户多个 Bot 时是"一实例一进程"，隔离靠每实例一份存储根（docs/domain.md §2）。
    """

    instance_id: str
    bot_token: str
    llm: LLMCredentials

    def secret_values(self) -> tuple[str, ...]:
        """实例相关的全部必须脱敏字符串（bot_token + LLM Key）。"""
        return tuple(value for value in (self.bot_token, *self.llm.secret_values()) if value)
