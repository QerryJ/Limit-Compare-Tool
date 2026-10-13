"""Regression tests for the O2-O5 decisions (M3 scope).

  * O2 -- coverage distinguishes 整体缺失 vs 局部缺失, rate over comparable zones
  * O3 -- GU must sit strictly inside FT (engine + report)
  * O4 -- analyze_datalog --ft-program drives a true GU-vs-FT baseline
  * O5 -- Aligner disambiguates same-named datalog items by reverse-engineered limit
"""

import os

import pytest

from src.engine.align import Aligner, MatchStatus
from src.engine.coverage import (
    CoverageStatus,
    evaluate_coverage,
    evaluate_gu_vs_ft,
    promote_qa_to_gu,
    GuVsFtStatus,
)
from src.model import (
    Bound,
    LimitItem,
    MachineType,
    ProgramModel,
    SourceType,
    TempZone,
)
from src.parsers.datalog import DatalogItem


def _ft_qa_item(name, function, ft, qa, zone=TempZone.ROOM):
    item = LimitItem(function=function, test_item=name, unit="V",
                     machine_type=MachineType.ETS88)
    if ft is not None:
        item.set_bound(zone, SourceType.FT, Bound(lo=ft[0], hi=ft[1]))
    if qa is not None:
        item.set_bound(zone, SourceType.QA, Bound(lo=qa[0], hi=qa[1]))
    return item


# --------------------------------------------------------------------- O2
def test_partial_missing_is_not_overall_and_rate_stays_sane():
    # A: covered on Room, but QA absent on Hot/Cold -> 局部缺失
    item_a = _ft_qa_item("A", "IQ", (2.0, 3.0), (1.5, 3.5), TempZone.ROOM)
    # B: covered on ALL three zones -> 覆盖 (the contrast case)
    item_b = LimitItem(function="IQ", test_item="B", unit="V",
                       machine_type=MachineType.ETS88)
    for z in (TempZone.ROOM, TempZone.HOT, TempZone.COLD):
        item_b.set_bound(z, SourceType.FT, Bound(lo=2.0, hi=3.0))
        item_b.set_bound(z, SourceType.QA, Bound(lo=1.5, hi=3.5))
    program = ProgramModel(
        id="p", name="p", machine_type=MachineType.ETS88,
        functions=["IQ"], items=[item_a, item_b],
    )
    report = evaluate_coverage(program)  # default = all three zones
    by_name = {i.item.test_item: i for i in report.items}
    assert by_name["A"].status is CoverageStatus.PARTIAL
    assert by_name["B"].status is CoverageStatus.COVERED
    # A contributes only its Room zone as comparable; B contributes all three,
    # all covered -> coverage over comparable zones = 100% (no false 0%)
    assert report.summary["覆盖率"] == 100.0
    assert report.summary["可比温区数"] == 4  # 1 from A + 3 from B
    assert report.summary[CoverageStatus.PARTIAL.value] == 1
    assert report.summary.get(CoverageStatus.MISSING.value, 0) == 0


def test_overall_missing_when_one_side_absent_everywhere():
    program = ProgramModel(
        id="p", name="p", machine_type=MachineType.ETS88, functions=["IQ"],
        items=[_ft_qa_item("A", "IQ", (2.0, 3.0), None)],
    )
    report = evaluate_coverage(program, [TempZone.ROOM])
    assert report.items[0].status is CoverageStatus.MISSING
    assert report.summary[CoverageStatus.MISSING.value] == 1


def test_uncovered_still_dominates_partial():
    # Room uncovered (real gap) + Hot/Cold missing -> UNCOVERED wins
    item = _ft_qa_item("A", "IQ", (2.0, 3.0), (2.2, 2.8), TempZone.ROOM)
    item.set_bound(TempZone.HOT, SourceType.FT, Bound(lo=2.0, hi=3.0))
    program = ProgramModel(id="p", name="p", machine_type=MachineType.ETS88,
                           functions=["IQ"], items=[item])
    report = evaluate_coverage(program)
    assert report.items[0].status is CoverageStatus.UNCOVERED


