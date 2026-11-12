"""Repositorios de los resultados del análisis: mapas, cotizaciones, totales y reportes.

Al reprocesar un documento se reemplazan sus resultados: nada se duplica.
"""

from app.domain.quotation import OfferTotal, Quotation
from app.domain.report import Report
from app.domain.sheet_map import SheetMap
from app.storage.mongo import get_db


class CellMapRepository:
    """Colección cell_maps: el mapa de cada hoja principal, con sus intentos."""

    def __init__(self) -> None:
        self.collection = get_db().cell_maps

    def for_document(self, document_id: str) -> list[SheetMap]:
        return [SheetMap.model_validate(doc) for doc in self.collection.find({"document_id": document_id})]

    def save(self, sheet_map: SheetMap) -> None:
        key = {"document_id": sheet_map.document_id, "sheet_name": sheet_map.sheet_name}
        self.collection.replace_one(key, sheet_map.model_dump(mode="json"), upsert=True)

    def delete_for_document(self, document_id: str) -> None:
        self.collection.delete_many({"document_id": document_id})


class QuotationRepository:
    """Colección quotations: una cotización por proveedor x ítem."""

    def __init__(self) -> None:
        self.collection = get_db().quotations

    def replace_for_document(self, document_id: str, quotations: list[Quotation]) -> None:
        self.collection.delete_many({"document_id": document_id})
        if quotations:
            self.collection.insert_many([q.model_dump(mode="json") for q in quotations])

    def for_document(self, document_id: str) -> list[Quotation]:
        return [Quotation.model_validate(doc) for doc in self.collection.find({"document_id": document_id})]


class OfferTotalRepository:
    """Colección offer_totals: los totales de cada proveedor, por tabla y por hoja."""

    def __init__(self) -> None:
        self.collection = get_db().offer_totals

    def replace_for_document(self, document_id: str, totals: list[OfferTotal]) -> None:
        self.collection.delete_many({"document_id": document_id})
        if totals:
            self.collection.insert_many([t.model_dump(mode="json") for t in totals])

    def for_document(self, document_id: str) -> list[OfferTotal]:
        return [OfferTotal.model_validate(doc) for doc in self.collection.find({"document_id": document_id})]


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
