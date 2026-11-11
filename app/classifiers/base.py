"""Interfaz común de los clasificadores de hojas."""

from dataclasses import dataclass
from typing import Protocol

from app.domain.ai_run import AiRun
from app.domain.classification import ClassificationResult
from app.domain.document import SheetProfile


@dataclass(frozen=True)
class ClassificationOutcome:
    result: ClassificationResult | None
    """None si la IA no entregó una respuesta válida (rechazo o corte)."""
    ai_run: AiRun | None = None
    """Registro de la llamada a la IA; None para el clasificador por reglas."""


class SheetClassifier(Protocol):
    name: str
    """Se guarda en documents.classification.classified_by ('ai' | 'rules')."""

    def classify(self, file_name: str, profiles: list[SheetProfile]) -> ClassificationOutcome:
        """Asigna un rol a cada hoja del libro a partir de sus fichas."""
        ...
