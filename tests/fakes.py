"""Dobles de prueba compartidos: un cliente de Claude que devuelve respuestas predefinidas."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from app.ai.client import ClaudeAnswer, ClaudeClient
from app.domain.ai_run import TokenUsage
from app.domain.cell_map import CellMapResult

SAMPLES = Path(__file__).parent.parent / "samples"


@dataclass(frozen=True)
class FakeClaude(ClaudeClient):
    """Devuelve las respuestas en orden y guarda los mensajes que recibió."""

    outputs: list[BaseModel | None] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def ask(self, *, system: str, user: str, schema: type[BaseModel]) -> ClaudeAnswer:
        self.messages.append(user)
        output = self.outputs.pop(0)
        return ClaudeAnswer(output=output, stop_reason="end_turn" if output else "refusal",
                            usage=TokenUsage(input_tokens=1, output_tokens=1), duration_ms=1, request_id=None)


def expected_map(book: str, sheet: str) -> CellMapResult:
    """Mapa correcto de una hoja de los libros de muestra (samples/expected)."""
    data = json.loads((SAMPLES / "expected" / f"{book}.json").read_text(encoding="utf-8"))
    return CellMapResult.model_validate(data["maps"][sheet])
