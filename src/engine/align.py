"""Test-item name alignment between the PE spec and the test program.

Three automatic tiers, then a persisted manual layer:

1. ``EXACT``      -- normalised names are identical.
2. ``PREFIX``     -- one name is a prefix of the other and the match is unique
                     (covers the truncated PE names, e.g. ``IQ_VDD33_3P15V_S``
                     vs ``IQ_VDD33_3P15V_SW``).
3. ``MAPPED``     -- resolved from the persisted mapping dictionary.
   ``AMBIGUOUS``  -- several candidates, needs a human decision.
   ``UNMATCHED``  -- no candidate at all. In practice this usually means the
                     program is MISSING the test the PE asks for, or the test
                     condition changed -- so it is surfaced, never dropped.

The manual layer is a JSON dictionary ``{normalised_pe_name: program_key}`` so a
decision made once is reused on every future import.
"""

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from src.model import Bound, LimitItem, PeItem, ProgramModel


def norm(name: str) -> str:
    """Normalise a test-item name: upper case, alphanumerics only."""
    return re.sub(r"[^A-Z0-9]", "", str(name or "").upper())


def _close_bound(b: "Optional[Bound]", lo: Optional[float], hi: Optional[float],
                 tol: float = 1e-9) -> bool:
    """True when a program bound equals the supplied (lo, hi) within tolerance."""
    if b is None or b.lo is None or b.hi is None:
        return False
    if lo is None or hi is None:
        return False
    return (abs(b.lo - lo) <= max(tol, tol * abs(lo))
            and abs(b.hi - hi) <= max(tol, tol * abs(hi)))


class MatchStatus(Enum):
    EXACT = "exact"
    PREFIX = "prefix"
    MAPPED = "mapped"
    HINT = "filename_hint"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


_STOPWORDS = {
    "limit", "limits", "rev", "v1", "and", "the", "xlsx", "xls",
    "pre", "post", "0", "1", "2", "10",
}


def file_tokens(source_file: str) -> set:
    """Keyword tokens from a PE file name, e.g. ``1. Pre cont and leakage``.

    The PE files are split by test block, and the block names line up with the
    program's Function names -- which lets us disambiguate a test item that
    exists in several functions.
    """
    base = os.path.basename(source_file or "").lower()
    base = re.sub(r"\.xlsx?$", "", base)
    tokens = [
        t for t in re.split(r"[^a-z0-9]+", base)
        if t and t not in _STOPWORDS and len(t) > 1
    ]
    return set(tokens)


def _function_score(function: str, tokens: set) -> int:
    lowered = function.lower()
    return sum(1 for t in tokens if t in lowered)


