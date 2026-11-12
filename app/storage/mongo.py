"""Conexión a MongoDB e índices."""

from functools import cache

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from app.config import settings

SERVER_TIMEOUT_MS = 3000  # falla rápido si Mongo no está corriendo
COLLECTIONS = ("documents", "source_sheets", "ai_runs", "cell_maps", "quotations", "offer_totals", "reports")
DOCUMENT_ID, SHEET_NAME = "document_id", "sheet_name"
"""Campos por los que se buscan los registros de un documento."""


@cache
def get_db() -> Database:
    """Base de datos del demo. La conexión se crea una sola vez y se reutiliza."""
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=SERVER_TIMEOUT_MS, tz_aware=True)
    return client[settings.mongo_db]


def ensure_indexes() -> None:
    """Crea los índices si no existen (operación idempotente). También sirve para probar la conexión."""
    db = get_db()
    db.documents.create_index([("status", ASCENDING)])
    for name, field, unique in (("source_sheets", SHEET_NAME, True), ("cell_maps", SHEET_NAME, True),
                                ("ai_runs", "stage", False), ("quotations", SHEET_NAME, False),
                                ("quotations", "provider.key", False), ("offer_totals", SHEET_NAME, False)):
        db[name].create_index([(DOCUMENT_ID, ASCENDING), (field, ASCENDING)], unique=unique)


def of_document(document_id: str) -> dict[str, str]:
    """Filtro de los registros de un documento."""
    return {DOCUMENT_ID: document_id}


def count_documents() -> dict[str, int]:
    """Cantidad de registros por colección."""
    db = get_db()
    return {name: db[name].count_documents({}) for name in COLLECTIONS}


def drop_collections() -> None:
    """Borra las colecciones del demo (datos e índices). Los índices se recrean en la siguiente conexión."""
    db = get_db()
    for name in COLLECTIONS:
        db.drop_collection(name)
