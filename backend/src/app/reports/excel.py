"""Builds .xlsx exports of report tables (one sheet per table, plus an "About" sheet)."""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="1F4E8C")
HEADER_FONT = Font(bold=True, color="FFFFFF")


@dataclass
class Sheet:
    title: str
    headers: list[str]
    rows: Sequence[Sequence[Any]]


def _cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return value


def build_workbook(sheets: list[Sheet], about: list[tuple[str, str]]) -> bytes:
    wb = Workbook()
    first = wb.active
    assert first is not None
    wb.remove(first)
    for sheet in sheets:
        ws = wb.create_sheet(sheet.title[:31])
        ws.append(sheet.headers)
        for c in ws[1]:
            c.fill, c.font = HEADER_FILL, HEADER_FONT
        for row in sheet.rows:
            ws.append([_cell(v) for v in row])
        ws.freeze_panes = "A2"
        for i, header in enumerate(sheet.headers, start=1):
            width = max([len(str(header))] + [len(str(r[i - 1])) for r in sheet.rows if r[i - 1] is not None])
            ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 10), 60)
            for col in ws.iter_cols(min_col=i, max_col=i, min_row=2):
                for c in col:
                    if isinstance(c.value, date):
                        c.number_format = "dd mmm yyyy"
    info = wb.create_sheet("About")
    info.column_dimensions["A"].width = 28
    info.column_dimensions["B"].width = 110
    for key, value in about:
        info.append([key, value])
        info.cell(row=info.max_row, column=1).font = Font(bold=True)
        info.cell(row=info.max_row, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
