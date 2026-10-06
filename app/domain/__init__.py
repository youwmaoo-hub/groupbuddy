"""领域对象（唯一权威说明见 docs/domain.md）：对象模型与身份模型。

本包只放数据结构，不含业务逻辑，也不依赖 app.* 之外的东西（不 import aiogram/openai/aiosqlite）。
"""

from app.domain.bot_instance import BotInstance, LLMCredentials

__all__ = ["BotInstance", "LLMCredentials"]
