"""Heuristic paragraph-style classifier and narrative flow estimates."""

from __future__ import annotations

import re

from plugins.upr_visuals.idml.constants import NARRATIVE_H
from plugins.upr_visuals.idml.xml_idml import _table_cell_height

_BANDS = {
    "ongoing emergency response",
    "strategic priorities",
    "enabling local actors",
    "success stories",
}
_MAJOR_H2 = {"context", "key achievements"}
_SUBHEADS = {
    "progress by the national society against objectives",
    "ifrc network joint support",
    "short description of the emergency operational strategy",
    "emergency appeal name",
    "emergency appeal number",
    "people assisted",
}
_SKIP_EXACT = {
    "(table for data)",
}
_SKIP_COVER_RE = re.compile(
    r"^(ifrc network (annual report|unified plan).+|appeal code:.+)$",
    re.IGNORECASE,
)
_SKIP_PREFIX = ("<space", "(table")

# space_before, leading, space_after — same as paragraph styles in _styles_xml.
_FLOW_METRICS = {
    "QHeading": (4.0, 24.0, 12.0),
    "SectionHead": (16.0, 18.0, 6.0),
    "TopicHead": (12.0, 17.0, 6.0),
    "BandHead": (14.0, 20.0, 10.0),
    "Subhead": (10.0, 13.5, 6.0),
    "Body": (0.0, 13.5, 8.5),
    "AdditionalHead": (8.0, 12.0, 10.0),
    "SourceItem": (0.0, 13.0, 6.0),
    "ContactHead": (16.0, 13.0, 10.0),
    "ContactName": (10.0, 13.0, 1.0),
    "ContactDetail": (0.0, 13.0, 1.0),
    "Blank": (0.0, 12.0, 4.0),
}
# Open Sans 10pt on a 530pt measure is ~100 characters, not 85.
_BODY_CHARS_PER_LINE = 100


def _para_hrefs(row: dict) -> list[str]:
    return [str(run.get("href") or "").strip() for run in (row.get("runs") or []) if str(run.get("href") or "").strip()]


def _para_is_bold(row: dict) -> bool:
    runs = [run for run in (row.get("runs") or []) if (run.get("text") or "").strip()]
    return bool(runs) and all(bool(run.get("bold")) for run in runs)


def _looks_like_link_line(text: str) -> bool:
    low = text.lower()
    return (
        "@" in text
        or "www." in low
        or low.startswith("http")
        or ".pdf" in low
        or low.startswith("t +")
        or low.startswith("t+")
    )


def _narrative_style(
    text: str,
    state: str,
    role: str = "",
    *,
    bullet: bool = False,
    has_href: bool = False,
    bold: bool = False,
) -> tuple[str | None, str]:
    raw = (text or "").strip()
    if not raw:
        return None, state
    low = raw.lower()
    if low.startswith("(box for additional"):
        return "AdditionalHead", "sources"
    if (
        low in _SKIP_EXACT
        or _SKIP_COVER_RE.match(raw)
        or any(low.startswith(p) for p in _SKIP_PREFIX)
        or role == "meta"
    ):
        return None, state
    if low == "additional information":
        return "AdditionalHead", "sources"
    if low == "contact information":
        return "ContactHead", "contact"
    if state == "sources":
        if low == "contact information":
            return "ContactHead", "contact"
        return "SourceItem", "sources"
    if state == "contact":
        if bold and not _looks_like_link_line(raw):
            return "ContactName", "contact"
        return "ContactDetail", "contact"
    if role == "body" and not low.startswith("q"):
        if low in _BANDS or low in _MAJOR_H2 or low in _SUBHEADS:
            pass
        else:
            return "Body", state
    if (low.startswith("q") and len(raw) < 120) or low.startswith("annex"):
        return "QHeading", "q"
    if low in _BANDS or (raw.isupper() and len(raw) > 14 and not low.startswith("mdr")):
        return "BandHead", f"band:{low}"
    if low in _MAJOR_H2:
        return "SectionHead", "major"
    if low in _SUBHEADS or (low.startswith("mdr") and len(raw) < 16):
        return "Subhead", state
    if role in {"h1", "h2"}:
        if state.startswith("band:") and any(key in state for key in ("strategic", "enabling", "success")):
            return "TopicHead", state
        if state == "major":
            return "Subhead", state
        return "TopicHead", state
    if (
        state.startswith("band:")
        and len(raw) < 70
        and not raw.endswith((".", ","))
        and not _looks_like_link_line(raw)
    ):
        return "TopicHead", state
    _ = (bullet, has_href)
    return "Body", state


