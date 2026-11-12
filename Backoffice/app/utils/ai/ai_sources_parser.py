"""
Structured AI chat sources parser.

Parses labeled ## Sources blocks from model answers and synthesizes
databank/timeseries source items from tool results so the UI does not
depend on brittle title/excerpt regex.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from app.utils.ai.ai_citation_parser import (
    build_sources_array,
    extract_markdown_source_links,
)

_SOURCES_SECTION_RE = re.compile(
    r"(?ms)^#{2,3}\s*Sources\s*:?\s*\n(.*)\Z",
    re.IGNORECASE,
)

_LABELED_TITLE_RE = re.compile(
    r"(?m)^\s*-\s*title\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)

_FIELD_RE = re.compile(
    r"(?m)^\s*(detail|page|url|kind)\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)

_LEGACY_BULLET_RE = re.compile(r"(?m)^\s*-\s+(.+?)\s*$")

_MD_LINK_IN_TEXT_RE = re.compile(
    r"\[([^\]]+)\]\((/api/ai/documents/\d+/download[^)]*)\)"
)

_TIMESERIES_TOOLS = frozenset({
    "get_indicator_timeseries",
    "get_upr_kpi_timeseries",
})

_DATABANK_VALUE_TOOLS = frozenset({
    "get_indicator_value",
    "get_upr_kpi_value",
    "get_indicator_values_for_all_countries",
    "get_upr_kpi_values_for_all_countries",
    "get_form_field_value",
    "get_form_field_values_for_all_countries",
})


def _squash(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _strip_quotes(text: str) -> str:
    return re.sub(r'^["“”«\s]+|["“”»\s]+$', "", text or "").strip()


def _normalize_item(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = _squash(raw.get("title"))
    if not title:
        return None
    detail = _squash(raw.get("detail") or raw.get("excerpt") or "")
    url = _squash(raw.get("url") or "") or None
    page = raw.get("page")
    if page is not None and page != "":
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = _squash(page) or None
    else:
        page = None
    kind = _squash(raw.get("kind") or raw.get("type") or "").lower() or None
    if not kind:
        if url or (isinstance(page, int)):
            kind = "document"
        else:
            kind = "other"
    if kind in {"document", "databank", "other"}:
        pass
    elif kind in {"doc"}:
        kind = "document"
    else:
        kind = "other"
    item: Dict[str, Any] = {
        "title": title,
        "detail": detail or None,
        "url": url,
        "page": page,
        "kind": kind,
    }
    # Preserve legacy citation fields when present
    for key in ("type", "document_id", "document_language", "document_date", "excerpt"):
        if raw.get(key) is not None and key not in item:
            item[key] = raw.get(key)
    if item.get("detail") and not item.get("excerpt"):
        item["excerpt"] = item["detail"]
    if not item.get("type"):
        item["type"] = "document" if kind == "document" else kind
    return item


def extract_sources_section(answer: str) -> str:
    """Return the body of the trailing ## Sources section, or empty string."""
    text = str(answer or "")
    m = _SOURCES_SECTION_RE.search(text)
    if not m:
        return ""
    return (m.group(1) or "").strip()


def parse_labeled_sources(answer: str) -> List[Dict[str, Any]]:
    """
    Parse labeled ## Sources blocks:

      - title: Short label
        detail: years / notes / excerpt
        page: 14
        url: /api/ai/documents/12/download
    """
    body = extract_sources_section(answer)
    if not body:
        # Allow parsing a fragment that is already just the sources body
        body = str(answer or "").strip()
        if not _LABELED_TITLE_RE.search(body):
            return []

    items: List[Dict[str, Any]] = []
    matches = list(_LABELED_TITLE_RE.finditer(body))
    if not matches:
        return []

    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        block = body[start:end]
        fields: Dict[str, Any] = {"title": _strip_quotes(m.group(1))}
        for fm in _FIELD_RE.finditer(block):
            key = (fm.group(1) or "").strip().lower()
            val = _strip_quotes(fm.group(2) or "")
            if key and val:
                fields[key] = val
        item = _normalize_item(fields)
        if item:
            items.append(item)
    return items


