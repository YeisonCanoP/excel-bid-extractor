"""Etapa de hojas: ficha de cada hoja, clasificación (IA o reglas), validación y JSON limpio.

    profile   ficha de todas las hojas                      -> documents.sheet_profiles
    classify  rol de cada hoja (IA o reglas)                -> ai_runs
    validate  las hojas existen, confianza, hay principal   -> documents.classification
    extract   JSON limpio de las hojas principal y apoyo    -> source_sheets
"""

from pathlib import Path

from openpyxl.workbook.workbook import Workbook

from app.classifiers import SheetClassifier
from app.classifiers.validation import ValidationResult, validate_classification
from app.config import settings
from app.domain.classification import DocumentClassification, SheetClassification
from app.domain.document import SheetProfile
from app.domain.source_sheet import SourceSheet
from app.excel.extractor import extract_sheet
from app.excel.profiler import profile_workbook
from app.excel.reader import load_formulas, load_values
from app.pipeline.stages import StageLogger
from app.storage.repositories import AiRunRepository, DocumentRepository, SourceSheetRepository


class SheetsStage:
    def __init__(self, classifier: SheetClassifier, logger: StageLogger) -> None:
        self.classifier = classifier
        self.logger = logger
        self.documents = DocumentRepository()
        self.source_sheets = SourceSheetRepository()
        self.ai_runs = AiRunRepository()

    def run(self, document_id: str, path: Path) -> ValidationResult:
        """Clasifica las hojas del libro y guarda el JSON limpio de las principales y de apoyo."""
        workbook, profiles = self._profile(document_id, path)
        validation = self._classify(document_id, path.name, profiles)
        with self.logger.stage(document_id, "extract"):
            sheets = _extract(document_id, path, workbook, profiles, validation.classification.selected())
            self.source_sheets.replace_for_document(document_id, sheets)
        return validation

    def _profile(self, document_id: str, path: Path) -> tuple[Workbook, list[SheetProfile]]:
        with self.logger.stage(document_id, "profile"):
            workbook = load_values(path)
            profiles = profile_workbook(workbook)
            self.documents.save_profiles(document_id, profiles)
        return workbook, profiles

    def _classify(self, document_id: str, file_name: str, profiles: list[SheetProfile]) -> ValidationResult:
        """Clasifica las hojas y valida la respuesta; guarda la llamada a la IA y la clasificación."""
        with self.logger.stage(document_id, "classify"):
            outcome = self.classifier.classify(file_name, profiles)
            ai_run_id = self.ai_runs.add(document_id, outcome.ai_run) if outcome.ai_run else None
        with self.logger.stage(document_id, "validate"):
            validation = validate_classification(outcome.result, profiles, settings.confidence_auto)
            self.documents.save_classification(document_id, self._document_classification(validation, ai_run_id))
        return validation

    def _document_classification(self, validation: ValidationResult, ai_run_id: str | None) -> DocumentClassification:
        classification = validation.classification
        return DocumentClassification(
            classified_by=self.classifier.name, ai_run_id=ai_run_id, sheets=classification.sheets,
            summary=classification.count_by_role(), warnings=classification.warnings,
            requires_human_review=validation.needs_review, review_reasons=validation.review_reasons,
        )


def _extract(document_id: str, path: Path, values: Workbook, profiles: list[SheetProfile],
             selected: list[SheetClassification]) -> list[SourceSheet]:
    """JSON limpio de las hojas seleccionadas. El libro con fórmulas solo se abre si hay algo que guardar."""
    if not selected:
        return []
    formulas = load_formulas(path)
    index_by_name = {profile.sheet_name: profile.sheet_index for profile in profiles}
    return [extract_sheet(values[sheet.sheet_name], formulas[sheet.sheet_name], sheet, document_id=document_id,
                          sheet_index=index_by_name[sheet.sheet_name]) for sheet in selected]
