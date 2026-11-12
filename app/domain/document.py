"""Estado de un documento (un Excel) y la ficha de cada una de sus hojas."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class DocumentStatus(StrEnum):
    RECEIVED = "RECEIVED"
    SHEETS_IDENTIFIED = "SHEETS_IDENTIFIED"
    """Hojas clasificadas y JSON limpio guardado; sigue el mapeo."""
    CELLS_MAPPED = "CELLS_MAPPED"
    """Mapas de las hojas principales guardados; siguen las cotizaciones."""
    QUOTATIONS_VALIDATED = "QUOTATIONS_VALIDATED"
    """Cotizaciones extraídas y todas las reglas de integridad cuadran."""
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    FAILED = "FAILED"

    @property
    def is_final(self) -> bool:
        """Un documento en estado final no se reprocesa, salvo con --force o --from."""
        return self in (DocumentStatus.QUOTATIONS_VALIDATED, DocumentStatus.HUMAN_REVIEW_REQUIRED)


class OutcomeSummary(BaseModel):
    """Resultados del análisis de un documento (documents.summary)."""

    principal_sheets: int = 0
    accepted_sheets: int = 0
    quotations: int = 0
    findings: dict[str, int] = {}
    """Hallazgos de la oferta por regla (R1, R9, R11…)."""


class DocumentOutcome(BaseModel):
    """Cómo terminó el análisis de un documento (campos de documents)."""

    status: DocumentStatus
    review_code: str | None = None
    review_reasons: list[str] = []
    summary: OutcomeSummary = OutcomeSummary()


class StageLog(BaseModel):
    """Registro de una etapa del pipeline (documents.stage_log)."""

    stage: str
    status: Literal["ok", "error"]
    at: datetime
    duration_ms: int
    error: str | None = None


class SheetSignals(BaseModel):
    """Cuántas celdas de texto de la hoja mencionan cada palabra clave."""

    correccion_aritmetica: int = 0
    aritmetica: int = 0
    valor_unitario: int = 0
    cantidad: int = 0
    valor_total: int = 0
    iva: int = 0
    puntaje: int = 0
    oferta_economica: int = 0


class SheetProfile(BaseModel):
    """Resumen de una hoja. Es lo que recibe el clasificador para decidir su rol."""

    sheet_name: str
    sheet_index: int
    state: str
    """visible | hidden | veryHidden"""
    used_range: str
    non_empty_cells: int
    numeric_nonzero_cells: int
    """Si es 0 (o casi), la hoja probablemente es una plantilla sin usar."""
    header_text: list[str]
    """Primeras etiquetas de texto: título y encabezados."""
    signals: SheetSignals
    detected_group: str | None
    """Grupo encontrado en el nombre o en el título ('G1', 'GRUPO IV'…)."""
