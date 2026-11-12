"""Escribe el reporte en Excel: Resumen, Cotizaciones, Totales, Hallazgos y Revisión.

Se genera a partir del reporte guardado en MongoDB, así que siempre coincide con la base.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.report import Report

MONEY = "#,##0.00"
HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
MAX_WIDTH = 60

SHEET, GROUP, PROVIDER, VALUE = "Hoja", "Grupo", "Proveedor", "Valor"
QUOTATION_HEADERS = (SHEET, GROUP, PROVIDER, "Ítem", "Producto", "Unidad", "Cantidad", "Precio", "Total",
                     "IVA %", "Administración %", "Utilidad %", "IVA s/utilidad %", "Estado", "Origen")
MONEY_COLUMNS = {"Cantidad", "Precio", "Total", VALUE}
TOTAL_HEADERS = (SHEET, GROUP, PROVIDER, "Concepto", VALUE)
FINDING_HEADERS = ("Regla", SHEET, PROVIDER, "Hallazgo", "Celdas")
REVIEW_HEADERS = (SHEET, "Código", "Motivo")


def report_path(folder: Path, file_name: str) -> Path:
    """'40. Informe.xlsx' -> folder/'40. Informe - reporte.xlsx'. Se sobrescribe en cada reproceso."""
    return folder / f"{Path(file_name).stem} - reporte.xlsx"


def write_report(report: Report, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    _summary_sheet(workbook.active, report)
    _table(workbook.create_sheet("Cotizaciones"), QUOTATION_HEADERS, _quotation_rows(report))
    _table(workbook.create_sheet("Totales"), TOTAL_HEADERS, _total_rows(report))
    _table(workbook.create_sheet("Hallazgos"), FINDING_HEADERS, _finding_rows(report))
    _table(workbook.create_sheet("Revisión"), REVIEW_HEADERS, _review_rows(report))
    workbook.save(path)
    return path


def _summary_sheet(sheet: Worksheet, report: Report) -> None:
    sheet.title = "Resumen"
    s = report.summary
    rows = [("Documento", report.file_name), ("Estado", report.status),
            ("Procesado", report.processed_at.strftime("%Y-%m-%d %H:%M")),
            ("Hojas principales", s.principal_sheets), ("Hojas aceptadas", s.accepted_sheets),
            ("Hojas en revisión", s.review_sheets), ("Proveedores", s.providers), ("Productos", s.products),
            ("Cotizaciones", s.quotations), *((f"Hallazgos {rule}", count) for rule, count in s.findings.items())]
    _table(sheet, ("Concepto", VALUE), rows)


def _quotation_rows(report: Report) -> Iterable[Sequence[object]]:
    for group in report.groups:
        for provider in group.providers:
            for i in provider.items:
                yield (group.sheet, group.group, provider.name, i.item_no, i.product, i.unit, i.quantity, i.price,
                       i.total, i.iva_pct, i.administration_pct, i.utility_pct, i.iva_on_utility_pct, i.status,
                       i.source)


def _total_rows(report: Report) -> Iterable[Sequence[object]]:
    for group in report.groups:
        for provider in group.providers:
            for concept, value in provider.totals.items():
                yield group.sheet, group.group, provider.name, concept, value


def _finding_rows(report: Report) -> Iterable[Sequence[object]]:
    return ((f.rule, f.sheet, f.provider, f.message, ", ".join(f.cells)) for f in report.findings)


def _review_rows(report: Report) -> Iterable[Sequence[object]]:
    return ((r.sheet, r.code, problem) for r in report.review for problem in r.problems or [""])


def _table(sheet: Worksheet, headers: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    """Encabezado con estilo, filas, filtros, primera fila fija y anchos de columna."""
    sheet.append(list(headers))
    for cell in sheet[1]:
        cell.font, cell.fill = HEADER_FONT, HEADER_FILL
    for row in rows:
        sheet.append(list(row))
    sheet.auto_filter.ref = sheet.dimensions
    sheet.freeze_panes = "A2"
    _format_columns(sheet, headers)


def _format_columns(sheet: Worksheet, headers: Sequence[str]) -> None:
    for index, header in enumerate(headers, start=1):
        letter = get_column_letter(index)
        values = [len(str(cell.value)) for cell in sheet[letter] if cell.value is not None]
        sheet.column_dimensions[letter].width = min(max(values, default=10) + 2, MAX_WIDTH)
        if header in MONEY_COLUMNS:
            for cell in sheet[letter][1:]:
                cell.number_format = MONEY
