"""Ficha de cada hoja: un resumen objetivo de su contenido, sin decidir su rol.

La ficha es lo que recibe el clasificador (IA o reglas). Es pequeña a propósito:
unos 300 tokens por hoja, para que un libro completo quepa en una sola llamada.
"""

import re
from dataclasses import dataclass, field

from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.document import SheetProfile, SheetSignals
from app.excel.reader import clean_text, iter_cells, normalize

MAX_HEADER_TEXTS = 40
MAX_TEXT_LENGTH = 80
GROUP_SEARCH_TEXTS = 6  # el grupo se busca en el nombre y en los primeros textos (título)

# Palabras clave (sobre texto en mayúsculas y sin tildes). Las claves son los campos de SheetSignals.
SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "correccion_aritmetica": re.compile(r"CORRECCION\s*ARITM"),
    "aritmetica": re.compile(r"ARITM"),
    "valor_unitario": re.compile(r"VALOR\s*UNITARIO|PRECIO\s*UNITARIO|VR\.?\s*UNIT"),
    "cantidad": re.compile(r"\bCANT(IDAD|\.)?\b|\bQTY\b"),
    "valor_total": re.compile(r"VALOR\s*(TOTAL|PARCIAL)|PRECIO\s*TOTAL"),
    "iva": re.compile(r"\bIVA\b"),
    "puntaje": re.compile(r"PUNTAJE"),
    "oferta_economica": re.compile(r"OFERTA\s*ECON"),
}

GROUP_PATTERNS = [
    re.compile(r"^G(\d+)(?!\d)"),                          # G1RevAritmetica
    re.compile(r"\bGRUPO\s*(?:NO\.?\s*)?(\d+|[IVX]+)\b"),  # GRUPO I, GRUPO 2, Grupo No. 3
]
ROMAN_NUMERALS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}


def profile_workbook(workbook: Workbook) -> list[SheetProfile]:
    return [profile_sheet(sheet, index) for index, sheet in enumerate(workbook.worksheets)]


@dataclass
class _SheetStats:
    """Conteos que se acumulan al recorrer las celdas de una hoja."""

    signals: dict[str, int] = field(default_factory=lambda: dict.fromkeys(SIGNAL_PATTERNS, 0))
    header_text: list[str] = field(default_factory=list)
    non_empty_cells: int = 0
    numeric_nonzero_cells: int = 0

    def add(self, value: object) -> None:
        self.non_empty_cells += 1
        if isinstance(value, str):
            _count_signals(normalize(value), self.signals)
            _add_header_text(clean_text(value), self.header_text)
        elif _is_number(value) and value != 0:
            self.numeric_nonzero_cells += 1


def profile_sheet(sheet: Worksheet, index: int) -> SheetProfile:
    stats = _SheetStats()
    for cell in iter_cells(sheet):
        stats.add(cell.value)
    return SheetProfile(
        sheet_name=sheet.title,
        sheet_index=index,
        state=sheet.sheet_state,
        used_range=sheet.dimensions,
        non_empty_cells=stats.non_empty_cells,
        numeric_nonzero_cells=stats.numeric_nonzero_cells,
        header_text=stats.header_text,
        signals=SheetSignals(**stats.signals),
        detected_group=detect_group(sheet.title, stats.header_text),
    )


def detect_group(sheet_name: str, header_text: list[str]) -> str | None:
    """Número del grupo de adjudicación ('1', '4'…) si aparece en el nombre o el título."""
    for text in [sheet_name, *header_text[:GROUP_SEARCH_TEXTS]]:
        normalized = normalize(text).strip()
        for pattern in GROUP_PATTERNS:
            if match := pattern.search(normalized):
                group = match.group(1)
                return str(ROMAN_NUMERALS.get(group, group))
    return None


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _count_signals(normalized_text: str, counts: dict[str, int]) -> None:
    for signal, pattern in SIGNAL_PATTERNS.items():
        if pattern.search(normalized_text):
            counts[signal] += 1


def _add_header_text(text: str, header_text: list[str]) -> None:
    text = text[:MAX_TEXT_LENGTH]
    if len(header_text) < MAX_HEADER_TEXTS and text not in header_text:
        header_text.append(text)
