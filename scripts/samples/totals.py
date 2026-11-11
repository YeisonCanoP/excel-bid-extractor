"""Filas de total por proveedor (SUBTOTAL, IVA, VALOR TOTAL y parciales) con su referencia para el mapa."""

from dataclasses import dataclass

from app.domain.cell_map import SheetTotal, TotalKind, TotalRef
from app.quotes.normalize import excel_round, without_noise
from scripts.samples.model import IVA_RATE, TOTAL_LABELS, Block, Layout
from scripts.samples.writer import SheetWriter


@dataclass(frozen=True)
class TotalRow:
    kind: TotalKind
    row: int
    label: str
    first: int
    last: int
    """Filas de ítems que suma (para subtotales y parciales)."""


def total_rows(layout: Layout, item_count: int) -> list[TotalRow]:
    """Filas de total debajo de los ítems; los parciales van después, separados por una fila."""
    start, last = layout.first_item_row + item_count + 1, layout.first_item_row + item_count - 1
    rows = [TotalRow(TotalKind(kind), start + i, TOTAL_LABELS[kind], layout.first_item_row, last)
            for i, kind in enumerate(layout.totals)]
    partial_start = start + len(layout.totals) + 1
    rows += [TotalRow(TotalKind.PARTIAL, partial_start + i, label, layout.first_item_row + a,
                      layout.first_item_row + b) for i, (label, a, b) in enumerate(layout.partials)]
    return rows


def write_total(w: SheetWriter, layout: Layout, block: Block, total: TotalRow, previous: list[TotalRef]) -> TotalRef:
    """Escribe el total del proveedor en esa fila y devuelve su referencia."""
    by_kind = {ref.kind: ref for ref in previous}
    if total.kind == TotalKind.IVA:
        return _iva(w, layout, block, total, by_kind[TotalKind.SUBTOTAL])
    if total.kind == TotalKind.TOTAL and TotalKind.SUBTOTAL in by_kind:
        return _total_with_iva(w, layout, block, total, by_kind)
    return _sum(w, layout, block, total)


def sheet_total(w: SheetWriter, name_address: str, parts: list[TotalRef], row: int, currency: str) -> SheetTotal:
    """Total de la hoja para un proveedor: suma de los totales de cada tabla."""
    offered_col, corrected_col = _column_of(parts[0].offered), _column_of(parts[0].corrected)
    offered = without_noise(sum(w.number(ref.offered) for ref in parts))
    corrected = without_noise(sum(w.number(ref.corrected) for ref in parts))
    w.put(f"{offered_col}{row}", offered, currency)
    w.formula(f"{corrected_col}{row}", "=" + "+".join(ref.corrected or "" for ref in parts), corrected, currency)
    return SheetTotal(kind=TotalKind.TOTAL, label_address=None, offered=f"{offered_col}{row}",
                      corrected=f"{corrected_col}{row}", check=None, rate=None, name_address=name_address)


def _sum(w: SheetWriter, layout: Layout, block: Block, total: TotalRow) -> TotalRef:
    offered_col, corrected_col = block.offered_column, block.corrected_column
    rows = range(total.first, total.last + 1)
    offered = without_noise(sum(w.number(f"{offered_col}{r}") for r in rows))
    corrected = without_noise(sum(w.number(f"{corrected_col}{r}") for r in rows))
    w.put(f"{offered_col}{total.row}", offered, layout.currency)
    w.formula(f"{corrected_col}{total.row}", f"=SUM({corrected_col}{total.first}:{corrected_col}{total.last})",
              corrected, layout.currency)
    return _ref(w, block, total, check=offered == corrected)


def _iva(w: SheetWriter, layout: Layout, block: Block, total: TotalRow, subtotal: TotalRef) -> TotalRef:
    offered_col, corrected_col = block.offered_column, block.corrected_column
    offered = block.provider.iva_offered or without_noise(w.number(subtotal.offered) * IVA_RATE)
    corrected = without_noise(w.number(subtotal.corrected) * IVA_RATE)
    w.put(f"{offered_col}{total.row}", offered, layout.currency)
    w.formula(f"{corrected_col}{total.row}", f"={subtotal.corrected}*19%", corrected, layout.currency)
    rate = _rate_cell(w, layout, block, total.row)
    return TotalRef(kind=TotalKind.IVA, label_address=None, offered=f"{offered_col}{total.row}",
                    corrected=f"{corrected_col}{total.row}", check=None, rate=rate)


def _total_with_iva(w: SheetWriter, layout: Layout, block: Block, total: TotalRow,
                    by_kind: dict[TotalKind, TotalRef]) -> TotalRef:
    offered_col, corrected_col = block.offered_column, block.corrected_column
    subtotal, iva = by_kind[TotalKind.SUBTOTAL], by_kind[TotalKind.IVA]
    offered = without_noise(w.number(subtotal.offered) + w.number(iva.offered))
    corrected = excel_round(w.number(subtotal.corrected) + w.number(iva.corrected), layout.total_digits)
    w.put(f"{offered_col}{total.row}", offered, layout.currency)
    w.formula(f"{corrected_col}{total.row}", f"=ROUND({subtotal.corrected}+{iva.corrected},{layout.total_digits})",
              corrected, layout.currency)
    return _ref(w, block, total, check=offered == corrected)


def _ref(w: SheetWriter, block: Block, total: TotalRow, *, check: bool) -> TotalRef:
    """Referencia del total; escribe la verificación OK/ERROR si el bloque la tiene."""
    offered_col, corrected_col = block.offered_column, block.corrected_column
    check_col = block.columns.get("check")
    if check_col:
        w.formula(f"{check_col}{total.row}", f'=IF({offered_col}{total.row}={corrected_col}{total.row},"OK","ERROR")',
                  "OK" if check else "ERROR")
    return TotalRef(kind=total.kind, label_address=None, offered=f"{offered_col}{total.row}",
                    corrected=f"{corrected_col}{total.row}", check=f"{check_col}{total.row}" if check_col else None,
                    rate=None)


def _rate_cell(w: SheetWriter, layout: Layout, block: Block, row: int) -> str | None:
    if not layout.iva_rate_cell or "unit_price" not in block.columns:
        return None
    address = f"{block.columns['unit_price']}{row}"
    w.put(address, IVA_RATE, "percent")
    return address


def _column_of(address: str | None) -> str:
    return (address).rstrip("0123456789")
