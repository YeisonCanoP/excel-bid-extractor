"""Valores de un ítem para Fact_cotizacion, con la regla del evaluador.

- precio: unitario corregido; sin unitario, total / cantidad.
- total_oferta: total corregido antes de IVA.
- iva, utilidad, iva sobre utilidad: ver taxes.py.
"""

from app.domain.cell_map import ProviderBlock
from app.domain.quotation import Derived, FactValues
from app.quotes.correction import Digits
from app.quotes.item import ItemValues
from app.quotes.normalize import excel_round, without_noise
from app.quotes.sheet import SheetCells
from app.quotes.taxes import tax_values


def fact_values(item: ItemValues, block: ProviderBlock, cells: SheetCells, currency: str | None) -> FactValues:
    columns = block.columns
    digits = Digits.of(cells.at(columns.unit_price_corrected, item.row),
                       cells.at(columns.total_price_corrected, item.row), currency)
    precio = _precio(item, digits)
    taxes = tax_values(item.components, block.totals, cells)
    return taxes.model_copy(update={"precio": precio, "total_oferta": _total_oferta(item, block, precio, digits)})


def _precio(item: ItemValues, digits: Digits) -> Derived | None:
    if item.corrected.unit_price is not None:
        return Derived.copy_of(item.corrected.unit_price, "unitario_corregido")
    if (unit := item.offered.unit_price) is not None:
        return Derived(value=excel_round(unit.value, digits.unit), rule=f"ROUND(unitario,{digits.unit})",
                       source=unit.source)
    total = item.corrected.total_price or item.offered.total_price
    if total is None or item.quantity is None or not item.quantity.value:
        return None
    return Derived(value=without_noise(total.value / item.quantity.value), rule="total/cantidad",
                   source=total.source + item.quantity.source)


def _total_oferta(item: ItemValues, block: ProviderBlock, precio: Derived | None, digits: Digits) -> Derived | None:
    """El total corregido ya es antes de IVA, salvo cuando la hoja suma el IVA por ítem."""
    if not block.columns.iva and item.corrected.total_price is not None:
        return Derived.copy_of(item.corrected.total_price, "total_corregido")
    if precio is None or item.quantity is None:
        return None
    return Derived(value=excel_round(item.quantity.value * precio.value, digits.total),
                   rule=f"ROUND(cantidad*precio,{digits.total})", source=item.quantity.source + precio.source)
