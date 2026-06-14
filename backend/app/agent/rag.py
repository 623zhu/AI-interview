from __future__ import annotations

"""RAG module — Chroma vector search for interview questions."""

import logging
import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chroma import get_question_collection
from app.core.embedding import get_embeddings
from app.core.reranker import rerank as rerank_pairs
from app.models.question import Question

logger = logging.getLogger(__name__)

_ZERO_VECTOR_DIM = 1024  # bge-m3 embedding dimension


@dataclass
class SearchResult:
    id: str
    score: float
    metadata: dict[str, Any]


def _embed_robust(texts: list[str]) -> list[list[float]]:
    """Embed texts one-at-a-time with NaN fallback."""
    embeddings = get_embeddings()
    vectors: list[list[float]] = []
    for i, text in enumerate(texts):
        try:
            vec = embeddings.embed_query(text)
            if any(math.isnan(v) for v in vec):
                raise ValueError("NaN in embedding")
            vectors.append(vec)
        except Exception:
            logger.warning("Embedding failed at index %d, using zero vector", i)
            vectors.append([0.0] * _ZERO_VECTOR_DIM)
    return vectors


# ── Interview Question Knowledge Base ────────────────────

def _question_to_text(q: Question) -> str:
    """Convert a Question to embedding text."""
    return f"{q.category} | {q.job_category or ''} | {q.difficulty} | {q.content}"


async def sync_questions_to_chroma(db: AsyncSession) -> int:
    """Sync all active questions from MySQL to Chroma.

    Clears stale entries first, then upserts current ones.
    Returns the number of questions synced.
    """
    result = await db.execute(select(Question).where(Question.is_active == True))
    questions = result.scalars().all()

    collection = get_question_collection()

    if not questions:
        # Delete all — nothing active
        try:
            existing = collection.get()
            if existing.get("ids"):
                collection.delete(ids=existing["ids"])
                logger.info("Deleted all %d stale questions from Chroma", len(existing["ids"]))
        except Exception:
            pass
        return 0

    # Clear stale entries not in MySQL
    try:
        existing_ids = set(collection.get().get("ids", []))
        current_ids = {q.id for q in questions}
        stale = existing_ids - current_ids
        if stale:
            collection.delete(ids=list(stale))
            logger.info("Deleted %d stale questions from Chroma", len(stale))
    except Exception:
        pass

    texts = [_question_to_text(q) for q in questions]
    vectors = _embed_robust(texts)

    collection.upsert(
        ids=[q.id for q in questions],
        embeddings=vectors,
        documents=texts,
        metadatas=[{
            "category": q.category,
            "job_category": q.job_category or "",
            "difficulty": q.difficulty,
            "mysql_id": q.id,
        } for q in questions],
    )
    logger.info("Synced %d questions to Chroma", len(questions))
    return len(questions)


async def search_questions(
    query: str,
    category: str | None = None,
    difficulty: str | None = None,
    k: int = 20,
    *,
    rerank: bool = True,
    over_fetch: int = 30,
) -> list[SearchResult]:
    """Search interview questions by semantic similarity, optionally reranked.

    Args:
        query: Search text (job title + skills + requirements)
        category: Optional filter (e.g., "basic", "scenario", "open_ended")
        difficulty: Optional difficulty filter ("easy", "medium", "hard")
        k: Number of candidates to return after reranking
        rerank: If True, vector-recall ``over_fetch`` candidates and rerank to ``k``
        over_fetch: Recall depth used before reranking; ignored when rerank=False
    """
    collection = get_question_collection()
    embeddings = get_embeddings()

    try:
        query_vector = embeddings.embed_query(query)
    except Exception:
        logger.warning("Embedding failed for question search query, returning empty results")
        return []

    # Build Chroma where filter
    where_clause = None
    conditions = []
    if category:
        conditions.append({"category": category})
    if difficulty:
        conditions.append({"difficulty": difficulty})
    if len(conditions) == 1:
        where_clause = conditions[0]
    elif len(conditions) > 1:
        where_clause = {"$and": conditions}

    n_results = max(k, over_fetch) if rerank else k
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=min(n_results, 50),
        where=where_clause,
    )

    items: list[SearchResult] = []
    docs: list[str] = []
    if results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
            distance = results["distances"][0][i] if results.get("distances") else 0
            doc_text = (
                results["documents"][0][i]
                if results.get("documents") and results["documents"][0]
                else ""
            )
            items.append(SearchResult(
                id=doc_id,
                score=1 - distance,
                metadata=metadata or {},
            ))
            docs.append(doc_text)

    if not items:
        return []

    if rerank and len(items) > 1:
        scores = rerank_pairs(query, docs)
        if scores is not None and len(scores) == len(items):
            ranked = sorted(zip(scores, items), key=lambda x: x[0], reverse=True)
            items = [
                SearchResult(id=it.id, score=float(s), metadata=it.metadata)
                for s, it in ranked
            ]

    return items[:k]


