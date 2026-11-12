"""Pipeline de punta a punta sobre los libros de muestra, con MongoDB en memoria (mongomock) y la IA simulada."""

import mongomock
import pytest
from openpyxl import Workbook, load_workbook

from app.classifiers.rules import RulesClassifier
from app.config import settings
from app.domain.cell_map import CellMapResult
from app.domain.document import DocumentStatus
from app.mapping.mapper import AiMapper
from app.pipeline import Pipeline, StartFrom
from app.storage import repositories, results
from tests.fakes import SAMPLES, FakeClaude, expected_map

GOODS = "01_suministro_equipos_usd"
SERVICES = "02_servicios_aseo_aiu"


@pytest.fixture(autouse=True)
def database(monkeypatch, tmp_path):
    """Cada prueba con su propia base en memoria y su carpeta de salida."""
    db = mongomock.MongoClient(tz_aware=True).db
    monkeypatch.setattr(repositories, "get_db", lambda: db)
    monkeypatch.setattr(results, "get_db", lambda: db)
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    return db


def _pipeline(*maps: CellMapResult | None) -> tuple[Pipeline, FakeClaude]:
    claude = FakeClaude("fake", "low", 1000, outputs=list(maps))
    return Pipeline(RulesClassifier(), AiMapper(claude=claude)), claude


def _shifted(book: str, sheet: str) -> CellMapResult:
    """Mapa con el total corregido del primer proveedor corrido a otra columna: no cuadra."""
    bad = expected_map(book, sheet)
    bad.tables[0].providers[0].columns.total_price_corrected = bad.tables[0].providers[0].columns.total_price
    return bad


def test_full_run_saves_quotations_report_and_excel(database, tmp_path):
    pipeline, _ = _pipeline(expected_map(GOODS, "Revisión aritmética"))

    report = pipeline.process_file(SAMPLES / f"{GOODS}.xlsx")

    assert report.status == DocumentStatus.QUOTATIONS_VALIDATED
    assert report.quotations == 18 and database.quotations.count_documents({}) == 18
    assert database.reports.count_documents({}) == 1 and database.cell_maps.count_documents({}) == 1
    assert report.report_path is not None and report.report_path.parent == tmp_path
    assert load_workbook(report.report_path).sheetnames == ["Resumen", "Cotizaciones", "Totales", "Hallazgos",
                                                            "Revisión"]


def test_processed_document_is_skipped_and_requote_does_not_call_the_ai(database):
    pipeline, claude = _pipeline(expected_map(GOODS, "Revisión aritmética"))
    path = SAMPLES / f"{GOODS}.xlsx"
    pipeline.process_file(path)

    skipped = pipeline.process_file(path)
    requoted = pipeline.process_file(path, start=StartFrom.QUOTES)

    assert skipped.skipped
    assert requoted.quotations == 18 and database.quotations.count_documents({}) == 18  # sin duplicados
    assert len(claude.messages) == 1


def test_sheet_that_does_not_add_up_keeps_the_others_and_goes_to_review(database):
    shifted = _shifted(SERVICES, "REV ARIT GRUPO 2")
    pipeline, _ = _pipeline(expected_map(SERVICES, "REV ARIT GRUPO 1"), shifted, shifted)

    report = pipeline.process_file(SAMPLES / f"{SERVICES}.xlsx")

    assert report.status == DocumentStatus.HUMAN_REVIEW_REQUIRED
    assert database.quotations.count_documents({"sheet_name": "REV ARIT GRUPO 1"}) == 12
    assert database.quotations.count_documents({"sheet_name": "REV ARIT GRUPO 2"}) == 0
    assert any("REV ARIT GRUPO 2" in reason for reason in report.review_reasons)


def test_remap_only_maps_the_pending_sheets(database):
    shifted = _shifted(SERVICES, "REV ARIT GRUPO 2")
    path = SAMPLES / f"{SERVICES}.xlsx"
    first, _ = _pipeline(expected_map(SERVICES, "REV ARIT GRUPO 1"), shifted, shifted)
    first.process_file(path)

    second, claude = _pipeline(expected_map(SERVICES, "REV ARIT GRUPO 2"))
    report = second.process_file(path, start=StartFrom.MAP)

    assert report.status == DocumentStatus.QUOTATIONS_VALIDATED and report.quotations == 24
    assert len(claude.messages) == 1  # solo la hoja pendiente


def test_workbook_without_arithmetic_review_ends_in_review_with_a_report(database, tmp_path):
    path = tmp_path / "sin_revision.xlsx"
    workbook = Workbook()
    workbook.active["A1"], workbook.active["B1"] = "NÚMERO DEL PROCESO", "PROC-0001"
    workbook.save(path)
    pipeline, claude = _pipeline()

    report = pipeline.process_file(path)

    assert report.status == DocumentStatus.HUMAN_REVIEW_REQUIRED and report.quotations == 0
    assert report.report_path is not None and report.report_path.exists()
    assert claude.messages == []
