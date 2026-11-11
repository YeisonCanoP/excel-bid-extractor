"""Clasificadores de hojas intercambiables: 'ai' (Claude en Foundry) o 'rules' (plan B)."""

from app.classifiers.base import ClassificationOutcome, SheetClassifier


def get_classifier(name: str) -> SheetClassifier:
    # Import diferido: con 'rules' no se carga el SDK de Anthropic ni se exige la API key.
    if name == "rules":
        from app.classifiers.rules import RulesClassifier
        return RulesClassifier()
    if name == "ai":
        from app.classifiers.ai import AiClassifier
        return AiClassifier()
    raise ValueError(f"Clasificador desconocido: {name!r} (usa 'ai' o 'rules')")


__all__ = ["ClassificationOutcome", "SheetClassifier", "get_classifier"]