# --------------------------------------------------------------------- O3
def test_gu_must_sit_inside_ft():
    item_ok = LimitItem(function="IQ", test_item="OK", machine_type=MachineType.ETS88)
    item_ok.set_bound(TempZone.ROOM, SourceType.FT, Bound(lo=10.0, hi=30.0))
    item_ok.set_bound(TempZone.ROOM, SourceType.GU, Bound(lo=12.0, hi=28.0))
    item_bad = LimitItem(function="IQ", test_item="BAD", machine_type=MachineType.ETS88)
    item_bad.set_bound(TempZone.ROOM, SourceType.FT, Bound(lo=625.0, hi=794.0))
    item_bad.set_bound(TempZone.ROOM, SourceType.GU, Bound(lo=670.0, hi=795.0))
    program = ProgramModel(id="p", name="p", machine_type=MachineType.ETS88,
                           functions=["IQ"], items=[item_ok, item_bad])
    report = evaluate_gu_vs_ft(program, [TempZone.ROOM])
    by_name = {i.item.test_item: i for i in report.items}
    assert by_name["OK"].status is GuVsFtStatus.INSIDE
    assert by_name["BAD"].status is GuVsFtStatus.OUTSIDE
    assert report.summary[GuVsFtStatus.OUTSIDE.value] == 1
    # the BAD item must call out the high-edge overrun
    bad_zone = by_name["BAD"].zones[0]
    assert "高边超FT" in bad_zone.detail


# --------------------------------------------------------------------- O3 (ETS88 GU 来自 QA)
def test_ets88_gu_from_qa_is_recognized():
    # 模拟 ETS88 .pds：只有 FT + QA，无独立 GU 列
    item = LimitItem(function="IQ", test_item="X", machine_type=MachineType.ETS88)
    item.set_bound(TempZone.ROOM, SourceType.FT, Bound(lo=10.0, hi=30.0))
    item.set_bound(TempZone.ROOM, SourceType.QA, Bound(lo=12.0, hi=28.0))  # QA 即 GU
    program = ProgramModel(id="p", name="p", machine_type=MachineType.ETS88,
                           functions=["IQ"], items=[item])
    promote_qa_to_gu(program)
    assert item.get_bound(TempZone.ROOM, SourceType.GU) is not None
    report = evaluate_gu_vs_ft(program, [TempZone.ROOM])
    assert report.items[0].status is GuVsFtStatus.INSIDE
    assert report.summary.get(GuVsFtStatus.MISSING.value, 0) == 0


def test_ets88_gu_promotion_skips_when_qa_missing():
    item = LimitItem(function="IQ", test_item="X", machine_type=MachineType.ETS88)
    item.set_bound(TempZone.ROOM, SourceType.FT, Bound(lo=10.0, hi=30.0))
    # 无 QA -> 无可补位的 GU
    program = ProgramModel(id="p", name="p", machine_type=MachineType.ETS88,
                           functions=["IQ"], items=[item])
    promote_qa_to_gu(program)
    assert item.get_bound(TempZone.ROOM, SourceType.GU) is None
    report = evaluate_gu_vs_ft(program, [TempZone.ROOM])
    assert report.items[0].status is GuVsFtStatus.MISSING


def test_ets88_gu_promotion_does_not_override_real_gu():
    # CTA8290 已有真实 GU（_GU_ 文件），promote 不应被 QA 覆盖
    item = LimitItem(function="IQ", test_item="X", machine_type=MachineType.CTA8290)
    item.set_bound(TempZone.ROOM, SourceType.FT, Bound(lo=10.0, hi=30.0))
    item.set_bound(TempZone.ROOM, SourceType.QA, Bound(lo=5.0, hi=35.0))
    item.set_bound(TempZone.ROOM, SourceType.GU, Bound(lo=12.0, hi=28.0))
    program = ProgramModel(id="p", name="p", machine_type=MachineType.CTA8290,
                           functions=["IQ"], items=[item])
    promote_qa_to_gu(program)
    gu = item.get_bound(TempZone.ROOM, SourceType.GU)
    assert gu.lo == 12.0 and gu.hi == 28.0  # 真实 GU 保留，未被 QA 覆盖


# --------------------------------------------------------------------- O5
def _two_function_program():
    return ProgramModel(
        id="p", name="p", machine_type=MachineType.ETS88,
        functions=["HW_Checker", "Contact"],
        items=[
            _ft_qa_item("KELVIN_VSEN1", "HW_Checker", (500.0, 2500.0), None),
            _ft_qa_item("KELVIN_VSEN1", "Contact", None, (0.1, 4.0)),
        ],
    )


