"""Identidad de cada cotización: proveedor, producto y unidad, con sus llaves normalizadas."""

from app.domain.cell_map import ProviderBlock, Table
from app.domain.quotation import ProductRef, ProviderRef, SourcedText
from app.quotes.normalize import is_placeholder_provider, product_key, provider_key, unit_label
from app.quotes.sheet import SheetCells


def provider_ref(cells: SheetCells, address: str) -> ProviderRef | None:
    """Proveedor del bloque; None si no es un proveedor real (INVITADO, 0, vacío)."""
    name = cells.text(address)
    if name is None or is_placeholder_provider(name.value):
        return None
    return ProviderRef(key=provider_key(name.value), name=name.value, source=address)


def product_ref(cells: SheetCells, table: Table, block: ProviderBlock, description: SourcedText,
                row: int) -> ProductRef:
    columns = table.item_columns
    detail = " ".join(text.value for column in columns.detail if (text := cells.text_at(column, row))) or None
    item_no, brand = cells.label_at(columns.item_no, row), cells.text_at(block.columns.brand, row)
    return ProductRef(
        key=product_key(description.value, detail), item_no=item_no.value if item_no else None,
        description=description.value, detail=detail, brand=brand.value if brand else None, row=row,
    )


def unit_ref(cells: SheetCells, table: Table, row: int, site: SourcedText | None) -> SourcedText:
    """Unidad + tipo de tarifa + sede, en mayúsculas."""
    columns = table.item_columns
    parts = (cells.text_at(columns.unit, row), cells.text_at(columns.tariff_type, row), site)
    label = unit_label(*(part.value if part else None for part in parts))
    return SourcedText(value=label, source=[s for part in parts if part for s in part.source])