def _is_leading_cover_line(text: str) -> bool:
    """Word cover chrome: country title, report line, appeal code — not a mismatch notice."""
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if _SKIP_COVER_RE.match(raw) or low in _SKIP_EXACT:
        return True
    if low in _BANDS or low in _MAJOR_H2 or low in _SUBHEADS:
        return False
    if (low.startswith("q") and len(raw) < 120) or low.startswith("annex"):
        return False
    if raw.endswith((".", "?", "!")) or len(raw) > 48:
        return False
    return True


def _is_cover_table(row: dict) -> bool:
    rows = row.get("rows") or []
    if len(rows) != 1 or len(rows[0]) != 1:
        return False
    text = " ".join((para.get("text") or "").strip() for para in (rows[0][0] or [])).strip()
    return _is_leading_cover_line(text)


def style_narrative_blocks(blocks: list[dict], *, country_name: str = "") -> list[dict]:
    styled: list[dict] = []
    state = ""
    country = (country_name or "").strip().lower()
    for row in blocks:
        if row.get("kind") == "table":
            if not styled and _is_cover_table(row):
                continue
            styled.append(row)
            continue
        if row.get("role") == "empty":
            if styled and styled[-1].get("style") != "Blank":
                styled.append({"style": "Blank", "text": "", "runs": [{"text": " ", "href": "", "bold": False}]})
            continue
        text = (row.get("text") or "").strip()
        if not styled and (_is_leading_cover_line(text) or (country and text.lower() == country)):
            continue
        if country and text.lower() == country:
            continue
        style, state = _narrative_style(
            text,
            state,
            row.get("role") or "",
            bullet=bool(row.get("bullet")),
            has_href=bool(_para_hrefs(row)),
            bold=_para_is_bold(row),
        )
        if not style:
            continue
        if style == "AdditionalHead":
            from plugins.upr_visuals.i18n import t

            text = t("ADDITIONAL INFORMATION")
            row = {"text": text, "runs": [{"text": text, "href": "", "bold": True}], "bullet": False}
        if style in {"QHeading", "BandHead"}:
            text = text.upper()
        styled.append(
            {
                "style": style,
                "text": text,
                "runs": row.get("runs") or [{"text": text, "href": "", "bold": False}],
            }
        )
    return styled


def folio_label(meta: dict) -> str:
    year = str((meta or {}).get("year") or "").strip()
    kind = str((meta or {}).get("kind") or "report")
    from plugins.upr_visuals.i18n import t

    label = "unified plan" if kind == "plan" else "annual report"
    if year:
        return t(f"{year} IFRC network {label}")
    return t(f"IFRC network {label}")


def folio_text(label: str, page_number: int) -> str:
    return f"{label}    /    {page_number}"


def _block_flow_height(para: dict) -> float:
    if para.get("kind") == "table":
        rows = para.get("rows") or []
        return 10.0 + sum(max((_table_cell_height(cell) for cell in row), default=16.0) for row in rows)
    style = para.get("style") or "Body"
    before, leading, after = _FLOW_METRICS.get(style, (0.0, 13.5, 8.5))
    text = para.get("text") or ""
    if style == "Body":
        lines = max(1, (len(text) + _BODY_CHARS_PER_LINE - 1) // _BODY_CHARS_PER_LINE)
    else:
        lines = max(1, (len(text) + 55) // 56)
    return before + leading * lines + after


def _narrative_page_count(styled: list[dict]) -> int:
    """Threaded frames for the story. Loose estimates left empty pages at the end."""
    total = sum(_block_flow_height(para) for para in styled)
    return max(1, int(total / NARRATIVE_H + 0.999))
