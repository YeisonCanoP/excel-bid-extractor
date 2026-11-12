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
from scripts.samples.model import AIU_RATE, IVA_RATE, Block, Item, Layout, Offer, Role

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
        unit = self.corrected_unit if Role.UNIT_PRICE_CORRECTED in self.block.columns else self.offer.unit
        base = self.quantity * unit
        tax = base * AIU_RATE * IVA_RATE if self.layout.aiu else 0
        return excel_round(base + tax, self.layout.total_digits)


def cell_for(row: ItemRow, role: str) -> Cell:
    return BUILDERS[role](row)


def _total_price(row: ItemRow) -> Cell:
    if row.layout.aiu:
        return f"={row.ref(Role.SUBTOTAL)}+{row.ref(Role.IVA)}", row.offered_total
    return None, row.offered_total


def _corrected_total(row: ItemRow) -> Cell:
    digits = row.layout.total_digits
    if row.offer.unit is None:
        return f"=ROUND({row.ref(Role.TOTAL_PRICE)},{digits})", row.corrected_total
    unit_role = Role.UNIT_PRICE_CORRECTED if Role.UNIT_PRICE_CORRECTED in row.block.columns else Role.UNIT_PRICE
    unit = row.ref(unit_role)
    base = f"{unit}*{row.quantity_expr}"
    expression = f"({base})+({base}*10%*19%)" if row.layout.aiu else base
    return f"=ROUND({expression},{digits})", row.corrected_total


def _check(row: ItemRow) -> Cell:
    offered = f"{row.block.offered_column}{row.row}"
    verdict = "OK" if row.offered_total == row.corrected_total else "ERROR"
    return f'=IF({offered}={row.ref(Role.TOTAL_PRICE_CORRECTED)},"OK","ERROR")', verdict


BUILDERS: dict[str, Callable[[ItemRow], Cell]] = {
    Role.BRAND: lambda row: (None, row.block.provider.brand),
    Role.UNIT_PRICE: lambda row: (None, row.offer.unit),
    Role.TOTAL_PRICE: _total_price,
    Role.SUBTOTAL: lambda row: (f"={row.quantity_expr}*{row.ref(Role.UNIT_PRICE)}", row.subtotal),
    Role.AIU: lambda row: (f"={row.ref(Role.SUBTOTAL)}*10%", without_noise(row.subtotal * AIU_RATE)),
    Role.IVA: lambda row: (f"={row.ref(Role.AIU)}*19%", row.iva),
    Role.UNIT_PRICE_CORRECTED: lambda row: (f"=ROUND({row.ref(Role.UNIT_PRICE)},{row.layout.unit_digits})",
                                         row.corrected_unit),
    Role.TOTAL_PRICE_CORRECTED: _corrected_total,
    Role.CHECK: _check,
}
