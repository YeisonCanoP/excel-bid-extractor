import pytest

from app.classifiers.validation import UnknownSheetError, validate_classification
from app.domain.classification import ClassificationResult, SheetClassification, SheetRole
from app.domain.document import DocumentStatus
from app.excel.profiler import profile_workbook

MIN_CONFIDENCE = 0.85


def _sheet(name: str, role: SheetRole, confidence: float = 0.95) -> SheetClassification:
    return SheetClassification(sheet_name=name, role=role, group=None, confidence=confidence, reason="test")


def _result(*sheets: SheetClassification, review: bool = False) -> ClassificationResult:
    return ClassificationResult(sheets=list(sheets), warnings=[], requires_human_review=review)


@pytest.fixture
def profiles(workbook):
    return profile_workbook(workbook)


def test_valid_classification_is_identified(profiles):
    result = _result(*[_sheet(p.sheet_name, SheetRole.DESCARTADA) for p in profiles[1:]],
                     _sheet("REV ARIT GRUPO II", SheetRole.PRINCIPAL))

    validation = validate_classification(result, profiles, MIN_CONFIDENCE)

    assert validation.status == DocumentStatus.SHEETS_IDENTIFIED
    assert validation.review_reasons == []


def test_unknown_sheet_is_an_error(profiles):
    result = _result(_sheet("Hoja inventada", SheetRole.PRINCIPAL))

    with pytest.raises(UnknownSheetError):
        validate_classification(result, profiles, MIN_CONFIDENCE)


def test_sheets_not_mentioned_are_discarded(profiles):
    result = _result(_sheet("REV ARIT GRUPO II", SheetRole.PRINCIPAL))

    validation = validate_classification(result, profiles, MIN_CONFIDENCE)

    assert len(validation.classification.sheets) == len(profiles)
    assert validation.classification.count_by_role()["descartada"] == len(profiles) - 1
    assert validation.status == DocumentStatus.SHEETS_IDENTIFIED


@pytest.mark.parametrize(("result", "expected_reason"), [
    (None, "no devolvió"),
    (_result(_sheet("Datos", SheetRole.DESCARTADA)), "ninguna hoja principal"),
    (_result(_sheet("REV ARIT GRUPO II", SheetRole.PRINCIPAL, confidence=0.6)), "Confianza baja"),
    (_result(_sheet("REV ARIT GRUPO II", SheetRole.PRINCIPAL), review=True), "pidió revisión"),
])
def test_cases_that_need_human_review(profiles, result, expected_reason):
    validation = validate_classification(result, profiles, MIN_CONFIDENCE)

    assert validation.status == DocumentStatus.HUMAN_REVIEW_REQUIRED
    assert any(expected_reason in reason for reason in validation.review_reasons)
