"""Recent INFORM, OCHA and IFRC GO snapshots for Decision Maker.

An edition is used only when its reference year is the current calendar year or the
previous one. Older editions are ignored, including INFORM Climate Change 2022.
GO operations are included only when they are active and started in that same window.
These figures are published context. They are not a score and they do not rank
National Societies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

# Current year and the previous year. Anything older is left out.
_RECENT_YEARS = 1
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_CLASS_LABELS = {
    "very_high": "Very High",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "very_low": "Very Low",
}


def risk_class(score: float) -> str:
    """INFORM Risk bands, matching ``plugins.upr.analysis.flow.inform_class``."""
    if score >= 6.5:
        return "very_high"
    if score >= 5:
        return "high"
    if score >= 3.5:
        return "medium"
    return "low"


def class_code(value: Any) -> str | None:
    key = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    key = "_".join(part for part in key.split() if part)
    return key if key in _CLASS_LABELS else None


def edition_year(text: str) -> int | None:
    years = [int(match) for match in _YEAR_RE.findall(text or "")]
    return max(years) if years else None


def reference_year_of(payload: dict[str, Any]) -> int | None:
    raw = payload.get("reference_year")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return edition_year(str(payload.get("edition") or ""))


def is_recent(year: int | None, today: date) -> bool:
    return year is not None and year >= today.year - _RECENT_YEARS


@dataclass(frozen=True)
class ExternalRecord:
    class_code: str | None = None
    class_label: str | None = None
    score: float | None = None
    people_in_need: float | None = None
    plan_name: str | None = None
    active_operations: int | None = None
    people_targeted: float | None = None
    operation_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExternalSnapshot:
    key: str
    edition: str
    reference_year: int
    label: str
    source_system: str
    dataset: str
    owner: str
    period: str
    synchronized_at: str | None
    note: str
    records: dict[str, ExternalRecord] = field(default_factory=dict)

    def source_row(self) -> dict[str, Any]:
        return {
            "source_system": self.source_system,
            "dataset": self.dataset,
            "owner": self.owner,
            "synchronized_at": self.synchronized_at,
            "period": self.period,
            "note": self.note,
            "label": self.label,
        }


@dataclass
class ExternalContext:
    snapshots: list[ExternalSnapshot] = field(default_factory=list)
    stale_editions: list[str] = field(default_factory=list)

    def notes(self) -> list[str]:
        if not self.stale_editions:
            return []
        listed = "; ".join(self.stale_editions)
        return [
            "These external editions are older than the previous calendar year and are not used: " + listed + "."
        ]

    def record(self, key: str, iso3: str) -> ExternalRecord | None:
        code = (iso3 or "").strip().upper()
        for snap in self.snapshots:
            if snap.key == key:
                return snap.records.get(code)
        return None


def _read_json(path: Any) -> dict[str, Any]:
    try:
        if not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def _files() -> dict[str, dict[str, Any]]:
    from plugins.upr.secondary import paths

    risk_path = paths.GLOBAL_FILES["inform_risk"]
    if not risk_path.is_file():
        risk_path = paths.LEGACY_INFORM_RISK
    return {
        "inform_severity": _read_json(paths.GLOBAL_FILES["inform_severity"]),
        "inform_risk": _read_json(risk_path),
        "ocha": _read_json(paths.GLOBAL_FILES["ocha_gho"]),
        "go": _read_json(paths.GLOBAL_FILES["go_operations"]),
    }


def _severity_records(payload: dict[str, Any]) -> dict[str, ExternalRecord]:
    block = payload.get("by_iso3") if isinstance(payload.get("by_iso3"), dict) else {}
    out: dict[str, ExternalRecord] = {}
    for iso3, raw in block.items():
        code = class_code(raw)
        if not code:
            continue
        out[str(iso3).strip().upper()] = ExternalRecord(class_code=code, class_label=_CLASS_LABELS[code])
    return out


def _risk_records(payload: dict[str, Any]) -> dict[str, ExternalRecord]:
    block = payload.get("scores") if isinstance(payload.get("scores"), dict) else payload.get("by_iso3")
    if not isinstance(block, dict):
        return {}
    out: dict[str, ExternalRecord] = {}
    for iso3, raw in block.items():
        try:
            score = float(raw)
        except (TypeError, ValueError):
            continue
        code = risk_class(score)
        out[str(iso3).strip().upper()] = ExternalRecord(
            class_code=code, class_label=_CLASS_LABELS[code], score=score
        )
    return out


def _ocha_records(payload: dict[str, Any]) -> dict[str, ExternalRecord]:
    block = payload.get("by_iso3") if isinstance(payload.get("by_iso3"), dict) else {}
    out: dict[str, ExternalRecord] = {}
    for iso3, raw in block.items():
        if not isinstance(raw, dict):
            continue
        try:
            people = float(raw.get("people_in_need"))
        except (TypeError, ValueError):
            continue
        out[str(iso3).strip().upper()] = ExternalRecord(
            people_in_need=people,
            plan_name=str(raw.get("plan_name") or "").strip() or None,
        )
    return out


def _go_records(payload: dict[str, Any]) -> dict[str, ExternalRecord]:
    """Active GO operations whose start year is inside the snapshot's recent window."""
    year = reference_year_of(payload) or 0
    floor = year - _RECENT_YEARS
    block = payload.get("by_iso3") if isinstance(payload.get("by_iso3"), dict) else {}
    out: dict[str, ExternalRecord] = {}
    for iso3, raw in block.items():
        if not isinstance(raw, dict):
            continue
        names: list[str] = []
        people = 0.0
        for op in raw.get("operations") or []:
            if not isinstance(op, dict):
                continue
            name = str(op.get("name") or "").strip()
            if not name or "regional" in name.lower():
                continue
            started = edition_year(str(op.get("start_date") or ""))
            if started is None or started < floor:
                continue
            kind = str(op.get("appeal_type") or "").strip()
            names.append(f"{kind}: {name}" if kind else name)
            try:
                people += float(op.get("people_targeted") or 0)
            except (TypeError, ValueError):
                pass
        if not names:
            continue
        out[str(iso3).strip().upper()] = ExternalRecord(
            active_operations=len(names),
            people_targeted=people,
            operation_names=tuple(names),
        )
    return out


