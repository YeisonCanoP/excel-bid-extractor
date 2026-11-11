"""Clasificación de hojas: el contrato que devuelve la IA (o las reglas) y lo que se guarda."""

from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, Field


class SheetRole(StrEnum):
    PRINCIPAL = "principal"
    """Revisión aritmética: de aquí saldrán las cotizaciones."""
    APOYO = "apoyo"
    """Precios o ítems que dan contexto (detalle de ítems, tarifas…)."""
    DESCARTADA = "descartada"
    """No aplica, o es una plantilla vacía."""


class SheetClassification(BaseModel):
    sheet_name: str = Field(description="Nombre exacto de la hoja, tal como viene en la lista")
    role: SheetRole
    group: str | None = Field(description="Grupo de adjudicación ('1', '2'…) o null si no aplica")
    confidence: float = Field(description="Confianza entre 0 y 1")
    reason: str = Field(description="Motivo breve de la decisión")


class ClassificationResult(BaseModel):
    """Respuesta del clasificador. Es el esquema que la IA debe cumplir (structured outputs)."""

    sheets: list[SheetClassification]
    warnings: list[str]
    requires_human_review: bool

    def with_role(self, role: SheetRole) -> list[SheetClassification]:
        return [sheet for sheet in self.sheets if sheet.role == role]

    def selected(self) -> list[SheetClassification]:
        """Hojas que se guardan: principales y de apoyo."""
        return [sheet for sheet in self.sheets if sheet.role != SheetRole.DESCARTADA]

    def count_by_role(self) -> dict[str, int]:
        counts = Counter(sheet.role for sheet in self.sheets)
        return {role.value: counts[role] for role in SheetRole}


class DocumentClassification(BaseModel):
    """Clasificación final de un libro, ya validada (campo documents.classification)."""

    classified_by: str
    ai_run_id: str | None
    sheets: list[SheetClassification]
    summary: dict[str, int]
    warnings: list[str]
    requires_human_review: bool
    review_reasons: list[str]
