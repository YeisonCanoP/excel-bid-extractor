"""Cliente de Claude en Microsoft Foundry.

- Structured outputs: la respuesta siempre cumple el esquema pydantic que se pide.
- Streaming: las respuestas largas (mapas de hojas grandes, con razonamiento) no chocan con el límite de tiempo.
- El prompt de sistema va en caché: se repite en cada hoja y en cada reintento.
"""

import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from anthropic import AnthropicFoundry
from anthropic.types import ParsedMessage
from pydantic import BaseModel

from app.config import settings
from app.domain.ai_run import AiRun, TokenUsage

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


@dataclass(frozen=True)
class ClaudeClient:
    """Llamadas a un deployment de Claude con esfuerzo y tope de tokens fijos."""

    deployment: str
    """En Foundry, el parámetro `model` es el nombre del deployment."""
    effort: str
    """low | medium | high: cuánto razona el modelo antes de responder (afecta costo y tiempo)."""
    max_tokens: int
    """Tope de la respuesta, razonamiento incluido. Solo se cobra lo generado."""

    def ask(self, *, system: str, user: str, schema: type[BaseModel]) -> ClaudeAnswer:
        """Envía un mensaje y devuelve la respuesta validada contra `schema`."""
        started = time.perf_counter()
        with _foundry().messages.stream(
            model=self.deployment,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": self.effort},
        ) as stream:
            message = stream.get_final_message()
        return _to_answer(message, started, stream.request_id)

    def record(self, answer: ClaudeAnswer, *, stage: str, prompt_version: str, schema_version: str,
               attempt: int = 1) -> AiRun:
        """Registro de la llamada para ai_runs, aunque la IA no haya devuelto una respuesta válida."""
        return AiRun(
            stage=stage, provider=PROVIDER, deployment=self.deployment, effort=self.effort,
            prompt_version=prompt_version, schema_version=schema_version, attempt=attempt,
            stop_reason=answer.stop_reason, usage=answer.usage, duration_ms=answer.duration_ms,
            request_id=answer.request_id,
            response=answer.output.model_dump(mode="json") if answer.output else None,
        )


def _to_answer(message: ParsedMessage, started: float, request_id: str | None) -> ClaudeAnswer:
    """Respuesta validada (None si la IA rechazó o se cortó) más los datos de auditoría."""
    completed = message.stop_reason not in INCOMPLETE_STOP_REASONS
    usage = message.usage
    return ClaudeAnswer(
        output=message.parsed_output if completed else None,
        stop_reason=message.stop_reason,
        usage=TokenUsage(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                         cache_read_input_tokens=usage.cache_read_input_tokens or 0,
                         cache_creation_input_tokens=usage.cache_creation_input_tokens or 0),
        duration_ms=int((time.perf_counter() - started) * 1000),
        request_id=request_id,
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
