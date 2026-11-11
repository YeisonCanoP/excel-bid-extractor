"""Apertura del libro, hash del archivo y utilidades de texto."""

import hashlib
import re
import unicodedata
import warnings
from collections.abc import Iterator
from pathlib import Path

import openpyxl
from openpyxl.cell.cell import Cell
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

# openpyxl avisa sobre extensiones de Excel que no soporta (p. ej. validación de datos).
# No afectan los valores que leemos, así que se silencian.
warnings.filterwarnings("ignore", module="openpyxl")

_WHITESPACE = re.compile(r"\s+")
_CHUNK_SIZE = 1 << 20  # 1 MB


def file_sha256(path: Path) -> str:
    """Huella del archivo. Es el _id del documento: el mismo archivo nunca se registra dos veces."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def load_values(path: Path) -> Workbook:
    """Libro con los valores calculados, tal como se ven en Excel."""
    return openpyxl.load_workbook(path, data_only=True)


def load_formulas(path: Path) -> Workbook:
    """Libro con las fórmulas originales."""
    return openpyxl.load_workbook(path, data_only=False)


def iter_cells(sheet: Worksheet) -> Iterator[Cell]:
    """Celdas con datos, ordenadas por fila y columna.

    Se recorre `sheet._cells` (solo las celdas guardadas en el archivo) y no `iter_rows`,
    porque algunas hojas declaran rangos enormes casi vacíos (p. ej. A1:WVB45).
    """
    for _, cell in sorted(sheet._cells.items()):
        value = cell.value
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        yield cell


def clean_text(text: str) -> str:
    """Une espacios, tabs y saltos de línea en un solo espacio."""
    return _WHITESPACE.sub(" ", text).strip()


def normalize(text: str) -> str:
    """Mayúsculas y sin tildes, para buscar palabras clave."""
    without_accents = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return without_accents.upper()
