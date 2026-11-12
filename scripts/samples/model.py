"""Descripción de una tabla de revisión aritmética de muestra: ítems, proveedores y disposición."""

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    """Columnas de un bloque de proveedor (los mismos nombres del mapa de celdas)."""

    BRAND = "brand"
    UNIT_PRICE = "unit_price"
    TOTAL_PRICE = "total_price"
    SUBTOTAL = "subtotal"
    AIU = "aiu"
    IVA = "iva"
    UNIT_PRICE_CORRECTED = "unit_price_corrected"
    TOTAL_PRICE_CORRECTED = "total_price_corrected"
    CHECK = "check"


class ItemField(StrEnum):
    """Columnas de la descripción del ítem."""

    ITEM_NO = "item_no"
    DESCRIPTION = "description"
    UNIT = "unit"
    TARIFF_TYPE = "tariff_type"


AIU_RATE = 0.10
IVA_RATE = 0.19

ROLE_LABELS = {
    Role.BRAND: "MARCA",
    Role.UNIT_PRICE: "VALOR UNITARIO",
    Role.TOTAL_PRICE: "VALOR TOTAL",
    Role.SUBTOTAL: "VALOR MES DE SERVICIOS",
    Role.AIU: "VALOR AIU",
    Role.IVA: "VALOR IVA",
    Role.UNIT_PRICE_CORRECTED: "VALOR UNITARIO REDONDEADO",
    Role.TOTAL_PRICE_CORRECTED: "CORRECCIÓN ARITMÉTICA",
    Role.CHECK: "VERIFICACIÓN",
}
TEXT_ROLES = {Role.BRAND, Role.CHECK}
TOTAL_LABELS = {Role.SUBTOTAL: "SUBTOTAL", Role.IVA: "IVA", "total": "VALOR TOTAL"}


@dataclass(frozen=True)
class Item:
    description: str
    quantities: tuple[float, ...]
    """Una cantidad por columna de cantidad (p. ej. usuarios y meses)."""
    unit: str | None = None
    tariff_type: str | None = None


@dataclass(frozen=True)
class Offer:
    unit: float | None = None
    total: float | None = None
    """Total escrito por el proveedor. None: cantidad x unitario (sin error)."""
    no_offer: bool = False


NO_OFFER = Offer(no_offer=True)


@dataclass(frozen=True)
class Provider:
    name: str
    roles: tuple[str, ...]
    """Columnas del bloque, en orden."""
    offers: tuple[Offer, ...] = ()
    """Una oferta por ítem. Vacío: el proveedor no ofertó (bloque vacío)."""
    brand: str | None = None
    iva_offered: float | None = None
    """IVA escrito por el proveedor; sirve para sembrar un error."""
    hidden: bool = False


@dataclass(frozen=True)
class Layout:
    table_id: str
    first_item_row: int
    item_columns: dict[str, str]
    """Rol -> columna: item_no, description, unit, tariff_type."""
    quantity_columns: tuple[str, ...]
    quantity_labels: tuple[str, ...]
    first_block: str
    currency: str
    totals: tuple[str, ...] = (Role.SUBTOTAL, Role.IVA, "total")
    partials: tuple[tuple[str, int, int], ...] = ()
    """(etiqueta, primer ítem, último ítem): totales de una parte de los ítems."""
    group: str | None = None
    unit_digits: int = 0
    total_digits: int = 0
    aiu: bool = False
    iva_rate_cell: bool = False
    """Escribe la tasa (0,19) junto al IVA, en la columna del unitario."""
    title: str | None = None
    """Título de la tabla (p. ej. su grupo), dos filas arriba del encabezado."""

    @property
    def name_row(self) -> int:
        return self.first_item_row - 2

    @property
    def header_row(self) -> int:
        return self.first_item_row - 1

    @property
    def title_address(self) -> str | None:
        return f"{self.item_columns['description']}{self.first_item_row - 3}" if self.title else None


@dataclass(frozen=True)
class Block:
    """Un proveedor ubicado en la hoja: rol -> columna."""

    provider: Provider
    columns: dict[str, str] = field(default_factory=dict)

    @property
    def has_offer(self) -> bool:
        return bool(self.provider.offers)

    @property
    def first_column(self) -> str:
        return self.columns[self.provider.roles[0]]

    @property
    def offered_column(self) -> str:
        """Columna del total ofertado; si el bloque no la tiene (cantidad 1), la del unitario."""
        return self.columns.get(Role.TOTAL_PRICE) or self.columns[Role.UNIT_PRICE]

    @property
    def corrected_column(self) -> str:
        return self.columns[Role.TOTAL_PRICE_CORRECTED]
