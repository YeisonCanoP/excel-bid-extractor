import json

from app.classifiers.ai import build_user_message
from app.excel.profiler import profile_workbook

FULL_PROFILE_FIELDS = {
    "sheet_name", "state", "used_range", "non_empty_cells", "numeric_nonzero_cells",
    "header_text", "signals", "detected_group", "suggested_role",
}


def _sheets_sent(message: str) -> dict[str, dict]:
    payload = message.split("(JSON):\n", 1)[1]
    return {sheet["sheet_name"]: sheet for sheet in json.loads(payload)}


def test_every_sheet_gets_full_profile(workbook):
    sheets = _sheets_sent(build_user_message("libro.xlsx", profile_workbook(workbook)))

    assert all(set(sheet) == FULL_PROFILE_FIELDS for sheet in sheets.values())
    assert sheets["REV ARIT GRUPO II"]["suggested_role"] == "principal"
    assert sheets["Revisión aritmética"]["suggested_role"] == "descartada"  # plantilla vacía


def test_message_is_compact(workbook):
    message = build_user_message("libro.xlsx", profile_workbook(workbook))

    assert '": ' not in message      # sin espacios en el JSON
    assert '"iva":0' not in message  # señales en cero no se envían
