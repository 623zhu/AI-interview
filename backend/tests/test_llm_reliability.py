import pytest
from langchain_core.runnables import Runnable

from app.agent import parse_agent
from app.core.config import settings
from app.core.llm import (
    CircuitBreakerRunnable,
    LLMServiceError,
    classify_llm_exception,
    deepseek_circuit_breaker,
)


class SuccessRunnable(Runnable):
    def invoke(self, input, config=None, **kwargs):
        return {"ok": True}

    async def ainvoke(self, input, config=None, **kwargs):
        return {"ok": True}

    def bind_tools(self, *args, **kwargs):
        return self


class TimeoutRunnable(Runnable):
    def invoke(self, input, config=None, **kwargs):
        raise TimeoutError("timed out")

    async def ainvoke(self, input, config=None, **kwargs):
        raise TimeoutError("timed out")


class FlakyRunnable(Runnable):
    def __init__(self, failures_before_success: int):
        self.failures_before_success = failures_before_success
        self.invoke_count = 0
        self.ainvoke_count = 0

    def invoke(self, input, config=None, **kwargs):
        self.invoke_count += 1
        if self.invoke_count <= self.failures_before_success:
            raise TimeoutError("timed out")
        return {"ok": True}

    async def ainvoke(self, input, config=None, **kwargs):
        self.ainvoke_count += 1
        if self.ainvoke_count <= self.failures_before_success:
            raise TimeoutError("timed out")
        return {"ok": True}


class StatusRunnable(Runnable):
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.invoke_count = 0

    def invoke(self, input, config=None, **kwargs):
        self.invoke_count += 1
        raise FakeStatusError(self.status_code)

    async def ainvoke(self, input, config=None, **kwargs):
        raise FakeStatusError(self.status_code)


class FakeStatusError(Exception):
    def __init__(self, status_code: int, message: str = "provider error"):
        super().__init__(message)
        self.status_code = status_code


class BadJsonLLM:
    async def ainvoke(self, messages):
        return type("Response", (), {"content": "not json"})()


@pytest.fixture(autouse=True)
def reset_breaker():
    deepseek_circuit_breaker.reset()
    yield
    deepseek_circuit_breaker.reset()


def test_classify_llm_timeout():
    error = classify_llm_exception(TimeoutError("timed out"))

    assert error.code == "llm_timeout"
    assert error.retryable is True


def test_classify_llm_rate_limit_by_status_code():
    error = classify_llm_exception(FakeStatusError(429))

    assert error.code == "llm_rate_limited"
    assert error.retryable is True
    assert error.status_code == 429


def test_classify_llm_auth_failure_by_status_code():
    error = classify_llm_exception(FakeStatusError(401))

    assert error.code == "llm_auth_failed"
    assert error.retryable is False


def test_classify_llm_context_length_from_message():
    error = classify_llm_exception(RuntimeError("maximum context length exceeded"))

    assert error.code == "llm_context_length_exceeded"
    assert error.retryable is False


def test_circuit_breaker_opens_after_retryable_failures(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr(settings, "LLM_CIRCUIT_BREAKER_RECOVERY_SECONDS", 60)
    monkeypatch.setattr(settings, "DEEPSEEK_MAX_RETRIES", 0)
    wrapped = CircuitBreakerRunnable(TimeoutRunnable())

    for _ in range(2):
        with pytest.raises(LLMServiceError) as exc:
            wrapped.invoke("hello")
        assert exc.value.code == "llm_timeout"

    with pytest.raises(LLMServiceError) as open_exc:
        wrapped.invoke("hello")

    assert open_exc.value.code == "llm_circuit_open"


def test_circuit_breaker_success_resets_failures(monkeypatch):
    monkeypatch.setattr(settings, "LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr(settings, "DEEPSEEK_MAX_RETRIES", 0)
    wrapped = CircuitBreakerRunnable(TimeoutRunnable())

    with pytest.raises(LLMServiceError):
        wrapped.invoke("hello")

    CircuitBreakerRunnable(SuccessRunnable()).invoke("hello")

    assert deepseek_circuit_breaker.state.failure_count == 0
    assert deepseek_circuit_breaker.state.opened_until == 0


def test_bind_tools_keeps_circuit_breaker_wrapper():
    wrapped = CircuitBreakerRunnable(SuccessRunnable())

    bound = wrapped.bind_tools([])

    assert isinstance(bound, CircuitBreakerRunnable)


def test_retry_eventually_succeeds_and_does_not_trip_circuit(monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_MAX_RETRIES", 2)
    monkeypatch.setattr(settings, "LLM_RETRY_BACKOFF_BASE_SECONDS", 0)
    monkeypatch.setattr(settings, "LLM_RETRY_BACKOFF_MAX_SECONDS", 0)
    inner = FlakyRunnable(failures_before_success=2)

    result = CircuitBreakerRunnable(inner).invoke("hello")

    assert result == {"ok": True}
    assert inner.invoke_count == 3
    assert deepseek_circuit_breaker.state.failure_count == 0


def test_non_retryable_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_MAX_RETRIES", 2)
    inner = StatusRunnable(401)

    with pytest.raises(LLMServiceError) as exc:
        CircuitBreakerRunnable(inner).invoke("hello")

    assert exc.value.code == "llm_auth_failed"
    assert inner.invoke_count == 1


@pytest.mark.asyncio
async def test_async_retry_eventually_succeeds(monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_MAX_RETRIES", 2)
    monkeypatch.setattr(settings, "LLM_RETRY_BACKOFF_BASE_SECONDS", 0)
    monkeypatch.setattr(settings, "LLM_RETRY_BACKOFF_MAX_SECONDS", 0)
    inner = FlakyRunnable(failures_before_success=1)

    result = await CircuitBreakerRunnable(inner).ainvoke("hello")

    assert result == {"ok": True}
    assert inner.ainvoke_count == 2


@pytest.mark.asyncio
async def test_parse_resume_classifies_bad_json_response(monkeypatch):
    monkeypatch.setattr(parse_agent, "get_llm", lambda temperature=0.1: BadJsonLLM())

    with pytest.raises(LLMServiceError) as exc:
        await parse_agent.parse_resume("raw resume")

    assert exc.value.code == "llm_response_format_error"
    assert exc.value.retryable is True
