"""ETS88 ``.pds`` parser (INI-style text with positional data columns).

Layout:
  * ``[Datasheet Variable Map]`` lists the data columns in order via quoted CSV
    rows ``"type","ColumnName","Description"``.
  * Every other ``[Function]`` section holds one quoted-CSV row per test item.
    The first data field is an empty selection column, so data field ``i+1``
    corresponds to variable-map column ``i``.

Column names are resolved dynamically from the variable map, so a reordered
``[Datasheet Variable Map]`` cannot break the parser.
"""

import csv
import os
from typing import Dict, List, Optional

from src.model import Bound, LimitItem, MachineType, ProgramModel, SourceType, TempZone
from src.parsers.numeric import parse_number

_SKIP_SECTIONS = {
    "DATASHEET PREFERENCES",
    "DOCUMENTATION BLOCK",
    "BINNING BLOCK",
    "DATASHEET VARIABLE MAP",
    "TEST ORDER",
}

_BOUND_COLUMNS = {
    (TempZone.ROOM, SourceType.FT): ("LoLimFTRoom", "HiLimFTRoom"),
    (TempZone.ROOM, SourceType.QA): ("LoLimQARoom", "HiLimQARoom"),
    (TempZone.HOT, SourceType.FT): ("LoLimFTHot", "HiLimFTHot"),
    (TempZone.HOT, SourceType.QA): ("LoLimQAHot", "HiLimQAHot"),
    (TempZone.COLD, SourceType.FT): ("LoLimFTCold", "HiLimFTCold"),
    (TempZone.COLD, SourceType.QA): ("LoLimQACold", "HiLimQACold"),
}


class PdsParser:
    @staticmethod
    def parse(content: str, file_name: str) -> ProgramModel:
        sections: Dict[str, List[str]] = {}
        current: Optional[str] = None
        for raw in content.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                current = stripped[1:-1].strip()
                sections.setdefault(current, [])
            elif current is not None:
                sections[current].append(raw)

        if "Datasheet Variable Map" not in sections:
            raise ValueError("Invalid .pds: missing [Datasheet Variable Map] section")

        col_to_index: Dict[str, int] = {}
        for row in csv.reader(sections["Datasheet Variable Map"]):
            if len(row) < 2:
                continue
            col_to_index[row[1].strip()] = len(col_to_index) + 1

        functions: List[str] = []
        items: List[LimitItem] = []
        for section_name, body in sections.items():
            if section_name.upper() in _SKIP_SECTIONS:
                continue
            func_items = PdsParser._parse_function(
                section_name, body, col_to_index, file_name
            )
            if not func_items:
                continue
            if section_name not in functions:
                functions.append(section_name)
            items.extend(func_items)

        return ProgramModel(
            id=os.path.basename(file_name).rsplit(".", 1)[0],
            name=file_name,
            machine_type=MachineType.ETS88,
            functions=functions,
            items=items,
        )

    @staticmethod
    def _cell(row: List[str], index: Optional[int]) -> Optional[str]:
        if index is None or index >= len(row):
            return None
        return row[index]

    @staticmethod
    def _parse_function(function, body, col_to_index, file_name) -> List[LimitItem]:
        out: List[LimitItem] = []
        for raw in body:
            row = next(csv.reader([raw]), None)
            if not row or len(row) < 4:
                continue
            test_item = (PdsParser._cell(row, col_to_index.get("DLogDesc")) or "").strip()
            if not test_item:
                continue
            item = LimitItem(
                function=function,
                test_item=test_item,
                unit=(PdsParser._cell(row, col_to_index.get("Units")) or "").strip(),
                sub_test_nmbr=(
                    PdsParser._cell(row, col_to_index.get("SubTestNmbr")) or ""
                ).strip(),
                machine_type=MachineType.ETS88,
                source_files=[file_name],
            )
            for (zone, side), (lo_col, hi_col) in _BOUND_COLUMNS.items():
                lo = parse_number(PdsParser._cell(row, col_to_index.get(lo_col)))
                hi = parse_number(PdsParser._cell(row, col_to_index.get(hi_col)))
                if lo is None and hi is None:
                    continue
                item.set_bound(zone, side, Bound(lo=lo, hi=hi))
            out.append(item)
        return out

    @staticmethod
    def parse_file(path: str) -> ProgramModel:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            return PdsParser.parse(fh.read(), path)
