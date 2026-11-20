"""Temporary link from a GO indicator title to the indicator bank.

GO still writes its own wording (``# of`` for ``Number of``, a dropped clause,
a translation, a row that is not marked emergency). This module links a title
when it is the same bank indicator and the strict in-sector emergency match
did not. The plan stores ``bank_adapted`` so those links stay visible.

Remove this module once the DREF list uses the bank names. Add a pair to
``_ALIASES`` only when the GO phrase and the bank name are the same indicator.
"""

from __future__ import annotations

import re

from plugins.dref_monitoring.services.report_template import _fold

_ZW = re.compile(r"[\u200b\u200c\u200d\ufeff]")
# ``#`` and ``%`` are not word characters, so a leading shorthand has no word boundary.
_HASH = re.compile(r"(?:#|\bno\.?|\bnbr)\s*of\b", re.IGNORECASE)
_PCT = re.compile(r"(?:%\s*of\b|\bpercent(?:age)?\s+of\b)", re.IGNORECASE)
_MIN_CORE = 24
_MIN_RATIO = 0.82

# Folded GO title -> folded indicator-bank name.
_ALIASES = {
    "numberofvolunteersinsured": "numberofvolunteerscoveredbyaccidentinsurance",
    "numberofinsuredvolunteers": "numberofvolunteerscoveredbyaccidentinsurance",
}


def canon(text: str) -> str:
    """Fold a title the way the bank does, after GO's ``#`` and ``%`` shorthand."""
    raw = _ZW.sub("", str(text or ""))
    raw = _HASH.sub("number of", raw)
    raw = _PCT.sub("percentage of", raw)
    return _fold(raw)


def _kind(folded: str) -> str:
    if folded.startswith("numberof"):
        return "number"
    if folded.startswith("percentageof"):
        return "percentage"
    return "text"


def _core(folded: str) -> str:
    kind = _kind(folded)
    if kind == "number":
        return folded[len("numberof") :]
    if kind == "percentage":
        return folded[len("percentageof") :]
    return folded


def _compatible(left: str, right: str) -> bool:
    return {_kind(left), _kind(right)} != {"number", "percentage"}


def _near(left: str, right: str) -> bool:
    """True when one title is the other plus a short clause, and the measure agrees."""
    if not left or not right or not _compatible(left, right):
        return False
    shorter_core, longer_core = _core(left), _core(right)
    if len(shorter_core) > len(longer_core):
        shorter_core, longer_core = longer_core, shorter_core
    if len(shorter_core) < _MIN_CORE or shorter_core not in longer_core:
        return False
    return len(shorter_core) / len(longer_core) >= _MIN_RATIO


def _sector_ids(indicator) -> set[int]:
    raw = indicator.sector if isinstance(getattr(indicator, "sector", None), dict) else {}
    found = set()
    for level in ("primary", "secondary", "tertiary"):
        try:
            found.add(int(raw.get(level)))
        except (TypeError, ValueError):
            continue
    return found


def _names(indicator) -> list[str]:
    names = [getattr(indicator, "name", "") or ""]
    translations = getattr(indicator, "name_translations", None)
    if isinstance(translations, dict):
        names.extend(value for value in translations.values() if isinstance(value, str))
    return names


def _one(candidates: list, sector_id: int | None):
    by_id = {}
    for indicator in candidates:
        by_id[indicator.id] = indicator
    rows = list(by_id.values())
    if len(rows) == 1:
        return rows[0]
    if sector_id is None:
        return None
    in_sector = [indicator for indicator in rows if sector_id in _sector_ids(indicator)]
    if len(in_sector) == 1:
        return in_sector[0]
    return None


class BankCatalog:
    """In-memory index of indicator-bank rows for one plan build."""

    def __init__(self, indicators):
        self._by_canon: dict[str, list] = {}
        self._primary: list[tuple] = []
        for indicator in indicators:
            primary = canon(getattr(indicator, "name", "") or "")
            if primary:
                self._primary.append((indicator, primary))
            for name in _names(indicator):
                folded = canon(name)
                if folded:
                    self._by_canon.setdefault(folded, []).append(indicator)

    def adapt(self, title: str, sector_id: int | None):
        """A bank row for this GO title, or None when the wording is not the bank's."""
        folded = canon(title)
        if not folded:
            return None
        alias = _ALIASES.get(folded)
        if alias:
            found = _one(self._by_canon.get(alias) or [], sector_id)
            if found is not None:
                return found
        found = _one(self._by_canon.get(folded) or [], sector_id)
        if found is not None:
            return found
        near = [indicator for indicator, primary in self._primary if _near(folded, primary)]
        return _one(near, sector_id)
