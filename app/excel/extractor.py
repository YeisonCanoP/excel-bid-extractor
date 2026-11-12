"""JSON limpio de una hoja.

- Solo se guardan las celdas con datos.
- El texto se limpia (espacios, tabs, saltos de línea); el original queda en `raw`.
- Se conservan la fórmula, el formato numérico y las celdas combinadas.
- Los números NO se modifican: redondear o corregir valores es responsabilidad de etapas posteriores.
"""

from datetime import UTC, date, datetime, time

from openpyxl.cell.cell import Cell as ExcelCell
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.classification import SheetClassification
from app.domain.source_sheet import Cell, Row, SourceSheet
from app.excel.reader import clean_text, iter_cells


def extract_sheet(
    values_sheet: Worksheet,
    formulas_sheet: Worksheet,
    classification: SheetClassification,
    *,
    document_id: str,
    sheet_index: int,
) -> SourceSheet:
    """Convierte una hoja en SourceSheet.

    `values_sheet` trae los valores calculados y `formulas_sheet` las fórmulas de la misma hoja.
    """
    rows = _rows(values_sheet, formulas_sheet)
    return SourceSheet(
        document_id=document_id,
        sheet_name=values_sheet.title,
        sheet_index=sheet_index,
        role=classification.role,
        group=classification.group,
        state=values_sheet.sheet_state,
        used_range=values_sheet.dimensions,
        cell_count=sum(len(row.cells) for row in rows),
        merged_cells=[str(cell_range) for cell_range in values_sheet.merged_cells.ranges],
        hidden_columns=_hidden_columns(values_sheet),
        rows=rows,
        created_at=datetime.now(UTC),
    )


def _rows(values_sheet: Worksheet, formulas_sheet: Worksheet) -> list[Row]:
    """Celdas con datos agrupadas por fila, cada una con su fórmula si la tiene."""
    rows: dict[int, list[Cell]] = {}
    for excel_cell in iter_cells(values_sheet):
        formula = _formula_at(formulas_sheet, excel_cell.row, excel_cell.column)
        rows.setdefault(excel_cell.row, []).append(_to_cell(excel_cell, formula))
    return [Row(row=row_number, cells=cells) for row_number, cells in rows.items()]


def _to_cell(excel_cell: ExcelCell, formula: str | None) -> Cell:
    value = excel_cell.value
    common = {"address": excel_cell.coordinate,"formula": formula}
    if isinstance(value, bool):
        return Cell(**common, value=value, type="bool")
    if isinstance(value, (int, float)):
        return Cell(**common, value=value, type="number", number_format=_number_format(excel_cell))
    if isinstance(value, (datetime, date, time)):
        return Cell(**common, value=value.isoformat(), type="date", number_format=_number_format(excel_cell))
    return _text_cell(excel_cell, common)


def _text_cell(excel_cell: ExcelCell, common: dict) -> Cell:
    """Texto limpio (el original queda en `raw`) o un error de Excel (#DIV/0!, #REF!…)."""
    text = str(excel_cell.value)
    if excel_cell.data_type == "e":
        return Cell(**common, value=text, type="error")
    cleaned = clean_text(text)
    return Cell(**common, value=cleaned, type="text", raw=text if cleaned != text else None)


def _hidden_columns(sheet: Worksheet) -> list[str]:
    """Letras de las columnas ocultas; openpyxl agrupa columnas consecutivas en un solo rango (min-max)."""
    hidden = {index for dimension in sheet.column_dimensions.values() if dimension.hidden
              for index in range(dimension.min, dimension.max + 1)}
    return [get_column_letter(index) for index in sorted(hidden)]


def _formula_at(formulas_sheet: Worksheet, row: int, column: int) -> str | None:
    cell = formulas_sheet._cells.get((row, column))
    if cell is None:
        return None
    value = getattr(cell.value, "text", cell.value)  # las fórmulas matriciales traen el texto en .text
    return value if isinstance(value, str) and value.startswith("=") else None


def _number_format(excel_cell: ExcelCell) -> str | None:
    return None if excel_cell.number_format == "General" else excel_cell.number_format
