"""Celdas de un ítem en el bloque de un proveedor: valor ofertado y fórmulas del evaluador con su resultado.

Las fórmulas siguen la regla que usan los evaluadores:
    unitario corregido = ROUND(unitario, d)
    total corregido    = ROUND(cantidad x unitario corregido, d)   (con AIU: + cantidad x unitario x 10 % x 19 %)
    verificación       = IF(total ofertado = total corregido, "OK", "ERROR")
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property

from app.quotes.normalize import excel_round, without_noise
from scripts.samples.model import AIU_RATE, IVA_RATE, Block, Item, Layout, Offer

Cell = tuple[str | None, object]
"""(fórmula o None, valor)."""


@dataclass(frozen=True)
class ItemRow:
    row: int
    item: Item
    offer: Offer
    block: Block
    layout: Layout

    def ref(self, role: str) -> str:
        return f"{self.block.columns[role]}{self.row}"

    @property
    def quantity_expr(self) -> str:
        return "*".join(f"${column}{self.row}" for column in self.layout.quantity_columns)

    @cached_property
    def quantity(self) -> float:
        return math.prod(self.item.quantities)

    @cached_property
    def subtotal(self) -> float:
        return without_noise(self.quantity * (self.offer.unit or 0))

    @cached_property
    def iva(self) -> float:
        return without_noise(self.subtotal * AIU_RATE * IVA_RATE)

    @cached_property
    def offered_total(self) -> float:
        if self.offer.total is not None:
            return self.offer.total
        return without_noise(self.subtotal + self.iva) if self.layout.aiu else self.subtotal

    @cached_property
    def corrected_unit(self) -> float:
        return excel_round(self.offer.unit or 0, self.layout.unit_digits)

    @cached_property
    def corrected_total(self) -> float:
        if self.offer.unit is None:
            return excel_round(self.offered_total, self.layout.total_digits)
        unit = self.corrected_unit if "unit_price_corrected" in self.block.columns else self.offer.unit
        base = self.quantity * unit
        tax = base * AIU_RATE * IVA_RATE if self.layout.aiu else 0
        return excel_round(base + tax, self.layout.total_digits)


def cell_for(row: ItemRow, role: str) -> Cell:
    return BUILDERS[role](row)


def _total_price(row: ItemRow) -> Cell:
    if row.layout.aiu:
        return f"={row.ref('subtotal')}+{row.ref('iva')}", row.offered_total
    return None, row.offered_total


def _corrected_total(row: ItemRow) -> Cell:
    digits = row.layout.total_digits
    if row.offer.unit is None:
        return f"=ROUND({row.ref('total_price')},{digits})", row.corrected_total
    unit = row.ref("unit_price_corrected") if "unit_price_corrected" in row.block.columns else row.ref("unit_price")
    base = f"{unit}*{row.quantity_expr}"
    expression = f"({base})+({base}*10%*19%)" if row.layout.aiu else base
    return f"=ROUND({expression},{digits})", row.corrected_total


def _check(row: ItemRow) -> Cell:
    offered = f"{row.block.offered_column}{row.row}"
    verdict = "OK" if row.offered_total == row.corrected_total else "ERROR"
    return f'=IF({offered}={row.ref("total_price_corrected")},"OK","ERROR")', verdict


BUILDERS: dict[str, Callable[[ItemRow], Cell]] = {
    "brand": lambda row: (None, row.block.provider.brand),
    "unit_price": lambda row: (None, row.offer.unit),
    "total_price": _total_price,
    "subtotal": lambda row: (f"={row.quantity_expr}*{row.ref('unit_price')}", row.subtotal),
    "aiu": lambda row: (f"={row.ref('subtotal')}*10%", without_noise(row.subtotal * AIU_RATE)),
    "iva": lambda row: (f"={row.ref('aiu')}*19%", row.iva),
    "unit_price_corrected": lambda row: (f"=ROUND({row.ref('unit_price')},{row.layout.unit_digits})",
                                         row.corrected_unit),
    "total_price_corrected": _corrected_total,
    "check": _check,
}