_LOADERS = {
    "inform_severity": _severity_records,
    "inform_risk": _risk_records,
    "ocha": _ocha_records,
    "go": _go_records,
}

_META = {
    "inform_severity": {
        "label": "INFORM Severity {year}",
        "source_system": "inform",
        "dataset": "INFORM Severity",
        "owner": "European Commission JRC",
        "note": (
            "Crisis severity class for the published edition. High and very high count as one crisis signal, "
            "together with a recent OCHA people-in-need figure. This is not a ranking of National Societies."
        ),
    },
    "inform_risk": {
        "label": "INFORM Risk {year}",
        "source_system": "inform",
        "dataset": "INFORM Risk",
        "owner": "European Commission JRC",
        "note": (
            "Risk class from the published score. It counts toward the crisis signal only for a country that "
            "has no INFORM Severity class. Scores are not added up and National Societies are not ranked."
        ),
    },
    "ocha": {
        "label": "OCHA GHO {year}",
        "source_system": "ocha",
        "dataset": "OCHA Global Humanitarian Overview",
        "owner": "OCHA",
        "note": (
            "People in need in the current Global Humanitarian Overview. Regional plans that cover more than "
            "one country are not assigned to a single country. The figure is not added to the Unified Plan's "
            "people to be reached."
        ),
    },
    "go": {
        "label": "GO active {year}",
        "source_system": "go",
        "dataset": "IFRC GO",
        "owner": "IFRC",
        "note": (
            "Active DREF and Emergency Appeal operations on the IFRC GO platform that started in the current "
            "or previous calendar year. Older operations that GO still marks active are not used. Regional "
            "operations are not assigned to one country. People targeted are not added to the Unified Plan."
        ),
    },
}


def _accept(key: str, payload: dict[str, Any] | None, today: date) -> tuple[ExternalSnapshot | None, str | None]:
    if not isinstance(payload, dict) or not payload:
        return None, None
    year = reference_year_of(payload)
    edition = str(payload.get("edition") or _META[key]["dataset"])
    if not is_recent(year, today):
        when = edition if year is None else f"{edition} ({year})"
        return None, when
    meta = _META[key]
    assert year is not None
    synced = payload.get("updated_at") or payload.get("as_of")
    return (
        ExternalSnapshot(
            key=key,
            edition=edition,
            reference_year=year,
            label=str(meta["label"]).format(year=year),
            source_system=str(meta["source_system"]),
            dataset=str(meta["dataset"]),
            owner=str(meta["owner"]),
            period=edition,
            synchronized_at=str(synced) if synced else None,
            note=str(meta["note"]),
            records=_LOADERS[key](payload),
        ),
        None,
    )


def load_external(today: date, override: dict[str, Any] | None = None) -> ExternalContext:
    """Load recent snapshots. ``override`` replaces the files (tests and explicit payloads)."""
    blocks = override if override is not None else _files()
    ctx = ExternalContext()
    if not isinstance(blocks, dict):
        return ctx
    for key in ("inform_severity", "inform_risk", "ocha", "go"):
        snap, stale = _accept(key, blocks.get(key), today)
        if snap is not None:
            ctx.snapshots.append(snap)
        elif stale:
            ctx.stale_editions.append(stale)
    return ctx
