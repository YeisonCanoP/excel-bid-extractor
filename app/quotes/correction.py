"""Regla de corrección aritmética del evaluador, leída de sus fórmulas.

    unitario corregido = ROUND(unitario ofertado, d)
    total corregido    = ROUND(cantidad x unitario corregido x (1 + IVA/base del ítem), d)

Los decimales `d` salen de la fórmula ROUND(…, d) de la celda corregida. Si no hay fórmula,
se usan 0 decimales para COP y 2 para otras monedas.
"""

import re
from dataclasses import dataclass

from app.domain.source_sheet import Cell
from app.quotes.item import ItemValues
from app.quotes.normalize import excel_round

_ROUND = re.compile(r"ROUND\((.*),\s*(-?\d+)\s*\)", re.IGNORECASE)
LOCAL_CURRENCY = "COP"


@dataclass(frozen=True)
class Digits:
    """Decimales del redondeo del evaluador para el unitario y para el total."""

    unit: int
    total: int

    @classmethod
    def of(cls, unit_cell: Cell | None, total_cell: Cell | None, currency: str | None) -> "Digits":
        """A partir de las celdas corregidas de unitario y total."""
        return cls(round_digits(unit_cell, currency), round_digits(total_cell, currency))


@dataclass(frozen=True)
class Correction:
    unit_price: float | None
    total_price: float | None


def round_digits(cell: Cell | None, currency: str | None) -> int:
    """Decimales de la fórmula ROUND(…, d) de la celda; sin fórmula, según la moneda."""
    if cell is not None and cell.formula and (match := _ROUND.search(cell.formula)):
        return int(match.group(2))
    return 0 if currency in (None, LOCAL_CURRENCY) else 2


def correct_item(item: ItemValues, digits: Digits) -> Correction:
    """Recalcula la corrección del ítem como lo hizo el evaluador."""
    quantity = item.quantity.value if item.quantity else None
    unit, total = item.offered.unit_price, item.offered.total_price
    if unit is not None and quantity is not None:
        corrected_unit = excel_round(unit.value, digits.unit)
        base = quantity * corrected_unit
        return Correction(corrected_unit, excel_round(base + base * item.tax_rate, digits.total))
    if total is not None:  # sin columna de unitario: solo se redondea el total
        return Correction(None, excel_round(total.value, digits.total))
    return Correction(None, None)
