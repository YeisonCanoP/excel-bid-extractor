"""Los cuatro libros de muestra. Datos inventados con semilla fija: siempre se generan iguales.

Cada libro cubre un patrón distinto de revisión aritmética y siembra errores a propósito
(redondeos, un total mal multiplicado, un IVA mal escrito, un precio en 0) para que las reglas los detecten.
"""

import random
from pathlib import Path

from xlsxwriter.workbook import Workbook

from app.domain.cell_map import Budget, SheetTotal
from scripts.samples.expected import SampleBook, cell_map
from scripts.samples.model import NO_OFFER, Item, Layout, Offer, Provider
from scripts.samples.sheets import (
    Process,
    write_empty_template,
    write_fillers,
    write_support_sheet,
    write_tariff_sheet,
    write_title,
)
from scripts.samples.table import TableResult, write_table
from scripts.samples.totals import sheet_total
from scripts.samples.writer import SheetWriter, new_workbook

ARITHMETIC_REVIEW = "EVALUACIÓN ECONÓMICA - REVISIÓN ARITMÉTICA"
GOODS_ROLES = ("brand", "unit_price", "total_price", "unit_price_corrected", "total_price_corrected", "check")
AIU_ROLES = ("unit_price", "subtotal", "aiu", "iva", "total_price", "unit_price_corrected", "total_price_corrected",
             "check")
PLAIN_ROLES = ("unit_price", "total_price", "unit_price_corrected", "total_price_corrected", "check")


def _prices(seed: int, bases: list[float], decimals: int) -> list[float]:
    """Precios alrededor de cada base, con decimales para que el redondeo del evaluador cambie algunos totales."""
    rng = random.Random(seed)
    return [round(base * rng.uniform(0.85, 1.15), decimals) for base in bases]


def _offers(prices: list[float]) -> tuple[Offer, ...]:
    return tuple(Offer(unit=price) for price in prices)


# ---------- 01: bienes en USD ----------

GOODS = Process("PROC-2026-001", "Suministro de equipos de red", 260_000, "USD")
GOODS_ITEMS = [Item("Switch de 24 puertos", (10,), "UND"), Item("Router de borde", (4,), "UND"),
               Item("Cable UTP categoría 6", (3000,), "METROS"), Item("Patch panel de 48 puertos", (8,), "UND"),
               Item("Access point de interior", (25,), "UND"), Item("Rack de 42 U", (3,), "UND")]
GOODS_BASES = [1850.0, 4200.0, 0.85, 310.0, 540.0, 1290.0]


def _goods_providers() -> list[Provider]:
    acme = list(_offers(_prices(1, GOODS_BASES, 3)))
    acme[1] = Offer(unit=acme[1].unit, total=round((acme[1].unit or 0) * 4 + 100, 2))  # total mal multiplicado
    beta = [*_offers(_prices(2, GOODS_BASES[:4], 3)), NO_OFFER, NO_OFFER]
    gamma = [*_offers(_prices(3, GOODS_BASES[:5], 2)), Offer(unit=0)]  # precio en 0
    return [Provider("ACME ANDINA SAS", GOODS_ROLES, tuple(acme), brand="Marca A"),
            Provider("BETA INDUSTRIAL SAS", GOODS_ROLES, tuple(beta), brand="Marca B"),
            Provider("GAMMA TECNOLOGÍA LTDA", GOODS_ROLES, tuple(gamma), brand="Marca C"),
            Provider("INVITADO", GOODS_ROLES)]


def build_goods(folder: Path) -> SampleBook:
    book = SampleBook("01_suministro_equipos_usd.xlsx")
    with new_workbook(folder / book.file_name) as workbook:
        w = SheetWriter(workbook, "Revisión aritmética")
        write_title(w, GOODS, ARITHMETIC_REVIEW)
        layout = Layout("t1", 9, {"item_no": "B", "description": "C", "unit": "F"}, ("G",), ("CANTIDAD",), "H",
                        "USD", unit_digits=2, total_digits=0, iva_rate_cell=True)
        result = write_table(w, layout, GOODS_ITEMS, _goods_providers())
        budget = _write_budget(w, GOODS, result.last_row)
        book.add_principal(w.name, cell_map("USD", [result.table], budget=budget), result.quotations, ["R1", "R9"])
        write_empty_template(workbook, "Revisión aritmética (plantilla)", GOODS)
        write_support_sheet(workbook, "Detalle de ítems", "REVISIÓN ARITMÉTICA - DETALLE DE ÍTEMS",
                            [(i.description, "Según ficha técnica", i.quantities[0]) for i in GOODS_ITEMS])
        write_fillers(workbook, GOODS, ["ACME ANDINA SAS", "BETA INDUSTRIAL SAS", "GAMMA TECNOLOGÍA LTDA"])
    book.apoyo.append("Detalle de ítems")
    return book


