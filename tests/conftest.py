"""Libros de Excel pequeños, creados en memoria, que imitan los casos reales de los informes."""

import openpyxl
import pytest
from openpyxl.workbook.workbook import Workbook


def _arithmetic_table(sheet, title: str, values: list[list]) -> None:
    sheet["B2"] = "PROC-0001"
    sheet["B4"] = title
    sheet["B6"], sheet["F6"] = "PARTICIPANTE", "\t\nPROVEEDOR UNO SAS"
    sheet["B7"], sheet["E7"], sheet["F7"], sheet["G7"], sheet["H7"] = (
        "ITEM", "CANTIDAD", "VALOR UNITARIO", "VALOR TOTAL", "CORRECCIÓN ARITMÉTICA",
    )
    for offset, row in enumerate(values):
        for col, value in zip("BEFGH", row, strict=True):
            sheet[f"{col}{8 + offset}"] = value


@pytest.fixture
def workbook() -> Workbook:
    """Libro con los cuatro casos típicos: principal, plantilla vacía, apoyo y descartada."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    _arithmetic_table(wb.create_sheet("REV ARIT GRUPO II"), "REVISIÓN ARITMÉTICA - GRUPO II", [
        [1, 10, 1500, 15000, 15000],
        [2, 4, 2500, 10000, 10000],
    ])
    template = wb.create_sheet("Revisión aritmética")
    template.sheet_state = "hidden"
    _arithmetic_table(template, "REVISIÓN ARITMÉTICA", [[1, 0, 0, 0, 0]])
    _fill(wb.create_sheet("OCASIONALES"), SUPPORT_CELLS)
    _fill(wb.create_sheet("Datos"), GENERAL_CELLS)
    return wb


SUPPORT_CELLS = {"A4": "REVISIÓN ARITMÉTICA - GRUPO 4", "A10": "N.", "D10": "Cantidad", "E10": "Valor Tarifa",
                 "A11": 1, "D11": 3, "E11": 98000}
GENERAL_CELLS = {"A1": "NÚMERO DEL PROCESO", "B1": "PROC-0001", "A2": "PRESUPUESTO OFICIAL", "B2": 500_000_000}


def _fill(sheet, cells: dict) -> None:
    for address, value in cells.items():
        sheet[address] = value
