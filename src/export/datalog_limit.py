"""Export the limits reverse-engineered from a datalog as a standalone file.

The exported workbook is the *as-run* limit sheet: it states which stage
(FT / QA) and which temperature zone the tester actually used, which is what
makes it possible to prove the production run against the PE specification.
"""

from typing import List, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.parsers.datalog import Datalog
from src.parsers.numeric import fmt

_HEADER_FILL = PatternFill("solid", fgColor="D9E1F2")
_LIMIT_HEADERS = [
    "Test item", "Units", "Test Number", "Lower Limit", "Upper Limit",
    "Limit 档位", "温区",
]


def export_datalog_limit(path: str, data: Datalog) -> str:
    wb = Workbook()

    ws = wb.active
    ws.title = "实际 Limit"
    for col, text in enumerate(_LIMIT_HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=text)
        cell.fill = _HEADER_FILL
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "A2"

    for r_idx, item in enumerate(data.items, start=2):
        values = [
            item.name, item.unit, item.test_number,
            fmt(item.lo), fmt(item.hi),
            data.side.value, data.zone.value,
        ]
        for c_idx, value in enumerate(values, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    for idx, width in enumerate([34, 10, 14, 14, 14, 12, 8], start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.auto_filter.ref = ws.dimensions

    ws = wb.create_sheet("元信息")
    ws.append(["项", "值"])
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = Font(bold=True)
    meta: List[Tuple[str, str]] = [
        ("来源 datalog", data.source_file),
        ("程序名", data.program_name),
        ("Data Sheet", data.data_sheet),
        ("Lot", data.lot),
        ("Current Limit 原文", data.limit_tag or "(未识别)"),
        ("识别档位", data.side.value),
        ("识别温区", data.zone.value),
        ("阶段标识", data.stage_label()),
        ("阶段识别方式", "自动识别" if data.tag_detected else "未识别，已默认 FT/Room"),
        ("测试项数", str(len(data.items))),
    ]
    for key, value in meta:
        ws.append([key, value])
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 60

    wb.save(path)
    return path
