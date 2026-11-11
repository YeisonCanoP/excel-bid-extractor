"""Reglas sobre los totales de cada proveedor en una tabla: R3, R4, R5 y R11."""

from collections import defaultdict

from app.domain.cell_map import TotalKind
from app.domain.quotation import OfferTotal, Quotation, SourcedNumber
from app.domain.validation import RuleResult
from app.quotes.rules.common import FINDING, INTEGRITY, Tolerances, cells_of, check_agreement

BlockKey = tuple[str, str]
"""(tabla, celda del nombre del proveedor): identifica el bloque de un proveedor en una tabla."""


def total_rules(total: OfferTotal, tol: Tolerances) -> list[RuleResult]:
    agreement = check_agreement(total.offered, total.corrected, total.excel_check)
    results = [agreement, offered_vs_corrected_rule(total, tol)]
    return [result for result in results if result is not None]


def offered_vs_corrected_rule(total: OfferTotal, tol: Tolerances) -> RuleResult | None:
    """R11 (hallazgo): el total ofertado difiere del corregido (p. ej. un IVA mal calculado)."""
    offered, corrected = total.offered, total.corrected
    if offered is None or corrected is None or abs(offered.value - corrected.value) <= tol.finding:
        return None
    return RuleResult(rule="R11", kind=FINDING, passed=False, expected=corrected.value, actual=offered.value,
                      message=f"{total.kind}: ofertado {offered.value:,.2f} ≠ corregido {corrected.value:,.2f}",
                      cells=cells_of(offered, corrected))


def table_rules(quotations: list[Quotation], totals: list[OfferTotal], tol: Tolerances) -> None:
    """R3 y R4 por bloque de proveedor; el resultado se agrega al total revisado."""
    items = _corrected_items_by_block(quotations)
    for key, by_kind in _totals_by_block(totals).items():
        items_sum_rule(items.get(key, []), by_kind, tol)
        subtotal_plus_iva_rule(by_kind, tol)


def items_sum_rule(items: list[SourcedNumber], by_kind: dict[TotalKind, OfferTotal], tol: Tolerances) -> None:
    """R3 (integridad): la suma de los totales corregidos de los ítems da el subtotal (o el total sin IVA)."""
    target = by_kind.get(TotalKind.SUBTOTAL) or (None if TotalKind.IVA in by_kind else by_kind.get(TotalKind.TOTAL))
    if target is None or target.corrected is None or not items:
        return
    expected = sum(item.value for item in items)
    passed = tol.close(expected, target.corrected.value)
    target.validations.append(RuleResult(
        rule="R3", kind=INTEGRITY, passed=passed, expected=expected, actual=target.corrected.value,
        message="La suma de los ítems da el total" if passed else "La suma de los ítems no da el total: revisar filas",
        cells=cells_of(target.corrected, *items)))


def subtotal_plus_iva_rule(by_kind: dict[TotalKind, OfferTotal], tol: Tolerances) -> None:
    """R4 (integridad): subtotal + IVA = total, con los valores corregidos."""
    subtotal, iva, total = (by_kind.get(kind) for kind in (TotalKind.SUBTOTAL, TotalKind.IVA, TotalKind.TOTAL))
    if not (subtotal and iva and total and subtotal.corrected and iva.corrected and total.corrected):
        return
    expected = subtotal.corrected.value + iva.corrected.value
    passed = tol.close(expected, total.corrected.value)
    total.validations.append(RuleResult(
        rule="R4", kind=INTEGRITY, passed=passed, expected=expected, actual=total.corrected.value,
        message="subtotal + IVA = total" if passed else "subtotal + IVA no da el total",
        cells=cells_of(subtotal.corrected, iva.corrected, total.corrected)))


def _corrected_items_by_block(quotations: list[Quotation]) -> dict[BlockKey, list[SourcedNumber]]:
    items: dict[BlockKey, list[SourcedNumber]] = defaultdict(list)
    for q in quotations:
        if q.corrected.total_price is not None:
            items[(q.table_id, q.provider.source)].append(q.corrected.total_price)
    return items


def _totals_by_block(totals: list[OfferTotal]) -> dict[BlockKey, dict[TotalKind, OfferTotal]]:
    blocks: dict[BlockKey, dict[TotalKind, OfferTotal]] = defaultdict(dict)
    for total in totals:
        if total.table_id is not None:
            blocks[(total.table_id, total.provider.source)].setdefault(total.kind, total)
    return blocks
