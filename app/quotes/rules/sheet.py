"""Reglas sobre la hoja completa: R7 (duplicados), R8 (presupuesto) y R10 (suma de tablas)."""

from collections import defaultdict
from dataclasses import dataclass, field

from app.domain.cell_map import TotalKind
from app.domain.quotation import OfferTotal, Quotation, QuoteStatus, SourcedNumber
from app.domain.validation import RuleResult
from app.quotes.rules.common import FINDING, INTEGRITY, Tolerances, cells_of

KindMap = dict[TotalKind, OfferTotal]


@dataclass
class ProviderOffer:
    """Totales de un proveedor: los de toda la hoja y los de cada tabla."""

    sheet: KindMap = field(default_factory=dict)
    tables: dict[str, KindMap] = field(default_factory=lambda: defaultdict(dict))

    def add(self, total: OfferTotal) -> None:
        target = self.sheet if total.table_id is None else self.tables[total.table_id]
        target.setdefault(total.kind, total)

    def final_total(self) -> OfferTotal | None:
        """Total de la oferta: el de la hoja o, si hay una sola tabla, el de esa tabla."""
        if TotalKind.TOTAL in self.sheet or len(self.tables) != 1:
            return self.sheet.get(TotalKind.TOTAL)
        only = next(iter(self.tables.values()))
        return only.get(TotalKind.TOTAL) or only.get(TotalKind.SUBTOTAL)


def offers_by_provider(totals: list[OfferTotal]) -> list[ProviderOffer]:
    offers: dict[str, ProviderOffer] = defaultdict(ProviderOffer)
    for total in totals:
        offers[total.provider.key].add(total)
    return list(offers.values())


def tables_sum_rule(offer: ProviderOffer, tol: Tolerances) -> None:
    """R10 (integridad): bases de las tablas + IVA = total de la oferta (hojas con varias tablas)."""
    grand = offer.sheet.get(TotalKind.TOTAL)
    if grand is None or grand.corrected is None or not offer.tables:
        return
    parts = [t.corrected for t in _table_bases(offer) + _taxes(offer) if t and t.corrected]
    expected = sum(part.value for part in parts)
    passed = tol.close(expected, grand.corrected.value)
    grand.validations.append(RuleResult(
        rule="R10", kind=INTEGRITY, passed=passed, expected=expected, actual=grand.corrected.value,
        message="La suma de las tablas da el total" if passed else "La suma de las tablas no da el total de la oferta",
        cells=cells_of(grand.corrected, *parts)))


def budget_rule(offer: ProviderOffer, budget: SourcedNumber | None) -> None:
    """R8 (hallazgo): desviación del total de la oferta frente al presupuesto."""
    final = offer.final_total()
    if budget is None or not budget.value or final is None or final.corrected is None:
        return
    value = final.corrected.value
    final.validations.append(RuleResult(
        rule="R8", kind=FINDING, passed=value <= budget.value, expected=budget.value, actual=value,
        message=f"Desviación frente al presupuesto: {value / budget.value - 1:+.2%}",
        cells=cells_of(final.corrected, budget)))


def duplicates_rule(quotations: list[Quotation]) -> None:
    """R7 (integridad): una cotización por grupo + proveedor + ítem + producto + unidad.

    El número de ítem cuenta: la misma descripción puede repetirse en capítulos distintos (3.1 y 4.1).
    """
    first_row: dict[tuple, int] = {}
    for q in quotations:
        if q.status == QuoteStatus.NO_OFFER:
            continue
        key = (q.group, q.provider.key, q.product.item_no, q.product.key, q.unit.value)
        if key in first_row:
            q.validations.append(RuleResult(rule="R7", kind=INTEGRITY, passed=False,
                                            message=f"Cotización duplicada con la fila {first_row[key]}",
                                            cells=[f"fila {first_row[key]}", f"fila {q.product.row}"]))
        first_row.setdefault(key, q.product.row)


def _table_bases(offer: ProviderOffer) -> list[OfferTotal | None]:
    return [kinds.get(TotalKind.SUBTOTAL) or kinds.get(TotalKind.TOTAL) for kinds in offer.tables.values()]


def _taxes(offer: ProviderOffer) -> list[OfferTotal | None]:
    """El IVA de la hoja si existe; si no, el de cada tabla."""
    if TotalKind.IVA in offer.sheet:
        return [offer.sheet[TotalKind.IVA]]
    return [kinds.get(TotalKind.IVA) for kinds in offer.tables.values()]
