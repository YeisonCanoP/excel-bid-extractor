"""Pipeline: de un Excel a sus cotizaciones validadas y su reporte final.

    sheets   ficha, clasificación, validación y JSON limpio  -> documents, source_sheets   (sheets.py)
    map      mapa de celdas de cada hoja principal (IA)       -> cell_maps, ai_runs         (mapping.py)
    quotes   cotizaciones y reglas R1-R11 (código)            -> quotations, offer_totals   (quotes.py)
    report   reporte final                                    -> reports y Excel            (reporting.py)

Un documento continúa desde donde quedó: si ya tiene las hojas clasificadas, sigue con el mapeo.
Con `start` se puede rehacer desde una etapa: MAP (solo hojas pendientes, todas con force) o QUOTES (sin IA).
"""

import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from app.classifiers import SheetClassifier
from app.domain.classification import SheetRole
from app.domain.document import DocumentOutcome, DocumentStatus
from app.domain.sheet_map import SheetMap
from app.excel.reader import file_sha256
from app.mapping.mapper import AiMapper
from app.pipeline.mapping import MappingStage
from app.pipeline.outcome import document_outcome, review_items
from app.pipeline.quotes import QuotesStage
from app.pipeline.reporting import ReportStage
from app.pipeline.sheets import SheetsStage
from app.pipeline.stages import StageLogger
from app.storage.repositories import DocumentRepository
from app.storage.results import CellMapRepository

RESUMABLE = (DocumentStatus.SHEETS_IDENTIFIED, DocumentStatus.CELLS_MAPPED)


class StartFrom(StrEnum):
    SHEETS = "sheets"
    MAP = "map"
    QUOTES = "quotes"


@dataclass
class ProcessingReport:
    """Resultado de procesar un archivo, para mostrarlo en consola."""

    file_name: str
    status: DocumentStatus
    skipped: bool = False
    """True si el archivo ya estaba procesado y no se volvió a procesar."""
    principal: list[str] = field(default_factory=list)
    apoyo: list[str] = field(default_factory=list)
    review_reasons: list[str] = field(default_factory=list)
    """Motivos de revisión humana, o el error si el documento quedó en FAILED."""
    quotations: int = 0
    findings: dict[str, int] = field(default_factory=dict)
    report_path: Path | None = None
    seconds: float = 0.0


class Pipeline:
    def __init__(self, classifier: SheetClassifier, mapper: AiMapper | None = None) -> None:
        self.documents = DocumentRepository()
        self.cell_maps = CellMapRepository()
        logger = StageLogger(self.documents)
        self.classifier = classifier
        self.sheets, self.mapping = SheetsStage(classifier, logger), MappingStage(logger, mapper)
        self.quotes, self.reporting = QuotesStage(logger), ReportStage(logger)

    def process_file(self, path: Path, *, force: bool = False, start: StartFrom | None = None) -> ProcessingReport:
        """Procesa un Excel desde la etapa que corresponda; lo omite si ya terminó (salvo force o start)."""
        started, document_id = time.perf_counter(), file_sha256(path)
        first = self._first_stage(document_id, force=force, start=start)
        if first is None:
            return ProcessingReport(path.name, self._status(document_id), skipped=True)
        report = self._process(document_id, path, first, all_sheets=force)
        report.seconds = time.perf_counter() - started
        return report

    def _first_stage(self, document_id: str, *, force: bool, start: StartFrom | None) -> StartFrom | None:
        document = self.documents.get(document_id)
        if document is None or not document.get("classification"):
            return StartFrom.SHEETS
        if start is not None:
            return start
        status = DocumentStatus(document["status"])
        if force:
            return StartFrom.SHEETS
        if status.is_final:
            return None
        return StartFrom.MAP if status in RESUMABLE else StartFrom.SHEETS

    def _process(self, document_id: str, path: Path, first: StartFrom, *, all_sheets: bool) -> ProcessingReport:
        """Corre las etapas; si algo falla, el documento queda en FAILED y se sigue con el siguiente."""
        try:
            return self._run(document_id, path, first, all_sheets=all_sheets)
        except Exception as error:
            self.documents.mark_failed(document_id, error)
            return ProcessingReport(path.name, DocumentStatus.FAILED, review_reasons=[str(error)])

    def _run(self, document_id: str, path: Path, first: StartFrom, *, all_sheets: bool) -> ProcessingReport:
        if first == StartFrom.SHEETS:
            self.documents.register(document_id, path)
            self.cell_maps.delete_for_document(document_id)
            self.sheets.run(document_id, path)
        document = self.documents.get(document_id) or {}
        maps = self.cell_maps.for_document(document_id) if first == StartFrom.QUOTES else []
        if not maps:
            maps = self.mapping.run(document, all_sheets=all_sheets)
            self.documents.set_status(document_id, DocumentStatus.CELLS_MAPPED)
        return self._finish(document, maps)

    def _finish(self, document: dict, maps: list[SheetMap]) -> ProcessingReport:
        """Cotizaciones, estado final y reporte."""
        quotes = self.quotes.run(document["_id"], maps)
        review = review_items(document, maps, quotes)
        outcome = document_outcome(maps, quotes, review)
        path = self.reporting.run(document, outcome.status, maps, quotes, review)
        self.documents.save_outcome(document["_id"], outcome)
        return _console_report(document, outcome, path)

    def _status(self, document_id: str) -> DocumentStatus:
        return self.documents.get_status(document_id) or DocumentStatus.RECEIVED


def _console_report(document: dict, outcome: DocumentOutcome, path: Path) -> ProcessingReport:
    sheets = (document.get("classification") or {}).get("sheets", [])
    names = {role: [s["sheet_name"] for s in sheets if s["role"] == role] for role in (SheetRole.PRINCIPAL,
                                                                                         SheetRole.APOYO)}
    return ProcessingReport(
        file_name=document["file_name"], status=outcome.status, principal=names[SheetRole.PRINCIPAL],
        apoyo=names[SheetRole.APOYO], review_reasons=outcome.review_reasons,
        quotations=outcome.summary.quotations, findings=outcome.summary.findings, report_path=path,
    )


__all__ = ["Pipeline", "ProcessingReport", "StartFrom"]
