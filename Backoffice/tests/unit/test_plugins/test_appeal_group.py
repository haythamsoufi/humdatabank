"""Subtype mapping for the appealgroupchild feed."""

from plugins.emergency_operations.appeal_group import (
    APPEAL_GROUP_URL,
    LEGACY_APPEAL_URL,
    effective_feed_id,
    map_subtype_to_appeal_type,
    normalize_appeal_group_row,
    resolve_appeals_url,
    url_for_feed,
)
from plugins.emergency_operations.routes import _cache_matches_feed


def test_emergency_and_minor_emergency_map_to_go_type_names():
    assert map_subtype_to_appeal_type("Emergency") == "Emergency Appeal"
    assert map_subtype_to_appeal_type("minor emergency") == "DREF"
    assert map_subtype_to_appeal_type("Annual") == "Annual"


def test_child_row_keeps_country_code_and_parent():
    row = normalize_appeal_group_row({
        "Appeal_Id": "MDRUG051",
        "Part_of": "MDRS1001",
        "Appeal_Name": "Uganda - Population Movement",
        "Status": "Active",
        "Start_Date": "2024-07-06T00:00:00",
        "End_Date": "2026-12-31T00:00:00",
        "Geographical_Code": "ug",
        "Subtype": "Emergency",
        "Original_Subtype": "Minor Emergency",
        "Group_Appeal_Name": "Sudan Crisis Regional Population Movement",
    })
    assert row["code"] == "MDRUG051"
    assert row["part_of"] == "MDRS1001"
    assert row["atype_display"] == "Emergency Appeal"
    assert row["original_subtype"] == "Minor Emergency"
    assert row["country"]["iso"] == "UG"
    assert row["end_date"].startswith("2026-12-31")


def test_legacy_go_url_resolves_to_appealgroupchild():
    assert resolve_appeals_url(None) == APPEAL_GROUP_URL
    assert resolve_appeals_url("https://goadmin.ifrc.org/api/v2/appeal/") == APPEAL_GROUP_URL
    assert resolve_appeals_url("https://example.test/custom") == APPEAL_GROUP_URL
    assert resolve_appeals_url("go_legacy") == LEGACY_APPEAL_URL


def test_explicit_feed_choice_wins_over_a_saved_url():
    assert effective_feed_id({"base_url": LEGACY_APPEAL_URL}) == "appeal_group"
    assert effective_feed_id({"feed": "go_legacy", "base_url": APPEAL_GROUP_URL}) == "go_legacy"
    assert url_for_feed("go_legacy") == LEGACY_APPEAL_URL
    assert url_for_feed("not-a-feed") == APPEAL_GROUP_URL


def test_legacy_cache_is_not_used_for_the_new_feed():
    assert _cache_matches_feed({"source": None, "results": []}, APPEAL_GROUP_URL) is False
    assert _cache_matches_feed({"source": "appealgroupchild", "results": []}, APPEAL_GROUP_URL) is True