def parse_legacy_source_bullets(answer: str) -> List[Dict[str, Any]]:
    """
    Best-effort parse of freeform `- …` source bullets (pre-labeled format).
    Prefer markdown document links; otherwise keep the whole line as title.
    """
    body = extract_sources_section(answer) or str(answer or "")
    items: List[Dict[str, Any]] = []
    for m in _LEGACY_BULLET_RE.finditer(body):
        line = (m.group(1) or "").strip()
        if not line:
            continue
        # Skip labeled blocks (handled elsewhere)
        if re.match(r"(?i)^title\s*:", line):
            continue
        link = _MD_LINK_IN_TEXT_RE.search(line)
        if link:
            link_text = link.group(1).strip()
            url = link.group(2).strip()
            page = None
            page_match = re.search(r"(?:page|p\.)\s*(\d+)", link_text, re.IGNORECASE)
            title = link_text
            if page_match:
                page = int(page_match.group(1))
                title = link_text[: page_match.start()].strip(" -,")
            rest = (line[link.end() :] or "").lstrip(" :–—-").strip()
            item = _normalize_item({
                "title": title,
                "url": url,
                "page": page,
                "detail": _strip_quotes(rest),
                "kind": "document",
            })
            if item:
                items.append(item)
            continue
        # Split on first spaced dash / colon outside a naive first pass:
        # keep whole line as title for legacy; detail left empty so UI can fall back.
        item = _normalize_item({"title": line, "kind": "other"})
        if item:
            items.append(item)
    return items


_PLAIN_LINE_PREFIX_RE = re.compile(r"^(?:[-*•]\s+|\d{1,3}[\.\)]\s+)")


def parse_plain_source_lines(answer: str) -> List[Dict[str, Any]]:
    """
    Last-resort structure for a ## Sources body that is not labeled or bulleted.

    A zero-hit search often ends as one sentence under ## Sources. That used to
    be wrapped as plain HTML with no data-source-* attributes. Every non-empty
    line becomes one source item so the chip always has a title.
    """
    body = extract_sources_section(answer)
    if not body:
        return []
    items: List[Dict[str, Any]] = []
    for raw in re.split(r"\n+", body):
        line = _PLAIN_LINE_PREFIX_RE.sub("", (raw or "").strip()).strip()
        if not line or re.match(r"(?i)^#{0,6}\s*sources\s*:?\s*$", line):
            continue
        link = _MD_LINK_IN_TEXT_RE.search(line)
        if link:
            link_text = link.group(1).strip()
            url = link.group(2).strip()
            page = None
            page_match = re.search(r"(?:page|p\.)\s*(\d+)", link_text, re.IGNORECASE)
            title = link_text
            if page_match:
                page = int(page_match.group(1))
                title = link_text[: page_match.start()].strip(" -,")
            rest = (line[link.end() :] or "").lstrip(" :–—-").strip()
            item = _normalize_item({
                "title": title or line,
                "url": url,
                "page": page,
                "detail": _strip_quotes(rest) or None,
                "kind": "document",
            })
        else:
            item = _normalize_item({"title": line, "kind": "other"})
        if item:
            items.append(item)
    return items


def _series_year_span(series: Iterable[Dict[str, Any]]) -> Optional[str]:
    years: List[Any] = []
    for row in series or []:
        if not isinstance(row, dict):
            continue
        x = row.get("x")
        if x is None:
            x = row.get("year")
        if x is None and row.get("period_name"):
            years.append(str(row.get("period_name")))
            continue
        if x is not None:
            years.append(x)
    if not years:
        return None
    # Prefer numeric min/max when possible
    nums = []
    for y in years:
        try:
            nums.append(int(y))
        except (TypeError, ValueError):
            pass
    if nums:
        lo, hi = min(nums), max(nums)
        return f"years {lo}–{hi}" if lo != hi else f"year {lo}"
    return f"years {years[0]}–{years[-1]}" if len(years) > 1 else f"year {years[0]}"


def _draft_note_from_series(series: List[Dict[str, Any]]) -> Optional[str]:
    statuses = []
    for row in series or []:
        if not isinstance(row, dict):
            continue
        st = (row.get("data_status") or row.get("status") or "").strip().lower()
        if st:
            statuses.append(st)
    if not statuses:
        return None
    draftish = {"saved", "draft", "in_progress", "in-progress"}
    if all(s in draftish or s.startswith("saved") for s in statuses):
        n = len(statuses)
        return (
            f"Note: all {n} points are saved/draft (not submitted)."
            if n > 1
            else "Note: This value is from saved/draft entries and has not been submitted."
        )
    if any(s in draftish or s.startswith("saved") for s in statuses):
        return "Note: some points are saved/draft (not submitted)."
    return None


