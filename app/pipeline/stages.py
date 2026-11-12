"""Registro de cada etapa en documents.stage_log: duración y si terminó bien o con error."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from app.domain.document import StageLog
from app.storage.repositories import DocumentRepository


class StageLogger:
    def __init__(self, documents: DocumentRepository) -> None:
        self.documents = documents

    @contextmanager
    def stage(self, document_id: str, name: str) -> Iterator[None]:
        """Mide la etapa y la registra, haya terminado bien o con error."""
        started_at, started = datetime.now(UTC), time.perf_counter()
        error: Exception | None = None
        try:
            yield
        except Exception as exc:
            error = exc
            raise
        finally:
            self.documents.add_stage_log(document_id, _stage_log(name, started_at, started, error))


def _stage_log(stage: str, started_at: datetime, started: float, error: Exception | None) -> StageLog:
    return StageLog(
        stage=stage,
        status="error" if error else "ok",
        at=started_at,
        duration_ms=int((time.perf_counter() - started) * 1000),
        error=str(error) if error else None,
    )
