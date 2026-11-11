"""Hojas que acompañan a la revisión aritmética: datos del proceso, participantes, jurídica, puntajes,
plantillas vacías y hojas de apoyo. Sirven para que la clasificación tenga que distinguir."""

from dataclasses import dataclass

from xlsxwriter.workbook import Workbook

from scripts.samples.writer import SheetWriter, shift


@dataclass(frozen=True)
class Process:
    number: str
    title: str
    budget: float
    currency: str


def write_title(w: SheetWriter, process: Process, subtitle: str) -> None:
    w.put("B2", process.number)
    w.put("B3", process.title.upper())
    w.put("B4", subtitle)


def write_fillers(workbook: Workbook, process: Process, providers: list[str]) -> None:
    """Datos del proceso, participantes, evaluación jurídica y puntaje económico."""
    general = SheetWriter(workbook, "Datos")
    rows = [("NÚMERO DEL PROCESO", process.number), ("OBJETO", process.title), ("MODALIDAD DE SELECCIÓN", "ABIERTA"),
            ("PRESUPUESTO OFICIAL (INCLUIDO IVA)", process.budget), ("PLAZO DE EJECUCIÓN", "12 MESES")]
    for row, (label, value) in enumerate(rows, start=2):
        general.put(f"B{row}", label)
        general.put(f"C{row}", value)
    contacts = [(name, f"900.000.{i:03d}-{i % 10}", f"contacto{i}@ejemplo.com") for i, name in enumerate(providers)]
    _provider_table(workbook, "Participantes", ("PROVEEDOR", "NIT", "CORREO"), contacts)
    _provider_table(workbook, "Evaluación jurídica", ("PROVEEDOR", "RESULTADO"), [(n, "CUMPLE") for n in providers])
    _provider_table(workbook, "Puntaje económico", ("PROVEEDOR", "PUNTAJE TOTAL"),
                    [(name, 1000 - 25 * i) for i, name in enumerate(providers)])


def write_empty_template(workbook: Workbook, name: str, process: Process) -> None:
    """Plantilla oculta con la estructura de una revisión aritmética, pero sin valores."""
    w = SheetWriter(workbook, name, hidden=True)
    write_title(w, process, "EVALUACIÓN ECONÓMICA - REVISIÓN ARITMÉTICA")
    for column, label in zip("BCDEFGH", ("ÍTEM", "DESCRIPCIÓN", "CANTIDAD", "VALOR UNITARIO", "VALOR TOTAL",
                                          "CORRECCIÓN ARITMÉTICA", "VERIFICACIÓN"), strict=True):
        w.put(f"{column}8", label)
    for row in range(9, 13):
        for column in "DEFG":
            w.put(f"{column}{row}", 0)
        w.put(f"H{row}", "OK")


def write_support_sheet(workbook: Workbook, name: str, title: str, rows: list[tuple[str, str, float]]) -> None:
    """Hoja de apoyo: menciona la revisión aritmética y trae cantidades, pero no tiene corrección."""
    w = SheetWriter(workbook, name)
    w.put("B2", title)
    for column, label in zip("BCD", ("DESCRIPCIÓN", "ESPECIFICACIÓN", "CANTIDAD"), strict=True):
        w.put(f"{column}4", label)
    for row, values in enumerate(rows, start=5):
        for column, value in zip("BCD", values, strict=True):
            w.put(f"{column}{row}", value)


def write_tariff_sheet(workbook: Workbook, name: str, title: str, services: list[str],
                       tariffs: dict[str, list[float]]) -> None:
    """Hoja de apoyo con tarifas de servicios ocasionales por proveedor (sin corrección aritmética)."""
    w = SheetWriter(workbook, name)
    w.put("B2", title)
    w.put("B4", "PARTICIPANTE")
    for column, label in (("B", "DESCRIPCIÓN DEL SERVICIO"), ("C", "CANTIDAD")):
        w.put(f"{column}5", label)
    for index, (provider, prices) in enumerate(tariffs.items()):
        column = shift("D", index)
        w.put(f"{column}4", provider)
        w.put(f"{column}5", "VALOR TARIFA (IVA INCLUIDO)")
        for row, price in enumerate(prices, start=6):
            w.put(f"{column}{row}", price, "COP")
    for row, service in enumerate(services, start=6):
        w.put(f"B{row}", service)
        w.put(f"C{row}", 1)


def _provider_table(workbook: Workbook, name: str, headers: tuple[str, ...], rows: list[tuple]) -> None:
    w = SheetWriter(workbook, name)
    for column, label in zip("BCD", headers, strict=False):
        w.put(f"{column}2", label)
    for row, values in enumerate(rows, start=3):
        for column, value in zip("BCD", values, strict=False):
            w.put(f"{column}{row}", value)
