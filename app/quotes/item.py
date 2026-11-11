"""Valores de un ítem en el bloque de un proveedor: cantidad, precios ofertados y corregidos, componentes."""

import math
from dataclasses import dataclass

from app.domain.cell_map import ProviderColumns
from app.domain.quotation import Components, Prices, SourcedNumber
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
