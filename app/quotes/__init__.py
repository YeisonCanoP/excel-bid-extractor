"""Cotizaciones y validaciones a partir del mapa de celdas.

    extractor.py   mapa + source_sheet -> quotations, offer_totals
    rules/         R1-R11 sobre lo extraído
"""

from app.domain.cell_map import CellMapResult
from app.domain.source_sheet import SourceSheet
from app.domain.validation import RuleResult
from app.quotes.extractor import SheetQuotes, extract_sheet_quotes
from app.quotes.rules import Tolerances, apply_rules
from app.quotes.sheet import SheetCells

__all__ = ["SheetQuotes", "Tolerances", "process_sheet"]


def process_sheet(
    sheet: SourceSheet, cell_map: CellMapResult, *, document_id: str, group: str | None, tolerances: Tolerances
) -> tuple[SheetQuotes, list[RuleResult]]:
    """Extrae y valida una hoja. Devuelve el resultado y las fallas de integridad (que bloquean)."""
    result = extract_sheet_quotes(sheet, cell_map, document_id=document_id, group=group)
    failures = apply_rules(result, cell_map, SheetCells(sheet), tolerances)
    return result, failures
