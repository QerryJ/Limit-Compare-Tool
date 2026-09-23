"""Core data model for the Limit Compare Tool.

Deliberately stdlib-only so parsers / engines / exporters can be tested and
reused without any GUI dependency.

Design contract:
  * ``LimitValue = float | None``. ``None`` means "not set" and must NEVER be
    stored or compared as ``0``.
  * Alignment key for a program test item: ``function + '|' + test_item``.
  * ``bounds`` layout: ``bounds[TempZone][SourceType] = Bound``, containing only
    the (zone, side) pairs actually present in the source file.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class MachineType(Enum):
    ETS88 = "ETS88"
    CTA8290 = "CTA8290"


class SourceType(Enum):
    FT = "FT"
    QA = "QA"
    GU = "GU"


class TempZone(Enum):
    ROOM = "Room"
    HOT = "Hot"
    COLD = "Cold"


ZONES: List[TempZone] = [TempZone.ROOM, TempZone.HOT, TempZone.COLD]

LimitValue = Optional[float]


@dataclass
class Bound:
    """A (lo, hi) numeric limit pair for one zone and one source side."""

    lo: LimitValue = None
    hi: LimitValue = None

    def is_empty(self) -> bool:
        return self.lo is None and self.hi is None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Bound):
            return NotImplemented
        return self.lo == other.lo and self.hi == other.hi

    def __hash__(self) -> int:
        return hash((self.lo, self.hi))


@dataclass
class LimitItem:
    """One test item inside a program."""

    function: str
    test_item: str
    unit: str = ""
    sub_test_nmbr: str = ""
    bounds: Dict = field(default_factory=dict)
    source_files: List[str] = field(default_factory=list)
    machine_type: MachineType = MachineType.ETS88

    def key(self) -> str:
        return f"{self.function}|{self.test_item}"

    def get_bound(self, zone: TempZone, side: SourceType) -> Optional[Bound]:
        return self.bounds.get(zone, {}).get(side)

    def set_bound(self, zone: TempZone, side: SourceType, bound: Bound) -> None:
        self.bounds.setdefault(zone, {})[side] = bound


@dataclass
class ProgramModel:
    """A whole test program (one .pds, or one .cpts side, or merged FT+QA)."""

    id: str
    name: str
    machine_type: MachineType
    functions: List[str] = field(default_factory=list)
    items: List[LimitItem] = field(default_factory=list)

    def get_item_by_key(self, key: str) -> Optional[LimitItem]:
        for it in self.items:
            if it.key() == key:
                return it
        return None


@dataclass
class PeItem:
    """One row of the PE specification spreadsheet.

    The PE sheet carries the *target* FT and QA limits plus the PE's own record
    of the previous program value (``old_*``), which is what enables the
    three-way baseline check.
    """

    name: str
    unit: str = ""
    ate_test_no: str = ""
    ft_lo: LimitValue = None
    ft_hi: LimitValue = None
    qa_lo: LimitValue = None
    qa_hi: LimitValue = None
    old_lo: LimitValue = None
    old_hi: LimitValue = None
    guardband: LimitValue = None
    source_file: str = ""
    row: int = 0


@dataclass
class PeProgram:
    """All PE rows collected from one or more spreadsheets."""

    id: str
    items: List[PeItem] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# FV-1: FT vs QA coverage inside one program
# ---------------------------------------------------------------------------
class CoverageStatus(Enum):
    """Single-zone FT-vs-QA verdict.

    * ``COVERED``    -- the QA interval fully contains the FT interval.
    * ``UNCOVERED``  -- it does not (the QA guard band is too loose).
    * ``MISSING``    -- *整体缺失*: no comparable zone at all (one side is
      entirely absent), so the item cannot be judged on any zone.
    * ``PARTIAL``    -- *局部缺失*: covered on some zones but missing on
      others; the coverage ratio is scored over the comparable zones only.
    * ``ERROR``      -- the FT interval itself is reversed (``lo > hi``).
    """

    COVERED = "覆盖"
    UNCOVERED = "未覆盖"
    MISSING = "整体缺失"
    PARTIAL = "局部缺失"
    ERROR = "数据异常"


@dataclass
class ZoneCoverage:
    zone: TempZone
    status: CoverageStatus
    ft: Optional[Bound] = None
    qa: Optional[Bound] = None
    # Sign convention: POSITIVE == there is margin.
    gb_lo: Optional[float] = None        # FT.lo - QA.lo
    gb_hi: Optional[float] = None        # QA.hi - FT.hi
    margin_lo: Optional[float] = None    # percent of the FT span
    margin_hi: Optional[float] = None
    detail: str = ""


@dataclass
class ItemCoverage:
    item: LimitItem
    zones: List[ZoneCoverage] = field(default_factory=list)
    status: Optional[CoverageStatus] = None
    detail: str = ""


@dataclass
class CoverageReport:
    program_id: str = ""
    items: List[ItemCoverage] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scenario 4: GU limit must sit strictly INSIDE the FT limit
# ---------------------------------------------------------------------------
class GuVsFtStatus(Enum):
    """Single-zone GU-vs-FT verdict (direction reversed vs FV-1).

    * ``INSIDE``   -- GU interval is strictly inside FT (guard band valid).
    * ``OUTSIDE``  -- GU is wider than FT somewhere (cannot prove setup healthy).
    * ``MISSING``  -- GU or FT is absent on this zone, cannot be judged.
    """

    INSIDE = "GU 在 FT 内(合格)"
    OUTSIDE = "GU 比 FT 宽(失效)"
    MISSING = "无法判定"


@dataclass
class GuVsFtZone:
    zone: TempZone
    status: GuVsFtStatus
    ft: Optional[Bound] = None
    gu: Optional[Bound] = None
    detail: str = ""


@dataclass
class GuVsFtItem:
    item: LimitItem
    zones: List[GuVsFtZone] = field(default_factory=list)
    status: Optional[GuVsFtStatus] = None
    detail: str = ""


@dataclass
class GuVsFtReport:
    program_id: str = ""
    items: List[GuVsFtItem] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# FV-4: before-vs-after program change review
# ---------------------------------------------------------------------------
class ChangeDirection(Enum):
    """Directional verdict for one changed item.

    Deliberately flat: a mixed change (Lo tightened but Hi loosened) is
    classified as ``LOOSER`` because a real loosening risk exists; the mixed
    nature is spelled out in ``ItemDiff.change_detail``.
    """

    TIGHTER = "收紧"
    LOOSER = "放宽"
    MIXED = "混合"
    SAME = "相同"
    ONLY_IN_A = "移除"
    ONLY_IN_B = "新增"


@dataclass
class CellDiff:
    zone: TempZone
    side: SourceType
    a_lo: Optional[float] = None
    a_hi: Optional[float] = None
    b_lo: Optional[float] = None
    b_hi: Optional[float] = None
    changed: bool = False
    delta_lo: Optional[float] = None
    delta_hi: Optional[float] = None


@dataclass
class ItemDiff:
    function: str = ""
    test_item: str = ""
    unit: str = ""
    direction: ChangeDirection = ChangeDirection.SAME
    zones: List[CellDiff] = field(default_factory=list)
    change_detail: str = ""


@dataclass
class CompareReport:
    base_id: str = ""
    compare_id: str = ""
    items: List[ItemDiff] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
