"""Arma el reporte final de un documento a partir de sus cotizaciones, totales y mapas.

Agrupa las cotizaciones por hoja y grupo, y dentro de cada grupo por proveedor; resume los hallazgos
de la oferta y lista lo que requiere revisión humana.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.cell_map import TotalKind
from app.domain.quotation import Derived, OfferTotal, Quotation, QuoteStatus
from app.domain.report import (
    Report,
    ReportFinding,
    ReportGroup,
    ReportItem,
    ReportProvider,
    ReportReview,
    ReportSummary,
)
from app.domain.validation import RuleKind

STATUS_LABELS = {QuoteStatus.QUOTED: "cotizado", QuoteStatus.ZERO_PRICE: "precio en 0",
                 QuoteStatus.NO_OFFER: "no cotizó"}
SKIPPED_TOTALS = {TotalKind.PARTIAL, TotalKind.OTHER}


@dataclass
class ReportInput:
    """Todo lo que necesita el reporte de un documento."""

    document_id: str
    file_name: str
    status: str
    principal_sheets: int
    accepted_sheets: int
    quotations: list[Quotation] = field(default_factory=list)
    totals: list[OfferTotal] = field(default_factory=list)
    review: list[ReportReview] = field(default_factory=list)


def build_report(data: ReportInput) -> Report:
    return Report(
        document_id=data.document_id, file_name=data.file_name, status=data.status,
        processed_at=datetime.now(UTC), summary=_summary(data), groups=_groups(data.quotations, data.totals),
        findings=_findings(data.quotations, data.totals), review=data.review,
    )


def _summary(data: ReportInput) -> ReportSummary:
    findings = Counter(finding.rule for finding in _findings(data.quotations, data.totals))
    return ReportSummary(
        principal_sheets=data.principal_sheets, accepted_sheets=data.accepted_sheets,
        review_sheets=len(data.review), providers=len({q.provider.key for q in data.quotations}),
        products=len({q.product.key for q in data.quotations}), quotations=len(data.quotations),
        findings=dict(sorted(findings.items())),
    )


def _groups(quotations: list[Quotation], totals: list[OfferTotal]) -> list[ReportGroup]:
    """Un grupo por hoja y grupo de adjudicación, en el orden en que aparecen."""
    by_group: dict[tuple[str, str | None], list[Quotation]] = defaultdict(list)
    for quotation in quotations:
        by_group[(quotation.sheet_name, quotation.group)].append(quotation)
    return [_group(sheet, group, items, totals) for (sheet, group), items in by_group.items()]


def _group(sheet: str, group: str | None, quotations: list[Quotation], totals: list[OfferTotal]) -> ReportGroup:
    by_provider: dict[str, list[Quotation]] = defaultdict(list)
    for quotation in quotations:
        by_provider[quotation.provider.key].append(quotation)
    tables = {q.table_id for q in quotations}
    sheet_totals = [t for t in totals if t.sheet_name == sheet]
    providers = [_provider(items, _provider_totals(sheet_totals, key, tables)) for key, items in by_provider.items()]
    return ReportGroup(sheet=sheet, group=group, currency=quotations[0].currency, providers=providers)


def _provider_totals(totals: list[OfferTotal], provider_key: str, tables: set[str]) -> dict[str, float]:
    """Totales corregidos del proveedor: los de toda la hoja si existen; si no, la suma de sus tablas."""
    mine = [t for t in totals if t.provider.key == provider_key and t.corrected and t.kind not in SKIPPED_TOTALS]
    sheet_level = [t for t in mine if t.table_id is None]
    chosen = sheet_level or [t for t in mine if t.table_id in tables]
    sums: dict[str, float] = defaultdict(float)
    for total in chosen:
        sums[total.kind.value] += total.corrected.value if total.corrected else 0.0
    return dict(sums)


def _provider(quotations: list[Quotation], totals: dict[str, float]) -> ReportProvider:
    return ReportProvider(name=quotations[0].provider.name, totals=totals, items=[_item(q) for q in quotations])


def _item(q: Quotation) -> ReportItem:
    fact = q.fact
    return ReportItem(
        item_no=q.product.item_no, product=q.product.description, unit=q.unit.value,
        quantity=q.quantity.value if q.quantity else None,
        price=_value(fact.precio if fact else None), total=_value(fact.total_oferta if fact else None),
        iva_pct=_value(fact.iva if fact else None), administration_pct=_value(fact.administracion if fact else None),
        utility_pct=_value(fact.utilidad if fact else None),
        iva_on_utility_pct=_value(fact.iva_sobre_utilidad if fact else None),
        status=STATUS_LABELS[q.status], source=f"{q.sheet_name}!{q.product.row}",
    )


def _findings(quotations: list[Quotation], totals: list[OfferTotal]) -> list[ReportFinding]:
    """Hallazgos de la oferta (reglas que fallaron y no bloquean), en el orden de la hoja."""
    sources = [(q.sheet_name, q.provider.name, q.validations) for q in quotations]
    sources += [(t.sheet_name, t.provider.name, t.validations) for t in totals]
    return [ReportFinding(rule=v.rule, sheet=sheet, provider=provider, message=v.message, cells=v.cells)
            for sheet, provider, validations in sources for v in validations
            if v.kind == RuleKind.FINDING and not v.passed]


def _value(derived: Derived | None) -> float | None:
    return derived.value if derived else None
