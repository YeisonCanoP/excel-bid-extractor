"""Extracción y reglas sobre hojas pequeñas que imitan informes de evaluación económica."""

from datetime import UTC, datetime

import pytest

from app.domain.cell_map import CellMapResult
from app.domain.classification import SheetRole
from app.domain.quotation import Components, Prices, QuoteStatus, SourcedNumber
from app.domain.source_sheet import Cell, Row, SourceSheet
from app.quotes import Tolerances, process_sheet
from app.quotes.correction import Digits, correct_item, round_digits
from app.quotes.item import ItemValues
from app.quotes.normalize import excel_round, provider_key, unit_label
from app.quotes.rules.common import excel_equal

TOL = Tolerances()
NO_COLUMNS = dict.fromkeys(["brand", "unit_price", "total_price", "unit_price_corrected", "total_price_corrected",
                            "subtotal", "aiu", "iva", "factor", "check"])


def _sheet(cells: dict[str, object]) -> SourceSheet:
    """cells: {'B10': 1, 'L10': (962, '=ROUND($G10*K10,0)')}; la tupla trae la fórmula."""
    rows: dict[int, list[Cell]] = {}
    for address, spec in cells.items():
        value, formula = spec if isinstance(spec, tuple) else (spec, None)
        col = ord(address[0]) - 64
        kind = "number" if isinstance(value, int | float) else "text"
        rows.setdefault(int(address[1:]), []).append(
            Cell(address=address, col=col, value=value, type=kind, formula=formula))
    return SourceSheet(document_id="doc", sheet_name="RevAritmética", sheet_index=0, role=SheetRole.PRINCIPAL,
                       group="1", state="visible", used_range="A1:Z30", cell_count=len(cells), merged_cells=[],
                       rows=[Row(row=r, cells=c) for r, c in sorted(rows.items())], created_at=datetime.now(UTC))


def _total(kind: str, row: int, offered: str | None, corrected: str | None, check: str | None = None,
           rate: str | None = None) -> dict:
    return {"kind": kind, "label_address": None, "offered": offered and f"{offered}{row}",
            "corrected": corrected and f"{corrected}{row}", "check": check and f"{check}{row}",
            "rate": rate and f"{rate}{row}"}


def _map(tables: list[dict], currency: str = "USD", sheet_totals: list[dict] | None = None) -> CellMapResult:
    return CellMapResult.model_validate({
        "status": "complete", "currency": currency, "currency_evidence": [], "iva_included": "no",
        "budget_address": "", "budget_label_address": "", "tables": tables,
        "sheet_totals": sheet_totals or [], "missing_fields": [], "confidence": 0.95, "warnings": [],
        "requires_human_review": False})


def _table(items: tuple[int, int], item_columns: dict, providers: list[dict], table_id: str = "t1",
           group: str | None = None) -> dict:
    return {"table_id": table_id, "group": group, "title_address": None, "site_address": None, "header_rows": [8],
            "item_rows": {"first": items[0], "last": items[1]},
            "item_columns": {"item_no": None, "detail": [], "unit": None, "tariff_type": None} | item_columns,
            "providers": providers, "confidence": 0.95}


def _provider(name_address: str, columns: dict, totals: list[dict]) -> dict:
    return {"name_address": name_address, "columns": NO_COLUMNS | columns, "totals": totals}


# ---------- USD, redondeo a entero, NO COTIZA, bloque INVITADO ----------

@pytest.fixture
def usd_sheet() -> SourceSheet:
    return _sheet({
        "H7": "PROVEEDOR UNO SAS", "N7": "INVITADO",
        "C10": "Soporte metálico", "F10": "EA", "G10": 10,
        "I10": 96.16, "J10": 961.6, "K10": (96.16, "=+ROUND(I10,2)"), "L10": (962, "=+ROUND($G10*K10,0)"),
        "M10": "ERROR",
        "C11": "Caja de conexión", "F11": "EA", "G11": 8,
        "I11": "NO COTIZA",
        "C12": "Cable de cobre", "F12": "metros", "G12": 2000,
        "I12": 1.19, "J12": 2380, "K12": (1.19, "=+ROUND(I12,2)"), "L12": (2380, "=+ROUND($G12*K12,0)"), "M12": "OK",
        "J23": 3341.6, "L23": 3342, "M23": "ERROR",
        "I24": 0.19, "J24": 634.9, "L24": 634.98,
        "J25": 3976.5, "L25": 3976.98,
    })