def test_align_datalog_disambiguates_by_reverse_engineered_limit():
    program = _two_function_program()
    aligner = Aligner(program)
    # datalog was run with QA/Room = [0.1, 4.0] -> must pick Contact, not HW_Checker
    matches = aligner.align_datalog_items(
        [DatalogItem(name="KELVIN_VSEN1", lo=0.1, hi=4.0)],
        TempZone.ROOM, SourceType.QA,
    )
    assert matches[0].resolved
    assert matches[0].item.function == "Contact"
    assert matches[0].status is MatchStatus.HINT


def test_align_datalog_unmatched_and_exact():
    program = _two_function_program()
    aligner = Aligner(program)
    unmatched = aligner.align_datalog_items(
        [DatalogItem(name="DOES_NOT_EXIST", lo=1.0, hi=2.0)],
        TempZone.ROOM, SourceType.QA,
    )
    assert unmatched[0].status.value == "unmatched"

    single = ProgramModel(
        id="p", name="p", machine_type=MachineType.ETS88, functions=["IQ"],
        items=[_ft_qa_item("UNIQUE", "IQ", (1.0, 2.0), (0.5, 2.5))],
    )
    resolved = Aligner(single).align_datalog_items(
        [DatalogItem(name="UNIQUE", lo=1.0, hi=2.0)],
        TempZone.ROOM, SourceType.FT,
    )
    assert resolved[0].status.value == "exact"
    assert resolved[0].item.function == "IQ"


# --------------------------------------------------------------------- O4
def _write_minimal_cpts(path, side_token, items):
    import xml.etree.ElementTree as ET

    root = ET.Element("program", name="mini")
    for func, params in items.items():
        f = ET.SubElement(root, "function", name=func)
        for pname, (lo, hi), unit in params:
            ET.SubElement(f, "param", name=pname, limitmin=str(lo),
                          limitmax=str(hi), unit=unit, subn="1")
    body = ET.tostring(root, encoding="unicode")
    # file name must carry the side token so _detect_side sees it
    fname = os.path.join(os.path.dirname(path), f"mini_{side_token}_X.cpts")
    with open(fname, "w", encoding="utf-8") as fh:
        fh.write(body)
    return fname


def _write_minimal_datalog(path):
    rows = [
        "Current Limit: QARoom",
        "Test Name,mini",
        "Test Name,ItemA,ItemB",
        "Test Number,1,2",
        "Lower Limit,10,20",
        "Upper Limit,30,40",
        "Units,V,V",
        "1,14,25",
        "2,16,26",
        "3,15,24",
        "4,14,25",
        "5,16,26",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows))


def test_ft_program_switches_gu_baseline_to_ft(tmp_path, capsys):
    from scripts.analyze_datalog import main as analyze_main

    # FT side: ItemA has a NARROW limit [14.5, 15.5] -> GU (mean +/- 3sigma)
    # from the datalog measurements will fall OUTSIDE FT (real GU failure).
    ft_file = _write_minimal_cpts(
        os.path.join(tmp_path, "x.cpts"), "FT",
        {"FuncA": [("ItemA_V", (14.5, 15.5), "V")],
         "FuncB": [("ItemB_V", (10.0, 30.0), "V")]},
    )
    datalog = os.path.join(tmp_path, "run.csv")
    _write_minimal_datalog(datalog)
    out_ft = os.path.join(tmp_path, "ft.xlsx")

    analyze_main(["--datalog", datalog, "--ft-program", ft_file, "--out", out_ft])
    out = capsys.readouterr().out
    assert "GU 比 FT 宽(失效)" in out, out

    # Without --ft-program, baseline is the datalog as-run QA limit [10, 30],
    # inside which the same GU is comfortably TIGHTER -> no failure printed.
    out_pseudo = os.path.join(tmp_path, "pseudo.xlsx")
    capsys.readouterr()
    analyze_main(["--datalog", datalog, "--out", out_pseudo])
    out2 = capsys.readouterr().out
    assert "GU 比 FT 宽(失效)" not in out2, out2
    assert "GU 更紧" in out2, out2
