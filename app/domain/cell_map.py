"""Mapa de celdas de una hoja principal (colección cell_maps).

Es el esquema que la IA debe cumplir (structured outputs). La IA solo devuelve
columnas, filas y direcciones; nunca números: el código copia los valores después.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

Column = str
"""Letra de columna de Excel, p. ej. 'H' o 'AN'."""
Address = str
"""Dirección de una celda, p. ej. 'J23'."""


class TotalKind(StrEnum):
    SUBTOTAL = "subtotal"
    IVA = "iva"
    AIU = "aiu"
    TOTAL = "total"
    PARTIAL = "partial"
    """Total de una parte de los ítems (p. ej. servicios REGULADOS): no se compara con la suma de ítems."""
    OTHER = "other"


class Currency(BaseModel):
    code: Literal["COP", "USD", "EUR"] | None = Field(description="Moneda ISO de los valores, o null si no se sabe")
    evidence: list[Address] = Field(description="Celdas de donde sale la moneda (encabezados, títulos)")


class IvaIncluded(BaseModel):
    value: bool | None = Field(description="true si los precios incluyen IVA; false si son antes de/sin IVA")
    evidence: list[Address]


class Budget(BaseModel):
    address: Address = Field(description="Celda con el valor del presupuesto oficial")
    label_address: Address | None


class RowRange(BaseModel):
    first: int = Field(description="Primera fila de ítems")
    last: int = Field(description="Última fila de ítems (sin filas de total)")


class ItemColumns(BaseModel):
    """Columnas comunes a todos los proveedores de la tabla."""

    item_no: Column | None
    description: Column
    detail: list[Column] = Field(description="Columnas con referencia, datos técnicos o particularidades del ítem")
    unit: Column | None
    tariff_type: Column | None = Field(description="Tipo de tarifa o de servicio (p. ej. 'TIPO DE TARIFA')")
    quantity: list[Column] = Field(description="Columnas de cantidad; si hay varias (usuarios y meses) se multiplican")


class ProviderColumns(BaseModel):
    """Columnas del bloque de un proveedor. null si el bloque no la tiene."""

    brand: Column | None
    unit_price: Column | None = Field(description="Valor unitario ofertado")
    total_price: Column | None = Field(description="Valor total ofertado del ítem")
    unit_price_corrected: Column | None = Field(description="Valor unitario redondeado/corregido por el evaluador")
    total_price_corrected: Column | None = Field(description="Valor total corregido por el evaluador")
    subtotal: Column | None = Field(description="Valor antes de impuestos por ítem (p. ej. 'valor mes de servicios')")
    aiu: Column | None = Field(description="Valor AIU del ítem")
    iva: Column | None = Field(description="Valor del IVA del ítem")
    factor: Column | None = Field(description="Factor multiplicador")
    check: Column | None = Field(description="Columna OK/ERROR del evaluador")


class TotalRef(BaseModel):
    """Una fila de total de un proveedor, con la dirección exacta de cada valor."""

    kind: TotalKind
    label_address: Address | None
    offered: Address | None = Field(description="Valor ofertado")
    corrected: Address | None = Field(description="Valor corregido por el evaluador")
    check: Address | None = Field(description="Celda OK/ERROR de esta fila")
    rate: Address | None = Field(description="Celda con la tasa (p. ej. 0.19 del IVA), si existe")


class ProviderBlock(BaseModel):
    name_address: Address = Field(description="Celda con el nombre del proveedor")
    columns: ProviderColumns
    totals: list[TotalRef] = Field(description="Filas de total de este proveedor dentro de la tabla")


class SheetTotal(TotalRef):
    """Total de toda la hoja (suma de varias tablas) para un proveedor."""

    name_address: Address


class Table(BaseModel):
    table_id: str = Field(description="'t1', 't2'… en orden de aparición")
    group: str | None = Field(description="Grupo de adjudicación de esta tabla ('1', '2'…) o null si es el de la hoja")
    title_address: Address | None
    site_address: Address | None = Field(description="Celda con la sede o región de la tabla, si existe")
    header_rows: list[int]
    item_rows: RowRange
    item_columns: ItemColumns
    providers: list[ProviderBlock]
    confidence: float = Field(description="Confianza entre 0 y 1 en el mapa de esta tabla")


class CellMapResult(BaseModel):
    """Respuesta del mapeo de una hoja principal."""

    status: Literal["complete", "partial", "unresolved"]
    currency: Currency
    iva_included: IvaIncluded
    budget: Budget | None
    tables: list[Table]
    sheet_totals: list[SheetTotal] = Field(description="Totales de la hoja completa por proveedor (varias tablas)")
    missing_fields: list[str] = Field(description="Campos críticos que no se encontraron")
    confidence: float
    warnings: list[str]
    requires_human_review: bool
