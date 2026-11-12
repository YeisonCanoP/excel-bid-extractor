"""Repositorios: una clase por colección. Reciben y guardan modelos de dominio."""

import re
from datetime import UTC, datetime
from pathlib import Path

from app.domain.ai_run import AiRun
from app.domain.classification import DocumentClassification, SheetRole
from app.domain.document import DocumentOutcome, DocumentStatus, SheetProfile, StageLog
from app.domain.source_sheet import SourceSheet
from app.storage.mongo import get_db

RESET_FIELDS = ("sheet_count", "sheet_profiles", "classification", "error", "review_code", "review_reasons", "summary")
"""Campos que se borran al reprocesar un documento."""


def _now() -> datetime:
    return datetime.now(UTC)


class DocumentRepository:
    """Colección documents: un registro por Excel, con _id = sha256 del archivo."""

    def __init__(self) -> None:
        self.collection = get_db().documents

    def get_status(self, document_id: str) -> DocumentStatus | None:
        document = self.collection.find_one({"_id": document_id}, {"status": 1})
        return DocumentStatus(document["status"]) if document else None

    def get(self, document_id: str) -> dict | None:
        return self.collection.find_one({"_id": document_id})

    def find_by_name(self, file_name: str) -> dict | None:
        """Documento por nombre de archivo (o por el inicio del nombre, p. ej. '40.')."""
        exact = self.collection.find_one({"file_name": file_name}, {"sheet_profiles": 0})
        return exact or self.collection.find_one({"file_name": {"$regex": f"^{re.escape(file_name)}"}},
                                                 {"sheet_profiles": 0})

    def list_summaries(self) -> list[dict]:
        """Todos los documentos sin las fichas de hojas (que son pesadas), ordenados por nombre."""
        return list(self.collection.find({}, {"sheet_profiles": 0}).sort("file_name"))

    def register(self, document_id: str, path: Path) -> None:
        """Crea el documento, o lo reinicia si se está reprocesando."""
        now = _now()
        fields = {"file_name": path.name, "file_path": path.as_posix(), "size_bytes": path.stat().st_size,
                  "status": DocumentStatus.RECEIVED, "stage_log": [], "updated_at": now}
        update = {"$set": fields, "$unset": dict.fromkeys(RESET_FIELDS, ""), "$setOnInsert": {"created_at": now}}
        self.collection.update_one({"_id": document_id}, update, upsert=True)

    def save_profiles(self, document_id: str, profiles: list[SheetProfile]) -> None:
        self._set(document_id, sheet_count=len(profiles), sheet_profiles=[p.model_dump() for p in profiles])

    def save_classification(self, document_id: str, classification: DocumentClassification) -> None:
        self._set(document_id, classification=classification.model_dump(mode="json"))

    def set_status(self, document_id: str, status: DocumentStatus) -> None:
        self._set(document_id, status=status)

    def save_outcome(self, document_id: str, outcome: DocumentOutcome) -> None:
        """Estado final del análisis: estado, código y motivos de revisión, y el resumen de resultados."""
        self._set(document_id, **outcome.model_dump(mode="json"))

    def mark_failed(self, document_id: str, error: Exception) -> None:
        self._set(document_id, status=DocumentStatus.FAILED, error=f"{type(error).__name__}: {error}")

    def add_stage_log(self, document_id: str, log: StageLog) -> None:
        self.collection.update_one({"_id": document_id}, {"$push": {"stage_log": log.model_dump(exclude_none=True)}})

    def _set(self, document_id: str, **fields: object) -> None:
        self.collection.update_one({"_id": document_id}, {"$set": {**fields, "updated_at": _now()}})


class SourceSheetRepository:
    """Colección source_sheets: el JSON limpio de cada hoja principal o de apoyo."""

    def __init__(self) -> None:
        self.collection = get_db().source_sheets

    def for_document(self, document_id: str, role: SheetRole) -> list[SourceSheet]:
        query = {"document_id": document_id, "role": role.value}
        return [SourceSheet.model_validate(doc) for doc in self.collection.find(query).sort("sheet_index")]

    def replace_for_document(self, document_id: str, sheets: list[SourceSheet]) -> None:
        """Reemplaza todas las hojas del documento (así reprocesar no deja hojas viejas)."""
        self.collection.delete_many({"document_id": document_id})
        if sheets:
            self.collection.insert_many([sheet.model_dump(exclude_none=True) for sheet in sheets])


class AiRunRepository:
    """Colección ai_runs: una entrada por llamada a la IA."""

    def __init__(self) -> None:
        self.collection = get_db().ai_runs

    def add(self, document_id: str, run: AiRun) -> str:
        inserted = self.collection.insert_one({"document_id": document_id, **run.model_dump(), "created_at": _now()})
        return str(inserted.inserted_id)
