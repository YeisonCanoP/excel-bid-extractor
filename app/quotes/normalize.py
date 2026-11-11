"""Normalización de valores y llaves (proveedor, producto, unidad)."""

import re
from decimal import ROUND_HALF_UP, Decimal

from app.domain.source_sheet import Cell
from app.excel.reader import clean_text, normalize

NO_OFFER_TEXTS = {"NO COTIZA", "NO OFERTADO", "NO OFERTA", "N/A", "NA", "-", "NO APLICA"}
PLACEHOLDER_PROVIDERS = {"", "0", "INVITADO", "PARTICIPANTE"}
DEFAULT_UNIT = "UND"
NOISE_DIGITS = 6
"""Decimales que se conservan al quitar el ruido de punto flotante."""

_COMPANY_SUFFIX = re.compile(r"\b(S\s?A\s?S|S\s?A|LTDA|LIMITADA|E\s?S\s?P|S\s?EN\s?C|Y CIA|CIA|SL|SRL)\b")
_NON_ALNUM = re.compile(r"[^A-Z0-9 ]+")
_SPACES = re.compile(r"\s+")


def excel_round(value: float, digits: int) -> float:
    """Igual que ROUND de Excel: la mitad se aleja de cero (round de Python es bancario)."""
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def without_noise(value: float) -> float:
    """12608509.200000001 -> 12608509.2, sin cambiar el monto."""
    return excel_round(value, NOISE_DIGITS)


def to_number(cell: Cell | None) -> float | None:
    """Número de la celda; acepta números guardados como texto. None si no es número."""
    if cell is None or cell.type not in ("number", "text"):
        return None
    try:
        return float(str(cell.value).replace(" ", ""))
    except ValueError:
        return None


def is_no_offer(cell: Cell | None) -> bool:
    """'NO COTIZA', 'NO OFERTADO'… en una celda de precio."""
    return cell is not None and cell.type == "text" and normalize(str(cell.value)).strip() in NO_OFFER_TEXTS


def is_placeholder_provider(name: str) -> bool:
    """Bloques sin proveedor real: 'INVITADO', '0' o vacío."""
    return normalize(name).strip() in PLACEHOLDER_PROVIDERS


def provider_key(name: str) -> str:
    """Mayúsculas, sin tildes, puntuación ni sufijos societarios: 'Acme Andina S.A.S.' -> 'ACME ANDINA'."""
    text = _NON_ALNUM.sub(" ", normalize(name).replace(".", ""))
    return _collapse(_COMPANY_SUFFIX.sub(" ", text))


def product_key(description: str, detail: str | None) -> str:
    """Descripción y detalle normalizados: el mismo ítem en otro grupo tiene la misma llave."""
    return _collapse(_NON_ALNUM.sub(" ", normalize(f"{description} {detail or ''}")))


def unit_label(unit: str | None, tariff_type: str | None, site: str | None) -> str:
    """Unidad del modelo destino: unidad + tipo + sede, en mayúsculas; sin datos, 'UND'."""
    parts = [clean_text(part).upper() for part in (unit, tariff_type, site) if part and clean_text(part)]
    return " ".join(parts) or DEFAULT_UNIT


def _collapse(text: str) -> str:
    return _SPACES.sub(" ", text).strip()
