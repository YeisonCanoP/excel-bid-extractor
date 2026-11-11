"""Pipeline: identificar las hojas de revisión aritmética de cada Excel y guardar su JSON limpio.

    profile   ficha de todas las hojas                      -> documents.sheet_profiles
    classify  rol de cada hoja (IA o reglas)                -> ai_runs
    validate  las hojas existen, confianza, hay principal   -> documents.classification
    extract   JSON limpio de las hojas principal y apoyo    -> source_sheets

El pipeline solo coordina: la lógica vive en excel/, classifiers/ y storage/.
Cada etapa queda registrada en documents.stage_log con su duración.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from openpyxl.workbook.workbook import Workbook

from app.classifiers import SheetClassifier
from app.classifiers.validation import ValidationResult, validate_classification
from app.config import settings
from app.domain.classification import DocumentClassification, SheetClassification, SheetRole
from app.domain.document import DocumentStatus, SheetProfile, StageLog
from app.domain.source_sheet import SourceSheet
from app.excel.extractor import extract_sheet
from app.excel.profiler import profile_workbook
from app.excel.reader import file_sha256, load_formulas, load_values
from app.storage.repositories import AiRunRepository, DocumentRepository, SourceSheetRepository


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
    seconds: float = 0.0


class Pipeline:
    """Procesa archivos Excel uno por uno con el clasificador indicado (IA o reglas)."""

    def __init__(self, classifier: SheetClassifier) -> None:
        self.classifier = classifier
        self.documents = DocumentRepository()
        self.source_sheets = SourceSheetRepository()
        self.ai_runs = AiRunRepository()

    def process_file(self, path: Path, force: bool = False) -> ProcessingReport:
        """Procesa un Excel. Si ya estaba procesado, lo omite (salvo con force=True)."""
        started = time.perf_counter()
        document_id = file_sha256(path)
        current_status = self.documents.get_status(document_id)
        if current_status and current_status.is_final and not force:
            return ProcessingReport(path.name, current_status, skipped=True)

        report = self._process(document_id, path)
        report.seconds = time.perf_counter() - started
        return report

    def _process(self, document_id: str, path: Path) -> ProcessingReport:
        """Registra el documento y corre las etapas. Si algo falla, queda en FAILED y se sigue con el siguiente."""
        self.documents.register(document_id, path)
        try:
            return self._run_stages(document_id, path)
        except Exception as error:
            self.documents.mark_failed(document_id, error)
            return ProcessingReport(path.name, DocumentStatus.FAILED, review_reasons=[str(error)])

    def _run_stages(self, document_id: str, path: Path) -> ProcessingReport:
        """Ejecuta las etapas en orden. Cualquier error corta el proceso del archivo."""
        workbook, profiles = self._profile(document_id, path)
        validation = self._classify(document_id, path.name, profiles)
        selected = validation.classification.selected()
        with self._stage(document_id, "extract"):
            sheets = self._extract(document_id, path, workbook, profiles, selected)
            self.source_sheets.replace_for_document(document_id, sheets)

        self.documents.set_status(document_id, validation.status)
        return _report(path.name, validation)

    def _profile(self, document_id: str, path: Path) -> tuple[Workbook, list[SheetProfile]]:
        with self._stage(document_id, "profile"):
            workbook = load_values(path)
            profiles = profile_workbook(workbook)
            self.documents.save_profiles(document_id, profiles)
        return workbook, profiles

    def _classify(self, document_id: str, file_name: str, profiles: list[SheetProfile]) -> ValidationResult:
        """Clasifica las hojas y valida la respuesta; guarda la llamada a la IA y la clasificación."""
        with self._stage(document_id, "classify"):
            outcome = self.classifier.classify(file_name, profiles)
            ai_run_id = self.ai_runs.add(document_id, outcome.ai_run) if outcome.ai_run else None

        with self._stage(document_id, "validate"):
            validation = validate_classification(outcome.result, profiles, settings.confidence_auto)
            self.documents.save_classification(document_id, self._document_classification(validation, ai_run_id))
        return validation

    def _document_classification(self, validation: ValidationResult, ai_run_id: str | None) -> DocumentClassification:
        """Arma lo que se guarda en documents.classification a partir de la clasificación validada."""
        classification = validation.classification
        return DocumentClassification(
            classified_by=self.classifier.name,
            ai_run_id=ai_run_id,
            sheets=classification.sheets,
            summary=classification.count_by_role(),
            warnings=classification.warnings,
            requires_human_review=validation.needs_review,
            review_reasons=validation.review_reasons,
        )

    @staticmethod
    def _extract(
        document_id: str,
        path: Path,
        values: Workbook,
        profiles: list[SheetProfile],
        selected: list[SheetClassification],
    ) -> list[SourceSheet]:
        """JSON limpio de las hojas seleccionadas. El libro con fórmulas solo se abre si hay algo que guardar."""
        if not selected:
            return []
        formulas = load_formulas(path)
        index_by_name = {profile.sheet_name: profile.sheet_index for profile in profiles}
        return [
            extract_sheet(
                values[sheet.sheet_name],
                formulas[sheet.sheet_name],
                sheet,
                document_id=document_id,
                sheet_index=index_by_name[sheet.sheet_name],
            )
            for sheet in selected
        ]

    @contextmanager
    def _stage(self, document_id: str, stage: str) -> Iterator[None]:
        """Mide la etapa y la registra en stage_log, haya terminado bien o con error."""
        started_at, started = datetime.now(UTC), time.perf_counter()
        error: Exception | None = None
        try:
            yield
        except Exception as exc:
            error = exc
            raise
        finally:
            self.documents.add_stage_log(document_id, _stage_log(stage, started_at, started, error))


def _stage_log(stage: str, started_at: datetime, started: float, error: Exception | None) -> StageLog:
    return StageLog(
        stage=stage,
        status="error" if error else "ok",
        at=started_at,
        duration_ms=int((time.perf_counter() - started) * 1000),
        error=str(error) if error else None,
    )


def _report(file_name: str, validation: ValidationResult) -> ProcessingReport:
    """Resumen para la consola: hojas principales y de apoyo, y motivos de revisión."""
    selected = validation.classification.selected()
    return ProcessingReport(
        file_name=file_name,
        status=validation.status,
        principal=[s.sheet_name for s in selected if s.role == SheetRole.PRINCIPAL],
        apoyo=[s.sheet_name for s in selected if s.role == SheetRole.APOYO],
        review_reasons=validation.review_reasons,
    )
