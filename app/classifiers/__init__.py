"""Clasificadores de hojas intercambiables: 'ai' (Claude en Foundry) o 'rules' (plan B, sin IA)."""

from app.classifiers.ai import AiClassifier
from app.classifiers.base import ClassificationOutcome, SheetClassifier
from app.classifiers.rules import RulesClassifier

CLASSIFIERS: dict[str, type[SheetClassifier]] = {"ai": AiClassifier, "rules": RulesClassifier}


def get_classifier(name: str) -> SheetClassifier:
    """El clasificador se crea aquí; el de IA no pide la API key hasta su primera llamada."""
    if name not in CLASSIFIERS:
        raise ValueError(f"Clasificador desconocido: {name!r} (usa 'ai' o 'rules')")
    return CLASSIFIERS[name]()


__all__ = ["ClassificationOutcome", "SheetClassifier", "get_classifier"]
