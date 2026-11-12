"""Mapeo de una hoja principal con la IA: pide el mapa, lo verifica y reintenta con los problemas encontrados.

    1. La IA devuelve el mapa (structured outputs).
    2. Estructura: direcciones dentro de la hoja, nombres de proveedor, columnas sin cruces, moneda.
    3. Prueba aritmética: el mapa se aplica en seco y las reglas de integridad deben cuadrar con el evaluador.
    4. Si algo falla, otro intento con el mapa anterior y la lista de problemas.

Un mapa que cuadra con las cuentas del evaluador se acepta. Si no cuadra después de los intentos,
o la IA no pudo interpretar la hoja, la hoja pasa a revisión humana con su código.
"""

from dataclasses import dataclass, field

from app.ai.client import ClaudeClient, load_prompt
from app.config import settings
from app.domain.ai_run import AiRun
from app.domain.cell_map import CellMapResult
from app.domain.document import SheetProfile
from app.domain.source_sheet import SourceSheet
from app.domain.validation import ReviewCode
from app.mapping.arithmetic import arithmetic_problems
from app.mapping.message import build_map_message, retry_message
from app.mapping.structure import structure_problems
from app.quotes import Tolerances
from app.quotes.sheet import SheetCells

STAGE = "cell_mapping"
SCHEMA_VERSION = "1.0"


@dataclass
class MapOutcome:
    cell_map: CellMapResult | None
    problems: list[str] = field(default_factory=list)
    review_code: ReviewCode | None = None
    runs: list[AiRun] = field(default_factory=list)
    history: list[list[str]] = field(default_factory=list)
    """Problemas encontrados en cada intento (vacío en el intento aceptado)."""

    @property
    def accepted(self) -> bool:
        return self.cell_map is not None and self.review_code is None


class AiMapper:
    def __init__(self, claude: ClaudeClient | None = None, tolerances: Tolerances | None = None) -> None:
        self.claude = claude or ClaudeClient(settings.model_map, settings.effort_map, settings.max_tokens_map)
        self.system = load_prompt(settings.prompt_map_version)
        self.tolerances = tolerances or Tolerances(settings.tol_finding, settings.tol_integrity_abs,
                                                   settings.tol_integrity_rel)

    def map_sheet(self, file_name: str, sheet: SourceSheet, support: list[SheetProfile]) -> MapOutcome:
        message = build_map_message(file_name, sheet, support)
        outcome = MapOutcome(cell_map=None)
        for attempt in range(1, settings.map_attempts + 1):
            previous = outcome
            outcome = self._attempt(sheet, retry_message(message, previous.cell_map, previous.problems), attempt,
                                    previous.runs)
            outcome.history = [*previous.history, outcome.problems]
            if outcome.accepted or outcome.review_code == ReviewCode.INTERPRETATION_ERROR:
                return outcome
        outcome.review_code = ReviewCode.UNRESOLVED_DOCUMENT
        return outcome

    def check(self, sheet: SourceSheet, cell_map: CellMapResult) -> list[str]:
        """Problemas del mapa: primero la estructura; si está bien, la prueba aritmética."""
        structure = structure_problems(cell_map, SheetCells(sheet), sheet.used_range)
        return structure or arithmetic_problems(sheet, cell_map, self.tolerances)

    def _attempt(self, sheet: SourceSheet, message: str, attempt: int, runs: list[AiRun]) -> MapOutcome:
        answer = self.claude.ask(system=self.system, user=message, schema=CellMapResult)
        runs = [*runs, self.claude.record(answer, stage=STAGE, prompt_version=settings.prompt_map_version,
                                          schema_version=SCHEMA_VERSION, attempt=attempt)]
        cell_map = answer.output if isinstance(answer.output, CellMapResult) else None
        if cell_map is None or cell_map.status == "unresolved":
            reason = "La IA no devolvió un mapa (rechazo o corte)." if cell_map is None else "; ".join(
                cell_map.warnings) or "La IA no pudo interpretar la hoja."
            return MapOutcome(cell_map, [reason], ReviewCode.INTERPRETATION_ERROR, runs)
        problems = self.check(sheet, cell_map)
        return MapOutcome(cell_map, problems, None if not problems else ReviewCode.UNRESOLVED_DOCUMENT, runs)
