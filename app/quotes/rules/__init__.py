"""Validaciones económicas R1-R11.

- Hallazgo (finding): error o particularidad de la oferta. Se reporta, no bloquea.
- Integridad (integrity): la extracción no cuadra con el evaluador. El documento pasa a revisión humana.

Cada resultado se agrega a la cotización o al total que revisa.
"""

from app.domain.cell_map import CellMapResult
from app.domain.validation import RuleResult
from app.quotes.extractor import SheetQuotes
from app.quotes.rules.common import Tolerances
from app.quotes.rules.items import item_rules
from app.quotes.rules.sheet import budget_rule, duplicates_rule, offers_by_provider, tables_sum_rule
from app.quotes.rules.totals import table_rules, total_rules
from app.quotes.sheet import SheetCells

__all__ = ["Tolerances", "apply_rules"]


def apply_rules(result: SheetQuotes, cell_map: CellMapResult, cells: SheetCells, tol: Tolerances) -> list[RuleResult]:
    """Ejecuta todas las reglas sobre una hoja y devuelve las fallas de integridad (las que bloquean)."""
    for quotation in result.quotations:
        quotation.validations += item_rules(quotation, cell_map, cells, tol)
    for total in result.totals:
        total.validations += total_rules(total, tol)
    table_rules(result.quotations, result.totals, tol)
    _sheet_rules(result, cell_map, cells, tol)
    return _blocking(result)


def _sheet_rules(result: SheetQuotes, cell_map: CellMapResult, cells: SheetCells, tol: Tolerances) -> None:
    budget = cells.number(cell_map.budget_address)
    for offer in offers_by_provider(result.totals):
        tables_sum_rule(offer, tol)
        budget_rule(offer, budget)
    duplicates_rule(result.quotations)


def _blocking(result: SheetQuotes) -> list[RuleResult]:
    validations = [v for q in result.quotations for v in q.validations]
    validations += [v for t in result.totals for v in t.validations]
    return [v for v in validations if v.blocks]