# ---------- 02: servicios con AIU, un grupo por hoja ----------

SERVICES = Process("PROC-2026-002", "Servicios de aseo y cafetería", 950_000_000, "COP")
SERVICE_GROUPS = {
    "1": [Item("Operario de aseo diurno", (6,)), Item("Operario de aseo nocturno", (2,)),
          Item("Supervisor de aseo", (1,))],
    "2": [Item("Auxiliar de cafetería diurno", (4,)), Item("Auxiliar de cafetería nocturno", (1,)),
          Item("Operario de mantenimiento", (2,)), Item("Supervisor de cafetería", (1,))],
}
SERVICE_BASES = [3_200_000.0, 3_650_000.0, 5_400_000.0, 2_900_000.0]
SERVICE_PROVIDERS = ["ACME ANDINA SAS", "BETA INDUSTRIAL SAS", "GAMMA SERVICIOS LTDA", "DELTA LIMPIEZA SAS"]
OCCASIONAL_SERVICES = ["Jornada adicional de aseo", "Lavado de fachada", "Desinfección de áreas", "Limpieza de vidrios"]
OCCASIONAL_BASES = [180_000.0, 2_400_000.0, 650_000.0, 420_000.0]


def _service_providers(group: str, items: list[Item]) -> list[Provider]:
    providers = []
    for index, name in enumerate(SERVICE_PROVIDERS):
        if group == "2" and name.startswith("DELTA"):  # no ofertó este grupo: bloque oculto y vacío
            providers.append(Provider(name, AIU_ROLES, hidden=True))
            continue
        prices = _prices(10 * index + int(group), SERVICE_BASES[:len(items)], 2)
        providers.append(Provider(name, AIU_ROLES, _offers(prices)))
    return providers


def _write_service_group(workbook: Workbook, book: SampleBook, group: str) -> None:
    items = SERVICE_GROUPS[group]
    w = SheetWriter(workbook, f"REV ARIT GRUPO {group}")
    write_title(w, SERVICES, f"REVISIÓN ARITMÉTICA - GRUPO {group}")
    partials = (("TOTAL SERVICIOS DIURNOS", 0, 1), ("TOTAL SERVICIOS NOCTURNOS Y OTROS", 2, 3)) if group == "2" else ()
    layout = Layout("t1", 9, {"item_no": "A", "description": "C"}, ("D",), ("CANTIDAD",), "E", "COP",
                    totals=("total",), partials=partials, aiu=True)
    result = write_table(w, layout, items, _service_providers(group, items))
    book.add_principal(w.name, cell_map("COP", [result.table]), result.quotations, ["R11"])


def build_services(folder: Path) -> SampleBook:
    book = SampleBook("02_servicios_aseo_aiu.xlsx")
    with new_workbook(folder / book.file_name) as workbook:
        for group in SERVICE_GROUPS:
            _write_service_group(workbook, book, group)
        tariffs = {name: _prices(40 + i, OCCASIONAL_BASES, 0) for i, name in enumerate(SERVICE_PROVIDERS)}
        write_tariff_sheet(workbook, "Servicios ocasionales", "REVISIÓN ARITMÉTICA - SERVICIOS OCASIONALES",
                           OCCASIONAL_SERVICES, tariffs)
        write_fillers(workbook, SERVICES, SERVICE_PROVIDERS)
    book.apoyo.append("Servicios ocasionales")
    return book


# ---------- 03: consultoría con bloques desiguales y un IVA mal escrito ----------

CONSULTING = Process("PROC-2026-003", "Consultoría para el diagnóstico de procesos", 780_000_000, "COP")
CONSULTING_ITEMS = [Item(f"Entregable {n}: {name}", (1,), "UND") for n, name in
                    enumerate(["Diagnóstico inicial", "Mapa de procesos", "Plan de mejora", "Informe final"], 1)]
CONSULTING_BASES = [120_000_000.0, 180_000_000.0, 95_000_000.0, 60_000_000.0]


def _consulting_providers() -> list[Provider]:
    acme = _offers([float(round(p)) for p in _prices(21, CONSULTING_BASES, 0)])
    beta = tuple(Offer(total=p) for p in _prices(22, CONSULTING_BASES, 2))
    gamma = tuple(Offer(total=p) for p in _prices(23, CONSULTING_BASES, 2))
    beta_iva = round(sum(o.total or 0 for o in beta) * 0.19 / 10, 2)  # IVA con un dígito de menos
    return [Provider("ACME ANDINA SAS", ("unit_price", "total_price_corrected"), acme),
            Provider("BETA CONSULTORES SAS", ("total_price", "total_price_corrected"), beta, iva_offered=beta_iva),
            Provider("GAMMA ASESORES LTDA", ("total_price", "total_price_corrected"), gamma)]


