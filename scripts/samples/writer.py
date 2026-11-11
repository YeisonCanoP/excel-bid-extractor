"""Escritura con XlsxWriter: valores y fórmulas con su resultado ya calculado.

openpyxl escribe fórmulas sin resultado, y el pipeline lee los valores calculados (data_only).
XlsxWriter permite guardar la fórmula junto con su valor, como lo haría Excel al guardar.
"""

from datetime import datetime
from pathlib import Path

from xlsxwriter.utility import xl_cell_to_rowcol, xl_col_to_name
from xlsxwriter.workbook import Workbook

FIXED_DATE = datetime(2026, 1, 1)
"""Fecha de creación fija: así regenerar los libros da archivos idénticos (sin cambios falsos en git)."""

FORMATS = {
    "COP": '_-"$"* #,##0_-',
    "USD": "[$USD] #,##0.00",
    "percent": "0%",
}


class SheetWriter:
    """Una hoja. Recuerda el valor de cada celda escrita para calcular sumas y totales."""

    def __init__(self, workbook: Workbook, name: str, *, hidden: bool = False) -> None:
        self.sheet = workbook.add_worksheet(name)
        self.formats = {key: workbook.add_format({"num_format": fmt}) for key, fmt in FORMATS.items()}
        self.name = name
        self.values: dict[str, object] = {}
        if hidden:
            self.sheet.hide()

    def put(self, address: str, value: object, fmt: str | None = None) -> None:
        row, col = xl_cell_to_rowcol(address)
        self.sheet.write(row, col, value, self.formats.get(fmt or ""))
        self.values[address] = value

    def formula(self, address: str, formula: str, value: object, fmt: str | None = None) -> None:
        """Fórmula con su resultado (el que mostraría Excel)."""
        row, col = xl_cell_to_rowcol(address)
        self.sheet.write_formula(row, col, formula, self.formats.get(fmt or ""), value)
        self.values[address] = value

    def number(self, address: str | None) -> float:
        """Valor numérico ya escrito en la celda; 0 si no hay."""
        value = self.values.get(address or "")
        return float(value) if isinstance(value, int | float) else 0.0

    def hide_columns(self, first: str, last: str) -> None:
        self.sheet.set_column(f"{first}:{last}", None, None, {"hidden": True})


def new_workbook(path: Path) -> Workbook:
    workbook = Workbook(path)
    workbook.set_properties({"created": FIXED_DATE, "author": "excel-bid-extractor"})
    return workbook


def column(index: int) -> str:
    """0 -> 'A', 27 -> 'AB'."""
    return xl_col_to_name(index)


def column_index(letter: str) -> int:
    return xl_cell_to_rowcol(f"{letter}1")[1]


def shift(letter: str, offset: int) -> str:
    return column(column_index(letter) + offset)
