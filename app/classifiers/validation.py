"""Validación de la clasificación antes de usarla.

La respuesta de la IA es un dato no confiable hasta pasar estas reglas:
- Toda hoja nombrada debe existir en el libro; si no, es un error (el documento queda en FAILED).
- Las hojas que el clasificador omitió se toman como descartadas: para ahorrar tokens,
  la IA solo responde las hojas relevantes.
- Pasa a revisión humana si no hay hoja principal, si una principal tiene confianza baja
  o si el clasificador lo pidió.
"""

from dataclasses import dataclass

from app.domain.classification import ClassificationResult, SheetClassification, SheetRole
from app.domain.document import DocumentStatus, SheetProfile


class UnknownSheetError(ValueError):
    """La clasificación menciona hojas que no existen en el libro."""


@dataclass(frozen=True)
class ValidationResult:
    classification: ClassificationResult
    review_reasons: list[str]

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)

    @property
    def status(self) -> DocumentStatus:
        return DocumentStatus.HUMAN_REVIEW_REQUIRED if self.needs_review else DocumentStatus.SHEETS_IDENTIFIED


def validate_classification(
    result: ClassificationResult | None,
    profiles: list[SheetProfile],
    min_confidence: float,
) -> ValidationResult:
    if result is None:
        empty = ClassificationResult(sheets=[], warnings=[], requires_human_review=True)
        return ValidationResult(empty, ["La IA no devolvió una respuesta válida (rechazo o corte)."])

    sheet_names = [profile.sheet_name for profile in profiles]
    _ensure_sheets_exist(result, set(sheet_names))
    completed = _add_missing_sheets(result, sheet_names)
    return ValidationResult(completed, _review_reasons(completed, min_confidence))


def _ensure_sheets_exist(result: ClassificationResult, sheet_names: set[str]) -> None:
    unknown = [sheet.sheet_name for sheet in result.sheets if sheet.sheet_name not in sheet_names]
    if unknown:
        raise UnknownSheetError(f"La clasificación nombra hojas que no existen: {unknown}")


def _add_missing_sheets(result: ClassificationResult, sheet_names: list[str]) -> ClassificationResult:
    classified = {sheet.sheet_name for sheet in result.sheets}
    missing = [name for name in sheet_names if name not in classified]
    if not missing:
        return result

    discarded = [
        SheetClassification(sheet_name=name, role=SheetRole.DESCARTADA, group=None, confidence=1.0,
                            reason="Sin señales de revisión aritmética (no seleccionada por el clasificador).")
        for name in missing
    ]
    return result.model_copy(update={"sheets": [*result.sheets, *discarded]})


def _review_reasons(result: ClassificationResult, min_confidence: float) -> list[str]:
    principal = result.with_role(SheetRole.PRINCIPAL)
    low_confidence = [sheet.sheet_name for sheet in principal if sheet.confidence < min_confidence]

    reasons = []
    if not principal:
        reasons.append("No se encontró ninguna hoja principal.")
    if low_confidence:
        reasons.append(f"Confianza baja en hojas principales: {low_confidence}")
    if result.requires_human_review:
        reasons.append("El clasificador pidió revisión humana.")
    return reasons
