"""Mapeador: verificación del mapa y reintentos, con un cliente falso (sin llamar a la IA)."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.ai.client import ClaudeAnswer, ClaudeClient
from app.domain.ai_run import TokenUsage
from app.domain.cell_map import CellMapResult
from app.domain.classification import SheetClassification, SheetRole
from app.domain.source_sheet import SourceSheet
from app.domain.validation import ReviewCode
from app.excel.extractor import extract_sheet
from app.excel.reader import load_formulas, load_values
from app.mapping.mapper import AiMapper

SAMPLE = Path(__file__).parent.parent / "samples" / "01_suministro_equipos_usd.xlsx"
EXPECTED = SAMPLE.parent / "expected" / "01_suministro_equipos_usd.json"
SHEET = "Revisión aritmética"


@dataclass(frozen=True)
class FakeClaude(ClaudeClient):
    """Devuelve los mapas en orden y guarda los mensajes que recibió."""

    outputs: list[BaseModel | None] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def ask(self, *, system: str, user: str, schema: type[BaseModel]) -> ClaudeAnswer:
        self.messages.append(user)
        output = self.outputs.pop(0)
        return ClaudeAnswer(output=output, stop_reason="end_turn" if output else "refusal",
                            usage=TokenUsage(input_tokens=1, output_tokens=1), duration_ms=1, request_id=None)


@pytest.fixture(scope="module")
def sheet() -> SourceSheet:
    values, formulas = load_values(SAMPLE), load_formulas(SAMPLE)
    classification = SheetClassification(sheet_name=SHEET, role=SheetRole.PRINCIPAL, group=None, confidence=1,
                                         reason="test")
    return extract_sheet(values[SHEET], formulas[SHEET], classification, document_id="doc", sheet_index=0)


def _good_map() -> CellMapResult:
    return CellMapResult.model_validate(json.loads(EXPECTED.read_text(encoding="utf-8"))["maps"][SHEET])


def _shifted_map() -> CellMapResult:
    """El total corregido del primer proveedor apunta a la columna del ofertado."""
    bad = _good_map()
    bad.tables[0].providers[0].columns.total_price_corrected = "J"
    return bad


def _mapper(*outputs: BaseModel | None) -> tuple[AiMapper, FakeClaude]:
    claude = FakeClaude("fake", "low", 1000, outputs=list(outputs))
    return AiMapper(claude=claude), claude


def test_correct_map_is_accepted_on_first_attempt(sheet):
    mapper, _ = _mapper(_good_map())

    outcome = mapper.map_sheet("libro.xlsx", sheet, [])

    assert outcome.accepted and outcome.problems == []
    assert [run.attempt for run in outcome.runs] == [1]


def test_shifted_column_is_retried_with_feedback(sheet):
    mapper, claude = _mapper(_shifted_map(), _good_map())

    outcome = mapper.map_sheet("libro.xlsx", sheet, [])

    assert outcome.accepted and len(outcome.runs) == 2
    assert "## Corrección" not in claude.messages[0]
    assert "## Corrección" in claude.messages[1] and "R2" in claude.messages[1]


def test_map_that_never_adds_up_goes_to_human_review(sheet):
    mapper, _ = _mapper(_shifted_map(), _shifted_map())

    outcome = mapper.map_sheet("libro.xlsx", sheet, [])

    assert outcome.review_code == ReviewCode.UNRESOLVED_DOCUMENT
    assert outcome.problems and not outcome.accepted


def test_no_answer_is_an_interpretation_error_without_retry(sheet):
    mapper, _ = _mapper(None)

    outcome = mapper.map_sheet("libro.xlsx", sheet, [])

    assert outcome.review_code == ReviewCode.INTERPRETATION_ERROR and len(outcome.runs) == 1


def test_structure_problems_are_reported_before_arithmetic(sheet):
    bad = _good_map()
    bad.tables[0].providers[0].name_address = "H99"

    problems = AiMapper(claude=FakeClaude("fake", "low", 1000)).check(sheet, bad)

    assert any("H99" in problem for problem in problems)
