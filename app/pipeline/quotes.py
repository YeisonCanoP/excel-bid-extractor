"""Etapa de cotizaciones: aplica los mapas aceptados, valida R1-R11 y guarda quotations y offer_totals.

No usa la IA: con los mapas guardados se puede repetir gratis (run --from quotes).
"""

from dataclasses import dataclass, field

from app.config import settings
from app.domain.classification import SheetRole
from app.domain.quotation import OfferTotal, Quotation
from app.domain.sheet_map import SheetMap
from app.domain.validation import RuleResult
from app.pipeline.stages import StageLogger
from app.quotes import SheetQuotes, Tolerances, process_sheet
from app.storage.repositories import SourceSheetRepository
from app.storage.results import OfferTotalRepository, QuotationRepository


@dataclass
class QuotesResult:
    quotations: list[Quotation] = field(default_factory=list)
    totals: list[OfferTotal] = field(default_factory=list)
    failures: dict[str, list[RuleResult]] = field(default_factory=dict)
    """Fallas de integridad por hoja (no debería haber: el mapa aceptado ya pasó la prueba aritmética)."""


class QuotesStage:
    def __init__(self, logger: StageLogger) -> None:
        self.logger = logger
        self.tolerances = Tolerances(settings.tol_finding, settings.tol_integrity_abs, settings.tol_integrity_rel)
        self.source_sheets = SourceSheetRepository()
        self.quotations = QuotationRepository()
        self.totals = OfferTotalRepository()

    def run(self, document_id: str, maps: list[SheetMap]) -> QuotesResult:
        with self.logger.stage(document_id, "quotes"):
            sheets = {s.sheet_name: s for s in self.source_sheets.for_document(document_id, SheetRole.PRINCIPAL)}
            result = QuotesResult()
            for sheet_map in (m for m in maps if m.accepted and m.cell_map and m.sheet_name in sheets):
                quotes, failures = process_sheet(sheets[sheet_map.sheet_name], sheet_map.cell_map,
                                                 document_id=document_id, group=sheets[sheet_map.sheet_name].group,
                                                 tolerances=self.tolerances)
                _add(result, sheet_map.sheet_name, quotes, failures)
            self.quotations.replace_for_document(document_id, result.quotations)
            self.totals.replace_for_document(document_id, result.totals)
        return result


def _add(result: QuotesResult, sheet_name: str, quotes: SheetQuotes, failures: list[RuleResult]) -> None:
    result.quotations += quotes.quotations
    result.totals += quotes.totals
    if failures:
        result.failures[sheet_name] = failures
