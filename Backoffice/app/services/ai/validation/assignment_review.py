"""Assignment-level AI validation briefing (Validation summary).

Field-level opinions stay on AIFormDataValidation. This module builds the
Validation summary payload from the deterministic UPR assignment-review pack
(``plugins/upr/ai/assignment_review.py``): ``overview_figures``, ``whats_good``,
``whats_not`` and ``comment_note`` always come straight from that pack — no LLM
call needed, which keeps them cheap, deterministic and correctly linked to the
right ``form_item_id`` for click-to-scroll. An LLM call (when configured) is only
used to add a ``headline`` + short ``narrative`` synthesis on top; it must not
restate those lists, so its absence/failure simply means no narrative is shown
rather than a duplicated summary.

``overview_figures`` only ever contains a tile for a check that is fully "ok"
(gated on the ``status`` each figures sub-dict carries — see ``_with_status()``
in ``plugins/upr/ai/assignment_review.py``, the single place that decision is
made). A flagged/highlighted check never gets a tile: it already has a full
sentence in the "Needs attention" list right below, and a bare number restating
that same issue is the unhelpful-figure pattern this briefing exists to avoid.
Tiles exist only so a passing check's sentence — otherwise hidden inside the
collapsed "In good shape" list — is still visible at a glance.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from plugins.upr.ai.assignment_review import (
    build_upr_assignment_review_pack,
    format_upr_assignment_review_for_prompt,
)
from plugins.upr.ai.prompts import get_upr_assignment_review_prompt, is_upr_form_template

logger = logging.getLogger(__name__)


def _fallback_review(pack: Optional[Dict[str, Any]], counts: Dict[str, Any], headline: str) -> Dict[str, Any]:
    figures: List[Dict[str, str]] = []
    whats_good: List[str] = []
    whats_not: List[Dict[str, Any]] = []
    comment_note = None
    if isinstance(pack, dict):
        fig = pack.get("figures") or {}
        # Overview-figure tiles are shown ONLY for checks whose own audit already
        # landed on "ok" (see ``_with_status()`` in plugins/upr/ai/assignment_review.py,
        # the single source of truth for each check's pass/fail). A flagged or
        # highlighted check is never also given a tile here — it already has a full,
        # friendly sentence in the "Needs attention" list a few lines below, and a
        # bare "0 of 4 completed"-style number restating that same issue is exactly
        # the unhelpful-figure pattern we removed from the LLM summary; it only
        # helps for "ok" checks, whose sentence is hidden inside the collapsed
        # "In good shape" list until clicked.
        people = fig.get("people_longer_term") or {}
        if people and people.get("status") == "ok":
            grand_total = people.get("grand_total") or 0
            try:
                total_txt = f"{int(grand_total):,}"
            except (TypeError, ValueError):
                total_txt = str(grand_total)
            value = (
                f"{total_txt} people planned in total "
                f"({people.get('nonzero_count') or 0} of {people.get('cell_count') or 0} entries filled in)"
            )
            figures.append({
                "label": "Longer-term people to be reached",
                "value": value,
            })
        ns = fig.get("ns_key_figures") or {}
        if ns and ns.get("status") == "ok":
            figures.append({
                "label": "National Society key figures",
                "value": f"{ns.get('filled') or 0} of {ns.get('total') or 0} completed",
            })
        em = fig.get("people_emergency") or {}
        available_count = em.get("available_count") or 0
        if (available_count or em.get("selected_rows")) and em.get("status") == "ok":
            noun = "emergency" if available_count == 1 else "emergencies"
            figures.append({
                "label": "Emergency appeals — people to be reached",
                "value": f"{len(em.get('rows_with_values') or [])} of {available_count} available {noun} reported",
            })
        fund = fig.get("funding_y0_ifrc") or {}
        required_total = fund.get("required_total")
        if required_total and fund.get("status") == "ok":
            value = f"{fund.get('required_filled') or 0} of {required_total} required categories completed"
            figures.append({
                "label": "IFRC Secretariat funding (this year)",
                "value": value,
            })
        for finding in pack.get("ok") or []:
            if isinstance(finding, dict) and finding.get("text"):
                whats_good.append(str(finding["text"]))
        for finding in (pack.get("flags") or []) + (pack.get("highlights") or []):
            if not isinstance(finding, dict):
                continue
            whats_not.append({
                "severity": finding.get("severity") or "highlight",
                "form_item_id": finding.get("form_item_id"),
                "label": finding.get("label") or "",
                "text": finding.get("text") or "",
            })
        comment = str(pack.get("comment_text") or "").strip()
        if comment:
            preview = comment if len(comment) <= 280 else comment[:277] + "…"
            comment_note = preview
        flags = pack.get("flags") or []
        highlights = pack.get("highlights") or []
        # Keep the headline short and DISTINCT from the numbered "Needs attention" list
        # and the "In good shape" list rendered alongside it — point at what matters
        # (by label) instead of repeating a finding's full sentence, which is exactly
        # what those lists already show.
        if flags:
            top_label = flags[0].get("label") or "one item"
            headline = (
                f"1 issue needs attention: {top_label}." if len(flags) == 1
                else f"{len(flags)} issues need attention, starting with {top_label}."
            )
        elif highlights:
            top_label = highlights[0].get("label") or "one item"
            headline = (
                f"1 item to double-check: {top_label}." if len(highlights) == 1
                else f"{len(highlights)} items to double-check, starting with {top_label}."
            )
    return {
        "headline": headline,
        "overview_figures": figures,
        "whats_good": whats_good[:8],
        "whats_not": whats_not[:10],
        "comment_note": comment_note,
        # No narrative paragraph without an LLM: there is nothing to add beyond the
        # figures / numbered issues / good-shape lists already shown, so leave it
        # blank rather than restate them.
        "narrative": "",
        "source": "heuristic",
    }


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    from app.services.ai.validation.parsers import _extract_json_object
    obj = _extract_json_object(raw) if raw else None
    return obj if isinstance(obj, dict) else {}


def _run_assignment_review_llm(prompt: str) -> Dict[str, Any]:
    if not (current_app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        return {}
    from openai import OpenAI

    model_name = current_app.config.get("OPENAI_MODEL", "gpt-5-mini")
    openai_key = current_app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    timeout_sec = int(current_app.config.get("AI_HTTP_TIMEOUT_SECONDS", 60))
    client = OpenAI(api_key=openai_key, timeout=max(timeout_sec, 45))
    supports_sampling = not (str(model_name or "").strip().lower().startswith("gpt-5"))
    kwargs: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You review IFRC Unified Plan/Report assignments. "
                    "Return ONLY valid JSON. Always write in English. "
                    "Use the assignment review pack as facts."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        # Only a headline + short narrative are generated now (figures / whats_good /
        # whats_not / comment_note are deterministic — see generate_assignment_review),
        # so the LLM output is small; keep the budget tight to control cost.
        "max_completion_tokens": 500,
    }
    if supports_sampling:
        kwargs["temperature"] = 0.2
    resp = client.chat.completions.create(**kwargs)
    raw = ""
    try:
        raw = (resp.choices[0].message.content or "").strip()
    except Exception:
        raw = ""
    parsed = _parse_llm_json(raw)
    if parsed.get("headline"):
        parsed["source"] = "llm"
        parsed["model"] = model_name
        return parsed
    return {}


def build_review_pack_and_fallback(
    *,
    assignment_entity_status: Any,
    counts: Dict[str, Any],
    fallback_headline: str,
    entries: Optional[List[Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Phase 1 (no network): the deterministic UPR audit + heuristic fallback review.

    Split out of ``generate_assignment_review`` so the streaming overview route
    (``forms_validation_summary.validation_summary_overview_stream``) can emit a real
    "checking the figures" stage event right before this runs, and a real
    "writing the summary" stage right before the LLM call in
    :func:`finish_review_with_llm` — instead of a blind client-side timer.
    """
    pack = None
    tmpl = getattr(getattr(assignment_entity_status, "assigned_form", None), "template", None)
    template_id = getattr(tmpl, "id", None)
    if is_upr_form_template(template_id):
        try:
            pack = build_upr_assignment_review_pack(assignment_entity_status, entries)
        except Exception:
            logger.exception("UPR assignment review pack failed")
            pack = None

    base = _fallback_review(pack, counts, fallback_headline)
    return pack, base


