"""Reproducible verification of a CTA8290 (.cpts) FT / QA / GU family.

The material directory is deliberately NOT part of this repository (see
``.gitignore``) -- it carries product numbers and measured data.  Point this
script at your own local copy instead:

    set LIMIT_COMPARE_MATERIAL_DIR=D:\\material        # once, or pass --material
    python scripts/verify_cpts_sample.py

The three sides are located by their ``_FT_`` / ``_QA_`` / ``_GU_`` file-name
token, so no product number is hardcoded anywhere.

Checks:
  * side detection (FT / QA / GU) -- real exports all have IsQAFile="0",
    so the side MUST come from the file-name token.
  * FV-1 FT-vs-QA coverage (QA must contain FT).
  * Scenario 4: GU must be strictly inside FT.
"""
import argparse
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.parsers.cpts import CptsParser, merge_sides
from src.engine.coverage import evaluate_coverage, anomalies
from src.model import SourceType, TempZone, ZONES

TOL = 1e-9


def locate(material, side):
    """First ``*_{side}_*.cpts`` under *material*; None when absent."""
    hits = sorted(glob.glob(os.path.join(material, "**", f"*_{side}_*.cpts"), recursive=True))
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--material", default=os.environ.get("LIMIT_COMPARE_MATERIAL_DIR", ""),
                    help="素材目录（含 .cpts 文件）；也可用环境变量 LIMIT_COMPARE_MATERIAL_DIR")
    ap.add_argument("--name", default="sample", help="报告里显示的产品代号（不进仓库，仅本地显示）")
    args = ap.parse_args()

    if not args.material or not os.path.isdir(args.material):
        raise SystemExit(
            "素材目录未指定或不存在。\n"
            "  用法: python scripts/verify_cpts_sample.py --material <dir>\n"
            "  或设置环境变量 LIMIT_COMPARE_MATERIAL_DIR=<dir>"
        )

    files = {side: locate(args.material, side) for side in ("FT", "QA", "GU")}
    missing = [s for s, p in files.items() if p is None]
    if missing:
        raise SystemExit(f"素材目录缺少 {', '.join(missing)} 侧 .cpts 文件: {args.material}")

    progs = {k: CptsParser.parse_file(v) for k, v in files.items()}
    for k, p in progs.items():
        sides = sorted({s.value for it in p.items for z, sd in it.bounds.items() for s in sd})
        print(f"{k:3s}: items={len(p.items)} funcs={len(p.functions)} sides={sides}")

    # FV-1: FT vs QA (QA must contain FT)
    merged = merge_sides(progs["FT"], progs["QA"], args.name)
    rep = evaluate_coverage(merged)
    print("\n=== FV-1 FT vs QA coverage ===")
    for k, v in rep.summary.items():
        print(f"  {k}: {v}")
    print(f"  anomalies (uncovered/error): {len(anomalies(rep))}")
    for e in anomalies(rep)[:10]:
        print("   ", e.item.function, e.item.test_item, "|", e.detail[:90])

    # Scenario 4: GU must be strictly inside FT
    merged_g = merge_sides(progs["FT"], progs["GU"], args.name)
    viol = []
    checked = 0
    for it in merged_g.items:
        for z in ZONES:
            f = it.get_bound(z, SourceType.FT)
            g = it.get_bound(z, SourceType.GU)
            if f is None or g is None or f.lo is None or f.hi is None or g.lo is None or g.hi is None:
                continue
            checked += 1
            if g.lo < f.lo - TOL or g.hi > f.hi + TOL:
                viol.append((it.function, it.test_item, z.value, f.lo, f.hi, g.lo, g.hi))
    print(f"\n=== Scenario 4 GU vs FT (GU must sit inside FT) ===")
    print(f"  compared zone-items: {checked} | violations (GU wider than FT): {len(viol)}")
    for v in viol[:15]:
        print(f"   {v[0]}/{v[1]} [{v[2]}] FT=[{v[3]},{v[4]}] GU=[{v[5]},{v[6]}]")


if __name__ == "__main__":
    main()
