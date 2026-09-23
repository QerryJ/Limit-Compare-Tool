"""Scenario 2b: production datalog vs the PE specification.

Reads an ETS88 datalog, works out which limit stage (FT / QA x Room / Hot /
Cold) the tester actually used from the ``Current Limit:`` line, exports those
as-run limits as a standalone file, and then compares them against the PE
specification to prove -- or disprove -- that the run used the PE limits.

    python datalog_pe.py --datalog <run.csv> --pe-dir <PE dir> \
        --out-limit <as_run.xlsx> --out <compare.xlsx>
"""

import argparse
import glob
import os
import sys

from src.engine.align import Aligner
from src.engine.pe_compare import compare_pe_to_program
from src.export.datalog_limit import export_datalog_limit
from src.export.report import export_pe_report
from src.parsers.datalog import datalog_to_program, parse_datalog
from src.parsers.pe_excel import parse_files


def collect_pe_files(args) -> list:
    if args.pe:
        return list(args.pe)
    if args.pe_dir:
        return sorted(glob.glob(os.path.join(args.pe_dir, "*.xlsx")))
    raise SystemExit("Provide --pe-dir or --pe")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Datalog as-run limits vs PE specification"
    )
    parser.add_argument("--datalog", required=True, help="ETS88 datalog .csv")
    parser.add_argument("--pe-dir", help="directory holding the PE spreadsheets")
    parser.add_argument("--pe", nargs="*", help="explicit PE spreadsheet paths")
    parser.add_argument("--out", default="datalog_vs_PE.xlsx", help="compare report")
    parser.add_argument("--out-limit", default="", help="as-run limit file to write")
    parser.add_argument("--mapping", default="", help="persisted name mapping JSON")
    args = parser.parse_args(argv)

    data = parse_datalog(args.datalog)
    print(f"datalog      : {data.source_file}")
    print(f"程序名       : {data.program_name or '(未知)'}")
    print(f"Current Limit: {data.limit_tag or '(未识别)'}"
          f"  -> {data.stage_label()}"
          f"  [{'自动识别' if data.tag_detected else '未识别，已默认'}]")
    print(f"反推测试项   : {len(data.items)}")

    if args.out_limit:
        os.makedirs(os.path.dirname(os.path.abspath(args.out_limit)), exist_ok=True)
        export_datalog_limit(args.out_limit, data)
        print(f"实际 limit 文件: {args.out_limit}")

    if not (args.pe_dir or args.pe):
        return 0

    pe_files = collect_pe_files(args)
    pe = parse_files(pe_files)
    program = datalog_to_program(data)

    mapping = Aligner.load_mapping(args.mapping) if args.mapping else {}
    aligner = Aligner(program, mapping)
    matches = aligner.match_all(pe.items)

    result = compare_pe_to_program(
        pe, program, matches, zone=data.zone, sides=[data.side]
    )

    if args.mapping:
        for m in matches:
            if m.item is not None:
                aligner.remember(m.pe_item.name, m.item.key())
        Aligner.save_mapping(args.mapping, aligner.mapping)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    export_pe_report(
        args.out, result, matches,
        program_name=f"{data.source_file} ({data.stage_label()})",
        pe_files=pe.source_files,
        extra_meta=[
            ("来源 datalog", data.source_file),
            ("程序名", data.program_name),
            ("Data Sheet", data.data_sheet),
            ("Lot", data.lot),
            ("Current Limit", data.limit_tag or "(未识别)"),
            ("实际档位 / 温区", data.stage_label()),
            ("方向含义", "收紧=程序现比 PE 松，须收紧否则漏放；放宽=程序现比 PE 紧，属过杀"),
        ],
    )

    print(f"PE           : {len(pe.items)} 行, 来自 {len(pe.source_files)} 个文件")
    for key, value in result.summary.items():
        print(f"  {key}: {value}")
    print(f"对比报告     : {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
