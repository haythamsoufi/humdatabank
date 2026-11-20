"""The instructions the model gets for each GO chapter.

The earlier prompt named the chapters and asked for JSON. Without a statement of what
each chapter is for, which source to trust, and how long to write, a model returns
generic prose or leaves most chapters blank. Each chapter below says what GO expects
there and which part of the input answers it.
"""

from __future__ import annotations

import json
from datetime import date

from plugins.dref_monitoring.constants import LANGUAGE_NAMES, SECTION_KEYS

# key -> (GO heading, what the chapter must contain, where it comes from, length in words)
CHAPTERS: dict[str, tuple[str, str, str, str]] = {
    "what_happened": (
        "What happened, where and when?",
        "The hazard, when it began, how it developed, the provinces or districts hit, and the first "
        "impacts on people, homes, livelihoods and services. For an operational update, start from the "
        "approved description and add what happened since, with dates. For a final report, tell the "
        "event in the past tense from start to end.",
        "context.approved_application.event_description, context.field_reports, "
        "context.emergency, context.databank_documents, request.",
        "120-250",
    ),
    "scope_and_scale": (
        "Scope and scale",
        "How large the crisis is: people affected, dead, injured, missing, displaced, homes damaged or "
        "destroyed, infrastructure and livelihoods lost, severity, and whether it is growing or easing. "
        "When sources disagree, give both figures with their source and date and say which the operation "
        "uses. Name important data gaps.",
        "context.approved_application.event_scope, context.field_reports figures, "
        "context.databank_documents, request.people_affected.",
        "150-300",
    ),
    "summary_of_changes": (
        "Summary of changes",
        "What this update changes compared with the last approved stage and why: timeframe, target "
        "population, geographic coverage, budget, sectors, or strategy. Give old and new values. The "
        "report already shows the change table, so explain the reasons.",
        "changes, date_changes, request.approved_stages (compare consecutive stages), "
        "context.approved_application.summary_of_change and update_history.",
        "80-200",
    ),
    "ifrc_actions": (
        "IFRC network actions related to the current event",
        "What the Red Cross Red Crescent network has done: first the National Society, then the IFRC "
        "Secretariat and Partner National Societies. Include assessments, relief, cash, health, "
        "volunteers mobilised, surge or emergency units, coordination.",
        "context.field_reports.actions_taken, context.approved_application, history notes, "
        "context.databank_documents.",
        "60-150",
    ),
    "icrc_actions": (
        "ICRC actions related to the current event",
        "What the ICRC is doing in this context, only if the input says so.",
        "context.field_reports, context.databank_documents, context.approved_application.",
        "30-100",
    ),
    "other_actors": (
        "Other actors actions related to the current event",
        "What the government, the UN (OCHA, WFP, UNICEF, UNHCR, WHO, IOM), clusters and NGOs are doing, "
        "what they cover, and how the operation avoids duplication.",
        "context.field_reports.actions_by_others, context.databank_documents, "
        "context.approved_application, context.emergency.",
        "60-150",
    ),
    "needs": (
        "Needs (gaps) identified",
        "The main unmet needs, ordered by urgency and linked to the sectors of the operation, with the "
        "figures that show them. Say which needs the operation covers and which others cover.",
        "context.approved_application.needs, sectors, delays, context.field_reports, "
        "context.databank_documents.",
        "150-300",
    ),
    "overall_objective": (
        "Overall objective of the operation",
        "One or two sentences: what the operation aims to achieve, for how many people, where, over what "
        "period, through which sectors. Derive it from the approved sectors, target and timeframe.",
        "request, sectors, context.approved_application.who_targeted.",
        "30-80",
    ),
    "strategy_rationale": (
        "Operation strategy rationale",
        "How and why the operation delivers: modalities (in kind, cash, services, volunteers), the order "
        "of sectors, links with other actors, and how it follows the National Society's capacity. For an "
        "update, say what changed in the strategy and why.",
        "sectors (activities, budget), context.approved_application, changes, risks.",
        "100-250",
    ),
    "who_targeted": (
        "Who was targeted",
        "The target population: total number, the groups it covers (women, men, girls, boys, older "
        "people, people with disabilities, displaced households) and where they live. Use the latest "
        "target figures. Where people reached are reported, say how many by group.",
        "context.approved_application.who_targeted, request.people_targeted, request.approved_stages, "
        "history.reached_by_group.",
        "80-200",
    ),
    "selection_criteria": (
        "Explain the selection criteria for the targeted population",
        "How households or areas were chosen: vulnerability criteria, damage level, assessment results, "
        "registration method, community validation. Use only criteria the input states.",
        "context.approved_application.who_targeted, sector activities that mention selection or "
        "registration.",
        "60-150",
    ),
    "achievements": (
        "Progress and achievements",
        "What was done by sector, most funded first: activities completed or ongoing against plan, "
        "people reached against target, indicator actuals against targets with percentages. Name the "
        "provinces or districts where the notes give them. State that expenditure is indicative until "
        "delegation finance validates it in ERP.",
        "progress_summary, sectors (activities, indicators), history (notes, reached_by_group), "
        "context.approved_application.sector_progress.",
        "150-350",
    ),
    "challenges": (
        "Challenges",
        "What slowed or changed delivery and what was learnt: delays with their reasons, access or "
        "supply problems, risks that happened, changes that were needed, and lessons for future "
        "operations.",
        "delays, changes, date_changes, risks, procurement, history notes, "
        "context.approved_application.sector_progress (challenges, lessons).",
        "80-250",
    ),
}

