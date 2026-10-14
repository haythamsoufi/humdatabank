"""Display text for the UPR Analysis feature (tab, PDF export, presentation).

One catalogue, one set of msgids. The view builders
(:mod:`plugins.upr.impact_views`, :mod:`plugins.upr.narrative_views`) pull every
title, hint, series name, column heading and note from here, so the Analysis tab
and any export always say the same thing. Placeholders such as ``{year}`` are
filled with :func:`fill` after translation.

Text is resolved per call (not at import) so it follows the active Flask-Babel
locale.
"""

from __future__ import annotations

import html
from typing import Any

from flask_babel import gettext as _


def fill(text: str, **values: Any) -> str:
    """Replace ``{name}`` placeholders. Plain ``str.replace`` so translated text may keep literal braces."""
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def analysis_labels() -> dict[str, str]:
    """Every display string of the Analysis visuals, in the active locale."""
    labels = {
        "intro_title": _("Analysis of Unified Plans and Reports"),
        "intro_lead": _("How the Unified Planning and Reporting process is growing across the IFRC network — rising participation, funding ambition, people reached, and partners engaged."),
        "narr_title": _("Participation: data and narrative"),
        "narr_lead": _("A National Society takes part in a round when it submits its data form or hands in its narrative. The internal narrative is the document sent to the Secretariat (IFRC GO, internal); the public narrative is the one published on the public site. Counting data alone misses countries that only take part through the narrative."),

        # Data visuals
        "coverage_title": _("Participation (coverage)"),
        "coverage_hint": _("National Societies completing a plan or report each year (reports: annual, or mid-year where the annual is not yet available)."),
        "funding_title": _("Funding ambition &amp; delivery"),
        "funding_hint": _("Same mix as the Financial Overview network, CHF. Planned requirement is the country plan (host National Society + IFRC Secretariat + PNS lines on the plan). Reported funding adds PNS self-reports, other sources, and IFRC Secretariat actuals. Reported expenditure adds PNS self-reports and IFRC Secretariat actuals."),
        "reach_hint": _("People the network plans to reach, by plan year."),
        "partners_title": _("Partners engaged"),
        "partners_hint": _("Participating National Societies providing bilateral support, and the funding they self-report (PNS data, CHF)."),
        "capacity_title": _("National Society capacity"),
        "capacity_hint": _("Volunteers, staff, branches and local units reported by host National Societies."),
        "impact_footnote": _("Indicative network totals summed from Unified Plans and Reports currently in the database. The trend spans the rounds that have submissions; it is not a historical back-fill."),
        "reach_title": _("People to be reached"),

        # Narrative visuals
        "stage_title": _("Participation by stage"),
        "stage_hint": _("National Societies in each round at each stage. “Either” is the real participation: data submitted or internal narrative handed in."),
        "mix_title": _("How countries take part"),
        "mix_hint": _("Both data and narrative, narrative only, or data only. Blank where the databank holds no data for that round."),
        "pub_title": _("From internal to public"),
        "pub_hint": _("Internal narratives received, and how many of those countries have a public document."),
        "gaps_title": _("Gaps to follow up"),
        "matrix_button_aria": _("View every country by round"),

        # Series, columns, KPIs and notes
        "plan_submitted": _("Plans submitted"),
        "report_submitted": _("Reports submitted"),
        "year": _("Year"),
        "plan_round": _("Plan round"),
        "report_round": _("Report round"),
        "plan_requirement": _("Planned requirement"),
        "report_funding": _("Reported funding"),
        "report_expenditure": _("Reported expenditure"),
        "people_reached": _("People to be reached"),
        "partners": _("Partners (PNS)"),
        "partner_funding": _("Partner funding (CHF)"),
        "volunteers": _("Volunteers"),
        "staff": _("Staff"),
        "branches": _("Branches"),
        "local_units": _("Local units"),
        # Reports submitted only. "Participating" is reserved for data or narrative
        # (see narr_kpi_any), so the two figures never share a name.
        "kpi_coverage": _("National Societies that reported"),
        "kpi_requirement": _("Planned funding requirement"),
        "kpi_reach": _("People to be reached"),
        "kpi_partners": _("Partners engaged"),
        "kpi_partner_funding": _("Partner funding"),
        "vs_previous": _("vs {year}"),
        "no_previous": _("first year"),
        "in_progress_note": _("* Year still open ({years}) — submissions are still coming in, so the latest point understates the final total. Headline figures use the latest completed year."),
        "midyear_note": _("Reporting figures use the annual report where available, otherwise the mid-year report (years: {years})."),
        "funding_source_note": _("Same mix as the Financial Overview network block. Planned requirement is the country plan: host National Society + IFRC Secretariat + PNS lines recorded on that plan. Reported funding is PNS self-reported funding + other sources on the country report + IFRC Secretariat actuals (2025 and 2026 snapshots; earlier years have none). Reported expenditure is PNS self-reported expenditure + those IFRC actuals. Host National Society strategic-priority totals are not added on top. Transfers are not counted as expenditure."),
        "midyear_legend": _("Mid-year report, shown where the annual report is not yet available"),
        "partners_source_note": _("Source: Participating National Society self-reports (PNS data). This is separate from the PNS amount a host National Society records in its own plan. Under a country, the partner count is the societies supporting that country; the year total counts each society once."),
        "narr_data_submitted": _("Data submitted"),
        "narr_internal": _("Internal narrative"),
        "narr_public": _("Public narrative"),
        "narr_either": _("Either (data or narrative)"),
        "narr_both": _("Data and narrative"),
        "narr_narrative_only": _("Narrative only"),
        "narr_data_only": _("Data only"),
        "narr_published": _("Internal and public"),
        "narr_not_public": _("Not yet public"),
        "narr_public_only": _("Public only"),
        "narr_publication_rate": _("Share made public"),
        "narr_baseline": _("First round (baseline)"),
        "narr_kpi_plans": _("Plans: participating"),
        "narr_kpi_midyear": _("Mid-year reports: participating"),
        "narr_kpi_annual": _("Annual reports: participating"),
        "narr_kpi_cycle": _("Planned and reported"),
        "narr_kpi_cycle_note": _("{both} of {plan} that planned also reported"),
        "narr_kpi_always": _("Took part in every round"),
        "narr_kpi_always_note": _("of {n} completed rounds"),
        "narr_eng_title": _("How consistently countries take part"),
        "narr_eng_hint": _("National Societies by the number of completed rounds (plans, mid-year and annual reports) they took part in. Rounds still open or only partly covered by the sources are left out."),
        "narr_eng_rounds": _("Completed rounds taken part in"),
        "narr_eng_series": _("National Societies"),
        "narr_ret_title": _("Retention year on year"),
        "narr_ret_hint": _("Participants that carried on, joined, or dropped out compared with the previous year. The first round is shown in grey as the baseline. When the previous round is only partly covered by the sources, joiners are not shown, because countries it simply missed would look new."),
        "narr_gap_always": _("Took part in every completed round"),
        "narr_gap_intermittent": _("Took part in some rounds only"),
        "narr_gap_planned_not_reported": _("Planned but did not report (latest year with both)"),
        "narr_gap_never": _("Only in open or partly covered rounds"),
        "narr_gaps_hint_all": _("Across {n} completed rounds."),
        "narr_retained": _("Carried on"),
        "narr_new": _("Joined"),
        "narr_lapsed": _("Dropped out"),
        "narr_round": _("Round"),
        "narr_country": _("National Society"),
        "narr_region": _("Region"),
        "narr_lapsed_title": _("Participated last year, not this year"),
        "narr_none": _("None — nothing to follow up."),
        "narr_participation_pct": _("Participation rate"),
        "narr_matrix_title": _("Country by round"),
        "narr_matrix_note": _("D = data submitted, N = internal narrative, P = public narrative. Blank = no participation recorded."),
        "narr_gaps_hint": _("Latest completed round: {round}."),
        "narr_kpi_any": _("Participating (data or narrative)"),
        "narr_kpi_internal": _("Internal narratives"),
        "narr_kpi_public": _("Public narratives"),
        "narr_kpi_hidden": _("Missed by data alone"),
        "narr_kpi_publication": _("Internal narratives made public"),
        "narr_note_in_progress": _("* Round still open ({years}) — documents and submissions are still coming in."),
        "narr_note_no_data": _("The databank holds no data assignments for {rounds}, so only narrative participation is shown for them."),
        "narr_note_sources": _("Sources: internal narratives {internal}, public narratives {public} (one per country and round, country appeals only)."),
        "narr_note_universe": _("Participation rate is out of the {n} National Societies seen in any round."),
    }
    # The msgid kept its HTML entity from when it lived in a template.
    labels["funding_title"] = html.unescape(labels["funding_title"])
    return labels


