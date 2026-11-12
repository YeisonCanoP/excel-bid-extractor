"""Repositorios de los resultados del análisis: mapas, cotizaciones, totales y reportes.

Al reprocesar un documento se reemplazan sus resultados: nada se duplica.
"""

from pydantic import BaseModel

from app.domain.quotation import OfferTotal, Quotation
from app.domain.report import Report
from app.domain.sheet_map import SheetMap
from app.storage.mongo import SHEET_NAME, get_db, of_document


class _PerDocument[T: BaseModel]:
    """Colección con varios registros por documento, que se reemplazan juntos."""

    model: type[T]
    collection_name: str

    def __init__(self) -> None:
        self.collection = get_db()[self.collection_name]

    def for_document(self, document_id: str) -> list[T]:
        return [self.model.model_validate(doc) for doc in self.collection.find(of_document(document_id))]

    def replace_for_document(self, document_id: str, items: list[T]) -> None:
        self.delete_for_document(document_id)
        if items:
            self.collection.insert_many([item.model_dump(mode="json") for item in items])

    def delete_for_document(self, document_id: str) -> None:
        self.collection.delete_many(of_document(document_id))


class CellMapRepository(_PerDocument[SheetMap]):
    """Colección cell_maps: el mapa de cada hoja principal, con sus intentos."""

    model, collection_name = SheetMap, "cell_maps"

    def save(self, sheet_map: SheetMap) -> None:
        key = {**of_document(sheet_map.document_id), SHEET_NAME: sheet_map.sheet_name}
        self.collection.replace_one(key, sheet_map.model_dump(mode="json"), upsert=True)


class QuotationRepository(_PerDocument[Quotation]):
    """Colección quotations: una cotización por proveedor x ítem."""

    model, collection_name = Quotation, "quotations"


class OfferTotalRepository(_PerDocument[OfferTotal]):
    """Colección offer_totals: los totales de cada proveedor, por tabla y por hoja."""

    model, collection_name = OfferTotal, "offer_totals"


class ReportRepository:
    """Colección reports: un reporte por documento (_id = id del documento)."""

    def __init__(self) -> None:
        self.collection = get_db().reports

    def save(self, report: Report) -> None:
        self.collection.replace_one({"_id": report.document_id}, report.model_dump(mode="json"), upsert=True)

    def get(self, document_id: str) -> Report | None:
        doc = self.collection.find_one({"_id": document_id})
        return Report.model_validate(doc) if doc else None

    def delete(self, document_id: str) -> None:
        self.collection.delete_one({"_id": document_id})