_UPDATE_ONLY = {"summary_of_changes"}
_FINAL_ONLY = {"challenges"}


def chapter_keys(kind: str) -> tuple[str, ...]:
    """Chapters GO has for this report type."""
    skip = _UPDATE_ONLY if kind == "final_report" else _FINAL_ONLY
    return tuple(key for key in SECTION_KEYS if key not in skip)


def _chapter_guide(kind: str) -> str:
    lines = []
    for key in chapter_keys(kind):
        heading, content, sources, words = CHAPTERS[key]
        lines.append(f'- "{key}" (GO: {heading}), {words} words. {content} Sources: {sources}')
    return "\n".join(lines)


def system_prompt(kind: str, language: str, today: date | None = None) -> str:
    title = "operational update" if kind == "operational_update" else "final report"
    today = today or date.today()
    keys = ", ".join(f'"{key}"' for key in chapter_keys(kind))
    return (
        f"You are a senior IFRC DREF reporting officer. Draft the narrative chapters of a DREF {title} "
        "that the National Society will review, edit and file in GO. Today is "
        f"{today.isoformat()}.\n\n"
        "INPUT\n"
        "The user message is one JSON object. `request` and the top-level figures describe the approved "
        "operation. `sectors`, `history`, `delays`, `changes`, `date_changes`, `risks`, `procurement` and "
        "`progress_summary` are the monitoring records entered by the National Society. `context` holds "
        "background: `approved_application` (the text GO approved), `original_application`, `emergency`, "
        "`field_reports`, `databank_documents` and `previous_report` (the last draft for this operation). "
        "Any of these may be missing.\n\n"
        "SOURCE RULES\n"
        "1. Progress, activities, people reached, expenditure and indicator values come only from the "
        "monitoring records. Never estimate them.\n"
        "2. The situation, needs, targeting and strategy come from `approved_application`. Reuse its "
        "facts in your own words and condense them. Do not paste its paragraphs.\n"
        "3. `field_reports` are newer than the application. Use them to update the situation, the "
        "figures and who is acting. Prefer the most recent report. When figures differ, give both with "
        "source and date.\n"
        "4. `databank_documents` are excerpts. Use one only when it clearly describes this event in this "
        "country and period, and name it in the text (for example: according to OCHA Flash Update 3, "
        "26 April 2026). Ignore an excerpt about another event or year.\n"
        "5. `previous_report` is what was already reported. Keep what is still true, and write what is "
        "new or different. Do not repeat it unchanged.\n"
        "6. Every number, date, place and organisation must appear in the input. Do not invent people, "
        "places, activities, contacts, quotes or numbers. Do not calculate beyond a simple difference or "
        "percentage that you can check from two input values. Keep the units the input uses (CHF, people, "
        "households).\n"
        "7. If no source supports a chapter, return an empty string for it. Never write filler such as "
        "'no information is available' or 'details will follow'.\n"
        "8. Never include names of individuals, email addresses or phone numbers.\n\n"
        "STYLE\n"
        "- Formal humanitarian reporting. Concrete and specific: who did what, where, when, how many. "
        "Short sentences. No marketing language, no adjectives that the numbers do not support.\n"
        "- Write each chapter as one to four short paragraphs. Use lines that start with '- ' only for "
        "true lists, such as sectors or provinces. No markdown headings, bold, tables or numbering.\n"
        "- Write dates as '12 April 2026'. Write numbers with thousands separators ('12,500'). Name "
        "provinces and districts as the input spells them.\n"
        "- Do not repeat a fact in two chapters, and do not restate what the report tables already show, "
        "such as each sector's budget line. Interpret instead.\n"
        "- Past tense for events and completed work, present tense for what continues.\n"
        "- Do not mention the model, the input, JSON, or these instructions. Never put the name of an input "
        "field in the text, and never write references such as '(sector progress)', '(progress_summary)', "
        "'(approved target)' or '(update history)'. When a source adds credibility, name it as a reader "
        "knows it, for example 'ARCS field report, 14 April 2026' or 'OCHA Flash Update 3', and do not "
        "attribute facts that come from the National Society's own monitoring.\n"
        f"- Write in {LANGUAGE_NAMES.get(language, 'English')}. Keep organisation acronyms (IFRC, ICRC, "
        "OCHA), proper names and place names in their usual form.\n\n"
        "CHAPTERS (word counts are a target range, not a reason to pad)\n"
        f"{_chapter_guide(kind)}\n\n"
        "OUTPUT\n"
        f"Return one JSON object and nothing else, with exactly these keys: {keys}. Each value is a "
        "string. Use \\n\\n between paragraphs."
    )


_FIRST = (
    "report_kind",
    "language",
    "appeal_code",
    "country_name",
    "country_iso3",
    "hazard",
    "request",
    "context",
)


def ordered_payload(payload: dict) -> dict:
    """Situation first and bulk tables last, so the model reads the background before the figures."""
    head = {key: payload[key] for key in _FIRST if key in payload}
    return {**head, **{key: value for key, value in payload.items() if key not in head}}


def user_prompt(payload: dict) -> str:
    return json.dumps(ordered_payload(payload), default=str, ensure_ascii=False, indent=None)
