"""Prueba de punta a punta con los libros de muestra (samples/), sin MongoDB ni IA.

Cada libro trae su resultado esperado en samples/expected/: hojas por rol, mapa de celdas, número de
cotizaciones y hallazgos sembrados a propósito. Se regeneran con: uv run python -m scripts.samples
"""

import json
from collections import Counter
from pathlib import Path

import pytest
from openpyxl.workbook.workbook import Workbook

from app.classifiers.rules import RulesClassifier
from app.domain.cell_map import CellMapResult
from app.domain.classification import ClassificationResult, SheetRole
from app.excel.extractor import extract_sheet
from app.excel.profiler import profile_workbook
from app.excel.reader import load_formulas, load_values
from app.quotes import SheetQuotes, Tolerances, process_sheet

SAMPLES = Path(__file__).parent.parent / "samples"
EXPECTED = sorted((SAMPLES / "expected").glob("*.json"))


@pytest.fixture(params=EXPECTED, ids=lambda path: path.stem)
def sample(request) -> dict:
    return json.loads(request.param.read_text(encoding="utf-8"))


def _classify(path: Path, values: Workbook) -> ClassificationResult | None:
    return RulesClassifier().classify(path.name, profile_workbook(values)).result


def test_rules_classifier_finds_principal_and_support_sheets(sample):
    path = SAMPLES / sample["file_name"]
    result = _classify(path, load_values(path))

    assert result is not None
    assert sorted(s.sheet_name for s in result.with_role(SheetRole.PRINCIPAL)) == sorted(sample["principal"])
    assert sorted(s.sheet_name for s in result.with_role(SheetRole.APOYO)) == sorted(sample["apoyo"])


def test_expected_map_extracts_quotations_without_integrity_failures(sample):
    path = SAMPLES / sample["file_name"]
    values, formulas = load_values(path), load_formulas(path)
    result = _classify(path, values)
    assert result is not None

    for classification in result.with_role(SheetRole.PRINCIPAL):
        name = classification.sheet_name
        sheet = extract_sheet(values[name], formulas[name], classification, document_id="doc", sheet_index=0)
        cell_map = CellMapResult.model_validate(sample["maps"][name])
        quotes, failures = process_sheet(sheet, cell_map, document_id="doc", group=None, tolerances=Tolerances())

        assert failures == [], [f.message for f in failures]
        assert len(quotes.quotations) == sample["quotations"][name]
        assert set(sample["findings"][name]) <= set(_failed_findings(quotes))


def _failed_findings(quotes: SheetQuotes) -> Counter:
    validations = [v for q in quotes.quotations for v in q.validations]
    validations += [v for t in quotes.totals for v in t.validations]
    return Counter(v.rule for v in validations if v.kind == "finding" and not v.passed)
