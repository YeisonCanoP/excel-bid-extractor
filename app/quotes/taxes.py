"""IVA, utilidad e IVA sobre utilidad en porcentaje, como los pide Fact_cotizacion.

- Con AIU por ítem: iva = 0, utilidad = AIU / base, iva sobre utilidad = IVA / AIU.
- Sin AIU: la tasa de la hoja (0,19 -> 19) o IVA / subtotal de los totales del proveedor; sin IVA, 0.
"""

from app.domain.cell_map import TotalKind, TotalRef
from app.domain.quotation import Components, Derived, FactValues
from app.quotes.normalize import excel_round
from app.quotes.sheet import SheetCells

PERCENT_DIGITS = 2
NO_IVA = "sin_iva"


def tax_values(components: Components, totals: list[TotalRef], cells: SheetCells) -> FactValues:
    """FactValues con solo los campos de impuestos; precio y total los completa fact.py."""
    aiu = _aiu_taxes(components)
    if aiu is not None:
        return aiu
    return FactValues(precio=None, total_oferta=None, iva=_iva_from_totals(totals, cells))


def _aiu_taxes(components: Components) -> FactValues | None:
    base, aiu, iva = components.subtotal, components.aiu, components.iva
    if base is None or aiu is None or iva is None or not base.value or not aiu.value:
        return None
    sources = base.source + aiu.source + iva.source
    return FactValues(
        precio=None,
        total_oferta=None,
        iva=Derived(value=0, rule="con_aiu", source=sources),
        utilidad=Derived(value=_percent(aiu.value / base.value), rule="aiu/base", source=sources),
        iva_sobre_utilidad=Derived(value=_percent(iva.value / aiu.value), rule="iva/aiu", source=sources),
    )


def _iva_from_totals(totals: list[TotalRef], cells: SheetCells) -> Derived:
    by_kind = {ref.kind: ref for ref in totals}
    iva_ref = by_kind.get(TotalKind.IVA)
    if iva_ref is None:
        return Derived(value=0, rule=NO_IVA, source=[])
    if (rate := cells.number(iva_ref.rate)) is not None:
        return Derived(value=_percent(rate.value), rule="tasa_hoja", source=rate.source)
    return _iva_ratio(iva_ref, by_kind.get(TotalKind.SUBTOTAL), cells)


def _iva_ratio(iva_ref: TotalRef, subtotal_ref: TotalRef | None, cells: SheetCells) -> Derived:
    """IVA / subtotal, con los valores corregidos (o los ofertados si no hay corregidos)."""
    if subtotal_ref is None:
        return Derived(value=0, rule=NO_IVA, source=[])
    iva = cells.number(iva_ref.corrected or iva_ref.offered)
    subtotal = cells.number(subtotal_ref.corrected or subtotal_ref.offered)
    if iva is None or subtotal is None or not subtotal.value:
        return Derived(value=0, rule=NO_IVA, source=[])
    return Derived(value=_percent(iva.value / subtotal.value), rule="iva/subtotal", source=iva.source + subtotal.source)


def _percent(ratio: float) -> float:
    return excel_round(ratio * 100, PERCENT_DIGITS)
