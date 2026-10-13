"""FV-1: FT vs QA coverage inside one program.

The QA limit must fully contain the FT limit, otherwise a part that passes FT
can still be outside what QA would accept -- i.e. the guard band is not doing
its job.

Sign convention (fixed, do not flip): **positive guard band = there is margin**
    ``gb_lo = FT.lo - QA.lo``   ``gb_hi = QA.hi - FT.hi``

``Margin%`` uses the FT span as the denominator so the number does not drift
when the range moves. ``N/A`` and ``ERROR`` are produced here and nowhere else.
"""

from typing import Dict, List, Optional

from src.model import (
    Bound,
    CoverageReport,
    CoverageStatus,
    GuVsFtItem,
    GuVsFtReport,
    GuVsFtStatus,
    GuVsFtZone,
    ItemCoverage,
    LimitItem,
    ProgramModel,
    SourceType,
    TempZone,
    ZoneCoverage,
    ZONES,
)

TOLERANCE = 1e-9


def _close(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(TOLERANCE, TOLERANCE * abs(b))


def zone_coverage(zone: TempZone, ft: Optional[Bound], qa: Optional[Bound]) -> ZoneCoverage:
    """Coverage verdict for one zone (engine is the single source of truth)."""
    result = ZoneCoverage(zone=zone, status=CoverageStatus.MISSING, ft=ft, qa=qa)

    if ft is None or qa is None:
        result.status = CoverageStatus.MISSING
        result.detail = "FT 或 QA 侧无限值，无法判定"
        return result

    if ft.lo is None or ft.hi is None or qa.lo is None or qa.hi is None:
        result.status = CoverageStatus.MISSING
        result.detail = "单边缺失，无法判定"
        return result

    if ft.lo > ft.hi:
        result.status = CoverageStatus.ERROR
        result.detail = f"FT 区间反向：Lo({ft.lo}) > Hi({ft.hi})"
        return result

    result.gb_lo = ft.lo - qa.lo
    result.gb_hi = qa.hi - ft.hi

    span = ft.hi - ft.lo
    if span <= 0:
        result.margin_lo = result.margin_hi = None
    else:
        result.margin_lo = result.gb_lo / span * 100.0
        result.margin_hi = result.gb_hi / span * 100.0

    if _close(qa.lo, ft.lo) and _close(qa.hi, ft.hi):
        result.status = CoverageStatus.COVERED
    elif qa.lo <= ft.lo and qa.hi >= ft.hi:
        result.status = CoverageStatus.COVERED
    else:
        result.status = CoverageStatus.UNCOVERED
        missing = []
        if qa.lo > ft.lo:
            missing.append(f"低边未覆盖：QA.Lo({qa.lo}) > FT.Lo({ft.lo})，缺口 {qa.lo - ft.lo:g}")
        if qa.hi < ft.hi:
            missing.append(f"高边未覆盖：QA.Hi({qa.hi}) < FT.Hi({ft.hi})，缺口 {ft.hi - qa.hi:g}")
        result.detail = "；".join(missing) + " → 需收紧 QA 或放宽 FT"
    return result


def item_coverage(item: LimitItem, zones: List[TempZone]) -> ItemCoverage:
    coverages = [
        zone_coverage(
            zone,
            item.get_bound(zone, SourceType.FT),
            item.get_bound(zone, SourceType.QA),
        )
        for zone in zones
    ]
    entry = ItemCoverage(item=item, zones=coverages)
    statuses = [c.status for c in coverages]
    # Priority (worst first): a real failure dominates a data-completeness note.
    #   ERROR      -> data anomaly, always surfaces first
    #   UNCOVERED  -> a zone where QA does not contain FT (real gap)
    #   MISSING    -> *整体缺失*: no zone is comparable (one side absent everywhere)
    #   PARTIAL    -> *局部缺失*: covered on some zones, absent on others
    #   COVERED    -> every comparable zone is clean
    if CoverageStatus.ERROR in statuses:
        entry.status = CoverageStatus.ERROR
    elif CoverageStatus.UNCOVERED in statuses:
        entry.status = CoverageStatus.UNCOVERED
    elif all(s is CoverageStatus.MISSING for s in statuses):
        entry.status = CoverageStatus.MISSING
    elif any(s is CoverageStatus.MISSING for s in statuses):
        entry.status = CoverageStatus.PARTIAL
    else:
        entry.status = CoverageStatus.COVERED
    entry.detail = " | ".join(
        f"{c.zone.value}: {c.detail}" for c in coverages if c.detail
    )
    return entry


def evaluate_coverage(program: ProgramModel, zones: List[TempZone] = None) -> CoverageReport:
    """Evaluate FT-vs-QA coverage for every item of a program.

    The coverage ratio is scored over *comparable zones* only -- zones where
    BOTH FT and QA bounds are present. A zone that is missing on one side is no
    longer counted as a failure, so a program whose QA only defines Room limits
    no longer collapses to a misleading 0% coverage.
    """
    zones = list(zones) if zones else list(ZONES)
    items = [item_coverage(item, zones) for item in program.items]
    summary: Dict[str, int] = {}
    for entry in items:
        key = entry.status.value if entry.status else CoverageStatus.MISSING.value
        summary[key] = summary.get(key, 0) + 1

    covered_zones = 0
    uncovered_zones = 0
    for entry in items:
        for z in entry.zones:
            if z.status is CoverageStatus.COVERED:
                covered_zones += 1
            elif z.status is CoverageStatus.UNCOVERED:
                uncovered_zones += 1
    summary["可比温区数"] = covered_zones + uncovered_zones
    denominator = covered_zones + uncovered_zones
    summary["覆盖率"] = (
        round(covered_zones / denominator * 100, 2) if denominator else None
    )
    return CoverageReport(program_id=program.id, items=items, summary=summary)


def anomalies(report: CoverageReport) -> List[ItemCoverage]:
    """Items worth looking at: everything that is not cleanly covered."""
    return [
        entry for entry in report.items
        if entry.status in (CoverageStatus.UNCOVERED, CoverageStatus.ERROR)
    ]


def partial_missing(report: CoverageReport) -> List[ItemCoverage]:
    """Items present on some zones but absent on others (data-completeness note)."""
    return [
        entry for entry in report.items if entry.status is CoverageStatus.PARTIAL
    ]


# ---------------------------------------------------------------------------
# Scenario 4: GU limit must sit strictly inside the FT limit
# ---------------------------------------------------------------------------
def gu_vs_ft_zone(
    zone: TempZone, ft: Optional[Bound], gu: Optional[Bound], tol: float = TOLERANCE
) -> GuVsFtZone:
    """One-zone GU-vs-FT verdict (engine is the single source of truth)."""
    result = GuVsFtZone(zone=zone, status=GuVsFtStatus.MISSING, ft=ft, gu=gu)
    if ft is None or gu is None or ft.lo is None or ft.hi is None or gu.lo is None or gu.hi is None:
        result.detail = "FT 或 GU 侧无限值，无法判定"
        return result
    if ft.lo > ft.hi:
        result.detail = f"FT 区间反向：Lo({ft.lo}) > Hi({ft.hi})"
        return result
    if gu.lo < ft.lo - tol or gu.hi > ft.hi + tol:
        result.status = GuVsFtStatus.OUTSIDE
        gaps = []
        if gu.lo < ft.lo - tol:
            gaps.append(f"低边超FT：GU.Lo({gu.lo:g}) < FT.Lo({ft.lo:g})，超出 {ft.lo - gu.lo:g}")
        if gu.hi > ft.hi + tol:
            gaps.append(f"高边超FT：GU.Hi({gu.hi:g}) > FT.Hi({ft.hi:g})，超出 {gu.hi - ft.hi:g}")
        result.detail = "；".join(gaps) + " → GU 无法验证 setup 正常"
    else:
        result.status = GuVsFtStatus.INSIDE
        result.detail = "GU 严格落在 FT 之内"
    return result


def evaluate_gu_vs_ft(
    program: ProgramModel, zones: List[TempZone] = None, tol: float = TOLERANCE
) -> GuVsFtReport:
    """Check that every GU limit sits strictly inside the corresponding FT limit."""
    zones = list(zones) if zones else list(ZONES)
    items: List[GuVsFtItem] = []
    for it in program.items:
        zones_c = [
            gu_vs_ft_zone(z, it.get_bound(z, SourceType.FT), it.get_bound(z, SourceType.GU), tol)
            for z in zones
        ]
        entry = GuVsFtItem(item=it, zones=zones_c)
        statuses = [z.status for z in zones_c]
        if GuVsFtStatus.OUTSIDE in statuses:
            entry.status = GuVsFtStatus.OUTSIDE
        elif all(s is GuVsFtStatus.MISSING for s in statuses):
            entry.status = GuVsFtStatus.MISSING
        else:
            entry.status = GuVsFtStatus.INSIDE
        entry.detail = " | ".join(
            f"{z.zone.value}: {z.detail}" for z in zones_c if z.detail
        )
        items.append(entry)
    summary: Dict[str, int] = {}
    for entry in items:
        key = entry.status.value if entry.status else GuVsFtStatus.MISSING.value
        summary[key] = summary.get(key, 0) + 1
    return GuVsFtReport(program_id=program.id, items=items, summary=summary)


def promote_qa_to_gu(program: ProgramModel) -> ProgramModel:
    """ETS88 程序无独立 GU 列，其 QA limit 在 GU↔FT 校验中即视为 GU limit。

    仅当某 (zone) 的 GU 缺失、且 QA 存在时才把 QA 复制为 GU；
    已有真实 GU（如 CTA8290 的 ``_GU_`` 文件）不被覆盖。原地修改并返回 program。
    """
    for item in program.items:
        for zone in list(item.bounds.keys()):
            if item.get_bound(zone, SourceType.GU) is not None:
                continue
            qa = item.get_bound(zone, SourceType.QA)
            if qa is not None:
                # 复制为新 Bound 实例，避免与 QA 共享引用产生副作用
                item.set_bound(zone, SourceType.GU, Bound(lo=qa.lo, hi=qa.hi))
    return program
