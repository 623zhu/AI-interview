"""RAG module — Chroma vector search for interview questions."""

from __future__ import annotations

import asyncio
import logging
import math
from contextlib import nullcontext as _nullcontext
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chroma import get_question_collection
from app.core.embedding import get_embeddings
from app.core.reranker import rerank as rerank_pairs
from app.core.timing import TimingRecorder
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
    result = await db.execute(select(Question).where(Question.is_active.is_(True)))
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
    job_category: str | None = None,
    rerank: bool = True,
    over_fetch: int = 30,
    timings: TimingRecorder | None = None,
) -> list[SearchResult]:
    """按语义召回题目，并可用交叉编码器重排后返回前 k 项。

    Args:
        query: Search text (job title + skills + requirements)
        category: Optional filter (e.g., "basic", "scenario", "open_ended")
        difficulty: Optional difficulty filter ("easy", "medium", "hard")
        k: Number of candidates to return after reranking
        rerank: If True, vector-recall ``over_fetch`` candidates and rerank to ``k``
        over_fetch: Recall depth used before reranking; ignored when rerank=False
    """
    if timings:
        timings.set_metadata(
            rag_k=k,
            rerank_enabled=rerank,
            rag_over_fetch=over_fetch,
            rag_category=category,
            rag_difficulty=difficulty,
            rag_job_category=job_category,
        )

    # Chroma、embedding 和 reranker 都是同步客户端；在线请求中放到工作线程，
    # 避免它们阻塞 FastAPI 的 asyncio 事件循环。
    with timings.span("rag_get_clients_ms") if timings else _nullcontext():
        collection, embeddings = await asyncio.gather(
            asyncio.to_thread(get_question_collection),
            asyncio.to_thread(get_embeddings),
        )

    try:
        with timings.span("rag_embedding_ms") if timings else _nullcontext():
            query_vector = await asyncio.to_thread(embeddings.embed_query, query)
    except Exception:
        logger.warning("Embedding failed for question search query, returning empty results")
        return []

    # 元数据过滤在向量查询时执行，先缩小到岗位、难度等合法范围。
    where_clause = None
    conditions = []
    if category:
        conditions.append({"category": category})
    if difficulty:
        conditions.append({"difficulty": difficulty})
    if job_category:
        conditions.append({"job_category": job_category})
    if len(conditions) == 1:
        where_clause = conditions[0]
    elif len(conditions) > 1:
        where_clause = {"$and": conditions}

    n_results = max(k, over_fetch) if rerank else k
    with timings.span("rag_chroma_query_ms") if timings else _nullcontext():
        results = await asyncio.to_thread(
            collection.query,
            query_embeddings=[query_vector],
            n_results=min(n_results, 50),
            where=where_clause,
        )

    items: list[SearchResult] = []
    docs: list[str] = []
    with timings.span("rag_parse_results_ms") if timings else _nullcontext():
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
        if timings:
            timings.set_metadata(rag_raw_result_count=0, rag_final_result_count=0)
        return []

    # 向量距离适合大范围召回，reranker 再精排 query 与题目文本的相关性。
    if rerank and len(items) > 1:
        with timings.span("rag_rerank_ms") if timings else _nullcontext():
            scores = await asyncio.to_thread(rerank_pairs, query, docs)
        if scores is not None and len(scores) == len(items):
            ranked = sorted(zip(scores, items), key=lambda x: x[0], reverse=True)
            items = [
                SearchResult(id=it.id, score=float(s), metadata=it.metadata)
                for s, it in ranked
            ]

    if timings:
        timings.set_metadata(
            rag_raw_result_count=len(docs),
            rag_final_result_count=min(len(items), k),
        )

    return items[:k]
