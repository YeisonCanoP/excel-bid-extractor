"""Etapa de reporte: guarda el reporte en la colección reports y lo escribe en Excel (output/confidencial)."""

from pathlib import Path

from app.config import settings
from app.domain.report import Report, ReportReview
from app.domain.sheet_map import SheetMap
from app.pipeline.quotes import QuotesResult
from app.pipeline.stages import StageLogger
from app.report.builder import ReportInput, build_report
from app.report.excel import report_path, write_report
from app.storage.results import ReportRepository


class ReportStage:
    def __init__(self, logger: StageLogger) -> None:
        self.logger = logger
        self.reports = ReportRepository()

    def run(self, document: dict, status: str, maps: list[SheetMap], quotes: QuotesResult,
            review: list[ReportReview]) -> Path:
        """Arma, guarda y escribe el reporte; devuelve la ruta del Excel."""
        with self.logger.stage(document["_id"], "report"):
            report = build_report(ReportInput(
                document_id=document["_id"], file_name=document["file_name"], status=status,
                principal_sheets=len(maps), accepted_sheets=sum(m.accepted for m in maps),
                quotations=quotes.quotations, totals=quotes.totals, review=review,
            ))
            self.reports.save(report)
            return write_report(report, report_path(settings.output_dir, document["file_name"]))


def export_report(report: Report) -> Path:
    """Vuelve a escribir el Excel de un reporte ya guardado (comando export)."""
    return write_report(report, report_path(settings.output_dir, report.file_name))
