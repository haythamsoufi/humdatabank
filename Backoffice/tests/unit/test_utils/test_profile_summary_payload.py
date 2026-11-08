"""Unit tests for profile summary payload helpers."""

import pytest

from app.utils.profile_summary_payload import (
    focal_scope_display_lines,
    profile_summary_scope_fields,
    role_badge_key_from_rbac_codes,
)


@pytest.mark.parametrize(
    "codes,expected",
    [
        (["assignment_viewer"], "focal_point"),
        (["assignment_editor_submitter"], "focal_point"),
        (["admin_core", "assignment_viewer"], "admin"),
        (["system_manager", "admin_full"], "system_manager"),
        ([], "user"),
        (["guest"], "user"),
    ],
)
def test_role_badge_key_from_rbac_codes(codes, expected):
    assert role_badge_key_from_rbac_codes(codes) == expected


def _region_map():
    return {
        "R1": {1, 2},
        "R2": {3, 4},
    }


def _country_meta():
    return {
        1: ("Alpha", "R1"),
        2: ("Beta", "R1"),
        3: ("Gamma", "R2"),
        4: ("Delta", "R2"),
    }


def test_focal_scope_full_region_and_loose_names():
    lines = focal_scope_display_lines(
        {1, 2, 3},
        {},
        country_id_to_name_region=_country_meta(),
        region_to_all_country_ids=_region_map(),
    )
    assert lines[0] == "R1"
    assert lines[1] == "Gamma"


def test_focal_scope_lists_country_names_when_five_or_fewer_units():
    lines = focal_scope_display_lines(
        {1, 3},
        {"ns_branch": 1},
        country_id_to_name_region=_country_meta(),
        region_to_all_country_ids=_region_map(),
    )
    assert "Alpha" in lines[0] and "Gamma" in lines[0]
    assert lines[1] == "ns branch: 1"


def test_focal_scope_summarizes_when_more_than_five_units():
    lines = focal_scope_display_lines(
        {1, 2, 3},
        {"ns_branch": 4},
        country_id_to_name_region=_country_meta(),
        region_to_all_country_ids=_region_map(),
    )
    assert lines[0] == "R1"
    assert lines[1] == "1 countries, 4 other assignments"


def test_focal_scope_global_when_all_countries():
    meta = {1: ("A", "R"), 2: ("B", "R")}
    region = {"R": {1, 2}}
    lines = focal_scope_display_lines({1, 2}, {}, country_id_to_name_region=meta, region_to_all_country_ids=region)
    assert lines == ["Global"]


def test_profile_summary_scope_fields_omits_for_admin():
    assert profile_summary_scope_fields(
        "admin",
        {1},
        {},
        country_id_to_name_region={1: ("X", "R")},
        region_to_all_country_ids={"R": {1}},
    ) == {}


def test_profile_summary_scope_fields_includes_for_focal():
    d = profile_summary_scope_fields(
        "focal_point",
        {1},
        {"division": 1},
        country_id_to_name_region=_country_meta(),
        region_to_all_country_ids=_region_map(),
    )
    assert d["scope_display_lines"]
    assert "countries_count" in d
    assert d["entity_summary"]
