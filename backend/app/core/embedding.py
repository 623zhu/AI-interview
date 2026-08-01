"""Ollama embedding client — direct OpenAI-compatible API.

Uses bge-m3 via Ollama's /v1/embeddings endpoint.
Avoids langchain_openai because it pre-tokenizes input (Ollama needs raw text).
"""
from functools import lru_cache
from openai import OpenAI
from app.core.config import settings


class OllamaEmbeddings:
    """Thin wrapper around Ollama's OpenAI-compatible embeddings API.

    Mirrors langchain's embed_documents / embed_query interface so the
    rest of the code doesn't need to change.
    """

    def __init__(self, model: str, base_url: str):
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key="ollama")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of documents (batch)."""
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self.model,
            input=texts,  # raw strings — Ollama handles both str and list[str]
        )
        # Sort by index to preserve order
        sorted_data = sorted(response.data, key=lambda d: d.index)
        return [d.embedding for d in sorted_data]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        response = self._client.embeddings.create(
            model=self.model,
            input=text,
        )
        return response.data[0].embedding


@lru_cache()
def get_embeddings() -> OllamaEmbeddings:
    """Get or create the Ollama embedding client."""
    return OllamaEmbeddings(
        model=settings.EMBEDDING_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
    )