def _usd_map(unit_corrected: str = "K") -> CellMapResult:
    columns = {"unit_price": "I", "total_price": "J", "unit_price_corrected": unit_corrected,
               "total_price_corrected": "L", "check": "M"}
    totals = [_total("subtotal", 23, "J", "L", "M"), _total("iva", 24, "J", "L", rate="I"),
              _total("total", 25, "J", "L")]
    return _map([_table((10, 12), {"description": "C", "unit": "F", "quantity": ["G"]},
                        [_provider("H7", columns, totals), _provider("N7", columns, [])])])


def test_usd_sheet_extracts_quotations_and_agrees_with_evaluator(usd_sheet):
    result, failures = process_sheet(usd_sheet, _usd_map(), document_id="doc", group="1", tolerances=TOL)

    assert failures == []
    assert [q.status for q in result.quotations] == [QuoteStatus.QUOTED, QuoteStatus.NO_OFFER, QuoteStatus.QUOTED]
    assert any("INVITADO" in w or "N7" in w for w in result.warnings)

    first = result.quotations[0]
    assert first.fact is not None
    assert (first.fact.precio.value, first.fact.total_oferta.value, first.fact.iva.value) == (96.16, 962, 19)
    assert first.unit.value == "EA"
    assert result.quotations[2].unit.value == "METROS"
    r5 = next(v for v in first.validations if v.rule == "R5")
    assert r5.passed and "ERROR" in r5.message  # 961,6 ≠ 962: el evaluador marcó ERROR y nosotros también


def test_shifted_column_in_map_is_detected(usd_sheet):
    """Si el mapa apunta a la columna equivocada, la prueba aritmética lo detecta (R2)."""
    _, failures = process_sheet(usd_sheet, _usd_map(unit_corrected="J"), document_id="doc", group="1",
                                tolerances=TOL)

    assert {f.rule for f in failures} == {"R2"}


def test_offered_total_difference_is_a_finding_not_a_failure(usd_sheet):
    result, failures = process_sheet(usd_sheet, _usd_map(), document_id="doc", group="1", tolerances=TOL)

    findings = [v for t in result.totals for v in t.validations if v.rule == "R11"]
    assert failures == []
    assert findings and not findings[0].passed


# ---------- AIU e IVA por ítem ----------

AIU_CELLS = {
    "E6": "PROVEEDOR DOS LTDA", "C9": "Servicio de soporte mensual", "D9": 4,
    "E9": 31521273, "F9": 126085092, "G9": 12608509.200000001, "H9": 2395616.748, "I9": 128480708.748,
    "J9": (31521273, "=+ROUND(E9,0)"), "K9": (128480709, "=+ROUND((J9*$D9)+(J9*$D9*10%*19%),0)"),
    "L9": "ERROR",
    "I11": 128480708.748, "K11": 128480709, "L11": "ERROR",
}
AIU_COLUMNS = {"unit_price": "E", "subtotal": "F", "aiu": "G", "iva": "H", "total_price": "I",
               "unit_price_corrected": "J", "total_price_corrected": "K", "check": "L"}


def test_aiu_sheet_reports_utilidad_and_iva_on_utility():
    cell_map = _map([_table((9, 9), {"description": "C", "quantity": ["D"]},
                            [_provider("E6", AIU_COLUMNS, [_total("total", 11, "I", "K", "L")])])], currency="COP")

    result, failures = process_sheet(_sheet(AIU_CELLS), cell_map, document_id="doc", group="1", tolerances=TOL)

    quotation = result.quotations[0]
    fact, aiu = quotation.fact, quotation.components.aiu
    assert failures == []
    assert fact is not None and fact.utilidad is not None and fact.iva_sobre_utilidad is not None
    assert (fact.iva.value, fact.utilidad.value, fact.iva_sobre_utilidad.value) == (0, 10, 19)
    assert fact.total_oferta is not None and fact.total_oferta.value == 126085092  # antes de IVA
    assert aiu is not None and aiu.value == 12608509.2


# ---------- Dos columnas de cantidad, dos tablas (una por grupo) y total de la hoja ----------

