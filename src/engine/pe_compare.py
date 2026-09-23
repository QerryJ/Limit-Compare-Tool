"""Scenario 2: PE specification vs the current test program.

Produces the "limits that must be updated" list.

Per aligned item and per side (FT / QA) one row is produced, carrying the
current program value, the PE target value, the delta and a direction:

  * ``TIGHTEN`` -- PE pulled the limit in (lo raised, or hi lowered).
  * ``LOOSEN``  -- PE pushed the limit out (real risk -- flagged).
  * ``MIXED``   -- one edge tightened while the other loosened.

A separate three-way baseline check compares the PE sheet's own "Old program"
column against the program's current value. A mismatch means the program was
already changed by someone else, or the PE baseline is a different revision --
exactly the situation where blindly applying the PE sheet corrupts the program.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from src.engine.align import Match, MatchStatus
from src.model import Bound, LimitItem, PeItem, PeProgram, ProgramModel, SourceType, TempZone


class UpdateStatus(Enum):
    SAME = "无需更新"
    CHANGE = "需更新"
    MISSING_IN_PROGRAM = "程序缺项"
    PROGRAM_ONLY = "仅程序有"
    NO_TARGET = "PE待测未定"


class Direction(Enum):
    TIGHTEN = "收紧"
    LOOSEN = "放宽"
    MIXED = "混合"
    SAME = "一致"
    FILL = "补值"
    UNKNOWN = "—"


@dataclass
class UpdateRow:
    function: str = ""
    test_item: str = ""
    unit: str = ""
    zone: str = ""
    side: str = ""
    cur_lo: Optional[float] = None
    cur_hi: Optional[float] = None
    tgt_lo: Optional[float] = None
    tgt_hi: Optional[float] = None
    d_lo: Optional[float] = None
    d_hi: Optional[float] = None
    direction: Direction = Direction.UNKNOWN
    status: UpdateStatus = UpdateStatus.SAME
    pe_file: str = ""
    pe_row: int = 0
    note: str = ""


@dataclass
class BaselineRow:
    function: str = ""
    test_item: str = ""
    unit: str = ""
    pe_old_lo: Optional[float] = None
    pe_old_hi: Optional[float] = None
    prog_lo: Optional[float] = None
    prog_hi: Optional[float] = None
    drift: bool = False
    pe_file: str = ""
    pe_row: int = 0


@dataclass
class PeCompareResult:
    updates: List[UpdateRow] = field(default_factory=list)
    baseline: List[BaselineRow] = field(default_factory=list)
    unmatched: List[Match] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)


def _pe_bound(item: PeItem, side: SourceType) -> Bound:
    if side is SourceType.FT:
        return Bound(lo=item.ft_lo, hi=item.ft_hi)
    return Bound(lo=item.qa_lo, hi=item.qa_hi)


def _is_unset(bound: Bound) -> bool:
    """Whether the PE side carries no usable limit.

    Confirmed with the user: in the PE sheets a ``0 / 0`` pair means the limit
    is **not yet decided** ("待测未定"), NOT a real limit of zero. Only a pair
    of explicit zeros counts as unset -- a single ``0`` edge (e.g. ``0 .. 1``)
    is a legitimate one-sided limit and must be kept.
    """
    if bound.is_empty():
        return True
    return bound.lo == 0 and bound.hi == 0


TOLERANCE = 1e-9


def _close(a: Optional[float], b: Optional[float]) -> bool:
    """Whether two limit values are equal within floating-point noise."""
    if a is None or b is None:
        return False
    return abs(a - b) <= max(TOLERANCE, TOLERANCE * abs(b))


def _edge_direction(cur, tgt, edge) -> Optional[Direction]:
    if cur is None or tgt is None:
        return None
    if _close(cur, tgt):
        return Direction.SAME
    if edge == "lo":
        return Direction.TIGHTEN if tgt > cur else Direction.LOOSEN
    return Direction.TIGHTEN if tgt < cur else Direction.LOOSEN


def _delta(cur, tgt) -> Optional[float]:
    if cur is None or tgt is None:
        return None
    if _close(cur, tgt):
        return 0.0
    return round(tgt - cur, 9)


def _combine(lo_dir: Optional[Direction], hi_dir: Optional[Direction]) -> Direction:
    real = [d for d in (lo_dir, hi_dir) if d not in (None, Direction.SAME)]
    if not real:
        return Direction.SAME
    if all(d is Direction.TIGHTEN for d in real):
        return Direction.TIGHTEN
    if all(d is Direction.LOOSEN for d in real):
        return Direction.LOOSEN
    return Direction.MIXED


def compare_pe_to_program(
    pe: PeProgram,
    program: ProgramModel,
    matches: List[Match],
    zone: TempZone = TempZone.ROOM,
    sides: Optional[List[SourceType]] = None,
) -> PeCompareResult:
    """Build the update list for scenario 2 (Room only by default).

    ``sides`` restricts the comparison. A datalog only carries ONE limit stage
    (e.g. FT), so comparing both sides there would fabricate QA rows.
    """
    sides = list(sides) if sides else [SourceType.FT, SourceType.QA]
    result = PeCompareResult()

    for match in matches:
        pe_item = match.pe_item

        if match.item is None:
            result.unmatched.append(match)
            result.updates.append(
                UpdateRow(
                    function="",
                    test_item=pe_item.name,
                    unit=pe_item.unit,
                    zone=zone.value,
                    side="FT",
                    tgt_lo=pe_item.ft_lo,
                    tgt_hi=pe_item.ft_hi,
                    status=UpdateStatus.MISSING_IN_PROGRAM,
                    direction=Direction.UNKNOWN,
                    pe_file=pe_item.source_file,
                    pe_row=pe_item.row,
                    note=(
                        "PE 有定义但程序中找不到对应测试项"
                        if match.status is MatchStatus.UNMATCHED
                        else "存在多个同名候选，需人工确认"
                    ),
                )
            )
            continue

        item: LimitItem = match.item
        for side in sides:
            current = item.get_bound(zone, side)
            target = _pe_bound(pe_item, side)
            row = UpdateRow(
                function=item.function,
                test_item=item.test_item,
                unit=item.unit or pe_item.unit,
                zone=zone.value,
                side=side.value,
                pe_file=pe_item.source_file,
                pe_row=pe_item.row,
            )

            if _is_unset(target):
                row.status = UpdateStatus.NO_TARGET
                row.note = "PE 该测试项 0/0，待测未定"
                row.cur_lo = current.lo if current else None
                row.cur_hi = current.hi if current else None
                result.updates.append(row)
                continue

            if current is None:
                row.tgt_lo, row.tgt_hi = target.lo, target.hi
                row.status = UpdateStatus.CHANGE
                row.direction = Direction.FILL
                row.note = "程序中该温区/侧别无限值，需补"
                result.updates.append(row)
                continue

            row.cur_lo, row.cur_hi = current.lo, current.hi
            row.tgt_lo, row.tgt_hi = target.lo, target.hi
            row.d_lo = _delta(current.lo, target.lo)
            row.d_hi = _delta(current.hi, target.hi)
            row.direction = _combine(
                _edge_direction(current.lo, target.lo, "lo"),
                _edge_direction(current.hi, target.hi, "hi"),
            )
            row.status = (
                UpdateStatus.SAME if row.direction is Direction.SAME
                else UpdateStatus.CHANGE
            )
            result.updates.append(row)

        # -- three-way baseline check (PE's own "old program" column) -------
        # The PE "old program" column records the previous FT limit, so the
        # check only makes sense when the FT side is in play.
        if SourceType.FT not in sides:
            continue
        current_ft = item.get_bound(zone, SourceType.FT)
        baseline = BaselineRow(
            function=item.function,
            test_item=item.test_item,
            unit=item.unit or pe_item.unit,
            pe_old_lo=pe_item.old_lo,
            pe_old_hi=pe_item.old_hi,
            prog_lo=current_ft.lo if current_ft else None,
            prog_hi=current_ft.hi if current_ft else None,
            pe_file=pe_item.source_file,
            pe_row=pe_item.row,
        )
        lo_drift = (
            pe_item.old_lo is not None
            and baseline.prog_lo is not None
            and not _close(pe_item.old_lo, baseline.prog_lo)
        )
        hi_drift = (
            pe_item.old_hi is not None
            and baseline.prog_hi is not None
            and not _close(pe_item.old_hi, baseline.prog_hi)
        )
        baseline.drift = lo_drift or hi_drift
        result.baseline.append(baseline)

    changed = [r for r in result.updates if r.status is UpdateStatus.CHANGE]
    result.summary = {
        "PE 测试项": len(pe.items),
        "已对齐": sum(1 for m in matches if m.item is not None),
        "未匹配": len(result.unmatched),
        "需更新": len(changed),
        "其中放宽": sum(1 for r in changed if r.direction is Direction.LOOSEN),
        "其中收紧": sum(1 for r in changed if r.direction is Direction.TIGHTEN),
        "其中混合": sum(1 for r in changed if r.direction is Direction.MIXED),
        "程序缺项": sum(
            1 for r in result.updates if r.status is UpdateStatus.MISSING_IN_PROGRAM
        ),
        "PE待测未定(0/0)": sum(
            1 for r in result.updates if r.status is UpdateStatus.NO_TARGET
        ),
        "基线漂移": sum(1 for b in result.baseline if b.drift),
        "程序测试项": len(program.items),
    }
    return result
