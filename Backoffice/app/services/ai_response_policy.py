"""
Response policy helpers:
- user-intent heuristics for table/follow-up handling
- output sanitization for end-user safety/UX
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.services.upr.ux import UPR_TOOL_LABELS

logger = logging.getLogger(__name__)


_USER_TABLE_REQUEST_RE = re.compile(
    r"\b("
    r"table|list\s+all|which\s+countries|show\s+(me\s+)?(a\s+)?table|give\s+me\s+(a\s+)?table|"
    r"full\s+list|every\s+country|all\s+countries\s+that|countries\s+that\s+(mention|have)|"
    r"i\s+want\s+(a\s+)?table|output\s+(a\s+)?table|produce\s+(the\s+)?table"
    r")\b",
    re.IGNORECASE,
)
_USER_TABLE_CONFIRM_RE = re.compile(
    r"^(yes|yeah|yep|ok|okay|sure|please|do\s+it|full\s+table|show\s+all|"
    r"list\s+(everyone|every\s+country|all)|option\s*1|the\s+first\s+one|"
    r"comprehensive|all\s+of\s+them|every\s+one)[\s\.\!]*$",
    re.IGNORECASE,
)

_FINDINGS_FOLLOWUP_RE = re.compile(
    r"\b("
    r"key\s*findings?|"
    r"takeaways?|key\s+highlights?|"
    r"insights?|"
    r"summary|summar(?:y|ize)|"
    r"interpret(?:ation)?|"
    r"analysis|analy(?:s|z)e|"
    r"explain|"
    r"what\s+does\s+this\s+mean|"
    r"so\s+what|"
    r"implications?"
    r")\b",
    re.IGNORECASE,
)

_REASONING_EVIDENCE_RE = re.compile(
    r"\b("
    r"why|reason(?:s)?|cause(?:s)?|driver(?:s)?|because|due\s+to|"
    r"what\s+happened|explain|interpret(?:ation)?|"
    r"evidence|cite|sources?|"
    r"covid|covid-19|pandemic"
    r")\b",
    re.IGNORECASE,
)


def user_expects_full_table(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]],
) -> bool:
    """
    True when we should inject a mandatory "output the full table" instruction
    so the model complies. User either asked for a table explicitly or is
    confirming after we offered it.
    """
    if not query or not isinstance(query, str):
        return False
    q = query.strip()
    if _USER_TABLE_REQUEST_RE.search(q):
        return True
    if not _USER_TABLE_CONFIRM_RE.search(q):
        return False
    if not conversation_history:
        return False
    last = conversation_history[-1]
    if last.get("isUser"):
        return False
    assistant_text = (last.get("message") or "").lower()
    if "table" in assistant_text and (
        "if you'd like" in assistant_text
        or "just ask" in assistant_text
        or "full table" in assistant_text
        or "produce" in assistant_text
        or "can produce" in assistant_text
    ):
        return True
    return False


def is_findings_followup_query(query: str) -> bool:
    """
    Detect follow-ups that want interpretation/summary rather than a
    chart-only response.
    """
    return bool(query and _FINDINGS_FOLLOWUP_RE.search(str(query)))


def wants_reasoning_evidence(query: str) -> bool:
    """
    True when user asks for explanations/causes/evidence (or a findings-style
    follow-up), so we should look for contextual evidence in documents before
    finishing.
    """
    if not query or not isinstance(query, str):
        return False
    return is_findings_followup_query(query) or bool(_REASONING_EVIDENCE_RE.search(query))


_MD_TABLE_LINE_RE = re.compile(r"^\s*\|.+\|\s*$")
_MD_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:]*-+[\s:]*")

_LARGE_TABLE_ROW_THRESHOLD = 15

# search_documents / search_documents_hybrid argument keys — models sometimes echo
# these JSON blobs in user-facing text instead of calling tools.
_SEARCH_DOCUMENTS_ARG_KEYS = frozenset({
    "query",
    "top_k",
    "offset",
    "limit",
    "return_all_countries",
    "country_identifier",
})


def _is_leaked_search_documents_args_dict(obj: Any) -> bool:
    if not isinstance(obj, dict) or len(obj) < 2:
        return False
    keys = frozenset(obj.keys())
    if not keys.issubset(_SEARCH_DOCUMENTS_ARG_KEYS):
        return False
    if "query" not in keys:
        return False
    return True


def _strip_leaked_search_documents_json_blobs(text: str) -> str:
    """Remove JSON objects that match search_documents tool arguments from prose."""
    if not text or "{" not in text or '"query"' not in text:
        return text

    lines_out: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                lines_out.append(line)
                continue
            if _is_leaked_search_documents_args_dict(parsed):
                logger.debug("sanitize_agent_answer: stripped leaked search_documents JSON line")
                continue
        lines_out.append(line)
    text = "\n".join(lines_out)

    if "{" not in text:
        return text

    out: list[str] = []
    i = 0
    n = len(text)
    dec = json.JSONDecoder()
    while i < n:
        j = text.find("{", i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        chunk = text[j : j + 8192]
        try:
            obj, end = dec.raw_decode(chunk)
        except json.JSONDecodeError:
            out.append(text[j])
            i = j + 1
            continue
        if isinstance(obj, dict) and _is_leaked_search_documents_args_dict(obj):
            logger.debug("sanitize_agent_answer: stripped inline leaked search_documents JSON blob")
            i = j + end
            while i < n and text[i] in " \t\r\n,":
                i += 1
            continue
        out.append(chunk[:end])
        i = j + end

    return "".join(out)


def contains_leaked_search_documents_tool_json(text: str) -> bool:
    """True when *text* includes JSON shaped like search_documents tool arguments.

    Models sometimes "simulate" a tool call by printing argument JSON in
    assistant message text instead of using native function calling.
    """
    if not text or "{" not in text:
        return False
    cleaned = _strip_leaked_search_documents_json_blobs(text)
    return cleaned.strip() != (text or "").strip()


def _strip_large_markdown_tables(text: str, *, strip_all: bool = False) -> str:
    """Remove markdown tables from the answer text.

    When *strip_all* is True every markdown table is removed (used when
    the platform is already rendering a ``table_payload``).
    Otherwise only tables with >= ``_LARGE_TABLE_ROW_THRESHOLD`` data rows
    are stripped.
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if _MD_TABLE_LINE_RE.match(lines[i]):
            block_start = i
            while i < len(lines) and _MD_TABLE_LINE_RE.match(lines[i]):
                i += 1
            block = lines[block_start:i]
            sep_count = sum(1 for ln in block if _MD_TABLE_SEP_RE.match(ln))
            data_rows = len(block) - sep_count - (1 if sep_count else 0)
            if strip_all or data_rows >= _LARGE_TABLE_ROW_THRESHOLD:
                logger.info(
                    "sanitize_agent_answer: stripped markdown table with %d data rows (strip_all=%s)",
                    data_rows, strip_all,
                )
            else:
                out.extend(block)
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def sanitize_agent_answer(text: str, *, has_table_payload: bool = False) -> str:
    """Strip leaked agent internals from a response before returning it.

    When *has_table_payload* is True the platform is already rendering a
    structured interactive table, so any large markdown table the LLM
    produced is redundant and gets stripped.
    """
    if not text or not isinstance(text, str):
        return text or ""

    original = text

    # Remove echoed search_documents tool argument JSON (whole lines and inline blobs).
    text = _strip_leaked_search_documents_json_blobs(text)

    # Strip internal classification labels the model sometimes echoes back
    # from system prompt instructions (e.g., "Classification: platform usage/navigation help.",
    # "Intent classification: (A) platform usage / navigation help.").
    text = re.sub(
        r"(?im)^\s*(?:Intent\s+)?[Cc]lassification\s*:\s*(?:\([A-Z]\)\s*)?(?:platform\s+usage|navigation|data|document)[\s/\w]*\.?\s*\n*",
        "",
        text,
    )

    if has_table_payload:
        text = _strip_large_markdown_tables(text, strip_all=True)

    text = re.sub(
        r"---\s*Step\s*\d+\s*---.*?(?=---\s*Step\s*\d+\s*---|$)",
        "",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"(?m)^Thought:\s*\n.*?(?=^Thought:\s*\n|^Action:\s*finish\b|\Z)",
        "",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )

    text = re.sub(r"(?m)^Action:\s+\w+\s*$", "", text)
    text = re.sub(r"(?m)^Action [Ii]nput:\s*$", "", text)
    text = re.sub(r"(?m)^Observation:\s*$", "", text)
    text = re.sub(r"(?m)^Timestamp:\s+\d{4}-\d{2}-\d{2}T[\d:.+Z-]+\s*$", "", text)

    text = re.sub(
        r"\{\s*\n\s*\"(?:execution_time_ms|result|success|error)\".*?\n\}",
        "",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    try:
        text = re.sub(r"(?i)\b(json)\s+payload\b", r"\1", text)
        text = re.sub(r"(?i)\b(world\s*heat\s*map|world\s*heatmap|heat\s*map|heatmap|world\s*map|worldmap|map|chart)\s+payload\b", r"\1", text)
        text = re.sub(r"(?i)\b(payload)\b", "data", text) if ("payload" in text.lower() and "http" not in text.lower() and "api" not in text.lower()) else text

        text = re.sub(
            r"(?is)^\s*here\s+is\s+a\s+best[-\s]*effort\s+(.{0,80}?)\s*(?:payload|data)\s+created\s+from\s+the\s+platform'?s?\s+document\s+search\s+results",
            r"I created a best-effort \1 from document search results",
            text,
        )
        text = re.sub(r"(?im)^\s*json\s+world\s*map\s*\(.*?\)\s*:?\s*$", "", text)
        text = re.sub(r"(?im)^\s*json\s+worldmap\s*\(.*?\)\s*:?\s*$", "", text)

        replacements = {
            r"\bget_indicator_values_for_all_countries\b": "the bulk Indicator Bank query",
            r"\bget_indicator_value\b": "the Indicator Bank query",
            **{rf"\b{k}\b": v for k, v in UPR_TOOL_LABELS.items()},
            r"\bsearch_documents_hybrid\b": "document search",
            r"\bsearch_documents\b": "document search",
        }
        for pat, rep in replacements.items():
            text = re.sub(pat, rep, text, flags=re.IGNORECASE)

        text = re.sub(r"(?im)^\s*options\s*\(choose\s+one\)\s*:\s*$", "", text)
        text = re.sub(r"(?is)\n\s*What I['’]ll run once enabled:\s*\n.*?(?=\n{2,}|\Z)", "\n", text)
        text = re.sub(r"(?is)\n\s*What I will deliver:\s*\n.*?(?=\n{2,}|\Z)", "\n", text)
        text = re.sub(r"(?is)\n\s*Quick questions\s*/\s*choices.*?(?=\n{2,}|\Z)", "\n", text)
        text = re.sub(r"(?im)^\s*Turnaround:\s*.*$", "", text)

        # Remove option-menu style follow-ups that conflict with table-first policy.
        # Keep the answer focused on the requested output + sources.
        text = re.sub(
            r"(?is)\n\s*If\s+you(?:'d|\s+would)?\s+like,\s*i\s+can\s*:\s*\n(?:\s*[-*].*\n?)+(?=\n##\s*Sources\b|\Z)",
            "\n",
            text,
        )
        text = re.sub(
            r"(?is)\n\s*If\s+you\s+want,\s*i\s+can\s*:\s*\n(?:\s*[-*].*\n?)+(?=\n##\s*Sources\b|\Z)",
            "\n",
            text,
        )
        text = re.sub(
            r"(?is)\n\s*If\s+you\s+want.*?(?:next\s+steps?.*?)?\n(?:\s*[-*].*\n?)+(?=\n##\s*Sources\b|\Z)",
            "\n",
            text,
        )
        text = re.sub(
            r"(?im)^\s*If\s+you\s+want,\s*i\s+can\s+.*(?:World\s*Bank|external\s+data).*$",
            "",
            text,
        )
        # In this system continent = operational region (platform data). No separate continent column.
        text = re.sub(r"IFRC Region \(est\.?\)", "Operational region", text)
        text = re.sub(r"(?im)\bIFRC Region\b", "Operational region", text)
        text = re.sub(r"Operational region \(est\.?\)", "Operational region", text)
        text = re.sub(r"(?im)\bContinent\s*\(est\.?\)", "Operational region", text)
        text = re.sub(r"(?im)\bContinent\b(?!\s*\(est)", "Operational region", text)
        # Strip fake UI elements the model sometimes generates.
        text = re.sub(r"(?im)^\s*Download\s+(?:Excel|CSV|File)\s*$", "", text)
        text = re.sub(r"(?im)^\s*Show\s+\d+\s+more\s+rows?\s*$", "", text)
        text = re.sub(r"(?im)^\s*\[Show\s+\d+\s+more\s+rows?\]\s*$", "", text)
    except Exception as e:
        logger.debug("sanitize_agent_answer: regex cleanup failed: %s", e)

    if not text:
        logger.warning("sanitize_agent_answer: entire response was agent traces; returning fallback")
        return "I searched for the information but was unable to compile a clear answer. Please try rephrasing your question."

    if len(text) < len(original) * 0.3 and len(original) > 500:
        logger.warning(
            "sanitize_agent_answer: stripped %.0f%% of response (orig=%d chars, clean=%d chars)",
            (1 - len(text) / len(original)) * 100,
            len(original),
            len(text),
        )

    return text
