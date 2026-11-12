"""Mapa de celdas de una hoja principal (colección cell_maps).

Es el esquema que la IA debe cumplir (structured outputs). La IA solo devuelve
columnas, filas y direcciones; nunca números: el código copia los valores después.

Los campos que pueden no existir son texto con "" (no `None`): cada campo anulable se compila como una
alternativa más en la gramática de structured outputs, y con decenas de ellos la API rechaza el esquema.
`None` se acepta al validar y se convierte en "".
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


def _blank(value: object) -> object:
    return "" if value is None else value


Text = Annotated[str, BeforeValidator(_blank)]
"""Texto que puede no aplicar: "" en lugar de null."""


def _column(value: object) -> object:
    """'B9' o 'B9:B11' -> 'B': a veces la IA escribe una celda o un rango donde va una columna."""
    return value.split(":")[0].rstrip("0123456789") if isinstance(value, str) else _blank(value)


Column = Annotated[str, BeforeValidator(_column)]
"""Letra de columna de Excel, p. ej. 'H' o 'AN'."""
Address = Text
"""Dirección de una celda, p. ej. 'J23'."""


class TotalKind(StrEnum):
    SUBTOTAL = "subtotal"
    IVA = "iva"
    AIU = "aiu"
    ADMINISTRATION = "administration"
    UTILITY = "utility"
    IVA_ON_UTILITY = "iva_on_utility"
    TOTAL = "total"
    PARTIAL = "partial"
    """Total de una parte de los ítems (p. ej. servicios REGULADOS): no se compara con la suma de ítems."""
    OTHER = "other"


COMPONENT_KINDS = (TotalKind.IVA, TotalKind.AIU, TotalKind.ADMINISTRATION, TotalKind.UTILITY, TotalKind.IVA_ON_UTILITY)
"""Filas que se suman al subtotal para dar el total (impuestos y AIU)."""


class RowRange(BaseModel):
    first: int = Field(description="Primera fila de ítems")
    last: int = Field(description="Última fila de ítems (sin filas de total)")


class ItemColumns(BaseModel):
    """Columnas comunes a todos los proveedores de la tabla."""

    item_no: Column
    description: Column
    detail: list[Column] = Field(description="Columnas con referencia, datos técnicos o particularidades del ítem")
    unit: Column
    tariff_type: Column = Field(description="Tipo de tarifa o de servicio (p. ej. 'TIPO DE TARIFA')")
    quantity: list[Column] = Field(description="Columnas de cantidad; si hay varias (usuarios y meses) se multiplican")


class ProviderColumns(BaseModel):
    """Columnas del bloque de un proveedor; "" si el bloque no la tiene."""

    brand: Column
    unit_price: Column = Field(description="Valor unitario ofertado")
    total_price: Column = Field(description="Valor total ofertado del ítem")
    unit_price_corrected: Column = Field(description="Valor unitario redondeado/corregido por el evaluador")
    total_price_corrected: Column = Field(description="Valor total corregido por el evaluador")
    subtotal: Column = Field(description="Valor antes de impuestos por ítem (p. ej. 'valor mes de servicios')")
    aiu: Column = Field(description="Valor AIU del ítem")
    iva: Column = Field(description="Valor del IVA del ítem")
    factor: Column = Field(description="Factor multiplicador")
    check: Column = Field(description="Columna OK/ERROR del evaluador")


class TotalRef(BaseModel):
    """Una fila de total de un proveedor, con la dirección exacta de cada valor."""

    kind: TotalKind
    label_address: Address
    offered: Address = Field(description="Valor ofertado")
    corrected: Address = Field(description="Valor corregido por el evaluador")
    check: Address = Field(description="Celda OK/ERROR de esta fila")
    rate: Address = Field(description="Celda con la tasa (p. ej. 0.19 del IVA), si existe")


class ProviderBlock(BaseModel):
    name_address: Address = Field(description="Celda con el nombre del proveedor")
    columns: ProviderColumns
    totals: list[TotalRef] = Field(description="Filas de total de este proveedor dentro de la tabla")


class Table(BaseModel):
    table_id: str = Field(description="'t1', 't2'… en orden de aparición")
    group: Text = Field(description="Grupo de adjudicación de esta tabla ('1', '2'…) o \"\" si es el de la hoja")
    title_address: Address
    site_address: Address = Field(description="Celda con la sede o región de la tabla, si existe")
    header_rows: list[int]
    item_rows: RowRange
    item_columns: ItemColumns
    providers: list[ProviderBlock]
    confidence: float = Field(description="Confianza entre 0 y 1 en el mapa de esta tabla")


CurrencyCode = Annotated[Literal["COP", "USD", "EUR", ""], BeforeValidator(_blank)]
YesNo = Annotated[Literal["si", "no", ""], BeforeValidator(_blank)]


class CellMapResult(BaseModel):
    """Respuesta del mapeo de una hoja principal.

    La raíz es plana (moneda, IVA y presupuesto como campos sueltos) y los totales de la hoja reutilizan
    ProviderBlock: con objetos pequeños de más, el esquema supera el límite de la gramática de structured outputs.
    """

    status: Literal["complete", "partial", "unresolved"]
    currency: CurrencyCode = Field(description="Moneda ISO de los valores, o \"\" si no se sabe")
    currency_evidence: list[Address] = Field(description="Celdas de donde sale la moneda (encabezados, títulos)")
    iva_included: YesNo = Field(description="'si' si los precios incluyen IVA; 'no' si son antes de/sin IVA")
    budget_address: Address = Field(description="Celda con el valor del presupuesto oficial")
    budget_label_address: Address
    tables: list[Table]
    sheet_totals: list[ProviderBlock] = Field(
        description="Totales de toda la hoja (varias tablas): un bloque por proveedor, solo con totals")
    missing_fields: list[str] = Field(description="Campos críticos que no se encontraron")
    confidence: float
    warnings: list[str]
    requires_human_review: bool

    @property
    def prices_include_iva(self) -> bool | None:
        return {"si": True, "no": False}.get(self.iva_included)