@dataclass
class Match:
    pe_item: PeItem
    item: Optional[LimitItem] = None
    status: MatchStatus = MatchStatus.UNMATCHED
    candidates: List[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.item is not None


@dataclass
class DatalogMatch:
    """Result of aligning one reverse-engineered datalog item to a program.

    A datalog column carries no Function name, so the same ``test_item`` can
    appear in several program Functions (e.g. ``KELVIN_VSEN1`` in both
    ``HW_Checker`` and ``Contact``). When names collide we disambiguate by the
    *as-run limit* that the datalog reverse-engineers: the candidate whose
    (zone, side) bound equals that limit is the real owner.
    """

    name: str
    unit: str = ""
    lo: Optional[float] = None
    hi: Optional[float] = None
    item: Optional[LimitItem] = None
    status: MatchStatus = MatchStatus.UNMATCHED
    candidates: List[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.item is not None


class Aligner:
    """Align PE rows against program test items, reusing a persisted mapping."""

    def __init__(self, program: ProgramModel, mapping: Optional[Dict[str, str]] = None):
        self.program = program
        self.mapping: Dict[str, str] = dict(mapping or {})
        self._by_norm: Dict[str, List[LimitItem]] = {}
        for item in program.items:
            self._by_norm.setdefault(norm(item.test_item), []).append(item)

    # -- persisted mapping -------------------------------------------------
    @staticmethod
    def load_mapping(path: str) -> Dict[str, str]:
        if not path or not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def save_mapping(path: str, mapping: Dict[str, str]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(mapping, fh, ensure_ascii=False, indent=2, sort_keys=True)

    def remember(self, pe_name: str, program_key: str) -> None:
        self.mapping[norm(pe_name)] = program_key

    # -- matching ----------------------------------------------------------
    def match_one(self, pe_item: PeItem) -> Match:
        key = norm(pe_item.name)

        mapped_key = self.mapping.get(key)
        if mapped_key:
            item = self.program.get_item_by_key(mapped_key)
            if item is not None:
                return Match(pe_item, item, MatchStatus.MAPPED)

        exact = self._by_norm.get(key)
        if exact:
            if len(exact) == 1 or len({i.key() for i in exact}) == 1:
                # Same (function, test_item) repeated in the program: identical
                # alignment target, so it is not real ambiguity.
                return Match(pe_item, exact[0], MatchStatus.EXACT)
            hinted = self._disambiguate(pe_item, exact)
            if hinted is not None:
                return hinted
            return Match(
                pe_item, None, MatchStatus.AMBIGUOUS, [i.key() for i in exact]
            )

        prefix_hits = [
            i for k, items in self._by_norm.items()
            if k.startswith(key) or key.startswith(k)
            for i in items
        ]
        if not prefix_hits:
            return Match(pe_item, None, MatchStatus.UNMATCHED)
        if len(prefix_hits) == 1 or len({i.key() for i in prefix_hits}) == 1:
            return Match(pe_item, prefix_hits[0], MatchStatus.PREFIX)
        hinted = self._disambiguate(pe_item, prefix_hits)
        if hinted is not None:
            return hinted
        return Match(
            pe_item, None, MatchStatus.AMBIGUOUS,
            [i.key() for i in prefix_hits[:10]],
        )

    def _disambiguate(self, pe_item: PeItem, candidates: List[LimitItem]):
        """Pick the candidate whose Function matches the PE file name best.

        Only fires when exactly one candidate wins -- a tie stays AMBIGUOUS
        rather than guessing.
        """
        tokens = file_tokens(pe_item.source_file)
        if not tokens:
            return None
        scored = [(_function_score(i.function, tokens), i) for i in candidates]
        best = max(score for score, _ in scored)
        if best <= 0:
            return None
        winners = [i for score, i in scored if score == best]
        if len(winners) != 1:
            return None
        return Match(pe_item, winners[0], MatchStatus.HINT)

    def _disambiguate_by_limit(
        self, candidates: List[LimitItem], lo: Optional[float], hi: Optional[float],
        zone: "TempZone", side: "SourceType",
    ) -> Optional[LimitItem]:
        """Among same-named candidates, keep those whose (zone, side) bound
        equals the reverse-engineered as-run limit. Unique hit wins; a tie or
        no hit returns None (caller should flag AMBIGUOUS)."""
        hits = [
            it for it in candidates
            if _close_bound(it.get_bound(zone, side), lo, hi)
        ]
        return hits[0] if len(hits) == 1 else None

    def align_datalog_items(
        self, datalog_items: List["DatalogItem"], zone: "TempZone", side: "SourceType"
    ) -> List[DatalogMatch]:
        """Align reverse-engineered datalog columns to program test items.

        ``side`` is the limit stage actually applied in the run (e.g. QA for a
        ``QARoom`` datalog); the as-run limit is matched against the candidate
        Function's *same* (zone, side) bound to pick the right owner.
        """
        from src.parsers.datalog import DatalogItem

        out: List[DatalogMatch] = []
        for d in datalog_items:
            key = norm(d.name)
            candidates = self._by_norm.get(key)
            if not candidates:
                prefix_hits = [
                    i for k, items in self._by_norm.items()
                    if k.startswith(key) or key.startswith(k)
                    for i in items
                ]
                if not prefix_hits:
                    out.append(DatalogMatch(name=d.name, unit=d.unit, lo=d.lo, hi=d.hi,
                                            status=MatchStatus.UNMATCHED))
                    continue
                candidates = prefix_hits

            if len(candidates) == 1 or len({i.key() for i in candidates}) == 1:
                out.append(DatalogMatch(name=d.name, unit=d.unit, lo=d.lo, hi=d.hi,
                                        item=candidates[0], status=MatchStatus.EXACT))
                continue

            resolved = self._disambiguate_by_limit(candidates, d.lo, d.hi, zone, side)
            if resolved is not None:
                out.append(DatalogMatch(name=d.name, unit=d.unit, lo=d.lo, hi=d.hi,
                                        item=resolved, status=MatchStatus.HINT))
            else:
                out.append(DatalogMatch(
                    name=d.name, unit=d.unit, lo=d.lo, hi=d.hi, item=None,
                    status=MatchStatus.AMBIGUOUS,
                    candidates=[i.key() for i in candidates],
                ))
        return out

    def match_all(self, pe_items: List[PeItem]) -> List[Match]:
        return [self.match_one(item) for item in pe_items]

    @staticmethod
    def unresolved(matches: List["Match"]) -> List["Match"]:
        return [
            m for m in matches
            if m.status in (MatchStatus.AMBIGUOUS, MatchStatus.UNMATCHED)
        ]

    def program_only(self, matches: List["Match"]) -> List[LimitItem]:
        """Program items that no PE row refers to (possibly obsolete tests)."""
        used = {m.item.key() for m in matches if m.item is not None}
        return [it for it in self.program.items if it.key() not in used]
