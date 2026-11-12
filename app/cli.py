"""Línea de comandos.

uv run python -m app.cli run [CARPETA | ARCHIVO] [--force] [--from map|quotes] [--classifier ai|rules] [--reset]
uv run python -m app.cli status
uv run python -m app.cli show ARCHIVO
uv run python -m app.cli export ARCHIVO
uv run python -m app.cli reset [--yes]
"""

import sys
from pathlib import Path
from typing import Annotated, Literal

import typer
from pymongo.errors import ServerSelectionTimeoutError
from rich.console import Console
from rich.table import Table

from app.classifiers import get_classifier
from app.config import settings
from app.domain.document import DocumentStatus
from app.domain.report import Report
from app.pipeline import Pipeline, ProcessingReport, StartFrom
from app.pipeline.reporting import export_report
from app.report.console import print_report
from app.storage.mongo import count_documents, drop_collections, ensure_indexes
from app.storage.repositories import DocumentRepository
from app.storage.results import ReportRepository

sys.stdout.reconfigure(encoding="utf-8")  # tildes y símbolos en la consola de Windows

app = typer.Typer(add_completion=False, help="Extracción de cotizaciones de informes de evaluación económica.")
console = Console()

EXCEL_PATTERN = "*.xls[xm]"
STATUS_COLORS = {
    DocumentStatus.QUOTATIONS_VALIDATED: "green",
    DocumentStatus.HUMAN_REVIEW_REQUIRED: "yellow",
    DocumentStatus.FAILED: "red",
}

SourceArg = Annotated[Path | None, typer.Argument(help="Carpeta o archivo Excel (por defecto INPUT_DIR del .env).")]
FileArg = Annotated[str, typer.Argument(help="Nombre del Excel o su inicio, p. ej. '40.'")]
ForceOpt = Annotated[bool, typer.Option("--force", help="Rehacer todo (con --from map: todas las hojas).")]
StartOpt = Annotated[Literal["map", "quotes"] | None, typer.Option(
    "--from", help="map: re-mapear las hojas pendientes (IA). quotes: recalcular cotizaciones y reportes (gratis).")]
ClassifierOpt = Annotated[Literal["ai", "rules"] | None, typer.Option(help="Por defecto CLASSIFIER del .env.")]
ResetOpt = Annotated[bool, typer.Option("--reset", help="Borrar la base antes de procesar (sin confirmación).")]
YesOpt = Annotated[bool, typer.Option("--yes", "-y", help="No pedir confirmación.")]


@app.command()
def run(source: SourceArg = None, force: ForceOpt = False, start: StartOpt = None,
        classifier: ClassifierOpt = None, reset_first: ResetOpt = False) -> None:
    """Procesa los Excel de la carpeta (por defecto INPUT_DIR), o un solo archivo, y deja su reporte."""
    files = _find_excel_files(source or settings.input_dir)
    if reset_first:
        reset(yes=True)
    _connect_to_mongo()
    pipeline = Pipeline(get_classifier(classifier or settings.classifier))
    console.print(f"Procesando {len(files)} archivo(s) con el clasificador [bold]{pipeline.classifier.name}[/bold]\n")
    for path in files:
        _print_processing(pipeline.process_file(path, force=force, start=StartFrom(start) if start else None))


@app.command()
def status() -> None:
    """Estado de cada documento: hojas mapeadas, cotizaciones, hallazgos y motivo de revisión."""
    _connect_to_mongo()
    table = Table(title="Documentos", show_lines=True)
    for column in ("Archivo", "Estado", "Hojas", "Cotizaciones", "Hallazgos", "Motivo de revisión"):
        table.add_column(column, overflow="fold")
    for document in DocumentRepository().list_summaries():
        table.add_row(*_status_row(document))
    console.print(table)


@app.command()
def show(file: FileArg) -> None:
    """Reporte de un documento en la consola."""
    print_report(console, _report(file))


@app.command()
def export(file: FileArg) -> None:
    """Vuelve a escribir el Excel del reporte de un documento (normalmente se genera solo al procesarlo)."""
    console.print(f"[green]Reporte:[/green] {export_report(_report(file))}")


@app.command()
def reset(yes: YesOpt = False) -> None:
    """Borra todo lo procesado para empezar de cero (los reportes en Excel no se borran)."""
    _connect_to_mongo()
    counts = count_documents()
    summary = ", ".join(f"{name}: {count}" for name, count in counts.items() if count)
    if not any(counts.values()):
        console.print(f"[dim]La base '{settings.mongo_db}' ya está vacía.[/dim]")
        return
    if not yes:
        typer.confirm(f"Se borrará la base '{settings.mongo_db}' ({summary}). ¿Continuar?", abort=True)
    drop_collections()
    console.print(f"[green]Base '{settings.mongo_db}' reiniciada[/green] (se borró {summary}).")


def _find_excel_files(source: Path) -> list[Path]:
    """El archivo indicado, o los Excel de la carpeta (sin los temporales '~$' que crea Excel al abrirlos)."""
    files = [source] if source.is_file() else sorted(
        path for path in source.glob(EXCEL_PATTERN) if not path.name.startswith("~$"))
    if not files:
        console.print(f"[yellow]No hay archivos .xlsx/.xlsm en {source}[/yellow]")
        raise typer.Exit(1)
    return files


def _report(file: str) -> Report:
    """Reporte guardado de un documento, buscado por nombre de archivo."""
    _connect_to_mongo()
    document = DocumentRepository().find_by_name(file)
    report = ReportRepository().get(document["_id"]) if document else None
    if report is None:
        console.print(f"[red]No hay reporte para '{file}'.[/red] ¿Ya se procesó? (make run)")
        raise typer.Exit(1)
    return report


def _connect_to_mongo() -> None:
    """Verifica la conexión (creando los índices) y sale con un mensaje claro si Mongo no responde."""
    try:
        ensure_indexes()
    except ServerSelectionTimeoutError:
        console.print(f"[red]Sin conexión a MongoDB en {settings.mongo_uri}. ¿Corriste 'docker compose up -d'?[/red]")
        raise typer.Exit(1) from None


def _print_processing(report: ProcessingReport) -> None:
    if report.skipped:
        console.print(f"  [dim]= {report.file_name}: ya procesado ({report.status}), se omite[/dim]")
        return
    console.print(f"  ● {report.file_name}  {_colored(report.status)}  ({report.seconds:.1f}s)")
    if report.principal:
        console.print(f"      principal: {', '.join(report.principal)}")
    console.print(f"      cotizaciones: {report.quotations}  hallazgos: {_findings(report.findings)}")
    for reason in report.review_reasons:
        console.print(f"      [yellow]⚠ {reason}[/yellow]")
    if report.report_path:
        console.print(f"      reporte: {report.report_path}")


def _status_row(document: dict) -> list[str]:
    summary = document.get("summary") or {}
    sheets = f"{summary.get('accepted_sheets', '-')}/{summary.get('principal_sheets', '-')}"
    reasons = "\n".join(document.get("review_reasons", [])) or document.get("error", "")
    return [document["file_name"], _colored(document["status"]), sheets, str(summary.get("quotations", "-")),
            _findings(summary.get("findings", {})), reasons]


def _findings(findings: dict[str, int]) -> str:
    return ", ".join(f"{rule}: {count}" for rule, count in findings.items()) or "-"


def _colored(status: str) -> str:
    color = STATUS_COLORS.get(status, "white")
    return f"[{color}]{status}[/{color}]"


if __name__ == "__main__":
    app()
