"""Cuadrícula compacta y mensaje para el mapeo con IA."""

from datetime import UTC, datetime

from app.domain.classification import SheetRole
from app.domain.document import SheetProfile, SheetSignals
from app.domain.source_sheet import Cell, Row, SourceSheet
from app.mapping.grid import MAX_TEXT, build_grid
from app.mapping.message import build_map_message

LONG_TEXT = "Cable de fibra óptica para exteriores con cubierta resistente a rayos UV y 24 hilos"


def _sheet() -> SourceSheet:
    cells = {
        7: [Cell(address="B7", value="PARTICIPANTE", type="text"),
            Cell(address="H7", value="ACME ANDINA SAS", type="text")],
        10: [Cell(address="C10", value=LONG_TEXT, type="text"),
             Cell(address="G10", value=8000, type="number", number_format="#,##0"),
             Cell(address="I10", value=12608509.200000001, type="number", number_format="[$USD] #,##0.00"),
             Cell(address="J10", value=5.5, type="number", number_format="[$USD] #,##0.00")],
    }
    return SourceSheet(document_id="doc", sheet_name="Revisión aritmética", sheet_index=0, role=SheetRole.PRINCIPAL,
                       state="visible", used_range="B7:J10", cell_count=6, merged_cells=["H7:M7"],
                       hidden_columns=["AC", "AD", "AE", "CH"], rows=[Row(row=r, cells=c) for r, c in cells.items()],
                       created_at=datetime.now(UTC))


def test_grid_has_one_compact_line_per_row():
    lines = build_grid(_sheet()).splitlines()

    assert lines[0] == "Hoja: Revisión aritmética | rango: B7:J10 | estado: visible"
    assert lines[1] == "Combinadas: H7:M7"
    assert lines[2] == "Ocultas: AC-AE, CH"
    assert lines[3] == "Formatos: G:#,##0 | I,J:[$USD] #,##0.00"
    assert lines[4] == "7|B:PARTICIPANTE|H:ACME ANDINA SAS"
    assert lines[5].startswith("10|C:Cable de fibra")


def test_grid_cleans_numbers_and_truncates_long_texts():
    row = build_grid(_sheet()).splitlines()[5]
    description = row.split("|")[1].removeprefix("C:")

    assert "|G:8000|" in row  # entero sin decimales
    assert "|I:12608509.2|" in row  # sin ruido de punto flotante
    assert len(description) == MAX_TEXT and description.endswith("…")


def test_message_includes_support_sheets_and_grid():
    support = SheetProfile(sheet_name="Detalle de ítems", sheet_index=1, state="visible", used_range="B2:D9",
                           non_empty_cells=20, numeric_nonzero_cells=6, header_text=["DESCRIPCIÓN", "CANTIDAD"],
                           signals=SheetSignals(), detected_group=None)

    message = build_map_message("libro.xlsx", _sheet(), [support])

    assert "Hoja a mapear: Revisión aritmética. Grupo detectado: ninguno." in message
    assert "- Detalle de ítems: DESCRIPCIÓN | CANTIDAD" in message
    assert "7|B:PARTICIPANTE|H:ACME ANDINA SAS" in message