TWO_TABLES_CELLS = {
    "F6": "PROVEEDOR TRES SAS",
    "B9": "Licencia de software", "C9": "USUARIO MES", "D9": 151, "E9": 12,
    "F9": 500000, "G9": 906000000, "H9": (500000, "=+ROUND(F9,0)"), "I9": (906000000, "=+ROUND(D9*E9*H9,0)"),
    "G12": 906000000, "I12": 906000000,
    "B16": "Licencia de software", "C16": "USUARIO MES", "D16": 16, "E16": 12,
    "F16": 500000, "G16": 96000000, "H16": (500000, "=+ROUND(F16,0)"), "I16": (96000000, "=+ROUND(D16*E16*H16,0)"),
    "G18": 96000000, "I18": 96000000,
    "G20": 1002000000, "I20": 1002000000,
}


def _two_tables_map() -> CellMapResult:
    columns = {"unit_price": "F", "total_price": "G", "unit_price_corrected": "H", "total_price_corrected": "I"}
    items = {"description": "B", "tariff_type": "C", "quantity": ["D", "E"]}
    tables = [_table((9, 9), items, [_provider("F6", columns, [_total("total", 12, "G", "I")])], "t1", "1"),
              _table((16, 16), items, [_provider("F6", columns, [_total("total", 18, "G", "I")])], "t2", "2")]
    return _map(tables, currency="COP", sheet_totals=[_provider("F6", {}, [_total("total", 20, "G", "I")])])


def test_two_quantity_columns_and_sheet_total():
    result, failures = process_sheet(_sheet(TWO_TABLES_CELLS), _two_tables_map(), document_id="doc", group=None,
                                     tolerances=TOL)

    first, second = result.quotations
    assert failures == []
    assert first.quantity is not None and first.quantity.value == 1812
    assert (first.unit.value, first.group, second.group) == ("USUARIO MES", "1", "2")
    assert first.product.key == second.product.key  # el mismo producto en los dos grupos
    assert any(v.rule == "R10" and v.passed for t in result.totals for v in t.validations)


def test_duplicate_quotation_is_an_integrity_failure():
    sheet = _sheet({"F6": "PROVEEDOR TRES SAS",
                    "B9": "Suscripción anual", "D9": 1, "F9": 10, "I9": 10,
                    "B10": "Suscripción anual", "D10": 1, "F10": 10, "I10": 10})
    cell_map = _map([_table((9, 10), {"description": "B", "quantity": ["D"]},
                            [_provider("F6", {"unit_price": "F", "total_price_corrected": "I"}, [])])],
                    currency="COP")

    _, failures = process_sheet(sheet, cell_map, document_id="doc", group=None, tolerances=TOL)

    assert [f.rule for f in failures] == ["R7"]


# ---------- normalización y regla del evaluador ----------

def test_excel_round_rounds_half_away_from_zero():
    assert (excel_round(2.5, 0), excel_round(0.125, 2), excel_round(-2.5, 0)) == (3, 0.13, -3)


def test_round_digits_come_from_the_formula():
    usd = Cell(address="K10", col=11, value=1.0, type="number", formula="=+ROUND(I10,2)")
    nested = Cell(address="K9", col=11, value=1.0, type="number", formula="=+ROUND((J9*$D9)+(J9*$D9*10%*19%),0)")
    assert (round_digits(usd, "USD"), round_digits(nested, "COP"), round_digits(None, "USD")) == (2, 0, 2)


def test_correct_item_without_unit_price_rounds_the_total():
    total = SourcedNumber(value=176808237.34, source=["H9"])
    item = ItemValues(row=9, quantity=SourcedNumber(value=1, source=["E9"]), offered=Prices(unit_price=None,
                      total_price=total), corrected=Prices(unit_price=None, total_price=None),
                      components=Components(subtotal=None, aiu=None, iva=None))

    correction = correct_item(item, Digits(unit=0, total=0))

    assert (correction.unit_price, correction.total_price) == (None, 176808237)


@pytest.mark.parametrize(("name", "key"), [
    ("ACME ANDINA S A S", "ACME ANDINA"),
    ("Servicios Delta Ltda.", "SERVICIOS DELTA"),
    ("OMEGA DE COLOMBIA Y CIA LTDA", "OMEGA DE COLOMBIA"),
    ("BETA INDUSTRIAL S.A.", "BETA INDUSTRIAL"),
])
def test_provider_key(name, key):
    assert provider_key(name) == key


