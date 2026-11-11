"""Cliente de Claude en Microsoft Foundry.

Usa structured outputs: la respuesta siempre cumple el esquema pydantic que se pide,
así que nunca hay que interpretar texto libre.
"""

import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from anthropic import AnthropicFoundry
from anthropic.types import ParsedMessage
from pydantic import BaseModel

from app.config import settings
from app.domain.ai_run import TokenUsage

PROVIDER = "azure-foundry"
PROMPTS_DIR = Path(__file__).parent / "prompts"
INCOMPLETE_STOP_REASONS = {"refusal", "max_tokens"}


@dataclass(frozen=True)
class ClaudeAnswer:
    """Respuesta de Claude junto con los datos que se guardan en ai_runs."""

    output: BaseModel | None
    """Respuesta validada; None si el modelo rechazó la solicitud o se cortó por max_tokens."""
    stop_reason: str | None
    usage: TokenUsage
    duration_ms: int
    request_id: str | None


class ClaudeClient:
    """Llamadas a un deployment de Claude con un nivel de esfuerzo fijo."""

    def __init__(self, deployment: str, effort: str) -> None:
        self.deployment = deployment
        """En Foundry, el parámetro `model` es el nombre del deployment."""
        self.effort = effort
        """low | medium | high: cuánto razona el modelo antes de responder (afecta costo y tiempo)."""

    def ask(self, *, system: str, user: str, schema: type[BaseModel]) -> ClaudeAnswer:
        """Envía un mensaje y devuelve la respuesta validada contra `schema`.

        Llamada normal (sin streaming): con max_tokens moderado el SDK no lo exige
        y las respuestas de clasificación son cortas.
        """
        started = time.perf_counter()
        message = _foundry().messages.parse(
            model=self.deployment,
            max_tokens=settings.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": self.effort},
        )
        return _to_answer(message, started)


def _to_answer(message: ParsedMessage, started: float) -> ClaudeAnswer:
    """Respuesta validada (None si la IA rechazó o se cortó) más los datos de auditoría."""
    completed = message.stop_reason not in INCOMPLETE_STOP_REASONS
    return ClaudeAnswer(
        output=message.parsed_output if completed else None,
        stop_reason=message.stop_reason,
        usage=TokenUsage(input_tokens=message.usage.input_tokens, output_tokens=message.usage.output_tokens),
        duration_ms=int((time.perf_counter() - started) * 1000),
        request_id=message._request_id,  # público pese al guion bajo (documentado por el SDK)
    )


def load_prompt(version: str) -> str:
    """Lee el prompt versionado, p. ej. 'classify-v1' -> prompts/classify_v1.md."""
    return (PROMPTS_DIR / f"{version.replace('-', '_')}.md").read_text(encoding="utf-8")


@cache
def _foundry() -> AnthropicFoundry:
    """Cliente del SDK, creado una sola vez. Falla con un mensaje claro si falta la configuración."""
    if not (settings.foundry_api_key and settings.foundry_resource):
        raise RuntimeError("Falta FOUNDRY_API_KEY o FOUNDRY_RESOURCE en .env (o usa --classifier rules).")
    return AnthropicFoundry(api_key=settings.foundry_api_key, resource=settings.foundry_resource)
