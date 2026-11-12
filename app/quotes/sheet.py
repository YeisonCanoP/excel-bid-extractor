"""Lectura por dirección del JSON limpio de una hoja (SourceSheet), con la celda de origen de cada valor."""

from app.domain.quotation import SourcedNumber, SourcedText
from app.domain.source_sheet import Cell, SourceSheet
from app.excel.reader import clean_text
from app.quotes.normalize import number_label, to_number, without_noise


class SheetCells:
    def __init__(self, sheet: SourceSheet) -> None:
        self.name = sheet.sheet_name
        self._cells: dict[str, Cell] = {cell.address: cell for row in sheet.rows for cell in row.cells}

    def get(self, address: str | None) -> Cell | None:
        return self._cells.get(address) if address else None

    def at(self, column: str | None, row: int) -> Cell | None:
        return self.get(f"{column}{row}") if column else None

    def number(self, address: str | None) -> SourcedNumber | None:
        """Número sin ruido de punto flotante; `raw` guarda el original si cambió."""
        cell = self.get(address)
        number = to_number(cell)
        if cell is None or number is None:
            return None
        value = without_noise(number)
        return SourcedNumber(value=value, source=[cell.address], raw=None if value == cell.value else cell.value)

    def number_at(self, column: str | None, row: int) -> SourcedNumber | None:
        return self.number(f"{column}{row}") if column else None

    def text(self, address: str | None) -> SourcedText | None:
        """Texto limpio. None si la celda está vacía."""
        cell = self.get(address)
        if cell is None or cell.value is None or not clean_text(str(cell.value)):
            return None
        return SourcedText(value=clean_text(str(cell.value)), source=[cell.address])

    def text_at(self, column: str | None, row: int) -> SourcedText | None:
        return self.text(f"{column}{row}") if column else None

    def label_at(self, column: str | None, row: int) -> SourcedText | None:
        """Texto de la celda; si es un número (p. ej. el número de ítem), sin ruido de punto flotante."""
        number = self.number_at(column, row)
        cell = self.at(column, row)
        if number is not None and cell is not None and cell.type == "number":
            return SourcedText(value=number_label(number.value), source=number.source)
        return self.text_at(column, row)
