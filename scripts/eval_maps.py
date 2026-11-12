"""Evalúa el mapeo con IA sin MongoDB: llama a Claude por cada hoja principal y verifica su mapa.

    uv run python -m scripts.eval_maps            # libros de muestra: compara contra samples/expected
    uv run python -m scripts.eval_maps --real     # además, los Excel de INPUT_DIR (solo prueba aritmética)
    uv run python -m scripts.eval_maps --real --only=33   # solo los libros cuyo nombre empieza así

Cada hoja hace 1 o 2 llamadas a la IA (con costo).
"""

import json
import sys
from collections import Counter
from pathlib import Path

from pymongo.errors import PyMongoError

from app.classifiers.rules import RulesClassifier
from app.config import settings
from app.domain.cell_map import CellMapResult
from app.domain.classification import ClassificationResult, SheetRole
from app.domain.document import SheetProfile
from app.domain.source_sheet import SourceSheet
from app.excel.extractor import extract_sheet
from app.excel.profiler import profile_workbook
from app.excel.reader import file_sha256, load_formulas, load_values
from app.mapping.mapper import AiMapper, MapOutcome
from app.quotes import Tolerances, process_sheet
from app.storage.repositories import DocumentRepository

SAMPLES = Path("samples")
PRICE_IN, PRICE_CACHE, PRICE_OUT = 2.0, 0.2, 10.0
"""US$ por millón de tokens (Sonnet 5.5): entrada, lectura de caché y salida."""


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    mapper = AiMapper()
    files = sorted(SAMPLES.glob("*.xlsx"))
    if "--real" in sys.argv:
        files += sorted(settings.input_dir.glob("*.xls[xm]"))
    if only := [arg.removeprefix("--only=") for arg in sys.argv if arg.startswith("--only=")]:
        files = [path for path in files if path.name.startswith(only[0])]
    totals = [_evaluate_book(mapper, path) for path in files]
    cost = sum(c for book in totals for c in book)
    print(f"\nTotal: {sum(len(book) for book in totals)} hojas, costo aproximado US${cost:.3f}")


def _evaluate_book(mapper: AiMapper, path: Path) -> list[float]:
    """Mapea cada hoja principal del libro y devuelve el costo de cada una."""
    values, formulas = load_values(path), load_formulas(path)
    profiles = profile_workbook(values)
    result = _classification(path, profiles)
    if result is None:
        return []
    support_names = {s.sheet_name for s in result.with_role(SheetRole.APOYO)}
    support = [profile for profile in profiles if profile.sheet_name in support_names]
    expected = _expected_maps(path)
    costs = []
    for classification in result.with_role(SheetRole.PRINCIPAL):
        name = classification.sheet_name
        sheet = extract_sheet(values[name], formulas[name], classification, document_id=path.stem, sheet_index=0)
        outcome = mapper.map_sheet(path.name, sheet, support)
        costs.append(_report(path.name, sheet, outcome, expected.get(name)))
    return costs


def _report(file_name: str, sheet: SourceSheet, outcome: MapOutcome, expected: CellMapResult | None) -> float:
    usage = [run.usage for run in outcome.runs]
    tokens_in, cached = sum(u.input_tokens for u in usage), sum(u.cache_read_input_tokens for u in usage)
    tokens_out = sum(u.output_tokens for u in usage)
    verdict = "ACEPTADO" if outcome.accepted else f"REVISIÓN ({outcome.review_code})"
    print(f"\n{file_name[:40]} | {sheet.sheet_name} | {verdict} | intentos {len(outcome.runs)} | "
          f"{tokens_in} in + {cached} caché / {tokens_out} out | {_seconds(outcome):.0f}s")
    for attempt, problems in enumerate(outcome.history, start=1):
        for problem in problems:
            print(f"   intento {attempt}: {problem}")
    if outcome.accepted and outcome.cell_map:
        _print_quotes(sheet, outcome.cell_map)
    if expected and outcome.cell_map:
        _print_score(outcome.cell_map, expected)
    return (tokens_in * PRICE_IN + cached * PRICE_CACHE + tokens_out * PRICE_OUT) / 1e6


def _seconds(outcome: MapOutcome) -> float:
    return sum(run.duration_ms for run in outcome.runs) / 1000


def _print_quotes(sheet: SourceSheet, cell_map: CellMapResult) -> None:
    """Cotizaciones que salen con el mapa de la IA y hallazgos de la oferta, por regla."""
    result, _ = process_sheet(sheet, cell_map, document_id=sheet.document_id, group=sheet.group,
                              tolerances=Tolerances())
    findings = Counter(v.rule for item in [*result.quotations, *result.totals] for v in item.validations
                       if v.kind == "finding" and not v.passed)
    statuses = Counter(q.status.value for q in result.quotations)
    print(f"   cotizaciones: {len(result.quotations)} {dict(statuses)} | hallazgos: {dict(findings)}")


def _print_score(actual: CellMapResult, expected: CellMapResult) -> None:
    mine, theirs = flatten(actual), flatten(expected)
    keys = sorted(set(mine) | set(theirs))
    diffs = [key for key in keys if mine.get(key) != theirs.get(key)]
    print(f"   coincide con el mapa esperado: {len(keys) - len(diffs)}/{len(keys)} campos")
    for key in diffs[:10]:
        print(f"   difiere {key}: IA={mine.get(key)} esperado={theirs.get(key)}")


def flatten(cell_map: CellMapResult) -> dict[str, str]:
    """Mapa como pares campo -> valor, para comparar dos mapas campo por campo."""
    fields: dict[str, object] = {"currency": cell_map.currency}
    for table in cell_map.tables:
        prefix = table.table_id
        fields |= {f"{prefix}.rows": f"{table.item_rows.first}-{table.item_rows.last}", f"{prefix}.group": table.group}
        fields |= {f"{prefix}.items.{k}": v for k, v in table.item_columns.model_dump().items()}
        for block in table.providers:
            fields |= {f"{prefix}.{block.name_address}.{k}": v for k, v in block.columns.model_dump().items()}
            fields |= {f"{prefix}.{block.name_address}.{r.kind}": f"{r.offered}/{r.corrected}" for r in block.totals}
    fields |= {f"hoja.{b.name_address}.{r.kind}": f"{r.offered}/{r.corrected}" for b in cell_map.sheet_totals
               for r in b.totals}
    return {key: str(value) for key, value in fields.items() if value not in (None, [], "")}


def _classification(path: Path, profiles: list[SheetProfile]) -> ClassificationResult | None:
    """La clasificación de la IA guardada en MongoDB si el libro ya se procesó; si no, la de reglas."""
    document = _stored_document(path)
    if document and document.get("classification"):
        return ClassificationResult.model_validate(document["classification"] | {"warnings": [],
                                                                                 "requires_human_review": False})
    return RulesClassifier().classify(path.name, profiles).result


def _stored_document(path: Path) -> dict | None:
    """Documento ya procesado en MongoDB; None si no existe o si MongoDB no responde."""
    try:
        return DocumentRepository().collection.find_one({"_id": file_sha256(path)}, {"classification": 1})
    except PyMongoError:
        return None


def _expected_maps(path: Path) -> dict[str, CellMapResult]:
    file = SAMPLES / "expected" / f"{path.stem}.json"
    if not file.exists():
        return {}
    maps = json.loads(file.read_text(encoding="utf-8"))["maps"]
    return {sheet: CellMapResult.model_validate(data) for sheet, data in maps.items()}


if __name__ == "__main__":
    main()
