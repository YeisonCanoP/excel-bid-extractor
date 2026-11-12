"""JSON limpio de una hoja (colección source_sheets)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.domain.classification import SheetRole

CellType = Literal["text", "number", "bool", "date", "error"]
CellValue = str | int | float | bool | None


class Cell(BaseModel):
    address: str
    """Dirección en Excel, p. ej. 'J10'."""
    value: CellValue
    """Valor calculado. Los números se guardan tal cual vienen; las fechas en ISO 8601."""
    type: CellType
    raw: str | None = None
    """Texto original, solo si la limpieza lo cambió."""
    formula: str | None = None
    number_format: str | None = None
    """Formato numérico de Excel, solo si no es 'General'."""


class Row(BaseModel):
    row: int
    cells: list[Cell]


class SourceSheet(BaseModel):
    """Una hoja principal o de apoyo, lista para las etapas de mapeo y extracción."""

    document_id: str
    sheet_name: str
    sheet_index: int
    role: SheetRole
    group: str | None = None
    state: str
    used_range: str
    cell_count: int
    merged_cells: list[str]
    hidden_columns: list[str] = []
    """Columnas ocultas (p. ej. bloques de proveedores que no ofertaron)."""
    rows: list[Row]
    created_at: datetime