def synthesize_timeseries_source(
    tool_payload: Dict[str, Any],
    *,
    org_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build one databank source item from a timeseries tool result payload."""
    if not isinstance(tool_payload, dict):
        return None
    # Tool registry often wraps as {success, result: {...}}
    root = tool_payload.get("result") if isinstance(tool_payload.get("result"), dict) else tool_payload
    if not isinstance(root, dict):
        return None

    indicator = root.get("indicator") if isinstance(root.get("indicator"), dict) else {}
    ind_name = (
        root.get("indicator_display_name")
        or indicator.get("display_name")
        or indicator.get("name")
        or root.get("metric")
        or root.get("indicator_name")
    )
    ind_name = _squash(ind_name)
    if not ind_name:
        return None

    org = _squash(org_name) or "IFRC Network Databank"
    title = f'{org} (indicator: "{ind_name}")'

    series = root.get("series") if isinstance(root.get("series"), list) else []
    # Chart payload shape
    if not series and isinstance(root.get("chart_payload"), dict):
        series = root["chart_payload"].get("series") or []
        if not ind_name:
            ind_name = _squash(root["chart_payload"].get("metric"))

    detail_parts: List[str] = []
    span = _series_year_span(series)
    if span:
        detail_parts.append(span)
    draft = _draft_note_from_series(series)
    if draft:
        detail_parts.append(draft)
    notes = root.get("data_quality_notes")
    if isinstance(notes, list):
        for n in notes:
            t = _squash(n)
            if t:
                detail_parts.append(t if t.lower().startswith("note:") else t)
    elif isinstance(notes, str) and notes.strip():
        detail_parts.append(notes.strip())

    return _normalize_item({
        "title": title,
        "detail": " ".join(detail_parts).strip() or None,
        "kind": "databank",
    })


def synthesize_sources_from_tool_steps(
    steps: Optional[List[Dict[str, Any]]],
    *,
    org_name: Optional[str] = None,
    chart_payload: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Prefer tool-backed sources for databank/timeseries so the UI does not
    depend on model wording for title/detail.
    """
    out: List[Dict[str, Any]] = []
    seen_titles: set = set()

    def _add(item: Optional[Dict[str, Any]]) -> None:
        if not item:
            return
        key = (item.get("title") or "").lower()
        if not key or key in seen_titles:
            return
        seen_titles.add(key)
        out.append(item)

    for step in steps or []:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or step.get("tool") or "").strip()
        obs = step.get("observation")
        payload = obs
        if isinstance(obs, dict) and isinstance(obs.get("result"), (dict, list)):
            payload = obs
        elif isinstance(obs, str):
            continue

        if action in _TIMESERIES_TOOLS and isinstance(payload, dict):
            _add(synthesize_timeseries_source(payload, org_name=org_name))
        elif action in _DATABANK_VALUE_TOOLS and isinstance(payload, dict):
            root = payload.get("result") if isinstance(payload.get("result"), dict) else payload
            if not isinstance(root, dict):
                continue
            indicator = root.get("indicator") if isinstance(root.get("indicator"), dict) else {}
            ind_name = _squash(
                root.get("indicator_display_name")
                or indicator.get("display_name")
                or indicator.get("name")
                or root.get("indicator_name_resolved")
                or root.get("field_label")
                or root.get("field_name")
            )
            if not ind_name:
                continue
            org = _squash(org_name) or "IFRC Network Databank"
            detail_parts: List[str] = []
            period = _squash(root.get("period_used") or root.get("period") or root.get("period_name"))
            if period:
                detail_parts.append(period)
            total = root.get("total")
            if total is None:
                total = root.get("value")
            if total is not None and total != "":
                detail_parts.append(f"value: {total}")
            status = _squash(root.get("data_status") or root.get("status")).lower()
            if status in {"saved", "draft"} or status.startswith("saved"):
                detail_parts.append(
                    "Note: This value is from saved/draft entries and has not been submitted."
                )
            _add(_normalize_item({
                "title": f'{org} (indicator: "{ind_name}")',
                "detail": " ".join(detail_parts) or None,
                "kind": "databank",
            }))

    if not out and isinstance(chart_payload, dict):
        _add(synthesize_timeseries_source(
            {"series": chart_payload.get("series"), "metric": chart_payload.get("metric"),
             "indicator_display_name": chart_payload.get("metric"),
             "country_display_name": chart_payload.get("country")},
            org_name=org_name,
        ))

    return out


