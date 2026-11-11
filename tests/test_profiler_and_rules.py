from app.classifiers.rules import RulesClassifier, suggest_role
from app.domain.classification import SheetRole
from app.excel.profiler import detect_group, profile_workbook


def test_profile_counts_signals_and_numbers(workbook):
    profile = {p.sheet_name: p for p in profile_workbook(workbook)}["REV ARIT GRUPO II"]

    assert profile.signals.correccion_aritmetica == 1
    assert profile.signals.valor_unitario == 1
    assert profile.numeric_nonzero_cells == 10
    assert profile.detected_group == "2"
    assert "PROVEEDOR UNO SAS" in profile.header_text  # texto limpio, sin \t\n


def test_suggested_roles(workbook):
    roles = {p.sheet_name: suggest_role(p) for p in profile_workbook(workbook)}

    assert roles == {
        "REV ARIT GRUPO II": SheetRole.PRINCIPAL,
        "Revisión aritmética": SheetRole.DESCARTADA,  # plantilla: tiene la etiqueta, pero solo ceros
        "OCASIONALES": SheetRole.APOYO,
        "Datos": SheetRole.DESCARTADA,
    }


def test_rules_classifier_keeps_group_only_for_selected_sheets(workbook):
    result = RulesClassifier().classify("libro.xlsx", profile_workbook(workbook)).result
    groups = {s.sheet_name: s.group for s in result.sheets}

    assert groups["REV ARIT GRUPO II"] == "2"
    assert groups["OCASIONALES"] == "4"
    assert groups["Datos"] is None
    assert result.requires_human_review is False


def test_detect_group_variants():
    assert detect_group("G1RevAritmetica", []) == "1"
    assert detect_group("REV ARIT GRUPO IV", []) == "4"
    assert detect_group("Hoja", ["REVISIÓN ARITMÉTICA - Grupo No. 3"]) == "3"
    assert detect_group("Revisión aritmética", ["EVALUACIÓN ECONÓMICA"]) is None
