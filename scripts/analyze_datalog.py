"""Datalog reasonableness analysis: Cpk against the limits actually used, plus
GU (golden unit) limit proposals derived from the measured spread.

    python analyze_datalog.py --datalog <run.csv> --out <analysis.xlsx>

The GU limit is ``mean +/- k * sigma`` (default k = 3, matching the
"30Pcs 3sigma" convention) and is then checked to sit strictly inside the FT
limit -- a GU limit wider than FT cannot prove the setup is healthy.

Note: a *rejects* datalog is a biased sample. Cpk and GU from such a run are
only indicative; use a normal (or dedicated GU) lot for the real numbers.
"""

import argparse
import os
import sys

from src.engine.align import Aligner
from src.engine.analysis import (
    compute_stat,
    propose_gu,
    summarise,
    summarise_gu,
)
from src.export.analysis_report import export_analysis
from src.model import SourceType
from src.parsers.datalog import parse_datalog
from src.parsers.pds import PdsParser

try:  # CTA8290 (and other) parsers are optional for the core path
    from src.parsers.cpts import CptsParser
except Exception:  # pragma: no cover
    CptsParser = None

MIN_NOTE = "样本数偏少，结论仅作参考（GU 建议 >= 30 颗）"


def _load_program(path: str):
    if path.lower().endswith(".pds"):
        return PdsParser.parse_file(path)
    if CptsParser is None:
        raise ValueError("CptsParser 不可用，无法解析 .cpts")
    return CptsParser.parse_file(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Datalog Cpk + GU limit analysis")
    parser.add_argument("--datalog", required=True)
    parser.add_argument("--out", default="datalog_analysis.xlsx")
    parser.add_argument("--ft-program", default=None,
                        help="FT 程序文件(.pds/.cpts)：GU 基准改为 FT 而非 datalog 的 "
                             "as-run limit，实现真 GU-vs-FT 校验")
    parser.add_argument("--sigma-k", type=float, default=3.0,
                        help="GU sigma multiplier (default 3.0)")
    parser.add_argument("--loose", type=float, default=2.0,
                        help="Cpk at or above this is 过松")
    parser.add_argument("--tight", type=float, default=1.33,
                        help="Cpk below this is 过紧")
    parser.add_argument("--skew", type=float, default=0.30,
                        help="off-centre ratio threshold")
    parser.add_argument("--min-n", type=int, default=2,
                        help="skip items with fewer samples")
    args = parser.parse_args(argv)

    data = parse_datalog(args.datalog)
    limits = {item.name: item for item in data.items}

    # Real GU-vs-FT: resolve each datalog item's FT/Room bound from the program.
    # The as-run limit (QA for a QARoom run) is used only to disambiguate the
    # owning Function when the same test name appears in several Functions.
    ft_by_name = {}
    ft_source = ""
    if args.ft_program:
        program = _load_program(args.ft_program)
        aligner = Aligner(program)
        for m in aligner.align_datalog_items(data.items, data.zone, data.side):
            if m.item is not None:
                b = m.item.get_bound(data.zone, SourceType.FT)
                ft_by_name[m.name] = (b.lo if b else None, b.hi if b else None)
        ft_source = os.path.basename(args.ft_program)

    stats = []
    gu = []
    for name, values in data.measurements.items():
        if len(values) < args.min_n:
            continue
        limit = limits.get(name)
        lo = limit.lo if limit else None
        hi = limit.hi if limit else None
        unit = limit.unit if limit else ""
        if lo == 0 and hi == 0:
            lo = hi = None  # 0/0 means the limit is undecided, not zero
        stats.append(
            compute_stat(name, unit, values, lo, hi,
                         loose=args.loose, tight=args.tight, skew=args.skew)
        )
        # GU baseline: FT program when provided, else the datalog as-run limit.
        if args.ft_program:
            f_lo, f_hi = ft_by_name.get(name, (None, None))
            if f_lo == 0 and f_hi == 0:
                f_lo = f_hi = None
        else:
            f_lo, f_hi = lo, hi
        gu.append(propose_gu(name, unit, values, f_lo, f_hi, k=args.sigma_k))

    stats.sort(key=lambda s: (s.cpk is None, s.cpk if s.cpk is not None else 0))
    gu.sort(key=lambda g: (g.verdict.value, g.name))

    sample_n = len(data.bins)
    meta = [
        ("来源 datalog", data.source_file),
        ("程序名", data.program_name),
        ("阶段 / 温区", data.stage_label()),
        ("DUT 样本数", str(sample_n)),
        ("GU sigma 倍数", f"k = {args.sigma_k}"),
        ("Cpk 阈值", f"过紧 < {args.tight}，过松 >= {args.loose}"),
        ("样本提示", MIN_NOTE if sample_n < 30 else ""),
    ]
    if args.ft_program:
        meta.append(("GU 基准", f"FT/{data.zone.value}（来自 {ft_source}）-- 真 GU 校验"))
    else:
        meta.append(("GU 基准", f"datalog as-run（{data.stage_label()}）-- 伪 GU"))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    export_analysis(args.out, stats, gu, meta, summarise(stats), summarise_gu(gu))

    print(f"阶段: {data.stage_label()} | DUT 样本数: {sample_n}")
    if args.ft_program:
        print(f"GU 基准: FT/{data.zone.value}（来自 {ft_source}）")
    else:
        print("GU 基准: datalog as-run limit（伪 GU，未提供 --ft-program）")
    print(f"分析测试项: {len(stats)}")
    for key, value in sorted(summarise(stats).items(), key=lambda kv: -kv[1]):
        print(f"  Cpk {key}: {value}")
    for key, value in sorted(summarise_gu(gu).items(), key=lambda kv: -kv[1]):
        print(f"  GU  {key}: {value}")
    print(f"报告: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
