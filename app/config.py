"""Configuración leída desde .env (ver .env.example). Cada campo se puede sobrescribir con una variable de entorno."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "evaluacion_demo"

    # Entrada
    input_dir: Path = Path("scripts/fixture")

    # Clasificación de hojas
    classifier: Literal["ai", "rules"] = "ai"
    confidence_auto: float = 0.85
    """Una hoja principal con menos confianza que esta pasa a revisión humana."""

    # Microsoft Foundry
    foundry_resource: str = ""
    foundry_api_key: str = ""
    model_classify: str = "claude-sonnet-5-5"
    """Nombre del deployment en Foundry."""
    effort_classify: Literal["low", "medium", "high"] = "low"
    max_tokens: int = 4096
    """Tope de la respuesta (no se cobra el tope, solo lo generado). Valores muy altos obligan a usar streaming."""
    prompt_version: str = "classify-v3"
    """Archivo de app/ai/prompts/ con las instrucciones (classify-v3 -> classify_v3.md)."""

    # Validaciones económicas
    tol_finding: float = 0.01
    """Diferencia mínima para reportar un hallazgo de la oferta (0,4 USD ya es una corrección)."""
    tol_integrity_abs: float = 1.0
    tol_integrity_rel: float = 0.0001
    """Tolerancia frente a los valores del evaluador: acepta su redondeo a entero."""


settings = Settings()
