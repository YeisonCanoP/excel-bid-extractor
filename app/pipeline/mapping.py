"""Etapa de mapeo: el mapa de celdas de cada hoja principal, con la IA, verificado y guardado en cell_maps.

Por defecto solo se mapean las hojas que aún no tienen un mapa aceptado: las aceptadas conservan el suyo
(no se paga de nuevo). Con all_sheets=True se mapean todas.
"""

from datetime import UTC, datetime

from app.domain.classification import SheetRole
from app.domain.document import SheetProfile
from app.domain.sheet_map import SheetMap
from app.domain.source_sheet import SourceSheet
from app.mapping.mapper import AiMapper, MapOutcome
from app.pipeline.stages import StageLogger
from app.storage.repositories import AiRunRepository, SourceSheetRepository
from app.storage.results import CellMapRepository


class MappingStage:
    def __init__(self, logger: StageLogger, mapper: AiMapper | None = None) -> None:
        self.logger = logger
        self.mapper = mapper
        self.source_sheets = SourceSheetRepository()
        self.cell_maps = CellMapRepository()
        self.ai_runs = AiRunRepository()

    def run(self, document: dict, *, all_sheets: bool) -> list[SheetMap]:
        """Mapa de cada hoja principal del documento, en el orden del libro."""
        with self.logger.stage(document["_id"], "map"):
            kept = {m.sheet_name: m for m in self.cell_maps.for_document(document["_id"]) if m.accepted}
            principal = self.source_sheets.for_document(document["_id"], SheetRole.PRINCIPAL)
            support = _support_profiles(document)
            maps = [kept[sheet.sheet_name] if sheet.sheet_name in kept and not all_sheets
                    else self._map(document, sheet, support) for sheet in principal]
            return self._inherit_currency(maps)

    def _inherit_currency(self, maps: list[SheetMap]) -> list[SheetMap]:
        """Una hoja sin moneda toma la del resto del libro, si todas las demás coinciden (y queda advertido)."""
        currencies = {m.cell_map.currency for m in maps if m.cell_map and m.cell_map.currency}
        if len(currencies) != 1:
            return maps
        currency = currencies.pop()
        missing = [(m, cell_map) for m in maps if (cell_map := m.cell_map) is not None and not cell_map.currency]
        for sheet_map, cell_map in missing:
            cell_map.currency = currency
            cell_map.warnings.append(f"Moneda no identificada en la hoja; se usa la del libro: {currency}")
            self.cell_maps.save(sheet_map)
        return maps

    def _map(self, document: dict, sheet: SourceSheet, support: list[SheetProfile]) -> SheetMap:
        self.mapper = self.mapper or AiMapper()  # se crea al primer uso: sin hojas que mapear no hace falta la IA
        outcome = self.mapper.map_sheet(document["file_name"], sheet, support)
        sheet_map = _sheet_map(sheet, outcome, [self.ai_runs.add(sheet.document_id, run) for run in outcome.runs])
        self.cell_maps.save(sheet_map)
        return sheet_map


def _sheet_map(sheet: SourceSheet, outcome: MapOutcome, ai_run_ids: list[str]) -> SheetMap:
    return SheetMap(
        document_id=sheet.document_id, sheet_name=sheet.sheet_name, accepted=outcome.accepted,
        review_code=outcome.review_code, problems=outcome.problems, history=outcome.history,
        cell_map=outcome.cell_map, ai_run_ids=ai_run_ids, created_at=datetime.now(UTC),
    )


def _support_profiles(document: dict) -> list[SheetProfile]:
    """Fichas de las hojas de apoyo: el contexto que recibe la IA junto con la hoja a mapear."""
    sheets = (document.get("classification") or {}).get("sheets", [])
    names = {sheet["sheet_name"] for sheet in sheets if sheet["role"] == SheetRole.APOYO}
    return [SheetProfile.model_validate(p) for p in document.get("sheet_profiles", []) if p["sheet_name"] in names]
