"""Mensajes para la IA: la hoja a mapear (cuadrícula) con el contexto de apoyo, y el reintento con los problemas."""

from app.domain.cell_map import CellMapResult
from app.domain.document import SheetProfile
from app.domain.source_sheet import SourceSheet
from app.mapping.grid import build_grid

SUPPORT_TEXTS = 15
"""Textos de encabezado por hoja de apoyo: suficientes para dar contexto sin gastar tokens."""


def build_map_message(file_name: str, sheet: SourceSheet, support: list[SheetProfile]) -> str:
    return "\n\n".join([
        f"Libro: {file_name}",
        f"Hoja a mapear: {sheet.sheet_name}. Grupo detectado: {sheet.group or 'ninguno'}.",
        f"Hojas de apoyo del libro (solo contexto, no se mapean):\n{_support(support)}",
        f"Cuadrícula de la hoja:\n{build_grid(sheet)}",
    ])


def _support(profiles: list[SheetProfile]) -> str:
    lines = [f"- {p.sheet_name}: {' | '.join(p.header_text[:SUPPORT_TEXTS])}" for p in profiles]
    return "\n".join(lines) or "(ninguna)"


def retry_message(message: str, previous: CellMapResult | None, problems: list[str]) -> str:
    """El mismo mensaje más el mapa anterior y lo que falló al verificarlo; sin intento previo, el mensaje tal cual."""
    if previous is None or not problems:
        return message
    issues = "\n".join(f"- {problem}" for problem in problems)
    return (f"{message}\n\n## Corrección\nTu mapa anterior no pasó la verificación contra las cuentas del "
            f"evaluador:\n{issues}\n\nMapa anterior:\n{previous.model_dump_json()}\n\n"
            "Revisa la cuadrícula y devuelve el mapa completo corregido.")
