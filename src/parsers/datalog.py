"""ETS88 datalog (``.csv``) parser.

The datalog is a *transposed* report: one column per test item, and the rows
``Test Name`` / ``Test Number`` / ``Lower Limit`` / ``Upper Limit`` / ``Units``
describe those columns. Measurement rows follow but are not needed here -- we
only reverse-engineer the limits that were actually in force during that run.

The limit *stage* comes from the ``Current Limit:`` line, e.g.::

    Current Limit: FTRoom

which decodes to side FT and zone Room (``QA``/``FT`` + ``Room``/``Hot``/``Cold``).
That single line is what lets us prove which limit set the tester really used.
"""

import csv
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.model import (
    Bound,
    LimitItem,
    MachineType,
    ProgramModel,
    SourceType,
    TempZone,
)
from src.parsers.numeric import parse_number

# Non-test bookkeeping columns that still carry a Test Number.
_NON_TEST_COLUMNS = {"DATE", "TIME", "ACTIVE_SITE", "SITE"}

# Row labels living in column 0 of the transposed table.
_LABEL_COLUMNS = {
    "TEST NAME", "TEST NUMBER", "LOWER LIMIT", "UPPER LIMIT", "UNITS",
}

_CURRENT_LIMIT_RE = re.compile(r"current\s*limit\s*:?\s*(.+)", re.IGNORECASE)


def parse_limit_tag(tag: str) -> Tuple[SourceType, TempZone]:
    """Decode a ``Current Limit`` tag such as ``FTRoom`` into (side, zone)."""
    text = (tag or "").upper()
    side = SourceType.QA if "QA" in text else SourceType.FT
    if "HOT" in text:
        zone = TempZone.HOT
    elif "COLD" in text:
        zone = TempZone.COLD
    else:
        zone = TempZone.ROOM
    return side, zone


@dataclass
class DatalogItem:
    name: str
    unit: str = ""
    test_number: str = ""
    lo: Optional[float] = None
    hi: Optional[float] = None


@dataclass
class Datalog:
    """Reverse-engineered limits of one production run."""

    program_name: str = ""
    data_sheet: str = ""
    lot: str = ""
    limit_tag: str = ""
    side: SourceType = SourceType.FT
    zone: TempZone = TempZone.ROOM
    items: List[DatalogItem] = field(default_factory=list)
    measurements: Dict[str, List[float]] = field(default_factory=dict)
    bins: List[str] = field(default_factory=list)
    source_file: str = ""
    tag_detected: bool = False
    meta: Dict[str, str] = field(default_factory=dict)

    def stage_label(self) -> str:
        return f"{self.side.value} / {self.zone.value}"


def _scan_meta(rows: List[List[str]], data: Datalog) -> None:
    """Pull program / datasheet / lot / limit-stage out of the header block."""
    for row in rows:
        if not row:
            continue
        first = (row[0] or "").strip()
        second = (row[1] or "").strip() if len(row) > 1 else ""

        if not data.limit_tag:
            match = _CURRENT_LIMIT_RE.match(first)
            if match and match.group(1).strip():
                data.limit_tag = match.group(1).strip()
                data.tag_detected = True
                continue
            if first.lower().startswith("current limit") and second:
                data.limit_tag = second
                data.tag_detected = True
                continue

        lowered = first.lower().rstrip(":")
        if lowered == "test name" and second:
            data.program_name = second
        elif lowered.startswith("data sheet file"):
            data.data_sheet = second
        elif lowered.startswith("datalog for lot number"):
            data.lot = second


def _locate_table(rows: List[List[str]]) -> Optional[int]:
    """Index of the column-header row (the one starting with 'Test Name').

    A datalog report carries a *metadata* ``Test Name`` line in its header
    block (only the program name in column 1) and a second *table* ``Test
    Name`` row that heads the transposed measurement table (followed by
    ``Test Number`` -> ``Lower Limit``).  Picking the first ``Test Name`` row
    therefore grabs the metadata line and yields an almost-empty table.

    We instead anchor on the ``Lower Limit`` row -- it exists only inside the
    real table block -- and backtrack to the nearest preceding ``Test Name``.
    """
    lower_idx = None
    for idx, row in enumerate(rows):
        if row and (row[0] or "").strip().lower() == "lower limit":
            lower_idx = idx
            break
    if lower_idx is None:
        return None
    for j in range(lower_idx, -1, -1):
        if rows[j] and (rows[j][0] or "").strip().lower() == "test name":
            return j
    return None


