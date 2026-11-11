import openpyxl

from app.domain.classification import SheetClassification, SheetRole
from app.excel.extractor import extract_sheet


def _sheet_pair():
    """openpyxl no calcula fórmulas: se simulan los dos libros (valores y fórmulas) de la misma hoja."""
    values = openpyxl.Workbook().active
    formulas = openpyxl.Workbook().active
    values.title = formulas.title = "Revisión aritmética"
    values["A1"] = formulas["A1"] = "\t\nPROVEEDOR UNO SAS"
    values["B2"] = formulas["B2"] = 12608509.200000001
    values["C2"], formulas["C2"] = 25217018.400000002, "=B2*2"
    values.merge_cells("A1:C1")
    return values, formulas


def test_extract_keeps_values_formulas_and_cleans_text():
    classification = SheetClassification(
        sheet_name="Revisión aritmética", role=SheetRole.PRINCIPAL, group="1", confidence=0.9, reason="test"
    )
    sheet = extract_sheet(*_sheet_pair(), classification, document_id="doc-1", sheet_index=0)
    cells = {cell.address: cell for row in sheet.rows for cell in row.cells}

    assert cells["A1"].value == "PROVEEDOR UNO SAS"
    assert cells["A1"].raw == "\t\nPROVEEDOR UNO SAS"
    assert cells["B2"].value == 12608509.200000001  # los números no se redondean
    assert cells["C2"].formula == "=B2*2"
    assert sheet.merged_cells == ["A1:C1"]
    assert sheet.role == SheetRole.PRINCIPAL and sheet.group == "1"
    assert sheet.cell_count == 3