def finish_review_with_llm(
    pack: Optional[Dict[str, Any]],
    base: Dict[str, Any],
    *,
    field_opinions: List[Dict[str, Any]],
    counts: Dict[str, Any],
) -> Dict[str, Any]:
    """Phase 2: ask the LLM for a ``headline`` + short ``narrative`` on top of ``base``.

    Only makes a network call when ``pack`` is truthy (a UPR assignment) and an LLM is
    configured; otherwise returns ``base`` unchanged. See module docstring — this never
    regenerates ``overview_figures``/``whats_good``/``whats_not``/``comment_note``.
    """
    if not pack:
        return base

    pack_text = format_upr_assignment_review_for_prompt(pack)
    prompt = get_upr_assignment_review_prompt(
        pack_text=pack_text,
        field_opinions=field_opinions,
        counts=counts,
    )
    try:
        llm = _run_assignment_review_llm(prompt)
    except Exception:
        logger.exception("assignment review LLM failed")
        llm = {}

    headline = str(llm.get("headline") or "").strip() or base["headline"]
    narrative = str(llm.get("narrative") or "").strip()
    return {
        **base,
        "headline": headline,
        "narrative": narrative,
        "source": "llm" if llm else "heuristic",
        "model": llm.get("model") if llm else None,
    }


def generate_assignment_review(
    *,
    assignment_entity_status: Any,
    counts: Dict[str, Any],
    field_opinions: List[Dict[str, Any]],
    fallback_headline: str,
    entries: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Build the Validation summary briefing (non-streaming convenience wrapper).

    ``overview_figures`` / ``whats_good`` / ``whats_not`` / ``comment_note`` are ALWAYS
    the deterministic UPR assignment-review audit (``plugins/upr/ai/assignment_review.py``)
    — cheap, reliable, and already carry the right ``form_item_id`` for click-to-scroll.
    When an LLM is configured it is only asked for a ``headline`` + short ``narrative``
    that adds genuine synthesis (prioritisation, cross-field connections, applying the
    reporting-country comment's caveats) on top of those lists. It must not restate
    them; if the LLM is unavailable or fails, we keep the deterministic headline and
    simply omit the narrative rather than duplicate the lists in prose.

    Just calls :func:`build_review_pack_and_fallback` then :func:`finish_review_with_llm`
    back-to-back — use those directly (with a yield/event in between) for real progress
    staging; use this wrapper when you just want the final dict in one call.
    """
    pack, base = build_review_pack_and_fallback(
        assignment_entity_status=assignment_entity_status,
        counts=counts,
        fallback_headline=fallback_headline,
        entries=entries,
    )
    return finish_review_with_llm(pack, base, field_opinions=field_opinions, counts=counts)
