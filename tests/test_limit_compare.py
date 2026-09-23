"""Regression tests for the parsers, alignment, comparison and analysis layers.

Focus is on the traps that already bit us once:
  * an empty cell must become ``None``, never ``0``;
  * ``0/0`` on the PE side means "limit not decided yet";
  * floating-point noise must never produce a direction verdict.
"""

import math
import os

import pytest

from src.engine.align import Aligner, norm
from src.engine.analysis import compute_stat, propose_gu
from src.engine.pe_compare import (
    Direction,
    UpdateStatus,
    compare_pe_to_program,
)
from src.model import (
    Bound,
    LimitItem,
    MachineType,
    PeItem,
    PeProgram,
    ProgramModel,
    SourceType,
    TempZone,
)
from src.parsers.datalog import parse_limit_tag
from src.parsers.numeric import parse_number
from src.parsers.pe_excel import parse_files

from real_material import real_cpts, real_pds

REAL_PDS = real_pds()
REAL_CPTS = real_cpts()


# --------------------------------------------------------------------- numeric
@pytest.mark.parametrize("raw", ["", None, "  ", "-", "N/A", "nan", "abc"])
def test_parse_number_blank_is_none(raw):
    assert parse_number(raw) is None


def test_parse_number_zero_is_zero_not_none():
    assert parse_number(0) == 0.0
    assert parse_number("0") == 0.0


def test_parse_number_handles_scientific_and_units():
    assert parse_number("1.5e3") == 1500.0
    assert parse_number("1,234.5") == 1234.5


# ---------------------------------------------------------------------- align
def _program(*names) -> ProgramModel:
    items = [
        LimitItem(function="IQ", test_item=n, unit="mA",
                  machine_type=MachineType.ETS88)
        for n in names
    ]
    return ProgramModel(id="p", name="p", machine_type=MachineType.ETS88,
                        functions=["IQ"], items=items)


def test_align_exact_and_prefix():
    program = _program("IQ_VDD33_3P15V_SW")
    aligner = Aligner(program)
    exact = aligner.match_one(PeItem(name="IQ_VDD33_3P15V_SW"))
    assert exact.status.value == "exact" and exact.item is not None
    prefix = aligner.match_one(PeItem(name="IQ_VDD33_3P15V_S"))
    assert prefix.status.value == "prefix" and prefix.item is not None


def test_align_unmatched_is_reported_not_dropped():
    aligner = Aligner(_program("ONLY_ONE"))
    match = aligner.match_one(PeItem(name="SOMETHING_ELSE"))
    assert match.status.value == "unmatched"
    assert match.item is None


def test_align_repeated_same_key_is_not_ambiguous():
    program = _program("DUP_ITEM")
    program.items.append(
        LimitItem(function="IQ", test_item="DUP_ITEM", machine_type=MachineType.ETS88)
    )
    match = Aligner(program).match_one(PeItem(name="DUP_ITEM"))
    assert match.item is not None


def test_norm_strips_separators():
    assert norm("LKG_FLT#_3P3V") == "LKGFLT3P3V"


# ------------------------------------------------------------------- compare
def _ft_program(lo, hi) -> ProgramModel:
    item = LimitItem(function="IQ", test_item="IQ_A", unit="mA",
                     machine_type=MachineType.ETS88)
    item.set_bound(TempZone.ROOM, SourceType.FT, Bound(lo=lo, hi=hi))
    item.set_bound(TempZone.ROOM, SourceType.QA, Bound(lo=lo - 1, hi=hi + 1))
    return ProgramModel(id="p", name="p", machine_type=MachineType.ETS88,
                        functions=["IQ"], items=[item])


def _pe(ft_lo, ft_hi) -> PeProgram:
    return PeProgram(id="PE", items=[PeItem(name="IQ_A", unit="mA",
                                            ft_lo=ft_lo, ft_hi=ft_hi,
                                            qa_lo=ft_lo - 1, qa_hi=ft_hi + 1)])


def _compare(program, pe):
    aligner = Aligner(program)
    matches = aligner.match_all(pe.items)
    return compare_pe_to_program(pe, program, matches, TempZone.ROOM)


def test_direction_tighten_and_loosen():
    result = _compare(_ft_program(22.5, 25.5), _pe(23.0, 25.0))
    ft_rows = [r for r in result.updates if r.side == "FT"]
    assert ft_rows[0].direction is Direction.TIGHTEN

    result = _compare(_ft_program(22.5, 25.5), _pe(21.5, 26.0))
    ft_rows = [r for r in result.updates if r.side == "FT"]
    assert ft_rows[0].direction is Direction.LOOSEN


