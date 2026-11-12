"""Mapa guardado de una hoja principal (colección cell_maps): el resultado del mapeo con sus intentos."""

from datetime import datetime

from pydantic import BaseModel

from app.domain.cell_map import CellMapResult
from app.domain.validation import ReviewCode


class SheetMap(BaseModel):
    document_id: str
    sheet_name: str
    accepted: bool
    """True si el mapa pasó la estructura y la prueba aritmética."""
    review_code: ReviewCode | None
    problems: list[str]
    """Problemas del último intento (vacío si se aceptó)."""
    history: list[list[str]]
    """Problemas de cada intento, en orden."""
    cell_map: CellMapResult | None
    ai_run_ids: list[str]
    created_at: datetime
