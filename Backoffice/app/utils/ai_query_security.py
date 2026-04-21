"""Heuristic detection of possible XSS / HTML-injection patterns in AI user queries.

Used by admin trace views to flag suspicious input for reviewers. This is not a
substitute for output encoding or CSP; it only surfaces likely probes in stored traces.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Set


def _refine_signals(signals: Set[str]) -> List[str]:
    """Drop generic markup hint when a more specific signal is present."""
    s = set(signals)
    specific = {
        "event_handler_attribute",
        "script_tag",
        "dangerous_html_tag",
        "html_img_tag",
        "dangerous_url_protocol",
        "data_html_protocol",
        "encoded_markup",
        "js_sink_pattern",
    }
    if s & specific:
        s.discard("html_markup_fragment")
    return sorted(s)


def analyze_ai_user_query(text: Any) -> dict:
    """Return {suspicious: bool, signals: list[str]} for the given query text."""
    if text is None or not isinstance(text, str):
        return {"suspicious": False, "signals": []}

    raw = text
    lower = raw.lower()
    signals: Set[str] = set()

    if re.search(r"\bon\w+\s*=", lower):
        signals.add("event_handler_attribute")

    if re.search(r"<\s*script\b", lower) or re.search(r"<\s*/\s*script\b", lower):
        signals.add("script_tag")

    for tag in (
        "iframe",
        "object",
        "embed",
        "svg",
        "math",
        "link",
        "meta",
        "base",
        "form",
        "input",
        "textarea",
        "button",
    ):
        if re.search(rf"<\s*{tag}\b", lower):
            signals.add("dangerous_html_tag")
            break

    if re.search(r"<\s*img\b", lower):
        signals.add("html_img_tag")

    if re.search(r"javascript\s*:", lower) or re.search(r"vbscript\s*:", lower):
        signals.add("dangerous_url_protocol")

    if re.search(r"data\s*:\s*text/html", lower):
        signals.add("data_html_protocol")

    # Tag-like angle brackets (avoid "a < b" where next char is not tag-like)
    if re.search(r"<\s*[a-zA-Z!/][^>\n]{0,500}>", raw):
        signals.add("html_markup_fragment")

    if re.search(r"%3c\s*script", lower) or "&#60;" in lower or "&#x3c;" in lower:
        signals.add("encoded_markup")

    if re.search(r"\beval\s*\(", lower) or "document.cookie" in lower:
        signals.add("js_sink_pattern")

    codes = _refine_signals(signals)
    return {"suspicious": bool(codes), "signals": codes}


def merge_ai_query_security_results(analyses: Iterable[dict]) -> dict:
    """Union signal codes from several analyze_ai_user_query results."""
    merged: Set[str] = set()
    for a in analyses:
        if not a or not isinstance(a, dict):
            continue
        merged.update(a.get("signals") or [])
    codes = _refine_signals(merged)
    return {"suspicious": bool(codes), "signals": codes}