def test_unit_label():
    assert (unit_label("metros", None, None), unit_label(None, "USUARIO MES", None),
            unit_label("Unidad", "Preventivo", "Centro"), unit_label(None, None, None)) == (
        "METROS", "USUARIO MES", "UNIDAD PREVENTIVO CENTRO", "UND")


# ---------- Capítulos y AIU al pie (administración, utilidad, IVA sobre utilidad) ----------

CHAPTER_CELLS = {
    "F6": "PROVEEDOR UNO SAS",
    "B9": 1, "C9": "Obras civiles",
    "B10": 1.1, "C10": "Excavación manual", "E10": 10, "F10": 100, "H10": (100, "=+ROUND(F10,0)"),
    "I10": (1000, "=+ROUND($E10*H10,0)"),
    "B11": 2, "C11": "Casetas",
    "B12": 2.1, "C12": "Excavación manual", "E12": 5, "F12": 100, "H12": (100, "=+ROUND(F12,0)"),
    "I12": (500, "=+ROUND($E12*H12,0)"),
    "I14": 1500, "F15": 0.25, "I15": 375, "F16": 0.05, "I16": 75, "F17": 0.19, "I17": 14.25, "I18": 1964.25,
}


def _chapters_map() -> CellMapResult:
    columns = {"unit_price": "F", "unit_price_corrected": "H", "total_price_corrected": "I"}
    totals = [_total("subtotal", 14, None, "I"), _total("administration", 15, None, "I", rate="F"),
              _total("utility", 16, None, "I", rate="F"), _total("iva_on_utility", 17, None, "I", rate="F"),
              _total("total", 18, None, "I")]
    items = {"item_no": "B", "description": "C", "quantity": ["E"]}
    return _map([_table((9, 12), items, [_provider("F6", columns, totals)])], currency="COP")


def test_chapter_rows_are_skipped_and_repeated_descriptions_are_not_duplicates():
    result, failures = process_sheet(_sheet(CHAPTER_CELLS), _chapters_map(), document_id="doc", group=None,
                                     tolerances=TOL)

    assert failures == []
    assert [q.product.item_no for q in result.quotations] == ["1.1", "2.1"]
    assert any(v.rule == "R4" and v.passed for t in result.totals for v in t.validations)


def test_aiu_footer_gives_administration_utility_and_iva_on_utility():
    result, _ = process_sheet(_sheet(CHAPTER_CELLS), _chapters_map(), document_id="doc", group=None, tolerances=TOL)

    fact = result.quotations[0].fact
    assert fact is not None and fact.administracion and fact.utilidad and fact.iva_sobre_utilidad
    assert (fact.iva.value, fact.administracion.value, fact.utilidad.value, fact.iva_sobre_utilidad.value) == (
        0, 25, 5, 19)


def test_excel_equality_ignores_noise_beyond_15_significant_digits():
    assert excel_equal(20307105.000000004, 20307105)
    assert not excel_equal(961.6, 962)
    assert not excel_equal(3376.4900000000002, 3376.48)


def test_site_headings_go_into_the_unit_so_repeated_items_are_not_duplicates():
    cells = {"F6": "PROVEEDOR UNO SAS", "B9": "PATIO DE 500KV",
             "B10": 1.1, "C10": "Aisladores", "D10": "Un", "E10": 27, "F10": 10, "I10": 270,
             "B11": "PATIO DE 230KV",
             "B12": 1.1, "C12": "Aisladores", "D12": "Un", "E12": 18, "F12": 10, "I12": 180}
    items = {"item_no": "B", "description": "C", "unit": "D", "quantity": ["E"]}
    cell_map = _map([_table((9, 12), items, [_provider("F6", {"unit_price": "F", "total_price_corrected": "I"}, [])])],
                    currency="COP")

    result, failures = process_sheet(_sheet(cells), cell_map, document_id="doc", group=None, tolerances=TOL)

    assert failures == []
    assert [q.unit.value for q in result.quotations] == ["UN PATIO DE 500KV", "UN PATIO DE 230KV"]
