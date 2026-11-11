"""Clasificador con IA: Claude recibe las fichas de todas las hojas y asigna un rol a cada una."""

import json

from app.ai.client import PROVIDER, ClaudeAnswer, ClaudeClient, load_prompt
from app.classifiers.base import ClassificationOutcome
from app.classifiers.rules import suggest_role
from app.config import settings
from app.domain.ai_run import AiRun
from app.domain.classification import ClassificationResult
from app.domain.document import SheetProfile

STAGE = "sheet_classification"
SCHEMA_VERSION = "1.0"


class AiClassifier:
    """Una llamada a Claude por libro. Toda llamada queda registrada (AiRun), aunque no haya respuesta válida."""

    name = "ai"

    def __init__(self) -> None:
        self.system_prompt = load_prompt(settings.prompt_version)
        self.claude = ClaudeClient(deployment=settings.model_classify, effort=settings.effort_classify)

    def classify(self, file_name: str, profiles: list[SheetProfile]) -> ClassificationOutcome:
        """Envía las fichas del libro y devuelve la clasificación junto con el registro de la llamada."""
        answer = self.claude.ask(
            system=self.system_prompt,
            user=build_user_message(file_name, profiles),
            schema=ClassificationResult,
        )
        result = answer.output if isinstance(answer.output, ClassificationResult) else None
        return ClassificationOutcome(result=result, ai_run=self._ai_run(answer, result))

    def _ai_run(self, answer: ClaudeAnswer, result: ClassificationResult | None) -> AiRun:
        """Registro de la llamada, aunque la IA no haya devuelto una respuesta válida."""
        return AiRun(
            stage=STAGE,
            provider=PROVIDER,
            deployment=self.claude.deployment,
            effort=self.claude.effort,
            prompt_version=settings.prompt_version,
            schema_version=SCHEMA_VERSION,
            stop_reason=answer.stop_reason,
            usage=answer.usage,
            duration_ms=answer.duration_ms,
            request_id=answer.request_id,
            response=result.model_dump(mode="json") if result else None,
        )


def build_user_message(file_name: str, profiles: list[SheetProfile]) -> str:
    """Mensaje para la IA: nombre del libro y la ficha completa de cada hoja.

    El JSON va compacto (sin espacios ni señales en cero) para ahorrar tokens sin perder información.
    """
    sheets = [_profile_for_ai(profile) for profile in profiles]
    return (
        f"Libro: {file_name}\n"
        f"Número de hojas: {len(profiles)}\n\n"
        f"Fichas de las hojas (JSON):\n{json.dumps(sheets, ensure_ascii=False, separators=(',', ':'))}"
    )


def _profile_for_ai(profile: SheetProfile) -> dict:
    """Ficha completa de la hoja más el rol sugerido por reglas, que la IA usa como pista."""
    return {
        "sheet_name": profile.sheet_name,
        "state": profile.state,
        "used_range": profile.used_range,
        "non_empty_cells": profile.non_empty_cells,
        "numeric_nonzero_cells": profile.numeric_nonzero_cells,
        "header_text": profile.header_text,
        "signals": profile.signals.model_dump(exclude_defaults=True),
        "detected_group": profile.detected_group,
        "suggested_role": suggest_role(profile).value,
    }
