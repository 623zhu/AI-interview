"""LLM client factory — DeepSeek via langchain-openai.

DeepSeek is OpenAI-compatible, so we use ChatOpenAI with a custom base_url.
"""
from functools import lru_cache
from langchain_openai import ChatOpenAI
from app.core.config import settings


@lru_cache()
def get_llm(model: str | None = None, temperature: float = 0.3) -> ChatOpenAI:
    """Return a cached ChatOpenAI instance pointed at DeepSeek.

    Cached per (model, temperature) combination so callers can vary temperature
    without creating needless client objects.
    """
    return ChatOpenAI(
        model=model or settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=temperature,
        max_tokens=4096,
    )
