"""PE specification spreadsheet parser (``.xlsx``).

Structure of the PE files (e.g. ``4. IQ limit_rev1.0.xlsx``)::

    row 4 (header) : Test item | Units | ATE Test# | FT limit | QA limit |
                     Comments | Old program
    row 5 (sub)    :                                              Test item |
                     LSL | HSL
    row 6..        : data

Column letters are NOT hardcoded: every column is located by its header text,
because the shipped PE files disagree on the sub-header wording
(``Test item`` / ``Item`` / ``ATE test #``, ``LSL|HSL`` / ``FT Limit``).

``FT limit`` and ``QA limit`` are merged header cells spanning two columns each
(LSL, HSL), so the hi column is always the lo column + 1.

The PE sheet carries no temperature zone and no Function column -- those are
supplied by the caller (scenario 2 currently compares Room only).
"""

import os
import re
from typing import Dict, List, Optional

from openpyxl import load_workbook

from src.model import PeItem, PeProgram
from src.parsers.numeric import parse_number

_HEADER_SCAN_ROWS = 15
_OLD_BLOCK_SPAN = 7


def _norm_header(text) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(text or "").upper())


def _find_header_row(rows: List) -> int:
    """Return the 0-based index of the header row, or -1."""
    for idx, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        cells = [_norm_header(c) for c in row]
        if any(c.startswith("TESTITEM") or c == "ITEM" for c in cells) and any(
            "FTLIMIT" in c for c in cells
        ):
            return idx
    return -1


def _locate(header: List, sub: List) -> Dict[str, Optional[int]]:
    """Map logical field -> 0-based column index from the header rows."""
    cells = [_norm_header(c) for c in header]
    sub_cells = [_norm_header(c) for c in sub]
    cols: Dict[str, Optional[int]] = {
        "name": None,
        "unit": None,
        "ate": None,
        "ft_lo": None,
        "ft_hi": None,
        "qa_lo": None,
        "qa_hi": None,
        "guardband": None,
        "old_lo": None,
        "old_hi": None,
    }

    for idx, cell in enumerate(cells):
        if cols["name"] is None and (cell.startswith("TESTITEM") or cell == "ITEM"):
            cols["name"] = idx
        elif cols["unit"] is None and cell.startswith("UNIT"):
            cols["unit"] = idx
        elif cols["ate"] is None and "ATE" in cell:
            cols["ate"] = idx
        elif cols["ft_lo"] is None and "FTLIMIT" in cell:
            cols["ft_lo"] = idx
            cols["ft_hi"] = idx + 1
        elif cols["qa_lo"] is None and "QALIMIT" in cell:
            cols["qa_lo"] = idx
            cols["qa_hi"] = idx + 1
        elif cols["guardband"] is None and "COMMENT" in cell:
            cols["guardband"] = idx

    old_start = None
    for idx, cell in enumerate(cells):
        if "OLDPROGRAM" in cell:
            old_start = idx
            break
    if old_start is not None:
        end = min(len(sub_cells), old_start + _OLD_BLOCK_SPAN)
        lsl = hsl = None
        for idx in range(old_start, end):
            text = sub_cells[idx] if idx < len(sub_cells) else ""
            if lsl is None and text == "LSL":
                lsl = idx
            elif hsl is None and text == "HSL":
                hsl = idx
        if lsl is not None and hsl is not None:
            cols["old_lo"], cols["old_hi"] = lsl, hsl
        elif lsl is not None:
            cols["old_lo"], cols["old_hi"] = lsl, lsl + 1
        else:
            for idx in range(old_start, end):
                text = sub_cells[idx] if idx < len(sub_cells) else ""
                if "LIMIT" in text:
                    cols["old_lo"], cols["old_hi"] = idx, idx + 1
                    break
    return cols


def _pick_sheet(workbook):
    for ws in workbook.worksheets:
        if "LIMIT" in ws.title.upper() and "REVISION" not in ws.title.upper():
            return ws
    return workbook.worksheets[0]


def parse_sheet(path: str) -> List[PeItem]:
    """Parse one PE spreadsheet into a list of :class:`PeItem`."""
    workbook = load_workbook(path, data_only=True)
    ws = _pick_sheet(workbook)
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    header_idx = _find_header_row(rows)
    if header_idx < 0:
        raise ValueError(f"Cannot locate the header row in {os.path.basename(path)}")

    cols = _locate(rows[header_idx], rows[header_idx + 1])
    if cols["name"] is None:
        raise ValueError(f"Cannot locate the Test item column in {os.path.basename(path)}")

    base = os.path.basename(path)
    items: List[PeItem] = []
    for offset, row in enumerate(rows[header_idx + 2 :], start=header_idx + 3):
        def cell(key):
            idx = cols.get(key)
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        raw_name = cell("name")
        if raw_name is None or not str(raw_name).strip():
            continue
        name = str(raw_name).strip()
        items.append(
            PeItem(
                name=name,
                unit=str(cell("unit") or "").strip(),
                ate_test_no=str(cell("ate") or "").strip(),
                ft_lo=parse_number(cell("ft_lo")),
                ft_hi=parse_number(cell("ft_hi")),
                qa_lo=parse_number(cell("qa_lo")),
                qa_hi=parse_number(cell("qa_hi")),
                old_lo=parse_number(cell("old_lo")),
                old_hi=parse_number(cell("old_hi")),
                guardband=parse_number(cell("guardband")),
                source_file=base,
                row=offset,
            )
        )
    return items


def parse_files(paths: List[str], program_id: str = "") -> PeProgram:
    """Parse several PE spreadsheets into one :class:`PeProgram`.

    Excel 打开表格时会在同目录留下 ``~$xxx.xlsx`` 属主锁文件（0 字节占位、被 Excel
    独占），它不是有效表格且读取会 PermissionError，必须跳过。工程师常开着 PE 表
    就用本工具，这是真实会踩到的坑。
    """
    program = PeProgram(id=program_id or "PE")
    seen = set()
    for path in paths:
        if os.path.basename(path).startswith("~$"):
            continue
        for item in parse_sheet(path):
            key = (item.name, item.source_file)
            if key in seen:
                continue
            seen.add(key)
            program.items.append(item)
        if os.path.basename(path) not in program.source_files:
            program.source_files.append(os.path.basename(path))
    return program
