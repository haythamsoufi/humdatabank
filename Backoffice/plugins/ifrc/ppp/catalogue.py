"""Public labels and field identities for the Pilot Programmatic Partnership dashboard.

Figures come from the Kobo forms imported by ``plugins/ifrc/ppp/sync.py``.
Each programme result is its own form. The overview form holds the unique
people reached across every result.
"""

from __future__ import annotations

import re

KOBO_MARKER = "Kobo asset "

# Asset uid stored in the template version description by the import script.
TEMPLATE_KEYS = {
    "aHQTGPhhLv5MhsycfNvBJZ": "overview",
    "afsHubF3oA3KpDV8eJRgn6": "drm",
    "aaMUkVa6QFuMEr4rV78YYC": "eppr",
    "aS8LroVXh5bSnEPz685UqS": "movement",
    "a855a2utxS7MCt8PJCR26Q": "cva",
    "ad2qnRrwYkhoHZSRokftBc": "rccea",
}

PILLARS = (
    {
        "id": "drm",
        "title": "Disaster risk management",
        "reach_kobo": "individuals_num_1",
        "icon": "umbrella",
    },
    {
        "id": "eppr",
        "title": "Epidemic and pandemic preparedness and response",
        "reach_kobo": "individuals_num_2",
        "icon": "virus",
    },
    {
        "id": "movement",
        "title": "Humanitarian assistance and protection for people on the move",
        "reach_kobo": "individuals_num_3",
        "icon": "people",
    },
    {
        "id": "cva",
        "title": "Cash and voucher assistance",
        "reach_kobo": "individuals_num_4",
        "icon": "card",
    },
    {
        "id": "rccea",
        "title": "Risk communication, community engagement and accountability",
        "reach_kobo": "individuals_num_5",
        "icon": "megaphone",
    },
)

OVERVIEW_REACH_KOBO = "unique_indiv_country_q"

HIGHLIGHTS = (
    {
        "id": "wash",
        "title": "People reached with WASH services",
        "icon": "tap",
        "label_contains": "water, sanitation and hygiene services",
    },
    {
        "id": "cva",
        "title": "People reached with CVA",
        "icon": "card",
        "kobo_name": "R4CVA_ind_2_CVA",
    },
    {
        "id": "protection",
        "title": "People (migrants, displaced, host communities) reached with assistance and protection",
        "icon": "people",
        "kobo_name": "R3APMOVE_ind_1_APS",
    },
    {
        "id": "inclusion",
        "title": "People (migrants, displaced, host communities) reached with social inclusion activities",
        "icon": "group",
        "kobo_name": "R3APMOVE_ind_3_SI",
    },
    {
        "id": "hsps",
        "title": "HSPs providing assistance and protection",
        "icon": "pin",
        "kobo_name": "R3APMOVE_ind_2_HSP",
    },
)

_ACTIVITY_RE = re.compile(
    r"^(?:R1DRM_act_|R2EPPR_\d|R3HAPPM_|R4CVA_act_|R5RCCEA_act_)"
)
_NUMBER_PREFIX_RE = re.compile(r"^\d+(?:\.\d+)*\s*")
_REACH_LABEL = "how many unique individuals"


def pillar_by_id(pillar_id: str) -> dict | None:
    for pillar in PILLARS:
        if pillar["id"] == pillar_id:
            return pillar
    return None


def display_label(label: str) -> str:
    """Drop the Kobo numbering prefix so a public row reads as a sentence."""
    text = _NUMBER_PREFIX_RE.sub("", (label or "").replace("\n", " ")).strip()
    return re.sub(r"\s+", " ", text)


def is_overview_reach(kobo_name: str, label: str) -> bool:
    if kobo_name == OVERVIEW_REACH_KOBO:
        return True
    text = (label or "").lower()
    return "unique individuals have been reached" in text and "across all results" in text


def is_pillar_reach(pillar_id: str, kobo_name: str, label: str) -> bool:
    pillar = pillar_by_id(pillar_id)
    if pillar and kobo_name == pillar["reach_kobo"]:
        return True
    return pillar_id != "overview" and (label or "").lower().startswith(_REACH_LABEL)


def is_activity_field(kobo_name: str) -> bool:
    name = kobo_name or ""
    return bool(_ACTIVITY_RE.match(name)) and not name.endswith("_nar")


def narrative_kobo_name(activity_kobo: str) -> str:
    return f"{activity_kobo}_nar"


def highlight_for_item(kobo_name: str, label: str) -> dict | None:
    text = (label or "").lower()
    for highlight in HIGHLIGHTS:
        if highlight.get("kobo_name") and highlight["kobo_name"] == kobo_name:
            return highlight
        needle = highlight.get("label_contains")
        if needle and needle in text:
            return highlight
    return None


def is_public_indicator(kobo_name: str, label: str, item_type: str, question_type: str) -> bool:
    """A result indicator shown in the detail table, not the pillar reach total."""
    if is_activity_field(kobo_name) or (kobo_name or "").endswith("_nar"):
        return False
    if any(is_pillar_reach(pillar["id"], kobo_name, label) for pillar in PILLARS):
        return False
    if is_overview_reach(kobo_name, label):
        return False
    if item_type == "indicator":
        return True
    if question_type == "yesno" and "_ind_" in (kobo_name or ""):
        return True
    return False
