"""Questions on the DREF monitoring template that are not indicator-bank indicators.

The template builder reads this module each time it publishes the cycle form.
Change the tuples below, or ``customize_questions``, to reword a question,
change its type, drop it, or add one. The next plan validation (or project
backfill) rewrites the template from what this module returns.

Activities are not questions on the template and not a repeat section. The entry
form lists the activities already on the plan, one card each.
``ACTIVITY_QUESTIONS`` is the wording of that card. A focal point does not add
activities there.

``SECTOR_NAME_TO_KEY`` maps a databank sector name to a GO sector key when the
names differ. Exact folded names still match on their own (Health, Education,
and the spelled-out WASH name). This dict covers the GO labels that are
longer, abbreviated, or renamed relative to the indicator bank.

``width`` is the form column width, from 1 to 12.
"""

from __future__ import annotations

from plugins.dref_monitoring.constants import ACTIVITY_TYPES, CARRIED_OUT_BY

# Databank sector name -> GO sector key.
SECTOR_NAME_TO_KEY: dict[str, str] = {
    "Shelter": "shelter_and_basic_household_items",
    "Food security and livelihoods": "livelihoods",
    "Cash and voucher assistance (CVA)": "multi_purpose_cash_grants",
    "WASH": "water_sanitation_and_hygiene",
    "Protection, Gender and Inclusion (PGI)": "protection_gender_and_inclusion",
    "Migration": "migration_and_displacement",
    "Disaster risk reduction": "risk_reduction_climate_adaptation_and_recovery",
    "Community Engagement and Accountability (CEA)": "community_engagement_and_accountability",
    "Climate and environment": "environmental_sustainability",
    "Coordination and cooperation": "coordination_and_partnerships",
    "National Society development": "national_society_strengthening",
}

ACTIVITY_SECTION_NAME = "Selected activities"

# Asked once, on every operation. The builder puts this in a section named Notes
# and hides that section's heading, so the field is not wrapped in a second title.
REPORT_QUESTIONS: tuple[dict, ...] = (
    {
        "key": "narrative",
        "label": "Notes",
        "label_translations": {
            "fr": "Notes",
            "es": "Notas",
            "ar": "ملاحظات",
        },
        "type": "textarea",
        "description": "Cumulative position for this reporting period.",
        "width": 12,
    },
)

# Top of each selected sector, before the indicators.
SECTOR_HEADER_QUESTIONS: tuple[dict, ...] = (
    {"key": "budget", "label": "Budget (CHF)", "type": "number", "width": 6},
    {"key": "people_targeted", "label": "People targeted", "type": "number", "width": 6},
)

# One card per activity already on the plan. The entry form draws these; it does not add activities.
ACTIVITY_QUESTIONS: tuple[dict, ...] = (
    {"key": "activity", "label": "Activity", "type": "text", "width": 12},
    {
        "key": "status",
        "label": "Status",
        "type": "single_choice",
        "options": ["Planned", "Ongoing", "Complete", "Blocked", "Delayed"],
        "width": 4,
    },
    {
        "key": "activity_type",
        "label": "Activity type",
        "type": "single_choice",
        "options": [label for _code, label in ACTIVITY_TYPES],
        "width": 4,
    },
    {
        "key": "carried_out_by",
        "label": "Activity carried out by",
        "type": "single_choice",
        "options": [label for _code, label in CARRIED_OUT_BY],
        "width": 4,
    },
    {"key": "activity_budget", "label": "Budget", "type": "number", "width": 3},
    {"key": "activity_target", "label": "Target", "type": "number", "width": 3},
    {"key": "start_date", "label": "Start date", "type": "date", "width": 3},
    {"key": "end_date", "label": "End date", "type": "date", "width": 3},
    {"key": "reached", "label": "Reached - total", "type": "number", "width": 4},
    {"key": "pct_female", "label": "% Female", "type": "number", "width": 2},
    {"key": "pct_male", "label": "% Male", "type": "number", "width": 2},
    {"key": "pct_girls", "label": "% Girls", "type": "number", "width": 2},
    {"key": "pct_boys", "label": "% Boys", "type": "number", "width": 2},
    {
        "key": "disaggregation_na",
        "label": "Can't provide disaggregation",
        "type": "yesno",
        "width": 12,
    },
)


def customize_questions(questions, *, sector_key=None, indicator=None):
    """Return the questions to place on the form.

    ``questions`` is a list of dicts with ``key``, ``label``, ``type``, and
    optional ``options``, ``description``, and ``width``. ``sector_key`` is the
    GO sector key for a sector section, otherwise None.
    """
    del sector_key, indicator
    return list(questions)
