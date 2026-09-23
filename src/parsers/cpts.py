"""CTA8290 ``.cpts`` parser (XML).

A ``.cpts`` file carries only ONE side (FT or QA); the side comes from the
``IsQAFile`` flag (``value="0"`` => FT).

Temperature zones live in the ``param`` name suffix:
  ``_V`` -> Room, ``_H`` -> Hot, ``_L`` -> Cold, ``_PF`` -> pass-flag (skipped).
Params sharing a base name merge into one ``LimitItem``.

The previous tool loaded FT and QA from two separate files. CTA8290 programs
must be merged with :func:`merge_sides` before a scenario-2 comparison.
"""

import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from src.model import Bound, LimitItem, MachineType, ProgramModel, SourceType, TempZone
from src.parsers.numeric import parse_number

_PROGRAM_ID_RE = re.compile(r"_(FT|QA|GU)(?=_|$)", re.IGNORECASE)


def _split_zone(param_name: str) -> Tuple[Optional[str], Optional[TempZone]]:
    if param_name.endswith("_PF"):
        return None, None
    if param_name.endswith("_V"):
        return param_name[:-2], TempZone.ROOM
    if param_name.endswith("_H"):
        return param_name[:-2], TempZone.HOT
    if param_name.endswith("_L"):
        return param_name[:-2], TempZone.COLD
    return param_name, TempZone.ROOM


def _detect_side(root: ET.Element, file_name: str) -> SourceType:
    """Decide FT / QA / GU for a .cpts file.

    Real CTA8290 exports set ``IsQAFile="0"`` even on QA files, so the flag
    alone cannot tell the sides apart. The side is therefore taken from the
    ``_FT_`` / ``_QA_`` / ``_GU_`` token in the file name, with ``IsQAFile``
    kept only as a fallback when no token is present.
    """
    base = os.path.basename(file_name).upper()
    if "_GU_" in base:
        return SourceType.GU
    if "_QA_" in base:
        return SourceType.QA
    if "_FT_" in base:
        return SourceType.FT
    for elem in root.iter():
        if (elem.get("name") or "").strip().lower() == "isqafile":
            return SourceType.QA if (elem.get("value") or "").strip() != "0" else SourceType.FT
    return SourceType.FT


class CptsParser:
    @staticmethod
    def parse(content: str, file_name: str) -> ProgramModel:
        try:
            root = ET.fromstring(content.lstrip("﻿"))
        except ET.ParseError as exc:
            raise ValueError(f"Invalid .cpts XML: {exc}") from exc

        source = _detect_side(root, file_name)
        grouped: Dict[Tuple[str, str], Dict] = {}
        function_order: List[str] = []

        for func in root.iter("function"):
            func_name = (func.get("name") or "").strip()
            if not func_name:
                continue
            params = list(func.iter("param"))
            if not params:
                continue
            if func_name not in function_order:
                function_order.append(func_name)

            for param in params:
                name = (param.get("name") or "").strip()
                if not name:
                    continue
                base_name, zone = _split_zone(name)
                if base_name is None or zone is None:
                    continue
                lo = parse_number(param.get("limitmin"))
                hi = parse_number(param.get("limitmax"))
                key = (func_name, base_name)
                entry = grouped.get(key)
                if entry is None:
                    entry = {
                        "item": LimitItem(
                            function=func_name,
                            test_item=base_name,
                            unit=(param.get("unit") or "").strip(),
                            sub_test_nmbr=(param.get("subn") or "").strip(),
                            machine_type=MachineType.CTA8290,
                            source_files=[file_name],
                        ),
                        "any_bound": False,
                    }
                    grouped[key] = entry
                entry["item"].set_bound(zone, source, Bound(lo=lo, hi=hi))
                if lo is not None or hi is not None:
                    entry["any_bound"] = True

        items = [e["item"] for e in grouped.values() if e["any_bound"]]
        return ProgramModel(
            id=_PROGRAM_ID_RE.sub("", os.path.basename(file_name).rsplit(".", 1)[0]),
            name=root.get("name", file_name),
            machine_type=MachineType.CTA8290,
            functions=function_order,
            items=items,
        )

    @staticmethod
    def parse_file(path: str) -> ProgramModel:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            return CptsParser.parse(fh.read(), path)


def merge_sides(ft: ProgramModel, qa: ProgramModel, name: str = "") -> ProgramModel:
    """Merge an FT-side and a QA-side ``.cpts`` program into one program."""
    merged = ProgramModel(
        id=ft.id or qa.id,
        name=name or ft.name,
        machine_type=MachineType.CTA8290,
        functions=list(ft.functions),
    )
    index: Dict[str, LimitItem] = {}
    for item in ft.items:
        clone = LimitItem(
            function=item.function,
            test_item=item.test_item,
            unit=item.unit,
            sub_test_nmbr=item.sub_test_nmbr,
            bounds={z: dict(sides) for z, sides in item.bounds.items()},
            source_files=list(item.source_files),
            machine_type=MachineType.CTA8290,
        )
        index[clone.key()] = clone
        merged.items.append(clone)
    for item in qa.items:
        target = index.get(item.key())
        if target is None:
            clone = LimitItem(
                function=item.function,
                test_item=item.test_item,
                unit=item.unit,
                sub_test_nmbr=item.sub_test_nmbr,
                bounds={z: dict(sides) for z, sides in item.bounds.items()},
                source_files=list(item.source_files),
                machine_type=MachineType.CTA8290,
            )
            index[clone.key()] = clone
            merged.items.append(clone)
            if clone.function not in merged.functions:
                merged.functions.append(clone.function)
            continue
        for zone, sides in item.bounds.items():
            for side, bound in sides.items():
                target.set_bound(zone, side, bound)
        for src in item.source_files:
            if src not in target.source_files:
                target.source_files.append(src)
    return merged
