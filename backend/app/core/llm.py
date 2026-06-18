"""LLM client factory for DeepSeek with error classification and circuit breaking."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
import openai
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from app.core.config import settings


class LLMServiceError(Exception):
    """Stable internal error for upstream LLM failures."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "status_code": self.status_code,
        }


@dataclass
class CircuitBreakerState:
    failure_count: int = 0
    opened_until: float = 0.0


class LLMCircuitBreaker:
    """Small in-process circuit breaker for DeepSeek calls."""

    def __init__(self):
        self.state = CircuitBreakerState()

    def before_request(self) -> None:
        now = time.monotonic()
        if self.state.opened_until > now:
            remaining = int(self.state.opened_until - now)
            raise LLMServiceError(
                "llm_circuit_open",
                f"DeepSeek 服务暂时不可用，请约 {remaining} 秒后重试。",
                retryable=True,
                status_code=503,
            )

    def record_success(self) -> None:
        self.state.failure_count = 0
        self.state.opened_until = 0.0

    def record_failure(self) -> None:
        self.state.failure_count += 1
        if self.state.failure_count >= settings.LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD:
            self.state.opened_until = (
                time.monotonic() + settings.LLM_CIRCUIT_BREAKER_RECOVERY_SECONDS
            )

    def reset(self) -> None:
        self.state = CircuitBreakerState()


deepseek_circuit_breaker = LLMCircuitBreaker()


def _exception_status_code(exc: BaseException) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _message(exc: BaseException) -> str:
    return str(exc) or exc.__class__.__name__


def _is_context_length_error(exc: BaseException) -> bool:
    text = _message(exc).lower()
    return (
        "context length" in text
        or "maximum context" in text
        or ("token" in text and ("exceed" in text or "limit" in text or "too long" in text))
    )


def classify_llm_exception(exc: BaseException) -> LLMServiceError:
    """Map provider/library exceptions to stable internal LLM error codes."""

    if isinstance(exc, LLMServiceError):
        return exc

    status_code = _exception_status_code(exc)

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException, openai.APITimeoutError)):
        return LLMServiceError(
            "llm_timeout",
            "DeepSeek 请求超时，请稍后重试。",
            retryable=True,
            status_code=status_code,
        )

    if isinstance(exc, openai.RateLimitError) or status_code == 429:
        return LLMServiceError(
            "llm_rate_limited",
            "DeepSeek 请求过于频繁，请稍后重试。",
            retryable=True,
            status_code=status_code or 429,
        )

    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)) or status_code in {401, 403}:
        return LLMServiceError(
            "llm_auth_failed",
            "DeepSeek 鉴权失败，请检查 API Key 配置。",
            retryable=False,
            status_code=status_code,
        )

    if _is_context_length_error(exc):
        return LLMServiceError(
            "llm_context_length_exceeded",
            "本次输入内容过长，已超过模型上下文限制。",
            retryable=False,
            status_code=status_code,
        )

    if isinstance(exc, openai.BadRequestError) or status_code == 400:
        return LLMServiceError(
            "llm_bad_request",
            "DeepSeek 拒绝了本次请求，请检查请求参数。",
            retryable=False,
            status_code=status_code or 400,
        )

    if isinstance(exc, openai.APIConnectionError):
        return LLMServiceError(
            "llm_connection_error",
            "DeepSeek 连接失败，请稍后重试。",
            retryable=True,
            status_code=status_code,
        )

    if isinstance(exc, openai.InternalServerError) or (status_code is not None and status_code >= 500):
        return LLMServiceError(
            "llm_provider_unavailable",
            "DeepSeek 服务不可用，请稍后重试。",
            retryable=True,
            status_code=status_code,
        )

    return LLMServiceError(
        "llm_unknown_error",
        "DeepSeek 请求失败，请稍后重试。",
        retryable=True,
        status_code=status_code,
    )


def should_trip_circuit(error: LLMServiceError) -> bool:
    return error.code in {
        "llm_timeout",
        "llm_rate_limited",
        "llm_connection_error",
        "llm_provider_unavailable",
        "llm_unknown_error",
    }


def should_retry(error: LLMServiceError) -> bool:
    return error.code in {
        "llm_timeout",
        "llm_rate_limited",
        "llm_connection_error",
        "llm_provider_unavailable",
        "llm_unknown_error",
    }


def _retry_delay_seconds(failed_attempt_index: int) -> float:
    delay = settings.LLM_RETRY_BACKOFF_BASE_SECONDS * (2 ** max(failed_attempt_index - 1, 0))
    return min(delay, settings.LLM_RETRY_BACKOFF_MAX_SECONDS)


def _deepseek_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        timeout=settings.DEEPSEEK_TIMEOUT_SECONDS,
        connect=settings.DEEPSEEK_CONNECT_TIMEOUT_SECONDS,
        read=settings.DEEPSEEK_READ_TIMEOUT_SECONDS,
        write=settings.DEEPSEEK_TIMEOUT_SECONDS,
        pool=settings.DEEPSEEK_CONNECT_TIMEOUT_SECONDS,
    )


class CircuitBreakerRunnable(Runnable):
    """Runnable wrapper that applies the DeepSeek circuit breaker."""

    def __init__(self, inner: Runnable):
        self.inner = inner

    def invoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
        deepseek_circuit_breaker.before_request()
        max_attempts = settings.DEEPSEEK_MAX_RETRIES + 1

        for attempt in range(1, max_attempts + 1):
            try:
                result = self.inner.invoke(input, config=config, **kwargs)
                deepseek_circuit_breaker.record_success()
                return result
            except Exception as exc:
                error = classify_llm_exception(exc)
                if not should_retry(error) or attempt >= max_attempts:
                    if should_trip_circuit(error):
                        deepseek_circuit_breaker.record_failure()
                    raise error from exc
                time.sleep(_retry_delay_seconds(attempt))

        raise LLMServiceError("llm_unknown_error", "DeepSeek 请求失败，请稍后重试。", retryable=True)

    async def ainvoke(self, input: Any, config: Any | None = None, **kwargs: Any) -> Any:
        deepseek_circuit_breaker.before_request()
        max_attempts = settings.DEEPSEEK_MAX_RETRIES + 1

        for attempt in range(1, max_attempts + 1):
            try:
                result = await self.inner.ainvoke(input, config=config, **kwargs)
                deepseek_circuit_breaker.record_success()
                return result
            except Exception as exc:
                error = classify_llm_exception(exc)
                if not should_retry(error) or attempt >= max_attempts:
                    if should_trip_circuit(error):
                        deepseek_circuit_breaker.record_failure()
                    raise error from exc
                await asyncio.sleep(_retry_delay_seconds(attempt))

        raise LLMServiceError("llm_unknown_error", "DeepSeek 请求失败，请稍后重试。", retryable=True)

    def bind_tools(self, *args: Any, **kwargs: Any) -> "CircuitBreakerRunnable":
        return CircuitBreakerRunnable(self.inner.bind_tools(*args, **kwargs))

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


@lru_cache()
def get_llm(model: str | None = None, temperature: float = 0.3) -> CircuitBreakerRunnable:
    """Return a cached DeepSeek chat model protected by a circuit breaker."""

    llm = ChatOpenAI(
        model=model or settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=temperature,
        max_tokens=4096,
        timeout=_deepseek_timeout(),
        max_retries=0,
    )
    return CircuitBreakerRunnable(llm)
