"""Línea de comandos del demo.

uv run python -m app.cli run [CARPETA | ARCHIVO] [--force] [--classifier ai|rules] [--reset]
uv run python -m app.cli status
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
from app.domain.classification import SheetRole
from app.domain.document import DocumentStatus
from app.pipeline import Pipeline, ProcessingReport
from app.storage.mongo import count_documents, drop_collections, ensure_indexes
from app.storage.repositories import DocumentRepository

sys.stdout.reconfigure(encoding="utf-8")  # tildes y símbolos en la consola de Windows

app = typer.Typer(add_completion=False, help="Demo: identificación de hojas de revisión aritmética.")
console = Console()

EXCEL_PATTERN = "*.xls[xm]"
STATUS_COLORS = {
    DocumentStatus.SHEETS_IDENTIFIED: "green",
    DocumentStatus.HUMAN_REVIEW_REQUIRED: "yellow",
    DocumentStatus.FAILED: "red",
}


SourceArg = Annotated[Path | None, typer.Argument(help="Carpeta o archivo Excel (por defecto INPUT_DIR del .env).")]
ForceOpt = Annotated[bool, typer.Option("--force", help="Reprocesar aunque ya estén procesados.")]
ClassifierOpt = Annotated[Literal["ai", "rules"] | None, typer.Option(help="Por defecto CLASSIFIER del .env.")]
ResetOpt = Annotated[bool, typer.Option("--reset", help="Borrar la base antes de procesar (sin confirmación).")]
YesOpt = Annotated[bool, typer.Option("--yes", "-y", help="No pedir confirmación.")]


@app.command()
def run(
    source: SourceArg = None,
    force: ForceOpt = False,
    classifier: ClassifierOpt = None,
    reset_first: ResetOpt = False,
) -> None:
    """Procesa todos los Excel de la carpeta (por defecto INPUT_DIR), o un solo archivo."""
    source = source or settings.input_dir
    files = _find_excel_files(source)
    if not files:
        console.print(f"[yellow]No hay archivos .xlsx/.xlsm en {source}[/yellow]")
        raise typer.Exit(1)

    if reset_first:
        reset(yes=True)
    _connect_to_mongo()
    pipeline = Pipeline(get_classifier(classifier or settings.classifier))
    console.print(f"Procesando {len(files)} archivo(s) con el clasificador [bold]{pipeline.classifier.name}[/bold]\n")

    for path in files:
        _print_report(pipeline.process_file(path, force=force))


@app.command()
def status() -> None:
    """Muestra el estado de los documentos procesados."""
    _connect_to_mongo()
    table = Table(title="Documentos", show_lines=True)
    for column in ("Archivo", "Estado", "Clasificó", "Principal", "Apoyo", "Desc.", "Motivo de revisión"):
        table.add_column(column, overflow="fold")
    for document in DocumentRepository().list_summaries():
        table.add_row(*_status_row(document))
    console.print(table)


@app.command()
def reset(yes: YesOpt = False) -> None:
    """Borra todo lo procesado (documents, source_sheets y ai_runs) para empezar de cero."""
    _connect_to_mongo()
    counts = count_documents()
    summary = ", ".join(f"{name}: {count}" for name, count in counts.items())

    if not any(counts.values()):
        console.print(f"[dim]La base '{settings.mongo_db}' ya está vacía.[/dim]")
        return
    if not yes:
        typer.confirm(f"Se borrará la base '{settings.mongo_db}' ({summary}). ¿Continuar?", abort=True)

    drop_collections()
    console.print(f"[green]Base '{settings.mongo_db}' reiniciada[/green] (se borró {summary}).")


def _find_excel_files(source: Path) -> list[Path]:
    """El archivo indicado, o los Excel de la carpeta (sin los temporales '~$' que crea Excel al abrirlos)."""
    if source.is_file():
        return [source]
    return sorted(path for path in source.glob(EXCEL_PATTERN) if not path.name.startswith("~$"))


def _connect_to_mongo() -> None:
    """Verifica la conexión (creando los índices) y sale con un mensaje claro si Mongo no responde."""
    try:
        ensure_indexes()
    except ServerSelectionTimeoutError:
        console.print(f"[red]Sin conexión a MongoDB en {settings.mongo_uri}. ¿Corriste 'docker compose up -d'?[/red]")
        raise typer.Exit(1) from None


def _print_report(report: ProcessingReport) -> None:
    if report.skipped:
        console.print(f"  [dim]= {report.file_name}: ya procesado ({report.status}), se omite[/dim]")
        return

    console.print(f"  ● {report.file_name}  {_colored(report.status)}  ({report.seconds:.1f}s)")
    if report.principal:
        console.print(f"      principal: {', '.join(report.principal)}")
    if report.apoyo:
        console.print(f"      apoyo:     {', '.join(report.apoyo)}")
    for reason in report.review_reasons:
        console.print(f"      [yellow]⚠ {reason}[/yellow]")


def _status_row(document: dict) -> list[str]:
    """Fila de la tabla de status: estado, clasificador, hojas por rol y motivo de revisión."""
    classification = document.get("classification") or {}
    sheets = classification.get("sheets", [])
    return [
        document["file_name"],
        _colored(document["status"]),
        classification.get("classified_by", "-"),
        _sheet_names(sheets, SheetRole.PRINCIPAL),
        _sheet_names(sheets, SheetRole.APOYO),
        str(classification.get("summary", {}).get(SheetRole.DESCARTADA, "-")),
        "\n".join(classification.get("review_reasons", [])) or document.get("error", ""),
    ]


def _sheet_names(sheets: list[dict], role: SheetRole) -> str:
    return "\n".join(sheet["sheet_name"] for sheet in sheets if sheet["role"] == role)


def _colored(status: str) -> str:
    color = STATUS_COLORS.get(status, "white")
    return f"[{color}]{status}[/{color}]"


if __name__ == "__main__":
    app()