def analysis_ui_labels() -> dict[str, str]:
    """Interface strings the browser needs for controls it renders itself."""
    return {
        "show_countries": _("Show countries"),
        "midyear_cell": _("Mid-year report — the annual report is not yet available"),
        "load_failed": _("Could not load analysis data. Try refreshing."),
        "close": _("Close"),
        "view_table": _("View as table"),
        "gaps_select": _("Select a list to see the countries."),
        # Presentation and A4 report
        "export_nothing": _("Nothing is ready to export yet. Wait for the analysis to finish loading."),
        "export_unavailable": _("Not loaded"),
        "export_print": _("Download PDF"),
        "export_print_hint": _("Saves an A4 PDF of these pages."),
        "export_pdf_working": _("Preparing PDF…"),
        "export_pdf_failed": _("Could not create the PDF. Try again."),
        "export_generated": _("Generated {date}"),
        "export_region": _("Region: {region}"),
        "export_all_regions": _("All regions"),
        "export_prev": _("Previous slide"),
        "export_next": _("Next slide"),
        "export_fullscreen": _("Full screen"),
        "export_page": _("Page {n} of {total}"),
        "export_notes": _("Notes"),
        "findings_title": _("Key findings"),
        "export_findings": _("Show or hide findings"),
        "export_finding": _("Finding {n}"),
        "export_tables_heading": _("Data tables"),
        "export_more": _("and {n} more"),
        "section_data": _("Data trends"),
        "track_ALL": _("Overview"),
        "track_P": _("Plans"),
        "track_MYR": _("Mid-year reports"),
        "track_AR": _("Annual reports"),
    }
