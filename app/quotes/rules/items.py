"""Reglas por cotización: R1, R2, R5, R6 y R9."""

from app.domain.cell_map import CellMapResult
from app.domain.quotation import Prices, Quotation, QuoteStatus, SourcedNumber
from app.domain.validation import RuleResult
from app.quotes.correction import Correction, Digits, correct_item
from app.quotes.item import ItemValues
from app.quotes.rules.common import FINDING, INTEGRITY, Tolerances, cells_of, check_agreement
from app.quotes.sheet import SheetCells


def item_rules(q: Quotation, cell_map: CellMapResult, cells: SheetCells, tol: Tolerances) -> list[RuleResult]:
    if q.status == QuoteStatus.NO_OFFER:
        return []
    results = [
        offered_total_rule(q, tol),
        evaluator_correction_rule(q, cells, cell_map.currency.code, tol),
        check_agreement(q.offered.total_price, q.corrected.total_price, q.excel_check),
        critical_fields_rule(q, cell_map),
        zero_price_rule(q),
    ]
    return [result for result in results if result is not None]


def offered_total_rule(q: Quotation, tol: Tolerances) -> RuleResult | None:
    """R1 (hallazgo): cantidad x unitario ofertado = total ofertado antes de impuestos."""
    unit, quantity = q.offered.unit_price, q.quantity
    base = q.components.subtotal or (None if q.components.iva else q.offered.total_price)
    if unit is None or quantity is None or base is None:
        return None
    expected = quantity.value * unit.value
    passed = abs(expected - base.value) <= tol.finding
    message = "Total ofertado correcto" if passed else "El total ofertado no es cantidad x unitario"
    return RuleResult(rule="R1", kind=FINDING, passed=passed, expected=expected, actual=base.value, message=message,
                      cells=cells_of(quantity, unit, base))


def evaluator_correction_rule(q: Quotation, cells: SheetCells, currency: str | None,
                              tol: Tolerances) -> RuleResult | None:
    """R2 (integridad): nuestro recálculo con la regla del evaluador da sus valores corregidos."""
    corrected = q.corrected.total_price
    if corrected is None or q.quantity is None:
        return None
    ours = _recalculate(q, cells, currency)
    passed = _matches(ours, q.corrected, tol)
    message = ("El recálculo coincide con el evaluador" if passed
               else "El recálculo no coincide con el evaluador: revisar las columnas del mapa")
    return RuleResult(rule="R2", kind=INTEGRITY, passed=passed, expected=ours.total_price, actual=corrected.value,
                      message=message, cells=cells_of(q.quantity, q.offered.unit_price, q.corrected.unit_price,
                                                      corrected))


def critical_fields_rule(q: Quotation, cell_map: CellMapResult) -> RuleResult:
    """R6 (integridad): campos críticos de una cotización."""
    present = {
        "proveedor": bool(q.provider.name), "producto": bool(q.product.description),
        "cantidad": q.quantity is not None, "precio": q.fact is not None and q.fact.precio is not None,
        "moneda": cell_map.currency.code is not None,
    }
    missing = [name for name, ok in present.items() if not ok]
    return RuleResult(rule="R6", kind=INTEGRITY, passed=not missing, cells=[f"fila {q.product.row}"],
                      message=f"Faltan campos críticos: {missing}" if missing else "Campos críticos completos")


def zero_price_rule(q: Quotation) -> RuleResult | None:
    """R9 (hallazgo): ítem cotizado en 0."""
    if q.status != QuoteStatus.ZERO_PRICE:
        return None
    return RuleResult(rule="R9", kind=FINDING, passed=False, message="Ítem cotizado en 0",
                      cells=cells_of(q.offered.unit_price, q.offered.total_price))


def _recalculate(q: Quotation, cells: SheetCells, currency: str | None) -> Correction:
    item = ItemValues(row=q.product.row, quantity=q.quantity, offered=q.offered, corrected=q.corrected,
                      components=q.components)
    digits = Digits.of(cells.get(_address(q.corrected.unit_price)), cells.get(_address(q.corrected.total_price)),
                       currency)
    return correct_item(item, digits)


def _matches(ours: Correction, theirs: Prices, tol: Tolerances) -> bool:
    pairs = [(ours.total_price, theirs.total_price), (ours.unit_price, theirs.unit_price)]
    return all(_close(mine, other, tol) for mine, other in pairs if other is not None)


def _close(mine: float | None, theirs: SourcedNumber, tol: Tolerances) -> bool:
    return mine is not None and tol.close(theirs.value, mine)


def _address(value: SourcedNumber | None) -> str | None:
    return value.source[0] if value is not None else None
