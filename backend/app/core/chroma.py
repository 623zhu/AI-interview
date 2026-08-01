"""Chroma vector database — interview question knowledge base."""
from __future__ import annotations

import chromadb
from chromadb.config import Settings as ChromaSettings
from app.core.config import settings

_client: chromadb.PersistentClient | None = None
_collections: dict[str, chromadb.Collection] = {}


def get_chroma_client() -> chromadb.PersistentClient:
    """Get or create the Chroma persistent client."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def _get_or_create(name: str, description: str) -> chromadb.Collection:
    """Get or create a Chroma collection by name."""
    if name not in _collections:
        client = get_chroma_client()
        try:
            _collections[name] = client.get_collection(name)
        except Exception:
            _collections[name] = client.create_collection(
                name=name,
                metadata={
                    "hnsw:space": "cosine",
                    "description": description,
                }
            )
    return _collections[name]


def get_question_collection() -> chromadb.Collection:
    """Get the interview_questions collection for 面试出题."""
    return _get_or_create("interview_questions", "面试出题知识库 - 问题向量索引")


def reset():
    """Reset the question collection (useful for reindexing)."""
    global _collections
    client = get_chroma_client()
    try:
        client.delete_collection("interview_questions")
    except Exception:
        pass
    _collections = {}
