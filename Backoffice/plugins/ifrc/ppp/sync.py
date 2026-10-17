#!/usr/bin/env python3
"""Import the six Pilot Programmatic Partnership (PPP) Kobo projects.

Creates one published Backoffice template per Kobo form, links a field to the
Indicator Bank when the English label matches an existing indicator, and copies
submissions into assignments.

Kobo validation status:

- Not approved: skipped
- On hold: assignment status ``submitted``
- Approved: assignment status ``approved``
- Anything else (including blank): skipped

People-reached blocks (total / sex / age / sex-and-age grids) become one
indicator with disaggregation. Calculated Kobo fields and grid chrome are not
copied as their own questions.

The Kobo API token is read from ``KOBO_API_TOKEN`` and is never written to disk.

Dry run (default) prints what would be written. ``--apply`` writes to the
database selected by the usual Backoffice config (local dev, or production
when the script runs in that environment).

    python plugins/ifrc/ppp/sync.py
    python plugins/ifrc/ppp/sync.py --apply --owner-email you@ifrc.org
    python plugins/ifrc/ppp/sync.py --repair
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

def _ensure_backoffice_on_path() -> Path:
    """Find Backoffice/ from this plugin script so ``import app`` works."""
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        if (parent / "app").is_dir() and (parent / "run.py").is_file():
            root = str(parent)
            if root not in sys.path:
                sys.path.insert(0, root)
            return parent
    raise RuntimeError(f"Cannot locate Backoffice root from {here}")


_BACKOFFICE_ROOT = _ensure_backoffice_on_path()

KOBO_API_ROOT = "https://kobo.ifrc.org/api/v2"
ASSET_UIDS = (
    "aHQTGPhhLv5MhsycfNvBJZ",  # Project Overview
    "afsHubF3oA3KpDV8eJRgn6",  # Result 1 DRM
    "aaMUkVa6QFuMEr4rV78YYC",  # Result 2 EPPR
    "aS8LroVXh5bSnEPz685UqS",  # Result 3 people on the move
    "a855a2utxS7MCt8PJCR26Q",  # Result 4 CVA
    "ad2qnRrwYkhoHZSRokftBc",  # Result 5 RCCEA
)
MARKER_PREFIX = "Kobo asset "
LANG_CODES = ("en", "fr", "es", "ar")
AGE_GROUPS = (
    "0-5",
    "6-12",
    "13-17",
    "18-29",
    "30-39",
    "40-49",
    "50-59",
    "60-69",
    "70-79",
    "80+",
)
AGE_GROUPS_CONFIG = ",".join(AGE_GROUPS)
SKIP_TYPES = {"start", "end", "today", "calculate", "hidden", "acknowledge"}
CHROME_LABELS = {"male", "female", "total", "0-5", "6-12", "13-17", "18-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"}
DISAGG_NAME_RE = re.compile(
    r"^(?P<kind>male|female|unknown|total)"
    r"(?:_(?P<band>\d+-\d+|80))?"
    r"(?:_(?P<suffix>.+))?$"
)
SEX_PAIR_RE = re.compile(r"^(?P<stem>.+)_(?P<sex>male|female)$")
TAG_RE = re.compile(r"<[^>]+>")
NUMBER_PREFIX_RE = re.compile(r"^\d+(?:\.\d+)*\s*")
MATCH_STOPWORDS = {
    "a", "an", "and", "are", "been", "by", "for", "from", "has", "have",
    "how", "in", "many", "national", "number", "of", "on", "or", "people",
    "society", "the", "their", "to", "with", "your",
}
COMPARE_REPLACEMENTS = (
    ("does your national society", "national society"),
    ("has your national society", "national society has"),
    ("your national society", "national society"),
    ("how many", "number of"),
    ("unique individuals", "people"),
)
STATUS_TO_ASSIGNMENT = {
    "approved": "approved",
    "on_hold": "submitted",
}
# Kobo society labels that are not the Backoffice country name.
COUNTRY_ALIASES = {
    "palestinian territories": "palestine state of",
    "yemen rep": "yemen",
}


def clean_text(value, *, keep_newlines: bool = False) -> str:
    """Strip Kobo HTML and markdown markers from a label."""
    if value is None:
        return ""
    text = str(value)
    lowered = text.lower()
    if "display:none" in lowered or "display: none" in lowered or "color:red" in lowered or "color: red" in lowered:
        return ""
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text).replace("**", "").replace("*", "")
    if keep_newlines:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line).strip()
    return re.sub(r"\s+", " ", text).strip()


def label_map(row) -> dict[str, str]:
    """English plus fr/es/ar from a Kobo label list, in form translation order."""
    raw = row.get("label")
    if isinstance(raw, str):
        text = clean_text(raw, keep_newlines=True)
        return {"en": text} if text else {}
    if not isinstance(raw, list):
        return {}
    out: dict[str, str] = {}
    for index, code in enumerate(LANG_CODES):
        if index >= len(raw):
            break
        text = clean_text(raw[index], keep_newlines=True)
        if text:
            out[code] = text
    return out


def english_label(row) -> str:
    return label_map(row).get("en") or ""


def base_type(type_str: str) -> str:
    return (type_str or "").strip().split()[0].lower()


def select_list_name(row) -> str:
    """List name from a survey row, or from a ``select_one listname`` type string."""
    if isinstance(row, dict):
        explicit = str(row.get("select_from_list_name") or "").strip()
        if explicit:
            return explicit
        type_str = row.get("type") or ""
    else:
        type_str = row or ""
    parts = str(type_str).strip().split()
    if len(parts) >= 2 and parts[0] in {"select_one", "select_multiple"}:
        return parts[1]
    return ""


def is_disagg_group(name: str, label: str) -> bool:
    """Sex/age grid groups have no human label. Real sections do."""
    if (label or "").strip():
        return False
    token = name or ""
    return (
        token in {"sexage", "gender", "age"}
        or token.startswith(("sexage_", "gender_", "age_"))
    )


def parse_disagg_name(name: str) -> dict | None:
    """Split a grid cell name into kind, age band, and indicator suffix.

    ``male_0-5_1.1`` is male, band 0-5. ``female_4`` is female for indicator 4,
    not an age band: only ``N-N`` and ``80`` (80+) are age bands.
    """
    match = DISAGG_NAME_RE.match(name or "")
    if not match:
        return None
    band = match.group("band")
    return {
        "kind": match.group("kind"),
        "band": "80+" if band == "80" else band,
        "suffix": match.group("suffix"),
    }


def parse_sex_pair_name(name: str) -> dict | None:
    """``unique_indiv_country_disability_male`` -> stem + sex. Grid names are not pairs."""
    if parse_disagg_name(name):
        return None
    match = SEX_PAIR_RE.match(name or "")
    if not match:
        return None
    return {"stem": match.group("stem"), "sex": match.group("sex")}


def kobo_validation_bucket(cell) -> str:
    """Coarse Kobo ``_validation_status`` bucket. Mirrors the data-import service."""
    if isinstance(cell, dict):
        cell = cell.get("uid") or cell.get("label") or ""
    text = "" if cell is None else str(cell).strip()
    if not text:
        return "empty"
    norm = text.lower().replace(" ", "_").replace("-", "_")
    if "not_approved" in norm or "notapproved" in norm:
        return "rejected"
    if "rejected" in norm or "denied" in norm or "declined" in norm:
        return "rejected"
    if "on_hold" in norm or "onhold" in norm:
        return "on_hold"
    if "approved" in norm:
        return "approved"
    if "not_validated" in norm or norm in {"draft"} or "pending" in norm:
        return "other"
    return "other"


def assignment_status_for_bucket(bucket: str) -> str | None:
    """Backoffice status for a Kobo bucket, or None when the row is not imported."""
    return STATUS_TO_ASSIGNMENT.get(bucket)


def fold_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_indicator_label(value: str) -> str:
    text = NUMBER_PREFIX_RE.sub("", value or "")
    text = fold_name(text)
    return text.rstrip(".").strip()


def compare_key(value: str) -> str:
    """Loosen 'how many' / 'your National Society' so bank titles can match."""
    text = normalize_indicator_label(value)
    for source, target in COMPARE_REPLACEMENTS:
        text = text.replace(source, target)
    return re.sub(r"\s+", " ", text).strip()


def _content_tokens(value: str) -> set[str]:
    return {word for word in compare_key(value).split() if word not in MATCH_STOPWORDS and len(word) > 2}


def _choice_rows(choices: list, list_name: str) -> list[dict]:
    rows = []
    for choice in choices or []:
        if (choice.get("list_name") or "") != list_name:
            continue
        stored = str(choice.get("name") or "").strip()
        if not stored:
            continue
        labels = label_map(choice)
        rows.append({
            "value": stored,
            "label": labels.get("en") or stored,
            "translations": {code: text for code, text in labels.items() if code != "en"},
            "don_code": str(choice.get("fdrs_country_code") or "").strip() or None,
        })
    return rows


def _new_field(*, kind, section, label, translations, qtype, kobo_name, binds, **extra):
    field = {
        "kind": kind,
        "section": section,
        "label": label,
        "translations": {code: text for code, text in (translations or {}).items() if code != "en"},
        "qtype": qtype,
        "kobo_name": kobo_name,
        "binds": binds,
        "options": extra.get("options"),
        "definition": extra.get("definition") or None,
        "disagg": bool(extra.get("disagg")),
        "allow_na": bool(extra.get("allow_na")),
    }
    return field


def _blank_measure(section, labels, kobo_name, applicable_path=None):
    return {
        "section": section,
        "label": labels.get("en") or "People reached",
        "translations": {code: text for code, text in labels.items() if code != "en"},
        "kobo_name": kobo_name,
        "applicable": applicable_path,
        "agd": None,
        "total": None,
        "sex": {},
        "age": {},
        "sex_age": {},
    }


def _measure_to_field(measure) -> dict | None:
    has_cells = bool(measure["total"] or measure["sex"] or measure["age"] or measure["sex_age"])
    if not has_cells:
        if not measure["applicable"]:
            return None
        return _new_field(
            kind="question",
            section=measure["section"],
            label=measure["label"],
            translations=measure["translations"],
            qtype="single_choice",
            kobo_name=measure["kobo_name"],
            binds={"value": measure["applicable"]},
            options=["applicable", "not applicable"],
        )
    modes = ["total"]
    if measure["sex"]:
        modes.append("sex")
    if measure["age"]:
        modes.append("age")
    if measure["sex_age"]:
        modes.append("sex_age")
    return _new_field(
        kind="indicator",
        section=measure["section"],
        label=measure["label"],
        translations=measure["translations"],
        qtype="number",
        kobo_name=measure["kobo_name"],
        binds={
            "applicable": measure["applicable"],
            "agd": measure["agd"],
            "total": measure["total"],
            "sex": measure["sex"],
            "age": measure["age"],
            "sex_age": measure["sex_age"],
            "modes": modes,
        },
        disagg=True,
        allow_na=bool(measure["applicable"]),
    )


def _is_chrome_note(name: str, label: str) -> bool:
    if (name or "").startswith("header"):
        return True
    folded = fold_name(label)
    return folded in CHROME_LABELS


def _row_path(group_stack: list[str], name: str) -> str:
    parts = [part for part in group_stack if part] + ([name] if name else [])
    return "/".join(parts)


def compile_survey(survey: list, choices: list | None = None) -> list[dict]:
    """Turn a Kobo survey array into sections of Backoffice fields.

    Grid chrome, calculates, and hidden cells are folded into the indicator
    they belong to instead of becoming their own questions.
    """
    choices = choices or []
    choice_lists = {}
    sections: list[dict] = []
    section_stack: list[dict] = []
    group_stack: list[str] = []
    measure = None
    skip_rows: set[int] = set()

    def current_section():
        if section_stack:
            return section_stack[-1]
        intro = {"name": "Introduction", "translations": {}, "fields": [], "kobo_name": "introduction"}
        sections.append(intro)
        section_stack.append(intro)
        return intro

    def flush_measure():
        nonlocal measure
        if measure is None:
            return
        field = _measure_to_field(measure)
        if field is not None:
            current_section()["fields"].append(field)
        measure = None

    def ensure_measure_from_note(row, name):
        nonlocal measure
        if measure is not None:
            return
        labels = label_map(row) or {"en": name or "People reached"}
        measure = _blank_measure(current_section(), labels, name)

    rows = [row for row in survey or [] if isinstance(row, dict)]
    for index, row in enumerate(rows):
        if index in skip_rows:
            continue
        type_str = row.get("type") or ""
        kind = base_type(type_str)
        name = str(row.get("name") or "").strip()
        labels = label_map(row)
        label = labels.get("en") or ""

        if kind == "begin_group":
            if is_disagg_group(name, label):
                group_stack.append(name)
                continue
            flush_measure()
            section = {
                "name": (label or name or "Section")[:100],
                "translations": {code: text for code, text in labels.items() if code != "en"},
                "fields": [],
                "kobo_name": name,
            }
            sections.append(section)
            section_stack.append(section)
            group_stack.append(name)
            continue

        if kind == "end_group":
            if group_stack:
                closed = group_stack.pop()
                if section_stack and section_stack[-1].get("kobo_name") == closed:
                    flush_measure()
                    section_stack.pop()
            continue

        if kind in SKIP_TYPES or not name:
            continue

        path = _row_path(group_stack, name)

        if kind == "note":
            raw_label = row.get("label")
            raw_text = raw_label if isinstance(raw_label, str) else " ".join(str(part or "") for part in raw_label or [])
            if "${" in raw_text or not label or _is_chrome_note(name, label):
                continue
            nxt = _peek_following(rows, index)
            if nxt in {"matrix", "sex_pair"}:
                flush_measure()
                measure = _blank_measure(current_section(), labels, name)
                continue
            flush_measure()
            current_section()["fields"].append(_new_field(
                kind="note",
                section=current_section(),
                label=label,
                translations=labels,
                qtype="blank",
                kobo_name=name,
                binds={},
            ))
            continue

        if kind == "select_one":
            list_name = select_list_name(row)
            if list_name == "agd":
                ensure_measure_from_note(row, name)
                measure["agd"] = path
                continue
            if list_name == "a-na":
                paired = _unlabeled_yesno_after(rows, index, group_stack)
                if paired is not None:
                    flush_measure()
                    skip_rows.add(paired["index"])
                    current_section()["fields"].append(_new_field(
                        kind="question",
                        section=current_section(),
                        label=label or name,
                        translations=labels,
                        qtype="yesno",
                        kobo_name=name,
                        binds={"value": paired["path"], "applicable": path},
                        allow_na=True,
                    ))
                    continue
                flush_measure()
                measure = _blank_measure(current_section(), labels or {"en": label or name}, name, path)
                continue
            flush_measure()
            if list_name == "y-n":
                qtype = "yesno"
                options = None
            else:
                qtype = "single_choice"
                if list_name not in choice_lists:
                    choice_lists[list_name] = _choice_rows(choices, list_name)
                # Option text must equal the value Kobo stored, or the entry form
                # cannot mark the saved answer as selected.
                options = [item["value"] for item in choice_lists[list_name]] or None
            current_section()["fields"].append(_new_field(
                kind="question",
                section=current_section(),
                label=label or name,
                translations=labels,
                qtype=qtype,
                kobo_name=name,
                binds={"value": path},
                options=options,
            ))
            continue

        if kind in {"integer", "decimal"}:
            parsed = parse_disagg_name(name)
            if parsed:
                ensure_measure_from_note(row, name)
                _attach_disagg_cell(measure, parsed, path)
                continue
            pair = parse_sex_pair_name(name)
            # Male/female pairs such as disability counts belong to the open
            # note-titled measure, not to a sex/age grid that already has cells.
            open_for_pair = (
                measure is not None
                and not measure["applicable"]
                and not measure["total"]
                and not measure["age"]
                and not measure["sex_age"]
            )
            if pair and open_for_pair:
                measure["sex"][pair["sex"]] = path
                continue
            if pair and measure is None:
                flush_measure()
                measure = _blank_measure(current_section(), {"en": label or name}, name)
                measure["sex"][pair["sex"]] = path
                continue
            flush_measure()
            current_section()["fields"].append(_new_field(
                kind="question",
                section=current_section(),
                label=label or name,
                translations=labels,
                qtype="number",
                kobo_name=name,
                binds={"value": path},
            ))
            continue

        flush_measure()
        if kind == "text":
            qtype = "text" if re.search(r"(email|name)$", name, re.I) else "textarea"
        elif kind == "date":
            qtype = "date"
        elif kind in {"image", "photo", "audio", "video", "file"}:
            qtype = "text"
        else:
            continue
        current_section()["fields"].append(_new_field(
            kind="file" if kind in {"image", "photo", "audio", "video", "file"} else "question",
            section=current_section(),
            label=label or name,
            translations=labels,
            qtype=qtype,
            kobo_name=name,
            binds={"value": path},
        ))

    flush_measure()
    return [section for section in sections if section["fields"]]


def _attach_disagg_cell(measure: dict, parsed: dict, path: str) -> None:
    kind = parsed["kind"]
    band = parsed["band"]
    if kind == "total" and not band:
        measure["total"] = path
        return
    if kind in {"male", "female"} and not band:
        measure["sex"][kind] = path
        return
    if kind == "unknown" and band:
        measure["age"][band] = path
        return
    if kind in {"male", "female"} and band:
        measure["sex_age"].setdefault(kind, {})[band] = path


def _unlabeled_yesno_after(rows: list, index: int, group_stack: list[str]) -> dict | None:
    """An applicable/not-applicable gate followed by a labelless yes/no is one question."""
    stack = list(group_stack)
    for cursor, row in enumerate(rows[index + 1:], start=index + 1):
        kind = base_type(row.get("type") or "")
        name = str(row.get("name") or "").strip()
        label = english_label(row)
        if kind in SKIP_TYPES or (kind == "note" and (not label or _is_chrome_note(name, label))):
            continue
        if kind == "begin_group":
            if is_disagg_group(name, label):
                stack.append(name)
                continue
            return None
        if kind == "end_group":
            return None
        if kind == "select_one" and select_list_name(row) == "y-n" and not label:
            return {"index": cursor, "path": _row_path(stack, name)}
        return None
    return None


def _peek_following(rows: list, index: int) -> str:
    """What the next real row is, so a note can become an indicator title."""
    saw_pair = False
    for row in rows[index + 1:]:
        kind = base_type(row.get("type") or "")
        name = str(row.get("name") or "").strip()
        label = english_label(row)
        if kind in SKIP_TYPES:
            continue
        if kind == "note" and (not label or _is_chrome_note(name, label)):
            continue
        if kind == "begin_group" and is_disagg_group(name, label):
            return "matrix"
        if kind == "end_group":
            return "sex_pair" if saw_pair else "field"
        if kind == "select_one" and select_list_name(row) == "agd":
            return "matrix"
        if kind in {"integer", "decimal"} and parse_disagg_name(name):
            return "matrix"
        if kind in {"integer", "decimal"} and parse_sex_pair_name(name):
            saw_pair = True
            continue
        if saw_pair:
            return "sex_pair"
        return "field"
    return "sex_pair" if saw_pair else "field"


def submission_time(row: dict) -> datetime:
    raw = row.get("_submission_time") or row.get("end") or ""
    text = str(raw).strip()
    if not text:
        return datetime.min
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def reporting_bounds(row: dict) -> tuple[date | None, date | None]:
    start = _find_answer(row, "reporting_start")
    end = _find_answer(row, "reporting_end")
    return _parse_date(start), _parse_date(end)


def national_society_answer(row: dict) -> str:
    return str(_find_answer(row, "ns_name") or "").strip()


def _find_answer(row: dict, field_name: str):
    if field_name in row and row.get(field_name) not in (None, ""):
        return row.get(field_name)
    suffix = "/" + field_name
    for key, value in row.items():
        if isinstance(key, str) and key.endswith(suffix) and value not in (None, ""):
            return value
    return None


def _parse_date(value) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


# Which calendar collection round a Kobo file belongs to, judged by its end date.
# The assignment period is that round (a quarter or half-year). The exact coverage
# each society reports stays in the form's own start and end date fields.
_ROUND_CUTOFFS = (
    (date(2022, 4, 15), "2022 Q1", date(2022, 1, 1), date(2022, 3, 31)),
    (date(2022, 10, 31), "2022 Q3", date(2022, 7, 1), date(2022, 9, 30)),
    (date(2023, 2, 15), "2022 Q4", date(2022, 10, 1), date(2022, 12, 31)),
    (date(2023, 8, 31), "Jan 2023 – Jun 2023", date(2023, 1, 1), date(2023, 6, 30)),
    (date(2024, 2, 15), "Jul 2023 – Dec 2023", date(2023, 7, 1), date(2023, 12, 31)),
    (date(2024, 8, 31), "Jan 2024 – Jun 2024", date(2024, 1, 1), date(2024, 6, 30)),
    (date(2025, 2, 15), "Jul 2024 – Dec 2024", date(2024, 7, 1), date(2024, 12, 31)),
    (date(2025, 12, 31), "Jan 2025 – Jun 2025", date(2025, 1, 1), date(2025, 6, 30)),
)
_PROGRAMME_STARTS = (date(2022, 4, 1), date(2022, 5, 1))

# Kobo question name -> distinctive substring of an existing Indicator Bank title.
# Matched by text so the link survives a different database id in production.
EXPLICIT_BANK_NAME_FRAGMENTS = {
    "R2EPPR_ind_5_2_HF": "infection prevention and control (IPC) assessment",
    "R2EPPR_ind_2_Epinfo": "epidemic-related health promotion",
    "R3APMOVE_ind_1_APS": "migrants and displaced persons reached with services for assistance and protection",
    "R3APMOVE_ind_2_HSP": "Humanitarian Service Points (HSPs) providing assistance",
    "R3APMOVE_ind_3_SI": "social cohesion activities to improve relations between migrants",
    "R4CVA_ind_4_cash": "cash-plus",
}


def canonical_round(start: date | None, end: date | None) -> tuple[str, date | None, date | None]:
    """Map a Kobo coverage window onto the calendar round it was collected in.

    Returns ``(period name, round start, round end)``. ``start`` is only used
    when the file has no end date. It does not become the assignment start:
    a file covering 1 Apr 2022–30 Jun 2024 still belongs to Jan–Jun 2024.
    """
    if end is None:
        return "PPP undated", start, None
    for cutoff, name, round_start, round_end in _ROUND_CUTOFFS:
        if end <= cutoff:
            return name, round_start, round_end
    return "Jan 2025 – Jun 2025", date(2025, 1, 1), date(2025, 6, 30)


def round_period_type(name: str) -> str:
    """Quarter labels are quarterly; half-years stay custom."""
    return "quarterly" if " Q" in (name or "") else "custom"


def period_name_for(start: date | None, end: date | None) -> str:
    """Assignment period for a Kobo window. Several exact date pairs share one round."""
    name, _canon_start, _canon_end = canonical_round(start, end)
    return name


def choose_submission(existing: dict | None, candidate: dict) -> dict:
    """Keep Approved over On hold, then the running total from April/May 2022, then the later end date."""
    if existing is None:
        return candidate
    return candidate if _submission_rank(candidate) >= _submission_rank(existing) else existing


def _submission_rank(item: dict) -> tuple:
    start = item.get("start")
    return (
        1 if item.get("status") == "approved" else 0,
        1 if start in _PROGRAMME_STARTS else 0,
        item.get("end") or date.min,
        item.get("submitted_at") or datetime.min,
    )


def read_number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return number


def matrix_payload(row: dict, binds: dict) -> dict | None:
    """Build a disaggregation write from one Kobo submission.

    Returns ``{'not_applicable': True}``, ``{'mode': 'total', 'value': n}``,
    ``{'mode': 'sex'|'age'|'sex_age', 'values': {...}}``, or None when empty.
    """
    applicable = _row_value(row, binds.get("applicable"))
    if applicable is not None:
        token = str(applicable).strip().lower().replace("_", " ")
        if token in {"not applicable", "na", "n/a"}:
            return {"not_applicable": True}

    sex_values = {}
    for sex, path in (binds.get("sex") or {}).items():
        number = read_number(_row_value(row, path))
        if number is not None:
            sex_values[sex] = number

    age_values = {}
    for band, path in (binds.get("age") or {}).items():
        number = read_number(_row_value(row, path))
        if number is not None:
            age_values[_age_slug(band)] = number

    sex_age_values = {}
    for sex, bands in (binds.get("sex_age") or {}).items():
        for band, path in (bands or {}).items():
            number = read_number(_row_value(row, path))
            if number is not None:
                sex_age_values[f"{sex}_{_age_slug(band)}"] = number

    total = read_number(_row_value(row, binds.get("total")))
    agd = str(_row_value(row, binds.get("agd")) or "").strip().lower()

    available = {
        "sex_age": sex_age_values,
        "age": age_values,
        "sex": sex_values,
        "total": {"total": total} if total is not None else {},
    }
    preferred = {"genderage": "sex_age", "gender": "sex", "age": "age"}.get(agd)
    order = [preferred] if preferred else []
    order.extend(mode for mode in ("sex_age", "age", "sex", "total") if mode not in order)
    for mode in order:
        payload = available.get(mode) or {}
        if not payload:
            continue
        if mode == "total":
            return {"mode": "total", "value": total}
        return {"mode": mode, "values": payload}
    return None


def _age_slug(band: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", str(band).strip().lower())


def _row_value(row: dict, path: str | None):
    if not path:
        return None
    if path in row:
        return row.get(path)
    return None


NOT_APPLICABLE = "__not_applicable__"


def scalar_answer(row: dict, field: dict):
    binds = field.get("binds") or {}
    path = binds.get("value")
    qtype = field.get("qtype")
    if qtype == "yesno" and binds.get("applicable"):
        applicable = _row_value(row, binds.get("applicable"))
        if applicable is not None and str(applicable).strip().lower().replace("_", " ") in {"not applicable", "na", "n/a"}:
            return NOT_APPLICABLE
    value = _row_value(row, path)
    if value is None or value == "":
        return None
    if qtype == "number":
        return read_number(value)
    if qtype == "yesno":
        token = str(value).strip().lower()
        if token in {"yes", "no"}:
            return token
        return None
    if qtype == "date":
        parsed = _parse_date(value)
        return parsed.isoformat() if parsed else str(value).strip()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def fetch_json(url: str, token: str):
    request = urllib.request.Request(url, headers={"Authorization": f"Token {token}"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_asset(uid: str, token: str) -> dict:
    return fetch_json(f"{KOBO_API_ROOT}/assets/{uid}/?format=json", token)


def fetch_submissions(uid: str, token: str) -> list[dict]:
    url = f"{KOBO_API_ROOT}/assets/{uid}/data/?format=json&limit=300"
    rows: list[dict] = []
    while url:
        payload = fetch_json(url, token)
        rows.extend(payload.get("results") or [])
        url = payload.get("next")
    return rows


def _report_path() -> Path:
    folder = _BACKOFFICE_ROOT / ".tmp"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "ppp_kobo_import_report.txt"


def _write_report(lines: list[str]) -> Path:
    path = _report_path()
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _truncate_name(name: str, limit: int = 100) -> str:
    text = (name or "").strip()
    if len(text) <= limit:
        return text
    shortened = text.replace("Pilot Programmatic Partnership | ", "PPP | ")
    if len(shortened) <= limit:
        return shortened
    return shortened[: limit - 1].rstrip() + "…"


def _indicator_texts(indicator) -> list[str]:
    texts = [indicator.name or ""]
    translations = indicator.name_translations if isinstance(indicator.name_translations, dict) else {}
    if translations.get("en"):
        texts.append(translations["en"])
    aggregated = getattr(indicator, "aggregated_label", None)
    if aggregated:
        texts.append(aggregated)
    monitoring = indicator.monitoring_questions
    if isinstance(monitoring, list):
        for item in monitoring:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                for key in ("question", "text", "label", "name"):
                    if item.get(key):
                        texts.append(str(item[key]))
                        break
    return texts


def _type_code(indicator) -> str:
    return str(indicator.type or "").strip().lower()


def _unit_allows_people_disagg(indicator) -> bool:
    unit = str(indicator.unit or "").strip().lower()
    if unit in {"people", "volunteers", "staff"}:
        return True
    measurement = getattr(indicator, "measurement_unit", None)
    return bool(measurement and getattr(measurement, "allows_disaggregation", False))


def build_indicator_index(indicators) -> dict[str, list]:
    index: dict[str, list] = {}
    for indicator in indicators:
        if getattr(indicator, "archived", False):
            continue
        for text in _indicator_texts(indicator):
            key = normalize_indicator_label(text)
            if len(key) < 8:
                continue
            index.setdefault(key, []).append(indicator)
    return index


def _indicator_compatible(indicator, *, numeric: bool, disagg: bool) -> bool:
    code = _type_code(indicator)
    if numeric and code not in {"number", "integer", "count"}:
        return False
    if not numeric and code not in {"yesno", "yes/no", "boolean"}:
        return False
    if disagg and not _unit_allows_people_disagg(indicator):
        return False
    return True


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def match_indicator(label: str, *, numeric: bool, disagg: bool, index: dict[str, list]):
    """Return one indicator when the label matches one bank row closely.

    Exact normalised titles win. Otherwise the question and the bank title must
    share most of their meaningful words and read as nearly the same sentence,
    and a second indicator must not be similarly close.
    """
    key = normalize_indicator_label(label)
    if len(key) < 8:
        return None
    exact = []
    seen = set()
    for indicator in index.get(key, []):
        if indicator.id in seen or not _indicator_compatible(indicator, numeric=numeric, disagg=disagg):
            continue
        seen.add(indicator.id)
        exact.append(indicator)
    if len(exact) == 1:
        return exact[0]

    question_key = compare_key(label)
    question_tokens = _content_tokens(label)
    if len(question_tokens) < 4:
        return None
    ranked = []
    considered = {}
    for indicators in index.values():
        for indicator in indicators:
            considered[indicator.id] = indicator
    for indicator in considered.values():
        if not _indicator_compatible(indicator, numeric=numeric, disagg=disagg):
            continue
        best_ratio = 0.0
        best_overlap = 0.0
        for text in _indicator_texts(indicator):
            candidate = compare_key(text)
            if not candidate:
                continue
            best_ratio = max(best_ratio, difflib.SequenceMatcher(None, question_key, candidate).ratio())
            best_overlap = max(best_overlap, _jaccard(question_tokens, _content_tokens(text)))
        if best_ratio >= 0.80 and best_overlap >= 0.72:
            ranked.append((best_overlap, best_ratio, indicator))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.08 and ranked[0][1] - ranked[1][1] < 0.04:
        return None
    return ranked[0][2]


def explicit_bank_match(kobo_name: str, indicators):
    """Return the Indicator Bank row named by a known Kobo question, if the bank has it."""
    fragment = EXPLICIT_BANK_NAME_FRAGMENTS.get(kobo_name or "")
    if not fragment:
        return None
    needle = fragment.lower()
    hits = [
        indicator for indicator in indicators
        if needle in (indicator.name or "").lower() and not getattr(indicator, "archived", False)
    ]
    if len(hits) == 1:
        return hits[0]
    return None


def _index_indicators(index: dict) -> list:
    found = {}
    for rows in (index or {}).values():
        for indicator in rows:
            found[indicator.id] = indicator
    return list(found.values())


def _ensure_ppp_indicator(label: str, people_unit):
    """Create a number/people Indicator Bank row when no existing title matches."""
    from app.extensions import db
    from app.models import IndicatorBank, IndicatorBankType

    name = bank_name_for_label(label)
    existing = IndicatorBank.query.filter(db.func.lower(IndicatorBank.name) == name.lower()).first()
    if existing is not None:
        return existing
    number_type = IndicatorBankType.query.filter_by(code="number").first()
    indicator = IndicatorBank(
        name=name,
        type="number",
        unit=(people_unit.name if people_unit is not None else "People"),
        indicator_type_id=(number_type.id if number_type is not None else None),
        indicator_unit_id=(people_unit.id if people_unit is not None else None),
        definition=name,
        comments=(
            "Created for the Pilot Programmatic Partnership Kobo import. "
            "No existing Indicator Bank title matched this question."
        ),
    )
    db.session.add(indicator)
    db.session.flush()
    return indicator


def bank_name_for_label(label: str) -> str:
    """Stable Indicator Bank title for a PPP question that has no existing match."""
    text = NUMBER_PREFIX_RE.sub("", label or "")
    text = re.sub(r"\s+", " ", text).strip().rstrip("?").strip()
    return text or "PPP indicator"


def _people_unit(units):
    for unit in units:
        if str(unit.name or "").strip().lower() == "people" or str(unit.code or "").strip().lower() == "people":
            return unit
    return None


def _default_config(*, disagg: bool, allow_na: bool, modes: list[str] | None = None) -> dict:
    config = {
        "is_required": False,
        "layout_column_width": 12,
        "layout_break_after": False,
        "allow_data_not_available": False,
        "allow_not_applicable": allow_na,
        "privacy": "ifrc_network",
        "kobo_import": "ppp",
    }
    if disagg:
        config["allowed_disaggregation_options"] = modes or ["total", "sex", "age", "sex_age"]
        config["age_groups_config"] = AGE_GROUPS_CONFIG
    return config


def _resolve_owner(email: str | None):
    from app.models import RbacRole, RbacUserRole, User

    if email:
        user = User.query.filter(User.email.ilike(email.strip())).first()
        if user is None:
            raise SystemExit(f"No user with email {email}")
        return user
    user = (
        User.query.join(RbacUserRole, RbacUserRole.user_id == User.id)
        .join(RbacRole, RbacRole.id == RbacUserRole.role_id)
        .filter(RbacRole.code == "system_manager")
        .order_by(User.id)
        .first()
    )
    if user is None:
        user = User.query.order_by(User.id).first()
    if user is None:
        raise SystemExit("No user exists to own the templates. Pass --owner-email.")
    return user


def _country_indexes():
    from app.models import Country, FdrsSociety, NationalSociety
    from sqlalchemy.exc import SQLAlchemyError

    from app.extensions import db

    countries = Country.query.all()
    by_fold = {}
    for country in countries:
        by_fold.setdefault(fold_name(country.name), country)
        if country.short_name:
            by_fold.setdefault(fold_name(country.short_name), country)
        if country.iso3:
            by_fold.setdefault(fold_name(country.iso3), country)
    societies = {}
    try:
        for society in FdrsSociety.query.all():
            if society.don_code and society.country_id and society.country:
                societies[society.don_code.strip().upper()] = society.country
    except SQLAlchemyError:
        db.session.rollback()
    ns_by_fold = {}
    try:
        for society in NationalSociety.query.all():
            country = getattr(society, "country", None)
            if country is not None and society.name:
                ns_by_fold.setdefault(fold_name(society.name), country)
    except SQLAlchemyError:
        db.session.rollback()
    return by_fold, societies, ns_by_fold


def resolve_country(stored_name: str, choice_by_value: dict, by_fold, societies, ns_by_fold):
    meta = choice_by_value.get(stored_name) or {}
    don = (meta.get("don_code") or "").upper()
    if don and don in societies:
        return societies[don]
    folded = fold_name(stored_name)
    if folded in by_fold:
        return by_fold[folded]
    alias = COUNTRY_ALIASES.get(folded)
    if alias and alias in by_fold:
        return by_fold[alias]
    label = meta.get("label") or ""
    if label and fold_name(label) in ns_by_fold:
        return ns_by_fold[fold_name(label)]
    return None


def _ns_choices(choices: list) -> dict[str, dict]:
    return {row["value"]: row for row in _choice_rows(choices, "national_society")}


def _delete_previous(template_id: int) -> None:
    from app.extensions import db
    from app.models import AssignedForm, FormTemplate

    template = db.session.get(FormTemplate, template_id)
    if template is None:
        return
    for assigned in AssignedForm.query.filter_by(template_id=template.id).all():
        db.session.delete(assigned)
    db.session.flush()
    template.published_version_id = None
    db.session.flush()
    db.session.delete(template)
    db.session.flush()


def _find_previous(uid: str):
    from app.models import FormTemplateVersion

    marker = f"{MARKER_PREFIX}{uid}"
    return FormTemplateVersion.query.filter(FormTemplateVersion.description.contains(marker)).first()


def _store_answer(aes, item, field, row, *, submitted_at, stats) -> None:
    from app.extensions import db
    from app.models import FormData

    if field["disagg"]:
        payload = matrix_payload(row, field["binds"])
        if not payload:
            return
        entry = FormData(assignment_entity_status_id=aes.id, form_item_id=item.id, submitted_at=submitted_at)
        if payload.get("not_applicable"):
            entry.not_applicable = True
            entry.data_not_available = False
            entry.value = None
            entry.numeric_value = None
            entry.disagg_data = None
            entry.disagg_type = None
        elif payload.get("mode") == "total":
            entry.set_simple_value(payload.get("value"))
        else:
            entry.set_disaggregated_data(payload["mode"], payload["values"])
        db.session.add(entry)
        stats["values"] += 1
        return

    if field["kind"] == "file":
        text = _file_answer(row, field)
        if not text:
            return
        entry = FormData(assignment_entity_status_id=aes.id, form_item_id=item.id, submitted_at=submitted_at)
        entry.set_simple_value(text)
        db.session.add(entry)
        stats["values"] += 1
        stats["files"] += 1
        return

    answer = scalar_answer(row, field)
    if answer is None or answer == "":
        return
    entry = FormData(assignment_entity_status_id=aes.id, form_item_id=item.id, submitted_at=submitted_at)
    if answer == NOT_APPLICABLE:
        entry.not_applicable = True
        entry.data_not_available = False
        entry.value = None
        entry.numeric_value = None
        entry.disagg_data = None
        entry.disagg_type = None
    else:
        entry.set_simple_value(answer)
    db.session.add(entry)
    stats["values"] += 1


def _file_answer(row: dict, field: dict) -> str | None:
    path = (field.get("binds") or {}).get("value")
    raw_name = _row_value(row, path)
    filename = str(raw_name).strip() if raw_name else ""
    field_name = field.get("kobo_name") or ""
    for attachment in row.get("_attachments") or []:
        if not isinstance(attachment, dict):
            continue
        xpath = str(attachment.get("question_xpath") or "")
        media = str(attachment.get("filename") or attachment.get("media_file") or "")
        if field_name and (xpath.endswith("/" + field_name) or xpath.endswith(field_name) or (filename and filename in media)):
            download = attachment.get("download_url") or attachment.get("download_large_url") or ""
            saved = _download_attachment(download, media or filename, row.get("_id"))
            if saved:
                return saved
            if media or filename:
                return media or filename
    return filename or None


def _download_attachment(url: str, filename: str, submission_id) -> str | None:
    token = os.environ.get("KOBO_API_TOKEN") or ""
    if not url or not token:
        return None
    try:
        from werkzeug.utils import secure_filename

        from app.services.platform.storage_service import upload

        request = urllib.request.Request(url, headers={"Authorization": f"Token {token}"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        safe = secure_filename(Path(filename).name) or "kobo-file"
        rel = f"ppp-kobo/{submission_id}/{safe}"
        upload("submissions", rel, data)
        return f"submissions/{rel}"
    except (OSError, urllib.error.URLError, ValueError):
        return None


def import_asset(asset: dict, submissions: list[dict], *, owner, apply: bool, replace: bool, indicator_index, people_unit) -> dict:
    from app.extensions import db
    from app.models import (
        AssignedForm,
        AssignmentEntityStatus,
        FormItem,
        FormSection,
        FormTemplate,
        FormTemplateVersion,
    )
    from app.models.enums import AssignmentEntityStatusValue
    from app.services.forms.reporting_period_service import sync_assigned_form_reporting_period, upsert_reporting_period
    from app.utils.datetime_helpers import utcnow

    uid = asset.get("uid")
    form_name = asset.get("name") or uid
    content = asset.get("content") or {}
    survey = content.get("survey") or []
    choices = content.get("choices") or []
    compiled = compile_survey(survey, choices)
    stats = {
        "uid": uid,
        "name": form_name,
        "sections": sum(1 for section in compiled),
        "fields": sum(len(section["fields"]) for section in compiled),
        "indicators": 0,
        "linked": 0,
        "submissions": len(submissions),
        "imported": 0,
        "skipped_status": 0,
        "skipped_country": 0,
        "skipped_duplicate": 0,
        "values": 0,
        "files": 0,
        "unmatched_countries": [],
        "links": [],
        "compiled": compiled,
    }

    kept: dict[tuple, dict] = {}
    for row in submissions:
        bucket = kobo_validation_bucket(row.get("_validation_status"))
        status = assignment_status_for_bucket(bucket)
        if status is None:
            stats["skipped_status"] += 1
            continue
        society = national_society_answer(row)
        if not society:
            stats["skipped_country"] += 1
            continue
        start, end = reporting_bounds(row)
        candidate = {
            "row": row,
            "status": status,
            "society": society,
            "start": start,
            "end": end,
            "period": period_name_for(start, end),
            "canon_start": canonical_round(start, end)[1],
            "canon_end": canonical_round(start, end)[2],
            "submitted_at": submission_time(row),
        }
        key = (society, candidate["period"])
        previous = kept.get(key)
        winner = choose_submission(previous, candidate)
        if previous is not None and winner is not previous:
            stats["skipped_duplicate"] += 1
        elif previous is not None and winner is previous:
            stats["skipped_duplicate"] += 1
        kept[key] = winner

    if not apply:
        by_fold, societies, ns_by_fold = _country_indexes()
        choice_by_value = _ns_choices(choices)
        unmatched = set()
        for (society, _period), payload in kept.items():
            if resolve_country(society, choice_by_value, by_fold, societies, ns_by_fold) is None:
                unmatched.add(society)
                continue
            stats["imported"] += 1
            for section in compiled:
                for field in section["fields"]:
                    if field["disagg"] and matrix_payload(payload["row"], field["binds"]):
                        stats["values"] += 1
                    elif field["kind"] == "file" and _row_value(payload["row"], (field.get("binds") or {}).get("value")):
                        stats["values"] += 1
                        stats["files"] += 1
                    elif field["kind"] != "note" and not field["disagg"] and scalar_answer(payload["row"], field) not in (None, ""):
                        stats["values"] += 1
        stats["unmatched_countries"] = sorted(unmatched)
        for section in compiled:
            for field in section["fields"]:
                if field["kind"] == "indicator":
                    stats["indicators"] += 1
                if field["kind"] == "indicator" or field["qtype"] == "yesno":
                    match = match_indicator(
                        field["label"],
                        numeric=field["qtype"] == "number",
                        disagg=field["disagg"],
                        index=indicator_index,
                    )
                    if match is not None:
                        stats["linked"] += 1
                        stats["links"].append((field["label"], match.id, match.name))
        return stats

    previous = _find_previous(uid)
    if previous is not None and not replace:
        raise SystemExit(
            f"{form_name} is already imported (template {previous.template_id}). "
            "Re-run with --replace to rebuild it."
        )
    if previous is not None and replace:
        _delete_previous(previous.template_id)

    by_fold, societies, ns_by_fold = _country_indexes()
    choice_by_value = _ns_choices(choices)
    now = utcnow()
    template = FormTemplate(created_by=owner.id, owned_by=owner.id)
    db.session.add(template)
    db.session.flush()
    version = FormTemplateVersion(
        template_id=template.id,
        version_number=1,
        status="published",
        name=_truncate_name(form_name),
        description=(
            f"{MARKER_PREFIX}{uid}. Imported from IFRC Kobo "
            f"({form_name}). Historical PPP submissions; not approved rows were skipped."
        ),
        add_to_self_report=False,
        display_order_visible=False,
        is_paginated=False,
        enable_export_pdf=True,
        enable_export_excel=True,
        enable_import_excel=False,
        created_by=owner.id,
        updated_by=owner.id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(version)
    db.session.flush()
    template.published_version_id = version.id

    item_by_key = {}
    section_order = 0.0
    for section_info in compiled:
        section_order += 1
        section = FormSection(
            template_id=template.id,
            version_id=version.id,
            name=(section_info["name"] or "Section")[:100],
            name_translations=section_info["translations"] or None,
            order=section_order,
            section_type="standard",
        )
        db.session.add(section)
        db.session.flush()
        item_order = 0.0
        for field in section_info["fields"]:
            item_order += 1
            linked = None
            if field["kind"] == "indicator" or field["qtype"] == "yesno":
                linked = explicit_bank_match(field["kobo_name"], _index_indicators(indicator_index))
                if linked is None:
                    linked = match_indicator(
                        field["label"],
                        numeric=field["qtype"] == "number",
                        disagg=field["disagg"],
                        index=indicator_index,
                    )
                if linked is None and field["kind"] == "indicator":
                    linked = _ensure_ppp_indicator(field["label"], people_unit)
            if field["kind"] == "indicator":
                stats["indicators"] += 1
            item_type = "indicator" if field["kind"] == "indicator" or linked is not None else (
                "question" if field["kind"] != "file" else "question"
            )
            if field["kind"] == "note":
                item_type = "question"
            config = _default_config(
                disagg=field["disagg"],
                allow_na=field["allow_na"],
                modes=(field["binds"] or {}).get("modes"),
            )
            config["kobo_name"] = field["kobo_name"]
            item = FormItem(
                section_id=section.id,
                template_id=template.id,
                version_id=version.id,
                item_type=item_type if not (linked and field["qtype"] == "yesno") else "indicator",
                label=field["label"][:5000],
                label_translations=field["translations"] or None,
                order=item_order,
                type=(linked.type if linked is not None else field["qtype"]),
                unit=(linked.unit if linked is not None else ("People" if field["disagg"] else None)),
                indicator_bank_id=linked.id if linked is not None else None,
                indicator_type_id=linked.indicator_type_id if linked is not None else None,
                indicator_unit_id=(
                    linked.indicator_unit_id
                    if linked is not None
                    else (people_unit.id if field["disagg"] and people_unit is not None else None)
                ),
                options_json=field["options"],
                definition=None if linked is not None else field.get("definition"),
                config=config,
            )
            if field["disagg"] and linked is None and people_unit is not None:
                item.unit = people_unit.name
                item.indicator_unit_id = people_unit.id
            db.session.add(item)
            db.session.flush()
            item_by_key[(section_info["kobo_name"], field["kobo_name"])] = (item, field)
            if linked is not None:
                stats["linked"] += 1
                stats["links"].append((field["label"], linked.id, linked.name))

    assignments: dict[str, object] = {}
    entities: dict[tuple, object] = {}
    unmatched = set()
    for (society, period), payload in sorted(kept.items(), key=lambda item: (item[0][1], item[0][0])):
        country = resolve_country(society, choice_by_value, by_fold, societies, ns_by_fold)
        if country is None:
            unmatched.add(society)
            stats["skipped_country"] += 1
            continue
        assigned = assignments.get(period)
        if assigned is None:
            assigned = AssignedForm(
                template_id=template.id,
                period_name=period[:100],
                is_active=True,
                is_closed=True,
                enable_export_excel=True,
                enable_export_pdf=True,
            )
            if payload.get("canon_start") and payload.get("canon_end"):
                upsert_reporting_period(
                    assigned.period_name,
                    period_type=round_period_type(assigned.period_name),
                    period_start=payload["canon_start"],
                    period_end=payload["canon_end"],
                )
            sync_assigned_form_reporting_period(assigned)
            db.session.add(assigned)
            db.session.flush()
            assignments[period] = assigned
        entity_key = (assigned.id, country.id)
        aes = entities.get(entity_key)
        if aes is None:
            aes = AssignmentEntityStatus(
                assigned_form_id=assigned.id,
                entity_type="country",
                entity_id=country.id,
                status=AssignmentEntityStatusValue(payload["status"]),
                status_timestamp=payload["submitted_at"] if payload["submitted_at"] != datetime.min else now,
                submitted_at=payload["submitted_at"] if payload["submitted_at"] != datetime.min else now,
            )
            db.session.add(aes)
            db.session.flush()
            entities[entity_key] = aes
            stats["imported"] += 1
        for section_info in compiled:
            for field in section_info["fields"]:
                item, spec = item_by_key[(section_info["kobo_name"], field["kobo_name"])]
                when = payload["submitted_at"] if payload["submitted_at"] != datetime.min else now
                _store_answer(aes, item, spec, payload["row"], submitted_at=when, stats=stats)

    stats["unmatched_countries"] = sorted(unmatched)
    db.session.commit()
    stats["template_id"] = template.id
    return stats


def _print_stats(stats: dict, report: list[str]) -> None:
    print(
        f"{stats['name']}: {stats['fields']} fields, {stats['linked']} indicator links, "
        f"{stats['imported']} submissions imported, {stats['skipped_status']} skipped by status, "
        f"{stats['values']} values"
        + (f", template {stats.get('template_id')}" if stats.get("template_id") else "")
    )
    if stats["unmatched_countries"]:
        print("  unmatched countries: " + ", ".join(stats["unmatched_countries"]))
    report.append(f"## {stats['name']} ({stats['uid']})")
    report.append(
        f"fields={stats['fields']} indicators={stats['indicators']} linked={stats['linked']} "
        f"kobo_rows={stats['submissions']} imported={stats['imported']} "
        f"skipped_status={stats['skipped_status']} duplicates={stats['skipped_duplicate']} "
        f"values={stats['values']} files={stats['files']}"
    )
    for label, indicator_id, indicator_name in stats["links"]:
        report.append(f"  link: {label} -> [{indicator_id}] {indicator_name}")
    if stats["unmatched_countries"]:
        report.append("  unmatched: " + ", ".join(stats["unmatched_countries"]))


def _status_value(status) -> str:
    return str(getattr(status, "value", status) or "")


def _apply_indicator_link(item, bank, people_unit) -> None:
    """Point a form indicator at a bank row without dropping a sex/age grid."""
    item.indicator_bank_id = bank.id
    item.indicator_type_id = bank.indicator_type_id
    disagg = bool((item.config or {}).get("allowed_disaggregation_options"))
    if disagg and not _unit_allows_people_disagg(bank) and people_unit is not None:
        item.type = "number"
        item.unit = people_unit.name
        item.indicator_unit_id = people_unit.id
        return
    if bank.type:
        item.type = bank.type
    if bank.unit:
        item.unit = bank.unit
    if bank.indicator_unit_id:
        item.indicator_unit_id = bank.indicator_unit_id


def repair_existing() -> dict:
    """Collapse exact Kobo date pairs into checkpoint assignments and fill indicator links.

    Does not call Kobo. Safe to re-run: a second pass finds the checkpoint
    assignments already in place and leaves them.
    """
    from app.extensions import db
    from app.models import (
        AssignedForm,
        AssignmentEntityStatus,
        FormItem,
        FormTemplateVersion,
        IndicatorBank,
        IndicatorBankUnit,
    )
    from app.services.forms.reporting_period_service import (
        sync_assigned_form_reporting_period,
        upsert_reporting_period,
    )

    versions = FormTemplateVersion.query.filter(FormTemplateVersion.description.contains(MARKER_PREFIX)).all()
    template_ids = sorted({version.template_id for version in versions})
    if not template_ids:
        raise SystemExit("No PPP Kobo templates found to repair.")

    people_unit = _people_unit(IndicatorBankUnit.query.all())
    indicators = IndicatorBank.query.filter_by(archived=False).all()
    summary = {"templates": len(template_ids), "assignments_removed": 0, "submissions_removed": 0, "indicators_linked": 0, "indicators_created": 0}

    for template_id in template_ids:
        removed_forms, removed_rows = _consolidate_template(template_id)
        summary["assignments_removed"] += removed_forms
        summary["submissions_removed"] += removed_rows
        linked, created = _link_template_indicators(template_id, indicators, people_unit)
        summary["indicators_linked"] += linked
        summary["indicators_created"] += created
        indicators = IndicatorBank.query.filter_by(archived=False).all()

    db.session.commit()
    return summary


def _consolidate_template(template_id: int) -> tuple[int, int]:
    from app.extensions import db
    from app.models import AssignedForm, AssignmentEntityStatus
    from app.services.forms.reporting_period_service import (
        sync_assigned_form_reporting_period,
        upsert_reporting_period,
    )

    forms = AssignedForm.query.filter_by(template_id=template_id).all()
    grouped: dict[tuple, list] = {}
    for form in forms:
        round_name, canon_start, canon_end = canonical_round(form.period_start, form.period_end)
        for aes in form.entity_statuses.all():
            grouped.setdefault((round_name, canon_start, canon_end, aes.entity_id), []).append((form, aes))

    drop_aes = []
    keep = []
    for (round_name, canon_start, canon_end, _entity_id), rows in grouped.items():
        winner = max(rows, key=lambda pair: _submission_rank({
            "status": _status_value(pair[1].status),
            "start": pair[0].period_start,
            "end": pair[0].period_end,
            "submitted_at": pair[1].submitted_at or datetime.min,
        }))
        keep.append((round_name, canon_start, canon_end, winner[1]))
        drop_aes.extend(aes for form, aes in rows if aes.id != winner[1].id)

    from app.models import FormData

    for aes in drop_aes:
        FormData.query.filter_by(assignment_entity_status_id=aes.id).delete(synchronize_session=False)
        db.session.delete(aes)
    db.session.flush()

    canonical_forms = {}
    for round_name, canon_start, canon_end, aes in keep:
        form = canonical_forms.get(round_name)
        if form is None:
            form = AssignedForm.query.filter_by(template_id=template_id, period_name=round_name).first()
        if form is None:
            from sqlalchemy.exc import IntegrityError

            form = AssignedForm(
                template_id=template_id,
                period_name=round_name,
                is_active=True,
                is_closed=True,
                enable_export_excel=True,
                enable_export_pdf=True,
            )
            try:
                with db.session.begin_nested():
                    db.session.add(form)
                    db.session.flush()
            except IntegrityError:
                form = AssignedForm.query.filter_by(
                    template_id=template_id,
                    period_name=round_name,
                ).one()
        if canon_start and canon_end:
            upsert_reporting_period(
                round_name,
                period_type=round_period_type(round_name),
                period_start=canon_start,
                period_end=canon_end,
            )
            sync_assigned_form_reporting_period(form)
        canonical_forms[round_name] = form
        if aes.assigned_form_id != form.id:
            aes.assigned_form_id = form.id
    db.session.flush()

    removed_forms = 0
    kept_ids = {form.id for form in canonical_forms.values()}
    for form in AssignedForm.query.filter_by(template_id=template_id).all():
        if form.id in kept_ids:
            continue
        if form.entity_statuses.count() == 0:
            db.session.delete(form)
            removed_forms += 1
    db.session.flush()
    return removed_forms, len(drop_aes)


def _link_template_indicators(template_id: int, indicators, people_unit) -> tuple[int, int]:
    from app.models import FormItem, IndicatorBank

    linked = 0
    created = 0
    before = {row.id for row in indicators}
    items = FormItem.query.filter_by(template_id=template_id, item_type="indicator").all()
    for item in items:
        if item.indicator_bank_id:
            continue
        kobo_name = (item.config or {}).get("kobo_name") or ""
        bank = explicit_bank_match(kobo_name, indicators)
        if bank is None:
            bank = match_indicator(
                item.label,
                numeric=(item.type or "number") == "number",
                disagg=bool((item.config or {}).get("allowed_disaggregation_options")),
                index=build_indicator_index(indicators),
            )
        if bank is None:
            bank = _ensure_ppp_indicator(item.label, people_unit)
            if bank.id not in before:
                created += 1
                before.add(bank.id)
                indicators.append(bank)
        _apply_indicator_link(item, bank, people_unit)
        linked += 1
    return linked, created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import PPP Kobo projects into Backoffice.")
    parser.add_argument("--apply", action="store_true", help="Write templates and submissions. Default is a dry run.")
    parser.add_argument("--replace", action="store_true", help="Delete a previous import of the same Kobo asset first.")
    parser.add_argument("--owner-email", default=None, help="User who owns the new templates.")
    parser.add_argument("--structure-only", action="store_true", help="Compile the forms and skip submission download.")
    parser.add_argument("--asset", action="append", dest="assets", help="Import only this Kobo asset uid. Repeatable.")
    parser.add_argument(
        "--repair",
        action="store_true",
        help="On an existing import, collapse date-pair assignments into checkpoint rounds and link indicators. Does not call Kobo.",
    )
    args = parser.parse_args(argv)

    if args.repair:
        from app import create_app

        app = create_app()
        with app.app_context():
            summary = repair_existing()
        print(
            f"Repaired {summary['templates']} templates: "
            f"removed {summary['assignments_removed']} assignments and {summary['submissions_removed']} duplicate submissions, "
            f"linked {summary['indicators_linked']} indicators ({summary['indicators_created']} new Indicator Bank rows)."
        )
        return 0

    token = (os.environ.get("KOBO_API_TOKEN") or "").strip()
    if not token:
        raise SystemExit("Set KOBO_API_TOKEN to a Kobo API token that can read these projects.")

    uids = tuple(args.assets) if args.assets else ASSET_UIDS
    from app import create_app

    app = create_app()
    report: list[str] = []
    with app.app_context():
        from app.models import IndicatorBank, IndicatorBankUnit

        owner = _resolve_owner(args.owner_email)
        indicators = IndicatorBank.query.filter_by(archived=False).all()
        indicator_index = build_indicator_index(indicators)
        people_unit = _people_unit(IndicatorBankUnit.query.all())
        from app.extensions import db

        print(f"Owner: {owner.email}. Indicator bank rows considered: {len(indicators)}.")
        for uid in uids:
            asset = fetch_asset(uid, token)
            submissions = [] if args.structure_only else fetch_submissions(uid, token)
            try:
                stats = import_asset(
                    asset,
                    submissions,
                    owner=owner,
                    apply=bool(args.apply) and not args.structure_only,
                    replace=args.replace,
                    indicator_index=indicator_index,
                    people_unit=people_unit,
                )
            except Exception:
                db.session.rollback()
                raise
            _print_stats(stats, report)
            for section in stats["compiled"]:
                report.append(f"  [{section['name']}]")
                for field in section["fields"]:
                    report.append(
                        f"    {field['kind']}/{field['qtype']} {field['label'][:160]}"
                    )
    path = _write_report(report)
    print(f"Report: {path}")
    if not args.apply:
        print("Dry run only. Re-run with --apply to write the local database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
