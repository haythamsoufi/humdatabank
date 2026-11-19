"""Read the IFRC MARC logframe mastersheet. No database access."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from plugins.global_awards.constants import SHEET_NAME
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
    "submission note",
}
_NOT_A_CODE = {"", "custom", "na", "n/a"}
# The mastersheet states "Not applicable" in a country column when a line does not apply
# there. That is the absence of a target, not a target.
_NO_TARGET = {"not applicable", "n/a", "na", "n.a.", "none", "-", "–", "—"}
# Header names the identifier column has gone by across revisions of the annex.
_CODE_HEADERS = ("code", "indicator id", "indicator code", "id")


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
    topic: str = ""
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
    parent_key: str = ""
    kind: str = ""


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


def _split_heading_lines(text: Any) -> tuple[str, str, str]:
    """First line, remainder, and the full cleaned statement.

    Annex objective cells put the title on the first line and the statement on
    the next. ``clean_text`` would join those into one sentence and hide the title.
    """
    raw = str(text or "").replace("\u000d", "\n").replace("_x000D_", "\n").replace("\xa0", " ")
    lines = [clean_text(part) for part in re.split(r"[\n\r]+", raw)]
    lines = [line for line in lines if line]
    first = lines[0] if lines else ""
    after = " ".join(lines[1:])
    return first, after, " ".join(lines)


def _title_after_label(rest: str) -> str:
    return rest.split(":")[0].strip(" .")


def _objective_parts(text: Any) -> tuple[str, str, str]:
    first, after, statement = _split_heading_lines(text)
    match = re.match(r"objective\s+(\d+)\b(.*)", first, flags=re.IGNORECASE)
    if not match:
        return f"objective:{slug(first or statement)}", clip(first or statement), statement
    number = match.group(1)
    rest = re.sub(r"^\s*\([^)]*\)\s*", "", match.group(2) or "")
    title = _title_after_label(rest) or _title_after_label(after)
    name = clip(f"{number}. {title}" if title else f"{number}.")
    return f"objective-{number}", name, statement


def _outcome_parts(text: Any) -> tuple[str, str, str]:
    first, after, statement = _split_heading_lines(text)
    match = re.match(r"outcome\s+([\d.]+)\s*[:.]?\s*(.*)", first, flags=re.IGNORECASE)
    if not match:
        return f"outcome:{slug(first or statement)}", clip(first or statement), statement
    code = match.group(1).strip(".")
    title = (match.group(2) or "").strip(" .") or after
    name = clip(f"{code}. {title}" if title else f"{code}.")
    return "outcome-" + code.replace(".", "-"), name, statement


def _cross_cutting_parts(text: Any) -> tuple[str, str, str]:
    _first, _after, statement = _split_heading_lines(text)
    return "cross-cutting", "Cross-cutting", statement


def _topic_parts(text: str, parent_key: str) -> tuple[str, str, str]:
    label = clean_text(text)
    return f"{parent_key}-{slug(label)}", clip(label), label


def _is_cross_cutting(text: str) -> bool:
    lowered = (text or "").casefold()
    return lowered.startswith("cross cutting") or lowered.startswith("cross-cutting")


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
    if _is_cross_cutting(text):
        return "cross_cutting"
    if not source and not unit and not definition and not code and len(text) <= _HEADING_LIMIT:
        return "topic"
    return None


def _is_indicator(source: str, unit: str, definition: str, code: str) -> bool:
    return bool(source or unit or definition or code)


class _Outline:
    """Tracks the goal / objective / outcome the next indicator belongs to."""

    def __init__(self) -> None:
        self.goal = ""
        self.objective_key = ""
        self.objective_name = ""
        self.objective_statement = ""
        self.outcome_key = ""
        self.outcome_name = ""
        self.outcome_statement = ""
        self.cross_cutting_key = ""
        self.cross_cutting_name = ""
        self.cross_cutting_statement = ""
        self.sector_key = ""
        self.sector_name = ""
        self.sector_statement = ""
        self.topic = ""

    def _clear_sector(self) -> None:
        self.sector_key = ""
        self.sector_name = ""
        self.sector_statement = ""

    def _clear_children(self) -> None:
        self.outcome_key = ""
        self.outcome_name = ""
        self.outcome_statement = ""
        self.cross_cutting_key = ""
        self.cross_cutting_name = ""
        self.cross_cutting_statement = ""
        self._clear_sector()
        self.topic = ""

    def goal_heading(self, text: str) -> None:
        self.goal = _split_heading_lines(text)[2]
        self.objective_key = ""
        self.objective_name = ""
        self.objective_statement = ""
        self._clear_children()

    def objective_heading(self, text: str) -> None:
        key, name, statement = _objective_parts(text)
        self.objective_key = key
        self.objective_name = name
        self.objective_statement = statement
        self._clear_children()

    def outcome_heading(self, text: str) -> None:
        key, name, statement = _outcome_parts(text)
        self.outcome_key = key
        self.outcome_name = name
        self.outcome_statement = statement
        self.cross_cutting_key = ""
        self.cross_cutting_name = ""
        self.cross_cutting_statement = ""
        self._clear_sector()
        self.topic = ""

    def cross_cutting_heading(self, text: str) -> None:
        key, name, statement = _cross_cutting_parts(text)
        self.cross_cutting_key = key
        self.cross_cutting_name = name
        self.cross_cutting_statement = statement
        self._clear_sector()
        self.topic = ""

    def topic_heading(self, text: str) -> None:
        self.topic = text
        if self.cross_cutting_key:
            key, name, statement = _topic_parts(text, self.cross_cutting_key)
            self.sector_key = key
            self.sector_name = name
            self.sector_statement = statement
            return
        self._clear_sector()

    @property
    def section_key(self) -> str:
        return self.sector_key or self.cross_cutting_key or self.outcome_key or self.objective_key or "goal"

    @property
    def section_name(self) -> str:
        if self.sector_key:
            return self.sector_name
        if self.cross_cutting_key:
            return self.cross_cutting_name
        if self.outcome_key:
            return self.outcome_name
        if self.objective_key:
            return self.objective_name
        return "Goal"

    @property
    def section_statement(self) -> str:
        if self.sector_key:
            return self.sector_statement
        if self.cross_cutting_key:
            return self.cross_cutting_statement
        if self.outcome_key:
            return self.outcome_statement
        if self.objective_key:
            return self.objective_statement
        return self.goal

    @property
    def section_parent_key(self) -> str:
        if self.sector_key:
            return self.cross_cutting_key
        if self.cross_cutting_key:
            return ""
        if self.outcome_key:
            return self.objective_key
        return ""

    @property
    def section_kind(self) -> str:
        if self.sector_key:
            return "topic"
        if self.cross_cutting_key:
            return "cross_cutting"
        if self.outcome_key:
            return "outcome"
        if self.objective_key:
            return "objective"
        return "goal"


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
        raw_label = _at(padded, columns["indicator"])
        label = clean_text(raw_label)
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
        heading_text = raw_label if raw_label is not None else label
        if kind == "goal":
            outline.goal_heading(heading_text)
            _put_section(sections, outline)
            continue
        if kind == "objective":
            outline.objective_heading(heading_text)
            _put_section(sections, outline)
            continue
        if kind == "outcome":
            outline.outcome_heading(heading_text)
            _put_section(sections, outline)
            continue
        if kind == "cross_cutting":
            outline.cross_cutting_heading(heading_text)
            _put_section(sections, outline)
            continue
        if kind == "topic":
            outline.topic_heading(label)
            if outline.sector_key:
                _put_section(sections, outline)
            continue
        if not _is_indicator(source, unit, definition, code):
            continue

        reference = clean_text(_at(padded, columns.get("reference")))
        display = _display_code(code, reference)
        # An identifier from the sheet's ID column survives a line moving to another
        # heading; without one the key falls back to heading plus reference or wording.
        base_key = f"id:{slug(code)}" if code else f"{outline.section_key}:{display or slug(label)}"
        seen_keys[base_key] = seen_keys.get(base_key, 0) + 1
        key = base_key if seen_keys[base_key] == 1 else f"{base_key}-{seen_keys[base_key]}"
        _put_section(sections, outline)
        targets = {}
        for name, index in columns["countries"]:
            target = format_cell(_at(padded, index))
            if target and target.casefold() not in _NO_TARGET:
                targets[name] = target
        section = sections[outline.section_key]
        indicators.append(
            LogframeIndicator(
                row=offset,
                key=key,
                section_key=section.key,
                section_name=section.name,
                section_statement=section.statement,
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
                topic=outline.topic,
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


def _timeframe_note(rows: List[tuple]) -> str:
    """The mastersheet label such as ``12 months``, when the file states one."""
    for row in rows:
        cells = [clean_text(cell) for cell in row]
        for index, cell in enumerate(cells):
            if cell.casefold().rstrip(":") == "timeframe" and index + 1 < len(cells):
                return cells[index + 1]
            # "Timeframe: 17 Sep 2026 to 16 Sep 2027" in one cell.
            inline = re.match(r"timeframe\s*:\s*(.+)", cell, flags=re.IGNORECASE)
            if inline:
                return inline.group(1).strip()
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
        "code": next((index[name] for name in _CODE_HEADERS if name in index), None),
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


def _put_section(sections: Dict[str, LogframeSection], outline: _Outline) -> None:
    """Record a heading as soon as it appears, even if no indicator sits under it yet."""
    key = outline.section_key
    if key in sections:
        return
    sections[key] = LogframeSection(
        key=key,
        name=outline.section_name or "General",
        statement=outline.section_statement,
        order=float(len(sections) + 1),
        parent_key=outline.section_parent_key,
        kind=outline.section_kind,
    )


def _at(row: list, index: Optional[int]) -> Any:
    if index is None or index >= len(row):
        return None
    return row[index]
