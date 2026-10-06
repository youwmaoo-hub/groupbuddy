"""DeepSeek（OpenAI 兼容）客户端：只负责一次补全与 usage 提取。"""

from __future__ import annotations

from dataclasses import dataclass

from openai import AsyncOpenAI

from app.domain.bot_instance import LLMCredentials


@dataclass(frozen=True, slots=True)
class LLMReply:
    text: str
    model: str
    input_tokens: int
    cached_tokens: int
    output_tokens: int


class LLMError(RuntimeError):
    """调用失败（超时、限流、网络、空响应）。"""


class DeepSeekClient:
    def __init__(self, credentials: LLMCredentials, client: AsyncOpenAI | None = None) -> None:
        self._llm = credentials
        self._client = client or AsyncOpenAI(
            api_key=credentials.api_key,
            base_url=credentials.base_url,
            timeout=credentials.timeout_seconds,
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMReply:
        try:
            response = await self._client.chat.completions.create(
                model=model or self._llm.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self._llm.temperature if temperature is None else temperature,
                max_tokens=self._llm.max_output_tokens if max_tokens is None else max_tokens,
            )
        except Exception as error:  # 统一转成业务错误，细节留给日志
            raise LLMError(f"{type(error).__name__}: {error}") from error

        if not response.choices:
            raise LLMError("模型返回空 choices")
        text = response.choices[0].message.content or ""
        usage = response.usage
        return LLMReply(
            text=text,
            model=str(getattr(response, "model", "") or self._llm.model),
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            cached_tokens=_cached_tokens(usage),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )

    async def aclose(self) -> None:
        await self._client.close()


def _cached_tokens(usage: object) -> int:
    """OpenAI 格式在 prompt_tokens_details.cached_tokens，DeepSeek 原生给 prompt_cache_hit_tokens。"""
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", None)
    if cached is None:
        cached = getattr(usage, "prompt_cache_hit_tokens", 0)
    return int(cached or 0)
