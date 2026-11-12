"""Clasificador por reglas.

Cumple tres funciones:
1. Plan B cuando no hay IA (`--classifier rules`).
2. Pista para la IA: `suggest_role` va en cada ficha que recibe.
3. Línea base para comparar contra la IA.
"""

from app.classifiers.base import ClassificationOutcome
from app.domain.classification import ClassificationResult, SheetClassification, SheetRole
from app.domain.document import SheetProfile
from app.excel.reader import normalize

MIN_NUMBERS_FOR_PRINCIPAL = 5  # menos que esto con la etiqueta de corrección = plantilla vacía

CONFIDENCE_BY_ROLE = {
    SheetRole.PRINCIPAL: 0.90,
    SheetRole.APOYO: 0.70,
    SheetRole.DESCARTADA: 0.80,
}


def suggest_role(profile: SheetProfile) -> SheetRole:
    signals = profile.signals

    if signals.correccion_aritmetica:
        has_values = profile.numeric_nonzero_cells >= MIN_NUMBERS_FOR_PRINCIPAL
        return SheetRole.PRINCIPAL if has_values else SheetRole.DESCARTADA

    mentions_arithmetic = signals.aritmetica > 0 or "ARIT" in normalize(profile.sheet_name)
    has_prices = signals.valor_unitario > 0 or signals.cantidad > 0
    if mentions_arithmetic and has_prices and profile.numeric_nonzero_cells > 0:
        return SheetRole.APOYO

    return SheetRole.DESCARTADA


class RulesClassifier:
    name = "rules"

    def classify(self, file_name: str, profiles: list[SheetProfile]) -> ClassificationOutcome:  # noqa: ARG002
        """Misma interfaz que el clasificador con IA; las reglas solo miran las fichas, no el nombre del archivo."""
        sheets = [self._classify_sheet(profile) for profile in profiles]
        has_principal = any(sheet.role == SheetRole.PRINCIPAL for sheet in sheets)
        result = ClassificationResult(sheets=sheets, warnings=[], requires_human_review=not has_principal)
        return ClassificationOutcome(result=result)

    @staticmethod
    def _classify_sheet(profile: SheetProfile) -> SheetClassification:
        role = suggest_role(profile)
        return SheetClassification(
            sheet_name=profile.sheet_name,
            role=role,
            group=profile.detected_group if role != SheetRole.DESCARTADA else None,
            confidence=CONFIDENCE_BY_ROLE[role],
            reason=_explain(role, profile),
        )


def _explain(role: SheetRole, profile: SheetProfile) -> str:
    if role == SheetRole.PRINCIPAL:
        return (f"Contiene 'corrección aritmética' ({profile.signals.correccion_aritmetica} celdas) "
                f"y {profile.numeric_nonzero_cells} valores numéricos.")
    if role == SheetRole.APOYO:
        return "Menciona aritmética y tiene precios o cantidades, sin columna de corrección."
    if profile.signals.correccion_aritmetica:
        return "Tiene la estructura de una revisión aritmética, pero sin valores: plantilla vacía."
    return "Sin señales de revisión aritmética."
