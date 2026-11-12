"""Sede de cada fila de ítems.

Algunas hojas repiten la misma lista de ítems por sede, con un encabezado entre una y otra:
"PATIO DE 500KV", "PATIO DE 230KV". El encabezado es una fila sin descripción, con texto antes de la
columna de descripción. Como pide el modelo destino, la sede se agrega a la unidad ("UN PATIO DE 230KV"),
así el mismo ítem en dos sedes no es un duplicado.
"""

from openpyxl.utils import column_index_from_string, get_column_letter

from app.domain.cell_map import Table
from app.domain.quotation import SourcedText
from app.quotes.sheet import SheetCells


def row_sites(cells: SheetCells, table: Table) -> dict[int, SourcedText]:
    """Sede vigente en cada fila: la de la tabla y, desde cada encabezado de sede, la de ese encabezado."""
    sites: dict[int, SourcedText] = {}
    current = cells.text(table.site_address)
    for row in range(table.item_rows.first, table.item_rows.last + 1):
        current = _site_heading(cells, table, row) or current
        if current is not None:
            sites[row] = current
    return sites


def _site_heading(cells: SheetCells, table: Table, row: int) -> SourcedText | None:
    """'PATIO DE 230KV': fila sin descripción ni números, con texto a la izquierda de la descripción.

    No depende de la columna de ítem del mapa: si la IA no la asignó, el encabezado se reconoce igual.
    """
    if cells.text_at(table.item_columns.description, row):
        return None
    labels = [cells.at(column, row) for column in _columns_before(table.item_columns.description)]
    present = [cell for cell in labels if cell is not None]
    if not present or any(cell.type != "text" for cell in present):
        return None
    return cells.text(present[0].address)


def _columns_before(column: str) -> list[str]:
    return [get_column_letter(index) for index in range(1, column_index_from_string(column))]
