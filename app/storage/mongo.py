"""Conexión a MongoDB e índices."""

from functools import cache

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from app.config import settings

SERVER_TIMEOUT_MS = 3000  # falla rápido si Mongo no está corriendo
COLLECTIONS = ("documents", "source_sheets", "ai_runs", "cell_maps", "quotations", "offer_totals", "reports")


@cache
def get_db() -> Database:
    """Base de datos del demo. La conexión se crea una sola vez y se reutiliza."""
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=SERVER_TIMEOUT_MS, tz_aware=True)
    return client[settings.mongo_db]


def ensure_indexes() -> None:
    """Crea los índices si no existen (operación idempotente). También sirve para probar la conexión."""
    db = get_db()
    db.source_sheets.create_index([("document_id", ASCENDING), ("sheet_name", ASCENDING)], unique=True)
    db.ai_runs.create_index([("document_id", ASCENDING), ("stage", ASCENDING)])
    db.documents.create_index([("status", ASCENDING)])
    db.cell_maps.create_index([("document_id", ASCENDING), ("sheet_name", ASCENDING)], unique=True)
    db.quotations.create_index([("document_id", ASCENDING), ("sheet_name", ASCENDING)])
    db.quotations.create_index([("document_id", ASCENDING), ("provider.key", ASCENDING)])
    db.offer_totals.create_index([("document_id", ASCENDING), ("sheet_name", ASCENDING)])


def count_documents() -> dict[str, int]:
    """Cantidad de registros por colección."""
    db = get_db()
    return {name: db[name].count_documents({}) for name in COLLECTIONS}


def drop_collections() -> None:
    """Borra las colecciones del demo (datos e índices). Los índices se recrean en la siguiente conexión."""
    db = get_db()
    for name in COLLECTIONS:
        db.drop_collection(name)
