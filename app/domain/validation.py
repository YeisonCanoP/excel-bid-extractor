"""Resultado de las reglas económicas (R1-R11) y códigos de revisión humana."""

from enum import StrEnum

from pydantic import BaseModel


class RuleKind(StrEnum):
    FINDING = "finding"
    """Hallazgo de la oferta (error aritmético, precio en 0…): se reporta, no bloquea."""
    INTEGRITY = "integrity"
    """Nuestra extracción no cuadra con el evaluador: probablemente el mapa está mal. Bloquea."""


class ReviewCode(StrEnum):
    INTERPRETATION_ERROR = "INTERPRETATION_ERROR"
    UNRESOLVED_DOCUMENT = "UNRESOLVED_DOCUMENT"
    MAX_RETRIES_EXCEEDED = "MAX_RETRIES_EXCEEDED"


class RuleResult(BaseModel):
    rule: str
    """R1…R11"""
    kind: RuleKind
    passed: bool
    message: str
    expected: float | None = None
    actual: float | None = None
    cells: list[str] = []

    @property
    def blocks(self) -> bool:
        """Falla de integridad: el documento pasa a revisión humana."""
        return self.kind == RuleKind.INTEGRITY and not self.passed
