"""Scenario 2 command line entry point.

    python compare_pe.py --pe-dir <PE Excel dir> --program <file.pds> \
        --out <report.xlsx>

For CTA8290 programs (two files, one per side):

    python compare_pe.py --pe-dir <dir> --program-ft <ft.cpts> \
        --program-qa <qa.cpts> --out <report.xlsx>

Room-only comparison is the default (``--zone`` accepts Room / Hot / Cold).
"""

import argparse
import glob
import os
import sys

from src.engine.align import Aligner
from src.engine.pe_compare import compare_pe_to_program
from src.export.report import export_pe_report
from src.model import TempZone
from src.parsers.cpts import CptsParser, merge_sides
from src.parsers.pds import PdsParser
from src.parsers.pe_excel import parse_files

ZONE_BY_NAME = {z.value.lower(): z for z in TempZone}


def load_program(args):
    if args.program:
        lower = args.program.lower()
        if lower.endswith(".pds"):
            return PdsParser.parse_file(args.program)
        if lower.endswith(".cpts"):
            return CptsParser.parse_file(args.program)
        raise SystemExit(f"Unsupported program file: {args.program}")
    if args.program_ft or args.program_qa:
        if not (args.program_ft and args.program_qa):
            raise SystemExit("CTA8290 needs both --program-ft and --program-qa")
        return merge_sides(
            CptsParser.parse_file(args.program_ft),
            CptsParser.parse_file(args.program_qa),
        )
    raise SystemExit("Provide --program, or both --program-ft and --program-qa")


def collect_pe_files(args):
    if args.pe:
        return list(args.pe)
    if args.pe_dir:
        return sorted(glob.glob(os.path.join(args.pe_dir, "*.xlsx")))
    raise SystemExit("Provide --pe-dir or --pe")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PE spec vs test program limit compare")
    parser.add_argument("--pe-dir", help="directory holding the PE limit spreadsheets")
    parser.add_argument("--pe", nargs="*", help="explicit PE spreadsheet paths")
    parser.add_argument("--program", help="program file (.pds, or a single .cpts)")
    parser.add_argument("--program-ft", help="CTA8290 FT side .cpts")
    parser.add_argument("--program-qa", help="CTA8290 QA side .cpts")
    parser.add_argument("--zone", default="Room", choices=list(ZONE_BY_NAME))
    parser.add_argument("--out", default="PE_limit_update_list.xlsx")
    parser.add_argument("--mapping", default="", help="persisted name mapping JSON")
    args = parser.parse_args(argv)

    pe_files = collect_pe_files(args)
    if not pe_files:
        raise SystemExit("No PE spreadsheets found")

    program = load_program(args)
    pe = parse_files(pe_files, program_id=args.pe_id if hasattr(args, "pe_id") else "PE")

    mapping = Aligner.load_mapping(args.mapping) if args.mapping else {}
    aligner = Aligner(program, mapping)
    matches = aligner.match_all(pe.items)

    result = compare_pe_to_program(pe, program, matches, ZONE_BY_NAME[args.zone.lower()])

    if args.mapping:
        for m in matches:
            if m.item is not None:
                aligner.remember(m.pe_item.name, m.item.key())
        Aligner.save_mapping(args.mapping, aligner.mapping)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    export_pe_report(
        args.out, result, matches,
        program_name=os.path.basename(args.program or args.program_ft or ""),
        pe_files=pe.source_files,
    )

    print(f"程序: {program.id} ({program.machine_type.value}), 测试项 {len(program.items)}")
    print(f"PE  : {len(pe.items)} 行, 来自 {len(pe.source_files)} 个文件")
    for key, value in result.summary.items():
        print(f"  {key}: {value}")
    print(f"报告: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
