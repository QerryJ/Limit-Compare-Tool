"""Limit reasonableness analysis from measured datalog data.

Two questions the一致性 check cannot answer:

1. **Is the limit reasonable?** -- ``Cpk`` against the measured distribution
   tells whether a limit is too loose (wasted margin / missed escape), too
   tight (yield loss) or off-centre.
2. **Is the GU limit tight enough?** -- a GU (golden unit) limit is derived
   from the measured spread (``mean +/- k * sigma``, typically k = 3) and must
   sit strictly INSIDE the FT limit, otherwise it cannot catch a bad setup.
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence


class Verdict(Enum):
    LOOSE = "过松"
    TIGHT = "过紧"
    OFF_CENTRE = "偏心"
    REASONABLE = "合理"
    NO_SPREAD = "无波动"
    NO_LIMIT = "无限值"
    NO_DATA = "数据不足"


@dataclass
class ItemStat:
    name: str = ""
    unit: str = ""
    n: int = 0
    mean: Optional[float] = None
    sigma: Optional[float] = None
    lo: Optional[float] = None
    hi: Optional[float] = None
    cpk: Optional[float] = None
    cpk_lo: Optional[float] = None
    cpk_hi: Optional[float] = None
    offset: Optional[float] = None
    verdict: Verdict = Verdict.NO_DATA


def mean_sigma(values: Sequence[float]):
    n = len(values)
    if n == 0:
        return None, None
    mean = sum(values) / n
    if n < 2:
        return mean, None
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(variance)


def compute_stat(
    name: str,
    unit: str,
    values: Sequence[float],
    lo: Optional[float],
    hi: Optional[float],
    loose: float = 2.0,
    tight: float = 1.33,
    skew: float = 0.30,
) -> ItemStat:
    """Cpk / verdict for one test item against the limits actually used."""
    stat = ItemStat(name=name, unit=unit, n=len(values), lo=lo, hi=hi)
    mean, sigma = mean_sigma(values)
    stat.mean, stat.sigma = mean, sigma

    if mean is None:
        stat.verdict = Verdict.NO_DATA
        return stat
    if lo is None and hi is None:
        stat.verdict = Verdict.NO_LIMIT
        return stat
    if sigma is None:
        stat.verdict = Verdict.NO_DATA
        return stat
    if sigma == 0:
        stat.verdict = Verdict.NO_SPREAD
        return stat

    span = 3.0 * sigma
    if lo is not None:
        stat.cpk_lo = (mean - lo) / span
    if hi is not None:
        stat.cpk_hi = (hi - mean) / span
    parts = [v for v in (stat.cpk_lo, stat.cpk_hi) if v is not None]
    stat.cpk = min(parts) if parts else None

    if lo is not None and hi is not None and hi != lo:
        centre = (lo + hi) / 2.0
        stat.offset = abs(mean - centre) / ((hi - lo) / 2.0)

    if stat.cpk is None:
        stat.verdict = Verdict.NO_LIMIT
    elif stat.cpk < tight:
        stat.verdict = Verdict.TIGHT
    elif stat.cpk >= loose:
        stat.verdict = Verdict.LOOSE
    elif stat.offset is not None and stat.offset > skew:
        stat.verdict = Verdict.OFF_CENTRE
    else:
        stat.verdict = Verdict.REASONABLE
    return stat


class GuVerdict(Enum):
    TIGHTER = "GU 更紧(合格)"
    EQUAL = "GU 与 FT 相同"
    LOOSER = "GU 比 FT 宽(失效)"
    MISSING = "无法判定"


@dataclass
class GuProposal:
    name: str = ""
    unit: str = ""
    n: int = 0
    mean: Optional[float] = None
    sigma: Optional[float] = None
    gu_lo: Optional[float] = None
    gu_hi: Optional[float] = None
    ft_lo: Optional[float] = None
    ft_hi: Optional[float] = None
    margin_lo: Optional[float] = None
    margin_hi: Optional[float] = None
    verdict: GuVerdict = GuVerdict.MISSING


def propose_gu(
    name: str,
    unit: str,
    values: Sequence[float],
    ft_lo: Optional[float],
    ft_hi: Optional[float],
    k: float = 3.0,
) -> GuProposal:
    """Derive a GU limit from ``mean +/- k*sigma`` and check it against FT."""
    proposal = GuProposal(name=name, unit=unit, n=len(values), ft_lo=ft_lo, ft_hi=ft_hi)
    mean, sigma = mean_sigma(values)
    proposal.mean, proposal.sigma = mean, sigma
    if mean is None or sigma is None:
        proposal.verdict = GuVerdict.MISSING
        return proposal

    proposal.gu_lo = mean - k * sigma
    proposal.gu_hi = mean + k * sigma
    proposal.margin_lo = (
        None if ft_lo is None else proposal.gu_lo - ft_lo
    )
    proposal.margin_hi = (
        None if ft_hi is None else ft_hi - proposal.gu_hi
    )

    if ft_lo is None and ft_hi is None:
        proposal.verdict = GuVerdict.MISSING
        return proposal
    looser = False
    equal = True
    if ft_lo is not None:
        if proposal.gu_lo < ft_lo:
            looser = True
        elif proposal.gu_lo > ft_lo:
            equal = False
    if ft_hi is not None:
        if proposal.gu_hi > ft_hi:
            looser = True
        elif proposal.gu_hi < ft_hi:
            equal = False
    if looser:
        proposal.verdict = GuVerdict.LOOSER
    elif equal:
        proposal.verdict = GuVerdict.EQUAL
    else:
        proposal.verdict = GuVerdict.TIGHTER
    return proposal


def summarise(stats: List[ItemStat]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for stat in stats:
        out[stat.verdict.value] = out.get(stat.verdict.value, 0) + 1
    return out


def summarise_gu(items: List[GuProposal]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for item in items:
        out[item.verdict.value] = out.get(item.verdict.value, 0) + 1
    return out
