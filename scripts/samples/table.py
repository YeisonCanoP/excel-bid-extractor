"""Escribe una tabla de revisión aritmética (ítems x bloques de proveedor) y arma su mapa de celdas esperado."""

from dataclasses import dataclass

from app.domain.cell_map import ItemColumns, ProviderBlock, ProviderColumns, RowRange, Table, TotalRef
from app.quotes.normalize import is_placeholder_provider
from scripts.samples.cells import ItemRow, cell_for
from scripts.samples.model import ROLE_LABELS, TEXT_ROLES, Block, Item, Layout, Provider
from scripts.samples.totals import total_rows, write_total
from scripts.samples.writer import SheetWriter, shift

NO_COLUMNS = dict.fromkeys(ProviderColumns.model_fields)


@dataclass(frozen=True)
class TableResult:
    table: Table
    """Mapa esperado de la tabla."""
    quotations: int
    """Cotizaciones que debe extraer el sistema (proveedores con oferta x ítems)."""
    totals: dict[str, list[TotalRef]]
    """Totales de cada proveedor, por celda del nombre."""
    last_row: int


def write_table(w: SheetWriter, layout: Layout, items: list[Item], providers: list[Provider]) -> TableResult:
    blocks = _place(w, layout, providers)
    _write_headers(w, layout, blocks)
    for index, item in enumerate(items):
        _write_item(w, layout, blocks, layout.first_item_row + index, item)
    totals, last_row = _write_totals(w, layout, blocks, len(items))
    offering = [b for b in blocks if b.has_offer and not is_placeholder_provider(b.provider.name)]
    return TableResult(table=_table_map(layout, blocks, totals, len(items)), quotations=len(offering) * len(items),
                       totals=totals, last_row=last_row)


def _place(w: SheetWriter, layout: Layout, providers: list[Provider]) -> list[Block]:
    """Ubica los bloques uno tras otro desde `first_block`; oculta los que piden estar ocultos."""
    blocks, offset = [], 0
    for provider in providers:
        columns = {role: shift(layout.first_block, offset + i) for i, role in enumerate(provider.roles)}
        if provider.hidden:
            w.hide_columns(columns[provider.roles[0]], columns[provider.roles[-1]])  # proveedor que no ofertó
        blocks.append(Block(provider, columns))
        offset += len(provider.roles)
    return blocks


def _write_headers(w: SheetWriter, layout: Layout, blocks: list[Block]) -> None:
    labels = {"item_no": "ÍTEM", "description": "DESCRIPCIÓN", "unit": "UNIDAD", "tariff_type": "TIPO DE TARIFA"}
    for role, column in layout.item_columns.items():
        w.put(f"{column}{layout.header_row}", labels[role])
    for column, label in zip(layout.quantity_columns, layout.quantity_labels, strict=True):
        w.put(f"{column}{layout.header_row}", label)
    w.put(f"{layout.item_columns['description']}{layout.name_row}", "PARTICIPANTE")
    for block in blocks:
        w.put(_name_address(layout, block), block.provider.name)
        for role, column in block.columns.items():
            suffix = "" if role in TEXT_ROLES else f" ({layout.currency})"
            w.put(f"{column}{layout.header_row}", ROLE_LABELS[role] + suffix)


def _write_item(w: SheetWriter, layout: Layout, blocks: list[Block], row: int, item: Item) -> None:
    values = {"item_no": row - layout.first_item_row + 1, "description": item.description, "unit": item.unit,
              "tariff_type": item.tariff_type}
    for role, column in layout.item_columns.items():
        w.put(f"{column}{row}", values[role])
    for column, quantity in zip(layout.quantity_columns, item.quantities, strict=True):
        w.put(f"{column}{row}", quantity)
    for block in blocks:
        if block.has_offer:
            _write_offer(w, ItemRow(row, item, block.provider.offers[row - layout.first_item_row], block, layout))


def _write_offer(w: SheetWriter, row: ItemRow) -> None:
    if row.offer.no_offer:
        w.put(row.ref("unit_price"), "NO COTIZA")
        return
    for role in row.block.provider.roles:
        formula, value = cell_for(row, role)
        fmt = None if role in TEXT_ROLES else row.layout.currency
        if formula:
            w.formula(row.ref(role), formula, value, fmt)
        else:
            w.put(row.ref(role), value, fmt)


def _write_totals(w: SheetWriter, layout: Layout, blocks: list[Block],
                  item_count: int) -> tuple[dict[str, list[TotalRef]], int]:
    """Totales de cada proveedor con oferta, por celda del nombre, y la primera fila libre debajo."""
    offering = [block for block in blocks if block.has_offer]
    totals: dict[str, list[TotalRef]] = {_name_address(layout, block): [] for block in offering}
    rows = total_rows(layout, item_count)
    for total in rows:
        w.put(f"{layout.item_columns['description']}{total.row}", total.label)
        for block in offering:
            refs = totals[_name_address(layout, block)]
            refs.append(write_total(w, layout, block, total, refs))
    return totals, rows[-1].row + 2


def _table_map(layout: Layout, blocks: list[Block], totals: dict[str, list[TotalRef]], item_count: int) -> Table:
    columns = layout.item_columns
    item_columns = ItemColumns(item_no=columns.get("item_no"), description=columns["description"], detail=[],
                               unit=columns.get("unit"), tariff_type=columns.get("tariff_type"),
                               quantity=list(layout.quantity_columns))
    providers = [ProviderBlock(name_address=_name_address(layout, block),
                               columns=ProviderColumns(**(NO_COLUMNS | block.columns)),
                               totals=totals.get(_name_address(layout, block), [])) for block in blocks]
    return Table(table_id=layout.table_id, group=layout.group, title_address=None, site_address=None,
                 header_rows=[layout.name_row, layout.header_row],
                 item_rows=RowRange(first=layout.first_item_row, last=layout.first_item_row + item_count - 1),
                 item_columns=item_columns, providers=providers, confidence=1.0)


def _name_address(layout: Layout, block: Block) -> str:
    return f"{block.first_column}{layout.name_row}"
