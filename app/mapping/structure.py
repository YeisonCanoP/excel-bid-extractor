"""Validación de estructura del mapa: lo que se revisa antes de copiar un solo valor.

Cada problema se describe en una frase que entiende la IA, porque se le devuelve en el reintento.
"""

from collections import defaultdict
from collections.abc import Iterator

from openpyxl.utils.cell import column_index_from_string, coordinate_from_string, range_boundaries

from app.domain.cell_map import CellMapResult, ProviderBlock, Table
from app.quotes.sheet import SheetCells


def structure_problems(cell_map: CellMapResult, cells: SheetCells, used_range: str) -> list[str]:
    problems = [p for table in cell_map.tables for p in _table_problems(table, cells)]
    problems += [f"La celda {a} está fuera de la hoja ({used_range})." for a in _addresses(cell_map)
                 if not _inside(a, used_range)]
    if not cell_map.tables:
        problems.append("El mapa no tiene ninguna tabla de ítems.")
    if not cell_map.currency:
        problems.append("No se identificó la moneda: búscala en los encabezados y títulos.")
    return problems


def _table_problems(table: Table, cells: SheetCells) -> list[str]:
    rows, description = table.item_rows, table.item_columns.description
    problems = [] if rows.first <= rows.last else [f"{table.table_id}: item_rows empieza después de terminar."]
    if not any(cells.text_at(description, row) for row in range(rows.first, rows.last + 1)):
        problems.append(f"{table.table_id}: la columna {description} no tiene descripciones en las filas "
                        f"{rows.first}-{rows.last}.")
    problems += [p for block in table.providers for p in _block_problems(table.table_id, block, cells)]
    return problems + _overlaps(table)


def _block_problems(table_id: str, block: ProviderBlock, cells: SheetCells) -> list[str]:
    problems = []
    if cells.text(block.name_address) is None:
        problems.append(f"{table_id}: la celda {block.name_address} del nombre del proveedor está vacía.")
    if not block.columns.unit_price and not block.columns.total_price:
        problems.append(f"{table_id}: el bloque de {block.name_address} no tiene unit_price ni total_price.")
    return problems


def _overlaps(table: Table) -> list[str]:
    """Columnas usadas por más de un dueño (un proveedor o las columnas comunes)."""
    owners: dict[str, set[str]] = defaultdict(set)
    common = table.item_columns
    for column in [common.item_no, common.description, common.unit, common.tariff_type, *common.quantity]:
        if column:
            owners[column].add("columnas comunes")
    for block in table.providers:
        for column in (c for c in block.columns.model_dump().values() if c):
            owners[column].add(f"proveedor {block.name_address}")
    return [f"{table.table_id}: la columna {column} está asignada a {' y '.join(sorted(who))}."
            for column, who in owners.items() if len(who) > 1]


def _addresses(cell_map: CellMapResult) -> Iterator[str]:
    blocks = [*(b for t in cell_map.tables for b in t.providers), *cell_map.sheet_totals]
    refs = [ref for block in blocks for ref in block.totals]
    for ref in refs:
        yield from (a for a in (ref.offered, ref.corrected, ref.check, ref.rate, ref.label_address) if a)
    yield from (block.name_address for block in blocks)
    if cell_map.budget_address:
        yield cell_map.budget_address


def _inside(address: str, used_range: str) -> bool:
    try:
        column, row = coordinate_from_string(address)
        min_col, min_row, max_col, max_row = range_boundaries(used_range)
    except ValueError:
        return False
    column_ok = (min_col or 1) <= column_index_from_string(column) <= (max_col or 0)
    return column_ok and (min_row or 1) <= row <= (max_row or 0)
