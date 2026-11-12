"""Extracción: aplica el mapa de celdas sobre el JSON limpio de la hoja.

Solo orquesta: los valores de cada ítem están en item.py, la identidad (proveedor, producto, unidad)
en refs.py y las validaciones en rules/.
"""

from dataclasses import dataclass, field

from app.domain.cell_map import CellMapResult, ProviderBlock, Table, TotalRef
from app.domain.quotation import OfferTotal, ProviderRef, Quotation, QuoteStatus, SourcedText
from app.domain.source_sheet import SourceSheet
from app.quotes.fact import fact_values
from app.quotes.item import is_item, quote_status, read_item
from app.quotes.normalize import is_no_offer
from app.quotes.refs import product_ref, provider_ref, unit_ref
from app.quotes.sheet import SheetCells
from app.quotes.sites import row_sites


@dataclass
class SheetQuotes:
    """Resultado de una hoja: cotizaciones, totales y advertencias."""

    quotations: list[Quotation] = field(default_factory=list)
    totals: list[OfferTotal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Sheet:
    """Lo que necesita cada paso de la extracción de una hoja."""

    document_id: str
    group: str | None
    cells: SheetCells
    cell_map: CellMapResult


@dataclass(frozen=True)
class _Line:
    """Una fila de la tabla en el bloque de un proveedor."""

    table: Table
    block: ProviderBlock
    provider: ProviderRef
    row: int
    site: SourcedText | None


def extract_sheet_quotes(
    sheet: SourceSheet, cell_map: CellMapResult, *, document_id: str, group: str | None
) -> SheetQuotes:
    """Cotizaciones (proveedor x ítem) y totales por proveedor de una hoja principal."""
    ctx = _Sheet(document_id, group, SheetCells(sheet), cell_map)
    result = SheetQuotes()
    for table in cell_map.tables:
        for block in table.providers:
            _extract_block(ctx, table, block, result)
    result.totals += _sheet_totals(ctx)
    return result


def _extract_block(ctx: _Sheet, table: Table, block: ProviderBlock, result: SheetQuotes) -> None:
    provider = provider_ref(ctx.cells, block.name_address)
    if provider is None or not _has_offer(ctx.cells, table, block):
        name = provider.name if provider else block.name_address
        result.warnings.append(f"{table.table_id}: bloque de '{name}' descartado (sin oferta)")
        return
    sites = row_sites(ctx.cells, table)
    lines = [_Line(table, block, provider, row, sites.get(row)) for row in _rows(table)]
    result.quotations += [quotation for line in lines if (quotation := _quotation(ctx, line))]
    result.totals += [_total(ctx, table.table_id, provider, ref) for ref in block.totals]


def _sheet_totals(ctx: _Sheet) -> list[OfferTotal]:
    """Totales de toda la hoja (suma de varias tablas)."""
    blocks = [(provider, block) for block in ctx.cell_map.sheet_totals
              if (provider := provider_ref(ctx.cells, block.name_address))]
    return [_total(ctx, None, provider, ref) for provider, block in blocks for ref in block.totals]


def _has_offer(cells: SheetCells, table: Table, block: ProviderBlock) -> bool:
    """Un bloque sin ningún precio distinto de 0 (ni 'NO COTIZA') es de un proveedor que no ofertó."""
    c = block.columns
    columns = [c.unit_price, c.total_price, c.unit_price_corrected, c.total_price_corrected]
    return any(_has_price(cells, column, row) for row in _rows(table) for column in columns)


def _has_price(cells: SheetCells, column: str | None, row: int) -> bool:
    number = cells.number_at(column, row)
    return (number is not None and number.value != 0) or is_no_offer(cells.at(column, row))


def _quotation(ctx: _Sheet, line: _Line) -> Quotation | None:
    """Cotización de un proveedor para un ítem; None si la fila no es un ítem."""
    cells, table, block = ctx.cells, line.table, line.block
    description = cells.text_at(table.item_columns.description, line.row)
    item = read_item(cells, block.columns, table.item_columns.quantity, line.row)
    if description is None or not is_item(item):
        return None
    status, currency = quote_status(cells, block.columns, item), ctx.cell_map.currency or None
    return Quotation(
        document_id=ctx.document_id, sheet_name=cells.name, table_id=table.table_id,
        group=table.group or ctx.group, currency=currency, iva_included=ctx.cell_map.prices_include_iva,
        provider=line.provider, product=product_ref(cells, table, block, description, line.row),
        unit=unit_ref(cells, table, line.row, line.site), status=status, quantity=item.quantity,
        offered=item.offered, corrected=item.corrected, components=item.components,
        excel_check=cells.text_at(block.columns.check, line.row),
        fact=None if status == QuoteStatus.NO_OFFER else fact_values(item, block, cells, currency),
    )


def _total(ctx: _Sheet, table_id: str | None, provider: ProviderRef, ref: TotalRef) -> OfferTotal:
    cells = ctx.cells
    return OfferTotal(
        document_id=ctx.document_id, sheet_name=cells.name, table_id=table_id, provider=provider, kind=ref.kind,
        offered=cells.number(ref.offered), corrected=cells.number(ref.corrected), rate=cells.number(ref.rate),
        excel_check=cells.text(ref.check),
    )


def _rows(table: Table) -> range:
    return range(table.item_rows.first, table.item_rows.last + 1)