def parse_datalog(path: str) -> Datalog:
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        rows = list(csv.reader(fh))

    data = Datalog(source_file=os.path.basename(path))
    _scan_meta(rows, data)
    data.side, data.zone = parse_limit_tag(data.limit_tag)

    header_idx = _locate_table(rows)
    if header_idx is None:
        raise ValueError(f"No datalog table found in {os.path.basename(path)}")

    width = len(rows[header_idx])
    names = rows[header_idx]

    def row_named(label: str) -> List[str]:
        for row in rows[header_idx: header_idx + 12]:
            if row and (row[0] or "").strip().lower() == label and len(row) == width:
                return row
        return [""] * width

    numbers = row_named("test number")
    lowers = row_named("lower limit")
    uppers = row_named("upper limit")
    units = row_named("units")

    seen: Dict[str, DatalogItem] = {}
    # Column 0 is the row-label column ("Test Name", "Units", ...) whenever the
    # report has one; skipping it keeps the labels out of the test list.
    label = (names[0] or "").strip().upper() if names else ""
    start = 1 if label in _LABEL_COLUMNS else 0
    for col in range(start, width):
        name = (names[col] or "").strip()
        if not name or name.upper() in _NON_TEST_COLUMNS:
            continue
        lo = parse_number(lowers[col] if col < len(lowers) else None)
        hi = parse_number(uppers[col] if col < len(uppers) else None)
        if name in seen:
            continue  # duplicate column: the first occurrence wins
        seen[name] = DatalogItem(
            name=name,
            unit=(units[col] or "").strip() if col < len(units) else "",
            test_number=(numbers[col] or "").strip() if col < len(numbers) else "",
            lo=lo,
            hi=hi,
        )
    data.items = list(seen.values())
    _read_measurements(rows, header_idx, width, names, start, data)
    return data


def _read_measurements(rows, header_idx, width, names, start, data) -> None:
    """Collect per-test measured values from the data rows.

    A data row has the same width as the header and starts with the site
    number. Values that are not numeric (``N/A``) are skipped.
    """
    series: Dict[str, List[float]] = {name: [] for name in seen_names(names, start)}
    bins: List[str] = []
    for row in rows[header_idx + 1:]:
        if len(row) != width:
            continue
        site = (row[0] or "").strip()
        if not site.isdigit():
            continue
        if len(row) > 2:
            bins.append((row[2] or "").strip())
        for col in range(start, width):
            name = (names[col] or "").strip()
            if not name or name.upper() in _NON_TEST_COLUMNS:
                continue
            value = parse_number(row[col])
            if value is not None:
                series.setdefault(name, []).append(value)
    data.measurements = series
    data.bins = bins


def seen_names(names, start) -> List[str]:
    out = []
    for col in range(start, len(names)):
        name = (names[col] or "").strip()
        if name and name.upper() not in _NON_TEST_COLUMNS:
            out.append(name)
    return out


def datalog_to_program(data: Datalog) -> ProgramModel:
    """Wrap a datalog as a single-side ``ProgramModel`` (the actual limits)."""
    items: List[LimitItem] = []
    for entry in data.items:
        item = LimitItem(
            function=data.limit_tag or data.side.value,
            test_item=entry.name,
            unit=entry.unit,
            sub_test_nmbr=entry.test_number,
            machine_type=MachineType.ETS88,
            source_files=[data.source_file],
        )
        item.set_bound(data.zone, data.side, Bound(lo=entry.lo, hi=entry.hi))
        items.append(item)
    return ProgramModel(
        id=os.path.splitext(data.source_file)[0],
        name=data.program_name or data.source_file,
        machine_type=MachineType.ETS88,
        functions=[data.limit_tag or data.side.value],
        items=items,
    )
