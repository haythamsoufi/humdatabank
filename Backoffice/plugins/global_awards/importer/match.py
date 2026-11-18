"""Match a logframe line to the indicator bank, or leave it as a question.

Cited IFRC indicator-bank ids win. Otherwise the wording has to be the same
name, or close enough that a second candidate is not plausible. Anything else
stays a question — this module never proposes a new bank row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

_STOP = {
    "a", "an", "the", "of", "and", "or", "to", "for", "with", "by", "in", "on",
    "through", "from", "that", "their", "who", "are", "is", "be", "as", "at",
    "per", "into", "than", "this", "these", "those", "number", "total",
}
_JACCARD_MIN = 0.85
_OVERLAP_MIN = 4
_WINNER_GAP = 0.08


@dataclass(frozen=True)
class BankRow:
    id: int
    name: str
    archived: bool = False


@dataclass(frozen=True)
class IndicatorMatch:
    bank_id: Optional[int]
    method: str  # bank_id | name | none
    bank_name: str = ""
    note: str = ""

    @property
    def linked(self) -> bool:
        return self.bank_id is not None and self.method != "none"


def normalize_name(text: str) -> str:
    text = (text or "").casefold().replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def significant_tokens(text: str) -> set[str]:
    return {token for token in normalize_name(text).split() if token not in _STOP and len(token) > 2}


def question_type_for(unit: str, label: str) -> str:
    """Question type for a logframe line that is not linked to the bank."""
    blob = f"{unit} {label}".casefold()
    if "percent" in blob:
        return "percentage"
    if "mean" in blob and "median" in blob:
        return "textarea"
    return "number"


def disaggregation_for_question(question_type: str, unit: str) -> list[str]:
    unit_text = (unit or "").casefold()
    if question_type == "number" and any(
        word in unit_text for word in ("people", "individual", "volunteer", "staff")
    ):
        return ["total", "sex", "age", "sex_age"]
    return ["total"]


class BankIndex:
    def __init__(self, rows: Sequence[BankRow]):
        self.rows = [row for row in rows if not row.archived]
        self.by_id = {row.id: row for row in self.rows}
        self.by_name: dict[str, list[BankRow]] = {}
        for row in self.rows:
            self.by_name.setdefault(normalize_name(row.name), []).append(row)

    def match(self, *, label: str, source: str, reference: str, cited_bank_id: Optional[int]) -> IndicatorMatch:
        if cited_bank_id is not None:
            hit = self.by_id.get(cited_bank_id)
            if hit is not None:
                note = ""
                if not _names_related(label, hit.name):
                    note = f"Linked by indicator bank id {cited_bank_id}. Bank name differs: {hit.name}"
                return IndicatorMatch(hit.id, "bank_id", hit.name, note)
            missing = (
                f"Logframe cites indicator bank id {cited_bank_id}, which is not in this bank."
            )
        else:
            missing = ""

        exact = self.by_name.get(normalize_name(label), [])
        if len(exact) == 1:
            return IndicatorMatch(exact[0].id, "name", exact[0].name, missing)

        contained = _containment(label, self.rows)
        if contained is not None:
            return IndicatorMatch(contained.id, "name", contained.name, missing)

        fuzzy = _fuzzy(label, self.rows)
        if isinstance(fuzzy, BankRow):
            return IndicatorMatch(fuzzy.id, "name", fuzzy.name, missing)
        if fuzzy:
            note = missing
            extra = "Several bank indicators are similarly worded, so this line stays a question."
            note = f"{note} {extra}".strip()
            return IndicatorMatch(None, "none", "", note)
        return IndicatorMatch(None, "none", "", missing)


def _names_related(left: str, right: str) -> bool:
    a = significant_tokens(left)
    b = significant_tokens(right)
    if not a or not b:
        return False
    overlap = len(a & b) / min(len(a), len(b))
    return overlap >= 0.34


def _containment(label: str, rows: Iterable[BankRow]) -> Optional[BankRow]:
    norm = normalize_name(label)
    if len(norm) < 40:
        return None
    hits = []
    for row in rows:
        other = normalize_name(row.name)
        if len(other) < 40:
            continue
        shorter, longer = (norm, other) if len(norm) <= len(other) else (other, norm)
        if len(shorter) / len(longer) < 0.75:
            continue
        if shorter in longer:
            hits.append(row)
    if len(hits) == 1:
        return hits[0]
    return None


def _fuzzy(label: str, rows: Sequence[BankRow]):
    """Return the winning row, the string ``'ambiguous'``, or None."""
    mine = significant_tokens(label)
    if len(mine) < _OVERLAP_MIN:
        return None
    scored = []
    for row in rows:
        theirs = significant_tokens(row.name)
        if not theirs:
            continue
        overlap = len(mine & theirs)
        if overlap < _OVERLAP_MIN:
            continue
        score = overlap / len(mine | theirs)
        if score >= _JACCARD_MIN:
            scored.append((score, overlap, row))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], -item[1], item[2].id))
    if len(scored) > 1 and scored[0][0] - scored[1][0] < _WINNER_GAP:
        return "ambiguous"
    return scored[0][2]