def merge_structured_sources(
    *,
    answer: str,
    steps: Optional[List[Dict[str, Any]]] = None,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
    chart_payload: Optional[Dict[str, Any]] = None,
    org_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Build the final structured sources list.

    Priority:
    1. Tool-synthesized databank/timeseries items
    2. Labeled ## Sources blocks from the answer
    3. Legacy markdown / citation parser (documents)
    4. Legacy freeform bullets
    5. Any remaining ## Sources lines, one item per line
    """
    merged: List[Dict[str, Any]] = []
    seen: set = set()

    def _key(item: Dict[str, Any]) -> tuple:
        return (
            (item.get("title") or "").strip().lower(),
            item.get("page"),
            (item.get("url") or "").strip().lower(),
        )

    def _extend(items: Iterable[Dict[str, Any]]) -> None:
        for raw in items or []:
            item = _normalize_item(raw) if "title" in (raw or {}) else None
            if not item:
                continue
            k = _key(item)
            if k in seen:
                # Prefer richer detail when duplicate title
                for existing in merged:
                    if _key(existing) == k and not existing.get("detail") and item.get("detail"):
                        existing["detail"] = item["detail"]
                        existing["excerpt"] = item.get("excerpt") or item["detail"]
                        break
                continue
            seen.add(k)
            merged.append(item)

    _extend(synthesize_sources_from_tool_steps(
        steps, org_name=org_name, chart_payload=chart_payload
    ))
    _extend(parse_labeled_sources(answer))

    # Document-oriented legacy enrichment (urls from chunks / md links)
    try:
        cite = build_sources_array(answer, retrieved_chunks)
        for c in cite:
            _extend([{
                "title": c.get("title"),
                "page": c.get("page"),
                "url": c.get("url"),
                "kind": "document",
                "type": c.get("type") or "document",
                "document_id": c.get("document_id"),
                "document_language": c.get("document_language"),
                "document_date": c.get("document_date"),
            }])
    except Exception:
        for lnk in extract_markdown_source_links(answer):
            _extend([{**lnk, "kind": "document"}])

    if not merged:
        _extend(parse_legacy_source_bullets(answer))
    if not merged:
        _extend(parse_plain_source_lines(answer))

    return merged


def render_sources_body_html(sources: List[Dict[str, Any]]) -> str:
    """
    Render structured sources as an HTML list with data-* attributes for clients.
    """
    from markupsafe import escape

    if not sources:
        return ""
    rows: List[str] = []
    for src in sources:
        item = _normalize_item(src)
        if not item:
            continue
        title = escape(item["title"])
        detail = escape(item["detail"]) if item.get("detail") else ""
        url = item.get("url")
        page = item.get("page")
        kind = escape(item.get("kind") or "other")
        attrs = [
            f'data-source-title="{title}"',
            f'data-source-kind="{kind}"',
        ]
        if item.get("detail"):
            attrs.append(f'data-source-detail="{detail}"')
        if url:
            attrs.append(f'data-source-url="{escape(url)}"')
        if page is not None and page != "":
            attrs.append(f'data-source-page="{escape(page)}"')

        # Human-readable row content
        if url and str(url).startswith("/"):
            label = title
            if page is not None and page != "":
                label = f"{title} — page {escape(page)}"
            inner = (
                f'<a href="{escape(url)}" class="text-blue-600 hover:text-blue-800 underline" '
                f'target="_blank" rel="noopener">{label}</a>'
            )
        else:
            inner = str(title)
            if page is not None and page != "":
                inner = f"{inner} — page {escape(page)}"
        if detail:
            inner = f"{inner}: {detail}" if inner else str(detail)
        rows.append(f"<li {' '.join(attrs)}>{inner}</li>")

    if not rows:
        return ""
    return "<ul class=\"chat-response-sources-list\">" + "".join(rows) + "</ul>"
