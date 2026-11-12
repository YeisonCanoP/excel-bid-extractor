"""Piezas compartidas por las reglas: tolerancias, R5 (concordancia con el OK/ERROR) y celdas involucradas."""

from dataclasses import dataclass

from app.domain.quotation import SourcedNumber, SourcedText
from app.domain.validation import RuleKind, RuleResult

FINDING, INTEGRITY = RuleKind.FINDING, RuleKind.INTEGRITY
EXCEL_DIGITS = 15
"""Cifras significativas con las que Excel compara dos números en IF(a = b)."""


@dataclass(frozen=True)
class Tolerances:
    finding: float = 0.01
    """Estricta: una diferencia de 0,4 ya es una corrección aritmética."""
    integrity_abs: float = 1.0
    integrity_rel: float = 0.0001
    """Aceptan el redondeo a entero que aplica el evaluador."""

    def close(self, expected: float, actual: float) -> bool:
        return abs(expected - actual) <= max(self.integrity_abs, self.integrity_rel * abs(expected))


def check_agreement(offered: SourcedNumber | None, corrected: SourcedNumber | None,
                    check: SourcedText | None) -> RuleResult | None:
    """R5: nuestra comparación exacta ofertado = corregido coincide con el OK/ERROR del evaluador."""
    if offered is None or corrected is None or check is None or check.value.upper() not in ("OK", "ERROR"):
        return None
    ours = "OK" if excel_equal(_original(offered), _original(corrected)) else "ERROR"
    return RuleResult(rule="R5", kind=INTEGRITY, passed=ours == check.value.upper(),
                      message=f"Evaluador: {check.value.upper()}; nuestra comparación: {ours}",
                      cells=cells_of(offered, corrected, check))


def excel_equal(a: float, b: float) -> bool:
    """Igualdad como la de Excel: 20307105.000000004 = 20307105, porque solo cuenta 15 cifras significativas."""
    return f"{a:.{EXCEL_DIGITS}g}" == f"{b:.{EXCEL_DIGITS}g}"


def _original(number: SourcedNumber) -> float:
    """El valor tal como está en el Excel, sin quitarle el ruido (la comparación de Excel decide qué ignora)."""
    return float(number.raw) if isinstance(number.raw, int | float) else number.value


def cells_of(*values: SourcedNumber | SourcedText | None) -> list[str]:
    """Direcciones de las celdas de los valores dados."""
    return [address for value in values if value is not None for address in value.source]
