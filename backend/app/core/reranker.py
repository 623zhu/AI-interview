"""Cross-encoder reranker — BGE Reranker v2 m3 via FlagEmbedding.

Loaded lazily on first use. Set RERANK_ENABLED=false (env) to skip entirely;
if FlagEmbedding is not installed or the model fails to load, the rest of
the system keeps working with pure vector top-k.
"""
from __future__ import annotations

import logging
import threading
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_model = None
_load_failed = False


def _try_load():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    with _lock:
        if _model is not None or _load_failed:
            return _model
        try:
            from FlagEmbedding import FlagReranker
        except Exception as e:
            logger.warning("FlagEmbedding not installed (%s); rerank disabled", e)
            _load_failed = True
            return None
        try:
            _model = FlagReranker(settings.RERANK_MODEL, use_fp16=True)
            logger.info("Loaded reranker model: %s", settings.RERANK_MODEL)
        except Exception:
            logger.exception("Failed to load reranker %s; rerank disabled", settings.RERANK_MODEL)
            _load_failed = True
            _model = None
    return _model


@lru_cache(maxsize=1)
def is_available() -> bool:
    return _try_load() is not None


def rerank(query: str, docs: list[str]) -> list[float] | None:
    """Score each (query, doc) pair. Returns scores aligned with docs, or None on failure.

    Caller decides how to use the scores (sort/threshold). Higher = more relevant.
    """
    if not docs:
        return []
    model = _try_load()
    if model is None:
        return None
    try:
        pairs = [[query, d] for d in docs]
        raw = model.compute_score(pairs, normalize=True)
        if isinstance(raw, (int, float)):
            return [float(raw)]
        return [float(x) for x in raw]
    except Exception:
        logger.exception("Reranker scoring failed")
        return None