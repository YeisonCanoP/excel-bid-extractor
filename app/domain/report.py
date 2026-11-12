"""Reporte final de un documento (colección reports y Excel en output/confidencial).

Resume en un solo documento lo que está repartido en quotations, offer_totals y cell_maps:
resumen, ofertas por grupo y proveedor, hallazgos y lo que requiere revisión humana.
"""

from datetime import datetime

from pydantic import BaseModel


class ReportItem(BaseModel):
    item_no: str | None
    product: str
    unit: str
    quantity: float | None
    price: float | None
    total: float | None
    iva_pct: float | None
    administration_pct: float | None
    utility_pct: float | None
    iva_on_utility_pct: float | None
    status: str
    source: str
    """Hoja y fila de origen, p. ej. 'Revisión aritmética!9'."""


class ReportProvider(BaseModel):
    name: str
    totals: dict[str, float]
    """Totales corregidos por tipo: subtotal, iva, administration, utility, total…"""
    items: list[ReportItem]


class ReportGroup(BaseModel):
    sheet: str
    group: str | None
    currency: str | None
    providers: list[ReportProvider]


class ReportFinding(BaseModel):
    rule: str
    sheet: str
    provider: str
    message: str
    cells: list[str]


class ReportReview(BaseModel):
    sheet: str
    code: str
    problems: list[str]


class ReportSummary(BaseModel):
    principal_sheets: int
    accepted_sheets: int
    review_sheets: int
    providers: int
    products: int
    quotations: int
    findings: dict[str, int]


class Report(BaseModel):
    document_id: str
    file_name: str
    status: str
    processed_at: datetime
    summary: ReportSummary
    groups: list[ReportGroup]
    findings: list[ReportFinding]
    review: list[ReportReview]
