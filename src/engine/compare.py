"""FV-4: before-vs-after program change review.

The point is to catch accidental edits when a limit change is applied: every
changed item gets a *directional* verdict, and **loosening is the real risk**
(loosened limits let bad parts through), so it is what the report leads with.

Rule inherited from the prototype and kept deliberately flat: a mixed change
(Lo tightened but Hi loosened) is classified as ``LOOSER``, with the mixed
nature spelled out in ``change_detail`` -- no separate enum value.
"""

from typing import Dict, List, Optional

from src.model import (
    Bound,
    CellDiff,
    ChangeDirection,
    CompareReport,
    ItemDiff,
    LimitItem,
    ProgramModel,
    SourceType,
    TempZone,
    ZONES,
)

TOLERANCE = 1e-9


def _close(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(TOLERANCE, TOLERANCE * abs(b))


def _edge_move(a: Optional[float], b: Optional[float], edge: str) -> Optional[str]:
    """Return 'tighten' / 'loosen' / None (unchanged or not comparable)."""
    if a is None or b is None:
        return None
    if _close(a, b):
        return None
    if edge == "lo":
        return "tighten" if b > a else "loosen"
    return "tighten" if b < a else "loosen"


def _combine(moves: List[Optional[str]]) -> ChangeDirection:
    real = [m for m in moves if m]
    if not real:
        return ChangeDirection.SAME
    if all(m == "tighten" for m in real):
        return ChangeDirection.TIGHTER
    if all(m == "loosen" for m in real):
        return ChangeDirection.LOOSER
    return ChangeDirection.MIXED


def compare_item(
    base: LimitItem, new: LimitItem, zones: List[TempZone]
) -> ItemDiff:
    """Directional diff for one aligned item across the selected zones."""
    diff = ItemDiff(
        function=new.function, test_item=new.test_item, unit=new.unit
    )
    moves: List[Optional[str]] = []
    notes: List[str] = []

    for zone in zones:
        for side in (SourceType.FT, SourceType.QA):
            a = base.get_bound(zone, side)
            b = new.get_bound(zone, side)
            if a is None and b is None:
                continue
            if a is None or b is None:
                diff.zones.append(
                    CellDiff(zone=zone, side=side, changed=True)
                )
                notes.append(f"{zone.value}/{side.value} 单侧存在")
                continue
            lo_move = _edge_move(a.lo, b.lo, "lo")
            hi_move = _edge_move(a.hi, b.hi, "hi")
            moves.extend([lo_move, hi_move])
            changed = bool(lo_move or hi_move)
            if lo_move:
                notes.append(f"{zone.value}/{side.value} Lo {a.lo}→{b.lo} ({'收紧' if lo_move == 'tighten' else '放宽'})")
            if hi_move:
                notes.append(f"{zone.value}/{side.value} Hi {a.hi}→{b.hi} ({'收紧' if hi_move == 'tighten' else '放宽'})")
            diff.zones.append(
                CellDiff(
                    zone=zone, side=side,
                    a_lo=a.lo, a_hi=a.hi, b_lo=b.lo, b_hi=b.hi,
                    changed=changed,
                    delta_lo=None if (a.lo is None or b.lo is None) else b.lo - a.lo,
                    delta_hi=None if (a.hi is None or b.hi is None) else b.hi - a.hi,
                )
            )

    diff.direction = _combine(moves)
    diff.change_detail = "；".join(notes)
    return diff


def compare_programs(
    base: ProgramModel, new: ProgramModel, zones: List[TempZone] = None
) -> CompareReport:
    """Compare two programs (base = before, new = after) item by item."""
    zones = list(zones) if zones else list(ZONES)
    base_index = {item.key(): item for item in base.items}
    new_index = {item.key(): item for item in new.items}

    diffs: List[ItemDiff] = []
    for key, item in new_index.items():
        if key not in base_index:
            diffs.append(ItemDiff(
                function=item.function, test_item=item.test_item, unit=item.unit,
                direction=ChangeDirection.ONLY_IN_B, change_detail="仅新程序有（新增）",
            ))
            continue
        diffs.append(compare_item(base_index[key], item, zones))
    for key, item in base_index.items():
        if key not in new_index:
            diffs.append(ItemDiff(
                function=item.function, test_item=item.test_item, unit=item.unit,
                direction=ChangeDirection.ONLY_IN_A, change_detail="仅旧程序有（已移除）",
            ))

    summary: Dict[str, int] = {}
    for diff in diffs:
        summary[diff.direction.value] = summary.get(diff.direction.value, 0) + 1
    summary["放宽风险"] = summary.get(ChangeDirection.LOOSER.value, 0) + summary.get(
        ChangeDirection.MIXED.value, 0
    )
    return CompareReport(base_id=base.id, compare_id=new.id, items=diffs, summary=summary)


def risky_changes(report: CompareReport) -> List[ItemDiff]:
    """Items where the change loosened a limit (or is mixed) -- review first."""
    return [
        d for d in report.items
        if d.direction in (ChangeDirection.LOOSER, ChangeDirection.MIXED)
    ]
