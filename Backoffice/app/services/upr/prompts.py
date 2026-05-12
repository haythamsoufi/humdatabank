"""
UPR prompt fragments.

Centralises all Unified Planning and Reporting (UPR) specific prompt text
so that the main prompt-policy, query-rewriter, and agent executor modules
can pull from a single source of truth.

The companion ``KNOWLEDGE.md`` (same directory) is the comprehensive domain
reference.  Use :func:`get_upr_knowledge` to load it at runtime — it is
suitable for injection into an LLM context window when deeper UPR domain
understanding is needed beyond the concise rules returned by
:func:`get_upr_prompt_section`.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import List, Optional

logger = logging.getLogger(__name__)

_KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "KNOWLEDGE.md")


@lru_cache(maxsize=1)
def _load_knowledge_file() -> str:
    """Read KNOWLEDGE.md from disk (cached after first load)."""
    try:
        with open(_KNOWLEDGE_PATH, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        logger.warning("UPR KNOWLEDGE.md not found at %s", _KNOWLEDGE_PATH)
        return ""
    except Exception as exc:
        logger.warning("Failed to read UPR KNOWLEDGE.md: %s", exc)
        return ""


def get_upr_knowledge(*, sections: Optional[List[str]] = None) -> str:
    """Return the full UPR domain knowledge document, or specific sections.

    Parameters
    ----------
    sections : list[str], optional
        Heading prefixes to include (case-insensitive).  For example,
        ``["2. Document types", "4. Metadata schema"]`` returns only those
        sections.  When ``None``, the entire document is returned.

    Returns
    -------
    str
        Markdown text suitable for LLM injection.  Empty string if the
        knowledge file is missing.
    """
    full = _load_knowledge_file()
    if not full or sections is None:
        return full

    lines = full.split("\n")
    result_lines: list[str] = []
    include = False
    for line in lines:
        if line.startswith("## "):
            heading = line.lstrip("# ").strip().lower()
            include = any(s.lower() in heading for s in sections)
        if include:
            result_lines.append(line)

    return "\n".join(result_lines).strip()


def get_upr_prompt_section() -> str:
    """Return the UPR-specific section of the agent system prompt.

    Only injected when ``is_upr_active()`` is True.
    """
    return (
        "=== UPR (Unified Planning and Reporting) RULES ===\n"
        "\n"
        "IFRC terminology – UPR:\n"
        "- UPR = Unified Planning and Reporting (Unified Plans and Reports). Do NOT use \"Universal Periodic Review\" in this platform.\n"
        "\n"
        "Tool routing – UPR KPIs:\n"
        "- Query structured data from the database (Indicator Bank, form submissions, UPR metadata)\n"
        "- get_upr_kpi_value: for UPR KPIs (branches, local_units, volunteers, staff) — structured metadata from document visual blocks.\n"
        "- For factual value questions (number of X, how many Y in country Z) that are NOT form/assignment data: you MUST call ALL relevant tools before saying \"not found\":\n"
        "  (1) get_indicator_value with period=None (returns most recent).\n"
        "  (2) search_documents with a short query (e.g. \"branches Myanmar\").\n"
        "  (3) For UPR KPIs (branches/local_units/volunteers/staff): also get_upr_kpi_value.\n"
        "- When a confident result is already available (e.g. get_upr_kpi_value confidence >= 0.9 + supporting search_documents), finish with your answer.\n"
        "\n"
        "Source priority – UPR:\n"
        "- **Documents only** (\"only from documents\", \"from reports\", \"from plans\", \"in the PDFs\"): use ONLY search_documents (or search_documents_hybrid). For UPR metrics (branches, volunteers, staff, local_units) you may also use get_upr_kpi_value / get_upr_kpi_values_for_all_countries. Do NOT call databank tools.\n"
        "- UPR KPI tools count as documents — exclude them when user asks for \"Databank only\".\n"
        "\n"
        "Bulk all-countries tools – UPR gap-fill:\n"
        "- For \"volunteers for all countries\", \"list [indicator] by country\": PRIORITIZE FDRS (Indicator Bank). (1) Call get_indicator_values_for_all_countries FIRST. (2) Call get_upr_kpi_values_for_all_countries only to FILL GAPS — add rows only for countries NOT already in the FDRS result. (3) If user asked for \"from UPR/documents\" only: use ONLY get_upr_kpi_values_for_all_countries. (4) If user asked \"databank only\": use ONLY get_indicator_values_for_all_countries. Do NOT call per-country tools — use the bulk tools.\n"
        "- Merge into ONE table, one row per country. Prefer FDRS value when both have data. When both sources are wanted, call get_indicator_values_for_all_countries first, then get_upr_kpi_values_for_all_countries only to fill gaps; optionally search_documents with return_all_countries=True to supplement.\n"
        "\n"
        "UPL-vs-UPR disambiguation:\n"
        "- Document titles use \"UPL\" not \"UPR\"; list_documents with \"UPR\" returns 0.\n"
        "- For \"which documents exist\" / inventory (e.g. \"which countries have UPL-2026 PDFs\"): use list_documents first. The \"query\" is matched as substring on title/filename — use ONE short term (e.g. \"UPL-\" or \"Unified Plan\").\n"
        "- Map/list of which countries have UPL/documents in a region (no specific metric): use ONLY list_documents(\"UPL-\"). Filter by region. Output country list with value=1 (has UPL document). Do NOT show KPI numbers.\n"
        "\n"
        "Map payload – UPR:\n"
        "- When the user asked for a map: do NOT include a ```json map_payload ... ``` block in your answer. "
        "The backend will attach the map from your list_documents (or get_upr_kpi) result.\n"
        "\n"
        "Time series – UPR:\n"
        "- When both sources have a value for the same year: use one row, prefer the databank value (especially submitted/approved). Use UPR only when the databank has no value for that year.\n"
        "\n"
        "Operational region – UPR tools:\n"
        "- Tools that return the region field: get_indicator_values_for_all_countries, get_upr_kpi_values_for_all_countries, list_documents, search_documents.\n"
        "- Map/list with a metric (e.g. \"volunteers in MENA\"): use get_upr_kpi_values_for_all_countries(metric) or get_indicator_values_for_all_countries; filter by region.\n"
        "- For \"documents in region + metric\": merge list_documents(\"UPL-\") with the appropriate bulk tool. Do NOT call get_country_information in a loop.\n"
        "\n"
        "Internal names – UPR:\n"
        "- Do NOT mention internal tool/function names in the final answer. Use user-facing terms: \"UPR documents\", \"uploaded documents\".\n"
    )


def get_upr_rewriter_rules() -> str:
    """Return UPR disambiguation rules for the query rewriter."""
    return (
        "- Fix obvious typos and expand common abbreviations. When expanding: FDRS = FDRS (Federation-wide Databank Reporting System); "
        "UPR = Unified Planning and Reporting (Unified Plans and Reports) — do NOT use 'Universal Periodic Review'.\n"
        "- Fill gaps when the user omits crucial intent: if they ask about UPR/UPL/Unified Plan in a region (e.g. 'UPR in MENA', "
        "'Unified Plans in Europe', 'which countries have UPL in Africa') without saying 'list' or 'which countries', make it explicit — "
        "e.g. 'List MENA countries that have Unified Plan (UPL) documents' or 'Which countries in Europe have UPL documents?' "
        "so the agent uses list_documents and region filtering. If they mention a region (MENA, Europe, Africa, Asia Pacific, Americas) "
        "with documents/plans/UPR/UPL, assume they want a list of countries in that region (unless they clearly ask for something else).\n"
    )


def get_upr_gapfill_reminder(actions_so_far: List[str]) -> str:
    """Return UPR gap-fill reminder if FDRS was used but UPR was not.

    Returns empty string if no reminder is needed.
    """
    has_fdrs = "get_indicator_values_for_all_countries" in actions_so_far
    has_upr = "get_upr_kpi_values_for_all_countries" in actions_so_far
    if has_fdrs and not has_upr:
        return (
            " For volunteers/staff/branches/local units you already have FDRS (Indicator Bank) data; "
            "only call get_upr_kpi_values_for_all_countries to fill gaps for countries missing from "
            "that result, or skip UPR if the user did not ask for it."
        )
    return ""