def test_zero_zero_is_undecided_not_a_value():
    """A 0/0 pair means the PE limit is undecided -- it must not drive an update."""
    program = _ft_program(22.5, 25.5)
    pe = PeProgram(id="PE", items=[PeItem(name="IQ_A", unit="mA",
                                          ft_lo=0.0, ft_hi=0.0,
                                          qa_lo=0.0, qa_hi=0.0)])
    result = _compare(program, pe)
    assert all(r.status is UpdateStatus.NO_TARGET for r in result.updates)
    assert result.summary["PE待测未定(0/0)"] == 2
    assert result.summary["需更新"] == 0


def test_one_sided_zero_is_still_a_limit():
    program = _ft_program(22.5, 25.5)
    result = _compare(program, _pe(0.0, 30.0))
    ft_rows = [r for r in result.updates if r.side == "FT"]
    assert ft_rows[0].status is UpdateStatus.CHANGE


def test_floating_point_noise_never_produces_a_direction():
    noisy = 22.5 + 1e-13
    result = _compare(_ft_program(22.5, 25.5), _pe(noisy, 25.5))
    ft_rows = [r for r in result.updates if r.side == "FT"]
    assert ft_rows[0].direction is Direction.SAME
    assert ft_rows[0].status is UpdateStatus.SAME


def test_both_sides_compared():
    result = _compare(_ft_program(22.5, 25.5), _pe(21.5, 25.5))
    assert {r.side for r in result.updates} == {"FT", "QA"}


# ------------------------------------------------------------------ analysis
def test_cpk_reasonable_and_tight():
    # sigma ~= 0.0707, so 3*sigma ~= 0.212; a +/-0.32 window lands Cpk ~= 1.5.
    values = [10.0, 10.1, 9.9, 10.05, 9.95]
    stat = compute_stat("X", "V", values, 9.68, 10.32)
    assert stat.verdict.value == "合理"
    assert 1.33 <= stat.cpk < 2.0

    tight = compute_stat("X", "V", values, 9.99, 10.01)
    assert tight.verdict.value == "过紧"

    loose = compute_stat("X", "V", values, 9.0, 11.0)
    assert loose.verdict.value == "过松"


def test_cpk_no_limit_and_no_data():
    assert compute_stat("X", "V", [1.0, 2.0], None, None).verdict.value == "无限值"
    assert compute_stat("X", "V", [], 1.0, 2.0).verdict.value == "数据不足"


def test_gu_tighter_and_looser():
    values = [10.0, 10.1, 9.9, 10.05, 9.95]
    ok = propose_gu("X", "V", values, 9.0, 11.0, k=3.0)
    assert ok.verdict.value.startswith("GU 更紧")
    assert ok.gu_lo > 9.0 and ok.gu_hi < 11.0

    bad = propose_gu("X", "V", values, 9.99, 10.01, k=3.0)
    assert bad.verdict.value.startswith("GU 比 FT 宽")


# ------------------------------------------------------------------- datalog
@pytest.mark.parametrize("tag,side,zone", [
    ("FTRoom", SourceType.FT, TempZone.ROOM),
    ("QA", SourceType.QA, TempZone.ROOM),
    ("FTHot", SourceType.FT, TempZone.HOT),
    ("QACold", SourceType.QA, TempZone.COLD),
])
def test_limit_tag_decoding(tag, side, zone):
    assert parse_limit_tag(tag) == (side, zone)


# ------------------------------------------------------------- real fixtures
@pytest.mark.skipif(not REAL_PDS, reason="sample .pds not available")
def test_real_pds_parses_with_both_sides():
    from src.parsers.pds import PdsParser

    program = PdsParser.parse_file(REAL_PDS)
    assert program.machine_type is MachineType.ETS88
    assert len(program.items) > 1000
    sample = program.items[0]
    assert sample.get_bound(TempZone.ROOM, SourceType.FT) is not None


@pytest.mark.skipif(not REAL_CPTS, reason="sample .cpts not available")
def test_real_cpts_parses():
    from src.parsers.cpts import CptsParser

    program = CptsParser.parse_file(REAL_CPTS)
    assert program.machine_type is MachineType.CTA8290
    assert len(program.items) > 50


def test_pe_parse_skips_excel_lock_files():
    """Excel 打开 PE 表时会留下 ~$xxx.xlsx 属主锁文件，必须跳过而不是崩在 PermissionError。"""
    program = parse_files(["~$4. IQ limit_rev1.0.xlsx"], "PE")
    assert program.items == []
    assert program.source_files == []
