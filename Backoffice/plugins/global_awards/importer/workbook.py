"""Read the IFRC MARC logframe mastersheet. No database access."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from plugins.global_awards.constants import DEFAULT_WORKBOOK, SHEET_NAME
from plugins.global_awards.importer.schedule import AwardWindow, parse_award_window

_HEADING_LIMIT = 120
_SKIP_PREFIXES = ("notes to self",)
_META_HEADERS = {
    "total",
    "targets",
    "unit of measurement",
    "data collection method",
    "assumptions",
    "disaggregation",
    "collection / reporting frequency",
    "responsibility",
    "measurement and aggregation rule",
    "baseline value",
    "baseline establishment",
    "target setting / aggregation",
    "quality and limitations",
    "decision / missing inputs",
    "evidence / rationale",
    "results level / placement",
}
_NOT_A_CODE = {"", "custom", "na", "n/a"}


@dataclass
class LogframeIndicator:
    """One measurable row, placed in a section and keyed for re-import."""

    row: int
    key: str
    section_key: str
    section_name: str
    section_statement: str
    display_code: str
    code: str
    reference: str
    source: str
    label: str
    definition: str
    unit: str
    disaggregation: str
    frequency: str
    scope: str
    results_level: str
    targets: Dict[str, str] = field(default_factory=dict)

    @property
    def cited_bank_id(self) -> Optional[int]:
        """IFRC indicator-bank id when the logframe names that source and a number."""
        if "indicator bank" not in (self.source or "").casefold():
            return None
        match = re.search(r"\d+", self.reference or "")
        if not match:
            return None
        return int(match.group())


@dataclass
class LogframeSection:
    key: str
    name: str
    statement: str
    order: float


@dataclass
class ParsedLogframe:
    goal: str
    countries: List[str]
    sections: List[LogframeSection]
    indicators: List[LogframeIndicator]
    award: Optional[AwardWindow] = None
    timeframe_note: str = ""


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).replace("\u000d", " ").replace("_x000D_", " ").replace("\xa0", " ")
    return " ".join(text.split())


def format_cell(value: Any) -> str:
    """Keep a target cell as written: whole numbers without a trailing .0."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        if value.is_integer():
            return str(int(value))
        text = format(value, "f").rstrip("0").rstrip(".")
        return text
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    text = clean_text(value)
    if text.startswith("#"):
        return ""
    return text


def slug(text: str, limit: int = 48) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", (text or "").casefold()).strip("-")
    return (token or "item")[:limit]


def clip(text: str, limit: int = 100) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return (cut or text[: limit - 1]).rstrip() + "…"


def _header_key(value: Any) -> str:
    return clean_text(value).casefold()


def _display_code(code: str, reference: str) -> str:
    if code:
        return code
    token = (reference or "").split()
    if not token:
        return ""
    head = token[0].strip("()")
    if head.casefold() in _NOT_A_CODE:
        return ""
    return head


def _objective_parts(text: str) -> tuple[str, str, str]:
    match = re.match(r"objective\s+(\d+)\b(.*)", text, flags=re.IGNORECASE)
    if not match:
        return f"objective:{slug(text)}", clip(text), text
    number = match.group(1)
    rest = re.sub(r"^\s*\([^)]*\)\s*", "", match.group(2) or "")
    title = rest.split(":")[0].strip(" .")
    short = f"Objective {number}"
    name = clip(f"{short}. {title}" if title else short)
    return f"objective-{number}", name, text


def _outcome_parts(text: str) -> tuple[str, str, str]:
    match = re.match(r"outcome\s+([\d.]+)\s*[:.]?\s*(.*)", text, flags=re.IGNORECASE)
    if not match:
        return f"outcome:{slug(text)}", clip(text), text
    code = match.group(1).strip(".")
    title = (match.group(2) or "").strip(" .")
    short = f"Outcome {code}"
    name = clip(f"{short}. {title}" if title else short)
    return "outcome-" + code.replace(".", "-"), name, text


