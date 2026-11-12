"""Un ítem en el bloque de un proveedor: sus valores, si la fila es un ítem y su estado (cotizado, en 0, sin oferta)."""

import math
from dataclasses import dataclass

from app.domain.cell_map import ProviderColumns
from app.domain.quotation import Components, Prices, QuoteStatus, SourcedNumber
from app.quotes.normalize import is_no_offer
from app.quotes.sheet import SheetCells


@dataclass(frozen=True)
class ItemValues:
    row: int
    quantity: SourcedNumber | None
    offered: Prices
    corrected: Prices
    components: Components

    @property
    def tax_rate(self) -> float:
        """IVA / base cuando el total del ítem incluye impuestos (10 % AIU x 19 % = 0,019); si no, 0."""
        subtotal, iva = self.components.subtotal, self.components.iva
        return iva.value / subtotal.value if subtotal and iva and subtotal.value else 0.0


def read_item(cells: SheetCells, columns: ProviderColumns, quantity_columns: list[str], row: int) -> ItemValues:
    return ItemValues(
        row=row,
        quantity=read_quantity(cells, quantity_columns, row),
        offered=Prices(unit_price=cells.number_at(columns.unit_price, row),
                       total_price=cells.number_at(columns.total_price, row)),
        corrected=Prices(unit_price=cells.number_at(columns.unit_price_corrected, row),
                         total_price=cells.number_at(columns.total_price_corrected, row)),
        components=Components(subtotal=cells.number_at(columns.subtotal, row),
                              aiu=cells.number_at(columns.aiu, row),
                              iva=cells.number_at(columns.iva, row)),
    )


def read_quantity(cells: SheetCells, columns: list[str], row: int) -> SourcedNumber | None:
    """Cantidad; con varias columnas (usuarios y meses) es su producto. Sin columna, 1. None si falta un factor."""
    if not columns:
        return SourcedNumber(value=1.0, source=[])
    factors = [number for column in columns if (number := cells.number_at(column, row)) is not None]
    if len(factors) < len(columns):
        return None
    return SourcedNumber(value=math.prod(f.value for f in factors), source=[s for f in factors for s in f.source])


def is_item(item: ItemValues) -> bool:
    """Ítem = fila con cantidad, distinta de 0 o con un valor unitario distinto de 0.

    Las demás son separadores o encabezados de capítulo ("1.3 CIMENTACIONES", sin cantidad o con 0): su valor
    es la suma de sus ítems, así que tomarlas como cotización contaría el capítulo dos veces.
    """
    if item.quantity is None:
        return False
    return item.quantity.value != 0 or _has_value(item.offered.unit_price)


def quote_status(cells: SheetCells, columns: ProviderColumns, item: ItemValues) -> QuoteStatus:
    """NO_OFFER ('NO COTIZA', o unitario vacío con total 0), ZERO_PRICE o QUOTED."""
    if any(is_no_offer(cells.at(column, item.row)) for column in (columns.unit_price, columns.total_price)):
        return QuoteStatus.NO_OFFER
    if columns.unit_price and item.offered.unit_price is None and not _has_value(item.offered.total_price):
        return QuoteStatus.NO_OFFER
    price = item.offered.unit_price or item.offered.total_price
    if price is None:
        return QuoteStatus.NO_OFFER
    return QuoteStatus.ZERO_PRICE if price.value == 0 else QuoteStatus.QUOTED


def _has_value(number: SourcedNumber | None) -> bool:
    return number is not None and number.value != 0
