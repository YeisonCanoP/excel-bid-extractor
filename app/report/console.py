"""Reporte en la consola (comando show): resumen, ofertas por proveedor, hallazgos y revisión.

El detalle ítem por ítem está en el Excel; aquí van los totales para leerlo de un vistazo.
"""

from collections import Counter

from rich.console import Console
from rich.table import Table

from app.domain.report import Report, ReportGroup

PROVIDER = "Proveedor"
MAX_FINDINGS = 15
"""Hallazgos que se listan; el resto se cuenta en el resumen."""


def print_report(console: Console, report: Report) -> None:
    console.print(f"[bold]{report.file_name}[/bold]  {report.status}  "
                  f"({report.processed_at:%Y-%m-%d %H:%M})")
    console.print(_summary(report))
    for group in report.groups:
        console.print(_offers(group))
    if report.findings:
        console.print(_findings(report))
    if report.review:
        console.print(_review(report))


def _summary(report: Report) -> Table:
    s = report.summary
    table = Table(title="Resumen", show_header=False)
    for label, value in (("Hojas principales", f"{s.accepted_sheets} aceptadas de {s.principal_sheets}"),
                         ("Proveedores", s.providers), ("Productos", s.products), ("Cotizaciones", s.quotations),
                         ("Hallazgos", ", ".join(f"{r}: {n}" for r, n in s.findings.items()) or "ninguno")):
        table.add_row(label, str(value))
    return table


def _offers(group: ReportGroup) -> Table:
    title = f"{group.sheet}" + (f" — grupo {group.group}" if group.group else "") + f" ({group.currency or '?'})"
    table = Table(title=title)
    for column in (PROVIDER, "Ítems", "Subtotal", "IVA", "Total"):
        table.add_column(column, justify="left" if column == PROVIDER else "right")
    for provider in group.providers:
        quoted = Counter(item.status for item in provider.items)["cotizado"]
        table.add_row(provider.name, f"{quoted}/{len(provider.items)}", *(_money(provider.totals.get(kind))
                                                                         for kind in ("subtotal", "iva", "total")))
    return table


def _findings(report: Report) -> Table:
    table = Table(title=f"Hallazgos ({len(report.findings)})")
    for column in ("Regla", "Hoja", PROVIDER, "Hallazgo"):
        table.add_column(column, overflow="fold")
    for finding in report.findings[:MAX_FINDINGS]:
        table.add_row(finding.rule, finding.sheet, finding.provider, finding.message)
    return table


def _review(report: Report) -> Table:
    table = Table(title="Requiere revisión humana")
    for column in ("Hoja", "Código", "Motivo"):
        table.add_column(column, overflow="fold")
    for item in report.review:
        table.add_row(item.sheet, item.code, "\n".join(item.problems))
    return table


def _money(value: float | None) -> str:
    return f"{value:,.2f}" if value is not None else "-"
