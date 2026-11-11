"""Extracción: aplica el mapa de celdas sobre el JSON limpio de la hoja.

Solo copia y convierte valores; las validaciones viven en rules/.
"""

from dataclasses import dataclass, field

from app.domain.cell_map import CellMapResult, ProviderBlock, Table, TotalRef
from app.domain.quotation import OfferTotal, ProductRef, ProviderRef, Quotation, QuoteStatus, SourcedText
from app.domain.source_sheet import SourceSheet
from app.quotes.fact import fact_values
from app.quotes.item import ItemValues, read_item
from app.quotes.normalize import is_no_offer, is_placeholder_provider, product_key, provider_key, unit_label
from app.quotes.sheet import SheetCells


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
    provider = _provider(ctx.cells, block.name_address)
    if provider is None or not _has_offer(ctx.cells, table, block):
        name = provider.name if provider else block.name_address
        result.warnings.append(f"{table.table_id}: bloque de '{name}' descartado (sin oferta)")
        return
    rows = range(table.item_rows.first, table.item_rows.last + 1)
    result.quotations += [q for row in rows if (q := _quotation(ctx, table, block, provider, row))]
    result.totals += [_total(ctx, table.table_id, provider, ref) for ref in block.totals]


def _sheet_totals(ctx: _Sheet) -> list[OfferTotal]:
    """Totales de toda la hoja (suma de varias tablas)."""
    refs = ctx.cell_map.sheet_totals
    return [_total(ctx, None, provider, ref) for ref in refs if (provider := _provider(ctx.cells, ref.name_address))]


def _provider(cells: SheetCells, address: str) -> ProviderRef | None:
    """None si el bloque no es de un proveedor real (INVITADO, 0, vacío)."""
    name = cells.text(address)
    if name is None or is_placeholder_provider(name.value):
        return None
    return ProviderRef(key=provider_key(name.value), name=name.value, source=address)


def _has_offer(cells: SheetCells, table: Table, block: ProviderBlock) -> bool:
    """Un bloque sin ningún precio distinto de 0 (ni 'NO COTIZA') es de un proveedor que no ofertó."""
    c = block.columns
    columns = [c.unit_price, c.total_price, c.unit_price_corrected, c.total_price_corrected]
    rows = range(table.item_rows.first, table.item_rows.last + 1)
    return any(_has_price(cells, column, row) for row in rows for column in columns)


def _has_price(cells: SheetCells, column: str | None, row: int) -> bool:
    number = cells.number_at(column, row)
    return (number is not None and number.value != 0) or is_no_offer(cells.at(column, row))


def _quotation(ctx: _Sheet, table: Table, block: ProviderBlock, provider: ProviderRef, row: int) -> Quotation | None:
    """Cotización de un proveedor para un ítem; None si la fila no tiene descripción."""
    description = ctx.cells.text_at(table.item_columns.description, row)
    if description is None:
        return None
    item = read_item(ctx.cells, block.columns, table.item_columns.quantity, row)
    status = _status(ctx.cells, block, item)
    currency = ctx.cell_map.currency.code
    return Quotation(
        document_id=ctx.document_id, sheet_name=ctx.cells.name, table_id=table.table_id,
        group=table.group or ctx.group, currency=currency, iva_included=ctx.cell_map.iva_included.value,
        provider=provider, product=_product(ctx.cells, table, block, description, row),
        unit=_unit(ctx.cells, table, row), status=status, quantity=item.quantity, offered=item.offered,
        corrected=item.corrected, components=item.components, excel_check=ctx.cells.text_at(block.columns.check, row),
        fact=None if status == QuoteStatus.NO_OFFER else fact_values(item, block, ctx.cells, currency),
    )


def _status(cells: SheetCells, block: ProviderBlock, item: ItemValues) -> QuoteStatus:
    columns = block.columns
    if any(is_no_offer(cells.at(column, item.row)) for column in (columns.unit_price, columns.total_price)):
        return QuoteStatus.NO_OFFER
    price = item.offered.unit_price or item.offered.total_price
    if price is None:
        return QuoteStatus.NO_OFFER
    return QuoteStatus.ZERO_PRICE if price.value == 0 else QuoteStatus.QUOTED


def _product(cells: SheetCells, table: Table, block: ProviderBlock, description: SourcedText, row: int) -> ProductRef:
    columns = table.item_columns
    detail = " ".join(text.value for column in columns.detail if (text := cells.text_at(column, row))) or None
    item_no, brand = cells.text_at(columns.item_no, row), cells.text_at(block.columns.brand, row)
    return ProductRef(
        key=product_key(description.value, detail), item_no=item_no.value if item_no else None,
        description=description.value, detail=detail, brand=brand.value if brand else None, row=row,
    )


def _unit(cells: SheetCells, table: Table, row: int) -> SourcedText:
    """Unidad + tipo de tarifa + sede, en mayúsculas."""
    columns = table.item_columns
    parts = (cells.text_at(columns.unit, row), cells.text_at(columns.tariff_type, row), cells.text(table.site_address))
    label = unit_label(*(part.value if part else None for part in parts))
    return SourcedText(value=label, source=[s for part in parts if part for s in part.source])


def _total(ctx: _Sheet, table_id: str | None, provider: ProviderRef, ref: TotalRef) -> OfferTotal:
    cells = ctx.cells
    return OfferTotal(
        document_id=ctx.document_id, sheet_name=cells.name, table_id=table_id, provider=provider, kind=ref.kind,
        offered=cells.number(ref.offered), corrected=cells.number(ref.corrected), rate=cells.number(ref.rate),
        excel_check=cells.text(ref.check),
    )
