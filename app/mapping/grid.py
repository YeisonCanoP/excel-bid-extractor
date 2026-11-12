"""Cuadrícula compacta de una hoja: lo que lee la IA para ubicar las celdas.

Una línea por fila con solo las celdas con datos (`10|B:1|C:Switch…|G:8000`). Arriba van las celdas
combinadas, las columnas ocultas y el formato numérico más frecuente de cada columna.
Los números se envían para que la IA entienda la tabla, pero la IA nunca los devuelve.
"""

from collections import Counter, defaultdict

from openpyxl.utils import column_index_from_string, get_column_letter

from app.domain.source_sheet import Cell, Row, SourceSheet
from app.quotes.normalize import number_label

MAX_TEXT = 60
NONE = "(ninguna)"


def build_grid(sheet: SourceSheet) -> str:
    lines = [
        f"Hoja: {sheet.sheet_name} | rango: {sheet.used_range} | estado: {sheet.state}",
        f"Combinadas: {', '.join(sheet.merged_cells) or NONE}",
        f"Ocultas: {_ranges(sheet.hidden_columns) or NONE}",
        f"Formatos: {_formats(sheet.rows) or NONE}",
    ]
    return "\n".join(lines + [_row_line(row) for row in sheet.rows])


def _row_line(row: Row) -> str:
    return "|".join([str(row.row), *(f"{_column(cell)}:{_value(cell)}" for cell in row.cells)])


def _value(cell: Cell) -> str:
    if cell.type == "number" and isinstance(cell.value, int | float):
        return number_label(float(cell.value))
    text = str(cell.value)
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def _formats(rows: list[Row]) -> str:
    """Formato numérico más frecuente por columna, agrupando las columnas que comparten formato."""
    by_column: dict[str, Counter[str]] = defaultdict(Counter)
    for cell in (cell for row in rows for cell in row.cells if cell.type == "number" and cell.number_format):
        by_column[_column(cell)][cell.number_format or ""] += 1
    columns_by_format: dict[str, list[str]] = defaultdict(list)
    for column in sorted(by_column, key=column_index_from_string):
        columns_by_format[by_column[column].most_common(1)[0][0]].append(column)
    return " | ".join(f"{','.join(columns)}:{fmt}" for fmt, columns in columns_by_format.items())


def _ranges(columns: list[str]) -> str:
    """['AC','AD','AE','CH'] -> 'AC-AE, CH'."""
    indexes = sorted(column_index_from_string(column) for column in columns)
    groups: list[list[int]] = []
    for index in indexes:
        if groups and index == groups[-1][-1] + 1:
            groups[-1].append(index)
        else:
            groups.append([index])
    return ", ".join(_span(group) for group in groups)


def _span(group: list[int]) -> str:
    first, last = get_column_letter(group[0]), get_column_letter(group[-1])
    return first if first == last else f"{first}-{last}"


def _column(cell: Cell) -> str:
    return cell.address.rstrip("0123456789")
