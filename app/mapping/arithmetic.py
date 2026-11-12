"""Prueba aritmética del mapa: se extraen las cotizaciones en seco y se corren las reglas de integridad.

La hoja ya trae las respuestas (los valores corregidos y el OK/ERROR del evaluador): si el mapa está bien,
las cuentas cuadran; si una columna está corrida, no. Las fallas se agrupan por regla para la retroalimentación.
"""

from collections import defaultdict

from app.domain.cell_map import CellMapResult
from app.domain.source_sheet import SourceSheet
from app.domain.validation import RuleResult
from app.quotes import Tolerances, process_sheet

MAX_PROBLEMS = 12
"""Reglas distintas que se reportan; más que eso solo agrega ruido al reintento."""


def arithmetic_problems(sheet: SourceSheet, cell_map: CellMapResult, tolerances: Tolerances) -> list[str]:
    result, failures = process_sheet(sheet, cell_map, document_id=sheet.document_id, group=sheet.group,
                                     tolerances=tolerances)
    if not result.quotations:
        return ["No se extrajo ninguna cotización: revisa item_rows, la columna de descripción y los bloques."]
    grouped: dict[tuple[str, str], list[RuleResult]] = defaultdict(list)
    for failure in failures:
        grouped[(failure.rule, failure.message)].append(failure)
    return [_describe(rule, message, cases) for (rule, message), cases in list(grouped.items())[:MAX_PROBLEMS]]


def _describe(rule: str, message: str, cases: list[RuleResult]) -> str:
    """'R3 (2 veces): La suma de los ítems no da el total. Ejemplo: celdas L23, L10…; esperado 68.436, hay 70.120.'"""
    example = cases[0]
    text = f"{rule} ({len(cases)} {'vez' if len(cases) == 1 else 'veces'}): {message}."
    text += f" Ejemplo: celdas {', '.join(example.cells[:6])}"
    if example.expected is not None and example.actual is not None:
        text += f"; esperado {example.expected:,.2f}, hay {example.actual:,.2f}"
    return text + "."