def build_consulting(folder: Path) -> SampleBook:
    book = SampleBook("03_consultoria_bloques_desiguales.xlsx")
    with new_workbook(folder / book.file_name) as workbook:
        w = SheetWriter(workbook, "Evaluación oferta económica")
        write_title(w, CONSULTING, "EVALUACIÓN DE LA OFERTA ECONÓMICA")
        layout = Layout("t1", 9, {"description": "C", "unit": "D"}, ("E",), ("CANT.",), "F", "COP")
        result = write_table(w, layout, CONSULTING_ITEMS, _consulting_providers())
        budget = _write_budget(w, CONSULTING, result.last_row)
        book.add_principal(w.name, cell_map("COP", [result.table], budget=budget), result.quotations, ["R11"])
        write_fillers(workbook, CONSULTING, ["ACME ANDINA SAS", "BETA CONSULTORES SAS", "GAMMA ASESORES LTDA"])
    return book


# ---------- 04: licencias, dos tablas (una por grupo) y total de la hoja ----------

LICENSES = Process("PROC-2026-004", "Licenciamiento de software en la nube", 1_500_000_000, "COP")
LICENSE_TABLES = {
    "1": [Item("Licencia de gestión de proyectos", (150, 12), tariff_type="USUARIO MES"),
          Item("Licencia de visor de planos", (150, 12), tariff_type="USUARIO MES"),
          Item("Licencia de programación de obra", (25, 12), tariff_type="USUARIO MES")],
    "2": [Item("Licencia de gestión de proyectos", (16, 12), tariff_type="USUARIO MES"),
          Item("Licencia de visor de planos", (16, 12), tariff_type="USUARIO MES")],
}
LICENSE_TITLES = {"1": "GRUPO 1 - SEDE PRINCIPAL", "2": "GRUPO 2 - SEDE REGIONAL"}
LICENSE_PROVIDERS = {
    "ACME ANDINA SAS": [500_000.0, 45_000.0, 840_000.0],
    "BETA SOFTWARE SAS": [511_125.0, 46_466.0, 851_874.0],
}


def _license_table(w: SheetWriter, group: str, first_row: int) -> TableResult:
    items = LICENSE_TABLES[group]
    providers = [Provider(name, PLAIN_ROLES, _offers(prices[:len(items)]))
                 for name, prices in LICENSE_PROVIDERS.items()]
    layout = Layout(f"t{group}", first_row, {"item_no": "A", "description": "B", "tariff_type": "C"}, ("D", "E"),
                    ("CANTIDAD USUARIOS", "CANTIDAD MESES"), "F", "COP", totals=("total",), group=group,
                    title=LICENSE_TITLES[group])
    return write_table(w, layout, items, providers)


def build_licenses(folder: Path) -> SampleBook:
    book = SampleBook("04_licencias_dos_grupos.xlsx")
    with new_workbook(folder / book.file_name) as workbook:
        w = SheetWriter(workbook, "Revisión aritmética")
        write_title(w, LICENSES, ARITHMETIC_REVIEW)
        first = _license_table(w, "1", 10)
        second = _license_table(w, "2", first.last_row + 4)
        totals = _write_offer_totals(w, first, second)
        sheet_map = cell_map("COP", [first.table, second.table], sheet_totals=totals)
        book.add_principal(w.name, sheet_map, first.quotations + second.quotations, [])
        write_fillers(workbook, LICENSES, list(LICENSE_PROVIDERS))
    return book


def _write_offer_totals(w: SheetWriter, first: TableResult, second: TableResult) -> list[SheetTotal]:
    """Fila 'VALOR TOTAL DE LA OFERTA': suma las dos tablas de cada proveedor (mismo orden en ambas)."""
    row = second.last_row + 1
    w.put(f"B{row}", "VALOR TOTAL DE LA OFERTA")
    pairs = zip(first.totals.items(), second.totals.values(), strict=True)
    return [sheet_total(w, name, refs + more, row, "COP") for (name, refs), more in pairs]


def _write_budget(w: SheetWriter, process: Process, row: int) -> Budget:
    w.put(f"C{row}", "PRESUPUESTO OFICIAL (INCLUIDO IVA)")
    w.put(f"C{row + 1}", process.budget, process.currency)
    return Budget(address=f"C{row + 1}", label_address=f"C{row}")


BUILDERS = [build_goods, build_services, build_consulting, build_licenses]
