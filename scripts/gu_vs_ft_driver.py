"""Verification driver: GU datalog vs the FT limits coming from the program.

A datalog run under QA/Room limits (``Current Limit: QARoom``) only yields QA
limits when reverse-engineered. A guardband must be judged against the *FT*
limit, so we pull FT/Room limits from the ETS88 .pds program and compare the
measured ``mean +/- k*sigma`` against FT.

Material is NOT part of this repo (see ``.gitignore``) -- pass your own paths:

    set LIMIT_COMPARE_MATERIAL_DIR=D:\\material
    python scripts/gu_vs_ft_driver.py
"""
import argparse
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.engine.analysis import compute_stat, propose_gu, summarise, summarise_gu
from src.export.analysis_report import export_analysis
from src.parsers.datalog import parse_datalog
from src.parsers.pds import PdsParser
from src.model import SourceType, TempZone

K = 3.0  # GU sigma multiplier


def _first(pattern, root):
    hits = sorted(glob.glob(os.path.join(root, "**", pattern), recursive=True))
    return hits[0] if hits else None


def _args():
    ap = argparse.ArgumentParser(description="GU datalog vs FT limit check")
    ap.add_argument("--material", default=os.environ.get("LIMIT_COMPARE_MATERIAL_DIR", ""),
                    help="素材目录；也可用环境变量 LIMIT_COMPARE_MATERIAL_DIR")
    ap.add_argument("--datalog", default="", help="GU datalog .csv（默认：素材目录下第一个 *.csv）")
    ap.add_argument("--program", default="", help="ETS88 .pds 程序（默认：素材目录下第一个 *.pds）")
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "GU_real_vs_FT.xlsx"))
    return ap.parse_args()


def norm(s: str) -> str:
    return (s or "").strip().lower()


def main():
    args = _args()
    datalog = args.datalog or _first("*.csv", args.material)
    program_pds = args.program or _first("*.pds", args.material)
    if not datalog or not os.path.exists(datalog):
        raise SystemExit("未找到 datalog .csv：请传 --datalog <run.csv> 或 --material <dir>")
    if not program_pds or not os.path.exists(program_pds):
        raise SystemExit("未找到 .pds 程序：请传 --program <file.pds> 或 --material <dir>")

    data = parse_datalog(datalog)
    program = PdsParser.parse_file(program_pds)

    # FT/Room limits from the program, keyed by normalised test item name.
    # A test item name can appear in several functions (e.g. KELVIN_VSEN1 in
    # both HW_Checker [500,2500] and Contact [0.1,4.0]); the datalog does NOT
    # carry the function name, so we disambiguate by matching the QA limit that
    # was actually applied (reverse-engineered from the datalog) to the program.
    candidates = {}
    for item in program.items:
        ft = item.get_bound(TempZone.ROOM, SourceType.FT)
        qa = item.get_bound(TempZone.ROOM, SourceType.QA)
        if ft is None:
            continue
        candidates.setdefault(norm(item.test_item), []).append(
            (item.function, qa.lo if qa else None, qa.hi if qa else None, ft.lo, ft.hi)
        )

    # Reverse-engineered QA limits actually applied in the run.
    qa_by_name = {}
    for it in data.items:
        qa_by_name.setdefault(norm(it.name), (it.lo, it.hi))

    stats = []
    gu = []
    real_fail = []  # GU wider than FT -> guardband invalid
    ambiguous = 0
    for name, values in data.measurements.items():
        if len(values) < 2:
            continue
        qlo, qhi = qa_by_name.get(norm(name), (None, None))
        if qlo == 0 and qhi == 0:
            qlo = qhi = None
        stats.append(compute_stat(name, "", values, qlo, qhi))

        # Disambiguate function by the QA limit actually applied in the run.
        cands = candidates.get(norm(name))
        ft_lo, ft_hi = None, None
        if cands:
            if len(cands) == 1:
                ft_lo, ft_hi = cands[0][3], cands[0][4]
            else:
                best = None
                best_d = None
                for func, clo, chi, flo, fhi in cands:
                    d = 0.0
                    if qlo is not None and clo is not None:
                        d += abs(qlo - clo)
                    if qhi is not None and chi is not None:
                        d += abs(qhi - chi)
                    if best_d is None or d < best_d:
                        best_d, best = d, (flo, fhi)
                ft_lo, ft_hi = best
                ambiguous += 1
        if ft_lo == 0 and ft_hi == 0:
            ft_lo = ft_hi = None
        g = propose_gu(name, "", values, ft_lo, ft_hi, k=K)
        gu.append(g)
        if g.verdict.value == "GU 比 FT 宽(失效)":
            real_fail.append((name, g.n, g.mean, g.sigma, g.gu_lo, g.gu_hi, ft_lo, ft_hi))

    stats.sort(key=lambda s: (s.cpk is None, s.cpk if s.cpk is not None else 0))
    gu.sort(key=lambda g: (g.verdict.value, g.name))

    meta = [
        ("来源 datalog", data.source_file),
        ("程序名", data.program_name),
        ("阶段 / 温区", data.stage_label() + " (datalog 反解=QA)"),
        ("FT 来源", os.path.basename(program_pds)),
        ("DUT 样本数", str(len(data.bins))),
        ("GU sigma 倍数", f"k = {K}"),
        ("GU 基准", "FT/Room (来自 PDS) -- 真 GU 校验"),
    ]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    export_analysis(args.out, stats, gu, meta, summarise(stats), summarise_gu(gu))

    print("=== Cpk vs QA(实际施加) ===")
    for k, v in sorted(summarise(stats).items(), key=lambda kv: -kv[1]):
        print(f"  Cpk {k}: {v}")
    print("=== 真 GU vs FT (来自 PDS) ===")
    for k, v in sorted(summarise_gu(gu).items(), key=lambda kv: -kv[1]):
        print(f"  GU  {k}: {v}")
    print(f"\n需要函数消歧的项数(同名多 function): {ambiguous}")
    print(f"真 GU 失效(比 FT 宽) 项数: {len(real_fail)}")
    for r in real_fail[:25]:
        print(f"  {r[0]:32s} n={r[1]} mean={r[2]:.4g} sig={r[3]:.4g} "
              f"GU=[{r[4]:.4g},{r[5]:.4g}] FT=[{r[6]},{r[7]}]")
    print(f"\n报告: {args.out}")


if __name__ == "__main__":
    main()
