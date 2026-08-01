"""Small helpers for request-scoped duration measurements."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator


class TimingRecorder:
    """Accumulate named durations and metadata for one logical operation."""

    def __init__(self) -> None:
        self._started_at = time.perf_counter()
        self.timings: dict[str, int] = {}
        self.counters: dict[str, int] = {}
        self.metadata: dict[str, Any] = {}

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        """Accumulate repeated measurements under the same operation name."""
        started_at = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            self.timings[name] = self.timings.get(name, 0) + duration_ms

    def increment(self, name: str, amount: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + amount

    def set_metadata(self, **values: Any) -> None:
        for key, value in values.items():
            if value is not None:
                self.metadata[key] = value

    def total_ms(self) -> int:
        return int((time.perf_counter() - self._started_at) * 1000)

    def summary(self) -> dict[str, Any]:
        return {
            "total_ms": self.total_ms(),
            "timings": dict(self.timings),
            "counters": dict(self.counters),
            "metadata": dict(self.metadata),
        }

    def log(
        self,
        logger: logging.Logger,
        event: str,
        *,
        level: int = logging.INFO,
        **extra: Any,
    ) -> None:
        """Emit the complete timing snapshot as structured logging fields."""
        payload = self.summary()
        payload["event"] = event
        payload.update(extra)
        logger.log(level, event, extra=payload)
