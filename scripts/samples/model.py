"""Descripción de una tabla de revisión aritmética de muestra: ítems, proveedores y disposición."""

from dataclasses import dataclass, field

AIU_RATE = 0.10
IVA_RATE = 0.19

ROLE_LABELS = {
    "brand": "MARCA",
    "unit_price": "VALOR UNITARIO",
    "total_price": "VALOR TOTAL",
    "subtotal": "VALOR MES DE SERVICIOS",
    "aiu": "VALOR AIU",
    "iva": "VALOR IVA",
    "unit_price_corrected": "VALOR UNITARIO REDONDEADO",
    "total_price_corrected": "CORRECCIÓN ARITMÉTICA",
    "check": "VERIFICACIÓN",
}
TEXT_ROLES = {"brand", "check"}
TOTAL_LABELS = {"subtotal": "SUBTOTAL", "iva": "IVA", "total": "VALOR TOTAL"}


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
    totals: tuple[str, ...] = ("subtotal", "iva", "total")
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
        return self.columns.get("total_price") or self.columns["unit_price"]

    @property
    def corrected_column(self) -> str:
        return self.columns["total_price_corrected"]
