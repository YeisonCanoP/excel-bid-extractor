"""Estado final de un documento: qué requiere revisión humana, con qué código, y el resumen de resultados.

Las hojas que cuadraron conservan sus cotizaciones aunque otras queden en revisión.
"""

from collections import Counter

from app.domain.document import DocumentOutcome, DocumentStatus, OutcomeSummary
from app.domain.report import ReportReview
from app.domain.sheet_map import SheetMap
from app.domain.validation import ReviewCode, RuleKind
from app.pipeline.quotes import QuotesResult

CLASSIFICATION = "(clasificación)"
"""Hoja ficticia para los motivos de revisión de la clasificación de hojas."""


def review_items(document: dict, maps: list[SheetMap], quotes: QuotesResult) -> list[ReportReview]:
    """Todo lo que requiere revisión: la clasificación, los mapas que no cuadraron y las fallas de integridad."""
    reasons = (document.get("classification") or {}).get("review_reasons", [])
    code = ReviewCode.INTERPRETATION_ERROR
    items = [ReportReview(sheet=CLASSIFICATION, code=code, problems=reasons)] if reasons else []
    items += [ReportReview(sheet=m.sheet_name, code=m.review_code or ReviewCode.UNRESOLVED_DOCUMENT,
                           problems=m.problems) for m in maps if not m.accepted]
    items += [ReportReview(sheet=sheet, code=ReviewCode.UNRESOLVED_DOCUMENT, problems=[f.message for f in failures])
              for sheet, failures in quotes.failures.items()]
    return items


def document_outcome(maps: list[SheetMap], quotes: QuotesResult, review: list[ReportReview]) -> DocumentOutcome:
    status = DocumentStatus.HUMAN_REVIEW_REQUIRED if review else DocumentStatus.QUOTATIONS_VALIDATED
    return DocumentOutcome(
        status=status, review_code=review[0].code if review else None,
        review_reasons=[f"{item.sheet}: {problem}" for item in review for problem in item.problems or [item.code]],
        summary=_summary(maps, quotes),
    )


def _summary(maps: list[SheetMap], quotes: QuotesResult) -> OutcomeSummary:
    validations = [v for item in [*quotes.quotations, *quotes.totals] for v in item.validations]
    findings = Counter(v.rule for v in validations if v.kind == RuleKind.FINDING and not v.passed)
    return OutcomeSummary(principal_sheets=len(maps), accepted_sheets=sum(m.accepted for m in maps),
                          quotations=len(quotes.quotations), findings=dict(sorted(findings.items())))
