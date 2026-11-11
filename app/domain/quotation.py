"""Cotizaciones y totales extraídos con el mapa (colecciones quotations y offer_totals).

Todo valor guarda la celda de origen; los valores calculados guardan además la regla usada.
"""

from enum import StrEnum

from pydantic import BaseModel

from app.domain.cell_map import TotalKind
from app.domain.source_sheet import CellValue
from app.domain.validation import RuleResult


class SourcedNumber(BaseModel):
    """Número leído del Excel."""

    value: float
    source: list[str]
    raw: CellValue = None
    """Valor original, solo si la normalización lo cambió."""


class SourcedText(BaseModel):
    """Texto leído del Excel (ya limpio)."""

    value: str
    source: list[str]


class Derived(BaseModel):
    """Valor calculado por código, con la regla y las celdas que usó."""

    value: float
    rule: str
    source: list[str]

    @classmethod
    def copy_of(cls, number: SourcedNumber, rule: str) -> "Derived":
        return cls(value=number.value, rule=rule, source=number.source)


class QuoteStatus(StrEnum):
    QUOTED = "quoted"
    ZERO_PRICE = "zero_price"
    NO_OFFER = "no_offer"


class ProviderRef(BaseModel):
    key: str
    """Nombre normalizado: une al mismo proveedor entre hojas."""
    name: str
    source: str


class ProductRef(BaseModel):
    key: str
    """Descripción normalizada: un producto se comparte entre proveedores y grupos."""
    item_no: str | None
    description: str
    detail: str | None
    brand: str | None
    row: int


class Prices(BaseModel):
    unit_price: SourcedNumber | None
    total_price: SourcedNumber | None


class Components(BaseModel):
    """Partes del valor por ítem, cuando la hoja las trae (p. ej. servicios con AIU)."""

    subtotal: SourcedNumber | None
    aiu: SourcedNumber | None
    iva: SourcedNumber | None


class FactValues(BaseModel):
    """Valores para la tabla de cotizaciones del modelo destino (Fact_cotizacion)."""

    precio: Derived | None
    total_oferta: Derived | None
    iva: Derived
    utilidad: Derived | None = None
    iva_sobre_utilidad: Derived | None = None


class Quotation(BaseModel):
    document_id: str
    sheet_name: str
    table_id: str
    group: str | None
    currency: str | None
    iva_included: bool | None
    provider: ProviderRef
    product: ProductRef
    unit: SourcedText
    status: QuoteStatus
    quantity: SourcedNumber | None
    offered: Prices
    corrected: Prices
    components: Components
    fact: FactValues | None
    """None si la cotización es no_offer."""
    excel_check: SourcedText | None
    validations: list[RuleResult] = []


class OfferTotal(BaseModel):
    document_id: str
    sheet_name: str
    table_id: str | None
    """None para los totales de toda la hoja."""
    provider: ProviderRef
    kind: TotalKind
    offered: SourcedNumber | None
    corrected: SourcedNumber | None
    rate: SourcedNumber | None
    excel_check: SourcedText | None
    validations: list[RuleResult] = []