def _heading_kind(text: str, source: str, unit: str, definition: str, code: str) -> Optional[str]:
    lowered = text.casefold()
    if any(lowered.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return "skip"
    if lowered.startswith("goal"):
        return "goal"
    if lowered.startswith("objective"):
        return "objective"
    if lowered.startswith("outcome"):
        return "outcome"
    if not source and not unit and not definition and not code and len(text) <= _HEADING_LIMIT:
        return "topic"
    return None


def _is_indicator(source: str, unit: str, definition: str, code: str) -> bool:
    return bool(source or unit or definition or code)


class _Outline:
    """Tracks the goal / objective / outcome / topic the next indicator belongs to."""

    def __init__(self) -> None:
        self.goal = ""
        self.parent_key = "goal"
        self.parent_name = "Goal"
        self.parent_short = "Goal"
        self.parent_statement = ""
        self.topic_key = ""
        self.topic_name = ""

    def goal_heading(self, text: str) -> None:
        self.goal = text
        self.parent_key = "goal"
        self.parent_name = "Goal"
        self.parent_short = "Goal"
        self.parent_statement = text
        self.topic_key = ""
        self.topic_name = ""

    def objective_heading(self, text: str) -> None:
        key, name, statement = _objective_parts(text)
        self.parent_key = key
        self.parent_name = name
        number = re.fullmatch(r"objective-(\d+)", key)
        self.parent_short = f"Objective {number.group(1)}" if number else "Objective"
        self.parent_statement = statement
        self.topic_key = ""
        self.topic_name = ""

    def outcome_heading(self, text: str) -> None:
        key, name, statement = _outcome_parts(text)
        self.parent_key = key
        self.parent_name = name
        if key.startswith("outcome-"):
            self.parent_short = "Outcome " + key[len("outcome-"):].replace("-", ".")
        else:
            self.parent_short = "Outcome"
        self.parent_statement = statement
        self.topic_key = ""
        self.topic_name = ""

    def topic_heading(self, text: str) -> None:
        self.topic_key = f"{self.parent_key}:{slug(text)}"
        self.topic_name = clip(f"{self.parent_short} · {text}")

    @property
    def section_key(self) -> str:
        return self.topic_key or self.parent_key

    @property
    def section_name(self) -> str:
        return self.topic_name or self.parent_name

    @property
    def section_statement(self) -> str:
        if self.topic_name and self.parent_statement:
            topic = self.topic_name.split("·", 1)[-1].strip()
            return f"{self.parent_statement}\n\n{topic}"
        return self.parent_statement


def parse_workbook(workbook) -> ParsedLogframe:
    """Turn an open workbook into sections and indicators."""
    if SHEET_NAME not in workbook.sheetnames:
        raise ValueError(f"The workbook has no sheet named {SHEET_NAME}.")
    sheet = workbook[SHEET_NAME]
    rows = [tuple(row) for row in sheet.iter_rows(values_only=True)]
    header_index = _find_header(rows)
    header = rows[header_index]
    columns = _columns(header)
    outline = _Outline()
    sections: Dict[str, LogframeSection] = {}
    indicators: List[LogframeIndicator] = []
    seen_keys: Dict[str, int] = {}

    for offset, raw in enumerate(rows[header_index + 1 :], start=header_index + 2):
        padded = list(raw) + [None] * max(0, len(header) - len(raw))
        label = clean_text(_at(padded, columns["indicator"]))
        if not label:
            continue
        if label.casefold().startswith("notes to self"):
            break
        source = clean_text(_at(padded, columns.get("source")))
        unit = clean_text(_at(padded, columns.get("unit")))
        definition = clean_text(_at(padded, columns.get("definition")))
        code = clean_text(_at(padded, columns.get("code")))
        kind = _heading_kind(label, source, unit, definition, code)
        if kind == "skip":
            break
        if kind == "goal":
            outline.goal_heading(label)
            continue
        if kind == "objective":
            outline.objective_heading(label)
            continue
        if kind == "outcome":
            outline.outcome_heading(label)
            continue
        if kind == "topic":
            outline.topic_heading(label)
            continue
        if not _is_indicator(source, unit, definition, code):
            continue

        reference = clean_text(_at(padded, columns.get("reference")))
        display = _display_code(code, reference)
        base_key = f"{outline.section_key}:{display or slug(label)}"
        seen_keys[base_key] = seen_keys.get(base_key, 0) + 1
        key = base_key if seen_keys[base_key] == 1 else f"{base_key}-{seen_keys[base_key]}"
        if outline.section_key not in sections:
            sections[outline.section_key] = LogframeSection(
                key=outline.section_key,
                name=outline.section_name or "General",
                statement=outline.section_statement,
                order=float(len(sections) + 1),
            )
        targets = {}
        for name, index in columns["countries"]:
            target = format_cell(_at(padded, index))
            if target:
                targets[name] = target
        indicators.append(
            LogframeIndicator(
                row=offset,
                key=key,
                section_key=outline.section_key,
                section_name=sections[outline.section_key].name,
                section_statement=sections[outline.section_key].statement,
                display_code=display,
                code=code,
                reference=reference,
                source=source,
                label=label,
                definition=definition,
                unit=unit,
                disaggregation=clean_text(_at(padded, columns.get("disaggregation"))),
                frequency=clean_text(_at(padded, columns.get("frequency"))),
                scope=clean_text(_at(padded, columns.get("scope"))),
                results_level=clean_text(_at(padded, columns.get("results"))),
                targets=targets,
            )
        )

    if not indicators:
        raise ValueError(f"{SHEET_NAME} has a header but no indicator rows.")
    return ParsedLogframe(
        goal=outline.goal,
        countries=[name for name, _index in columns["countries"]],
        sections=list(sections.values()),
        indicators=indicators,
        award=parse_award_window(workbook),
        timeframe_note=_timeframe_note(rows[:header_index]),
    )


def load_logframe(source) -> ParsedLogframe:
    """Open a path or uploaded bytes and parse the mastersheet."""
    workbook = open_workbook(source)
    try:
        return parse_workbook(workbook)
    finally:
        workbook.close()


def open_workbook(source):
    if isinstance(source, (bytes, bytearray)):
        from app.utils.files.safe_workbook import load_workbook_safe

        return load_workbook_safe(source, read_only=True, data_only=True)
    import openpyxl

    return openpyxl.load_workbook(source, read_only=True, data_only=True)


def default_workbook_path():
    return DEFAULT_WORKBOOK


def _timeframe_note(rows: List[tuple]) -> str:
    """The mastersheet label such as ``12 months``, when the file states one."""
    for row in rows:
        cells = [clean_text(cell) for cell in row]
        for index, cell in enumerate(cells):
            if cell.casefold().rstrip(":") == "timeframe" and index + 1 < len(cells):
                return cells[index + 1]
    return ""


def _find_header(rows: List[tuple]) -> int:
    for index, row in enumerate(rows[:30]):
        labels = {_header_key(cell) for cell in row}
        if "indicator" in labels and "unit of measurement" in labels:
            return index
    raise ValueError(
        f"{SHEET_NAME} has no header row with Indicator and Unit of measurement."
    )


def _columns(header: tuple) -> dict:
    index = {_header_key(cell): position for position, cell in enumerate(header) if _header_key(cell)}
    required = ("indicator", "unit of measurement")
    missing = [name for name in required if name not in index]
    if missing:
        raise ValueError(f"{SHEET_NAME} is missing column(s): {', '.join(missing)}.")
    definition_at = index.get("definition", index["indicator"])
    stop_candidates = [
        index[name]
        for name in ("total", "unit of measurement")
        if name in index and index[name] > definition_at
    ]
    stop_at = min(stop_candidates) if stop_candidates else len(header)
    countries = []
    for position in range(definition_at + 1, stop_at):
        name = clean_text(header[position] if position < len(header) else None)
        if not name or _header_key(name) in _META_HEADERS:
            continue
        countries.append((name, position))
    return {
        "indicator": index["indicator"],
        "code": index.get("code"),
        "source": index.get("indicator source"),
        "reference": index.get("indicator reference"),
        "definition": index.get("definition"),
        "unit": index.get("unit of measurement"),
        "scope": index.get("scope"),
        "disaggregation": index.get("disaggregation"),
        "frequency": index.get("collection / reporting frequency"),
        "results": index.get("results level / placement"),
        "countries": countries,
    }


def _at(row: list, index: Optional[int]) -> Any:
    if index is None or index >= len(row):
        return None
    return row[index]
