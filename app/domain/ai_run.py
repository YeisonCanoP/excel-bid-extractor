"""Registro de cada llamada a la IA (colección ai_runs), para auditoría y costos."""

from typing import Any

from pydantic import BaseModel


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class AiRun(BaseModel):
    stage: str
    provider: str
    deployment: str
    effort: str
    prompt_version: str
    schema_version: str
    stop_reason: str | None
    usage: TokenUsage
    duration_ms: int
    request_id: str | None
    response: dict[str, Any] | None
    """Respuesta validada de la IA; None si rechazó la solicitud o se cortó."""

    @property
    def succeeded(self) -> bool:
        return self.response is not None
