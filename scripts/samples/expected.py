"""Resultado esperado de cada libro de muestra: hojas por rol, mapas de celdas y cotizaciones."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.cell_map import (
    Budget,
    CellMapResult,
    Currency,
    IvaIncluded,
    SheetTotal,
    Table,
)


@dataclass
class SampleBook:
    file_name: str
    principal: list[str] = field(default_factory=list)
    apoyo: list[str] = field(default_factory=list)
    maps: dict[str, CellMapResult] = field(default_factory=dict)
    quotations: dict[str, int] = field(default_factory=dict)
    findings: dict[str, list[str]] = field(default_factory=dict)
    """Hallazgos sembrados a propósito, por hoja (reglas que deben aparecer)."""

    def add_principal(self, sheet: str, cell_map: CellMapResult, quotations: int, findings: list[str]) -> None:
        self.principal.append(sheet)
        self.maps[sheet] = cell_map
        self.quotations[sheet] = quotations
        self.findings[sheet] = findings

    def save(self, folder: Path) -> Path:
        path = folder / f"{Path(self.file_name).stem}.json"
        data = {"file_name": self.file_name, "principal": self.principal, "apoyo": self.apoyo,
                "quotations": self.quotations, "findings": self.findings,
                "maps": {sheet: m.model_dump(mode="json") for sheet, m in self.maps.items()}}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def cell_map(currency: str, tables: list[Table], *, budget: Budget | None = None,
             sheet_totals: list[SheetTotal] | None = None, iva_included: bool | None = None) -> CellMapResult:
    """Mapa esperado de una hoja principal, con el mismo esquema que devuelve la IA."""
    return CellMapResult(
        status="complete", currency=Currency.model_validate({"code": currency, "evidence": []}),
        iva_included=IvaIncluded(value=iva_included, evidence=[]), budget=budget, tables=tables,
        sheet_totals=sheet_totals or [], missing_fields=[], confidence=1.0, warnings=[], requires_human_review=False,
    )
