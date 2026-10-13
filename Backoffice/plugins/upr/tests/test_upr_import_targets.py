"""Tests for precise UPR import targets (template + round -> assigned form)."""

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_plugin_scripts = _HERE.parents[1] / "scripts"
_core_imports = _HERE.parents[3] / "scripts" / "imports"
for _p in (_plugin_scripts, _core_imports):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import import_upr_excel_data as imp  # noqa: E402
import upr_import_targets as tg  # noqa: E402
from upr_import_targets import (  # noqa: E402
    ImportTarget,
    ImportTargetError,
    build_import_plan,
    group_targets,
    normalize_targets,
    targets_from_templates_and_rounds,
    verify_targets,
    workbook_round_stats,
)


def _af(af_id, template_id, period, *, iso3s=(), counts=None, **overrides):
    rec = {
        "id": af_id,
        "template_id": template_id,
        "period_name": period,
        "canonical_period": imp.canonical_upr_period(period),
        "custom_name": None,
        "is_active": True,
        "is_closed": False,
        "aes_total": len(iso3s),
        "status_counts": counts if counts is not None else {"pending": len(iso3s)},
        "iso3s": set(iso3s),
    }
    rec.update(overrides)
    return rec


def _ready(*template_ids):
    return {
        tid: {"template_id": tid, "name": "x", "published_version_id": 1, "items": {}, "missing": [], "ready": True}
        for tid in template_ids
    }


def _stats(round_code, template_id, *, rows, iso3=(), ns_names=()):
    return {round_code: {template_id: {"rows": rows, "iso3": set(iso3), "ns_names": set(ns_names)}}}


def _item(plan, key):
    return next(i for i in plan["targets"] if i["key"] == key)


class TestLegality:
    def test_legal_template_ids_follow_profiles(self):
        assert tg.legal_template_ids_for_round("P26") == (22, 24)
        assert tg.legal_template_ids_for_round("AR25") == (23, 33)
        assert tg.legal_template_ids_for_round("MYR25") == (33,)

    @pytest.mark.parametrize(
        "template_id,round_code",
        [(23, "MYR25"), (24, "AR25"), (33, "P26"), (24, "P27"), (33, "MYR26"), (99, "P26"), (24, "")],
    )
    def test_illegal_pairs_rejected(self, template_id, round_code):
        assert tg.validate_target(template_id, round_code)
        with pytest.raises(ImportTargetError):
            normalize_targets([{"template_id": template_id, "round": round_code}])

    def test_normalize_accepts_strings_dicts_and_dedupes(self):
        targets = normalize_targets(["24:P26", {"template_id": 24, "round": "p26"}, (33, "MYR25")])
        # Planning first, then reports; stable regardless of input order.
        assert [t.key for t in targets] == ["24:P26", "33:MYR25"]

    def test_empty_selection_is_an_error(self):
        with pytest.raises(ImportTargetError):
            normalize_targets([])

    def test_all_errors_reported_together(self):
        with pytest.raises(ImportTargetError) as exc:
            normalize_targets(["23:MYR25", "24:P27"])
        assert len(exc.value.errors) == 2

    def test_legacy_payload_requires_explicit_rounds(self):
        with pytest.raises(ImportTargetError):
            targets_from_templates_and_rounds([24, 22], [])

    def test_legacy_payload_only_expands_legal_pairs(self):
        targets = targets_from_templates_and_rounds([24, 22, 33], ["P26", "AR25"])
        assert {t.key for t in targets} == {"24:P26", "22:P26", "33:AR25"}

    def test_legacy_round_without_matching_template_is_an_error(self):
        with pytest.raises(ImportTargetError):
            targets_from_templates_and_rounds([24, 22], ["AR25"])


class TestGrouping:
    def test_rounds_with_different_template_sets_run_separately(self):
        targets = [ImportTarget(33, "MYR25"), ImportTarget(33, "AR25"), ImportTarget(23, "AR25")]
        groups = group_targets(targets)
        as_tuples = {(g.template_ids, g.rounds) for g in groups}
        assert as_tuples == {((33,), ("MYR25",)), ((23, 33), ("AR25",))}

    def test_same_template_set_shares_one_run(self):
        targets = [ImportTarget(24, "P25"), ImportTarget(22, "P25"), ImportTarget(24, "P26"), ImportTarget(22, "P26")]
        groups = group_targets(targets)
        assert len(groups) == 1
        assert groups[0].template_ids == (22, 24)
        assert groups[0].rounds == ("P25", "P26")

    def test_partial_template_selection_is_not_cross_multiplied(self):
        groups = group_targets([ImportTarget(24, "P26"), ImportTarget(22, "P25")])
        assert {(g.template_ids, g.rounds) for g in groups} == {((24,), ("P26",)), ((22,), ("P25",))}


class TestImportScope:
    def test_rounds_are_required(self):
        with pytest.raises(ValueError, match="rounds are required"):
            imp.assert_import_scope([24], None)
        with pytest.raises(ValueError, match="rounds are required"):
            imp.assert_import_scope([24], set())

    def test_template_23_never_takes_midyear(self):
        with pytest.raises(ValueError, match="Template 23 does not import round MYR25"):
            imp.assert_import_scope([33, 23], {"MYR25"})

    def test_live_round_rejected(self):
        with pytest.raises(ValueError, match="closed UPR Master set"):
            imp.assert_import_scope([33], {"MYR26"})

    def test_valid_scope_passes(self):
        imp.assert_import_scope([33, 23], {"AR25"})
        imp.assert_import_scope([24, 22], {"P25", "P26"})
        imp.assert_import_scope([33], {"MYR25"})

    def test_run_upr_import_refuses_empty_rounds_before_touching_the_db(self):
        with pytest.raises(ValueError, match="rounds are required"):
            imp.run_upr_import("does-not-matter.xlsx", template_ids=[24, 22], rounds=[])
        with pytest.raises(ValueError, match="templates are required"):
            imp.run_upr_import("does-not-matter.xlsx", template_ids=[], rounds=["P26"])


class TestRowFiltering:
    def _rows(self):
        base = {"ISO3": "JOR", "Indicator": "x", "ValueNum": 1}
        return [
            {**base, "Round": "P26", "Section": "Funding"},
            {**base, "Round": "P26", "Section": "Staff"},
            {**base, "Round": "AR25", "Section": "Funding"},
            {**base, "Round": "MYR25", "Section": "Funding"},
            {**base, "Round": "P27", "Section": "Funding"},
        ]

    def test_template_22_alone_keeps_planning_funding_rows(self):
        out = imp._filter_rows(self._rows(), template_ids=[22])
        assert {(r["Round"], r["Section"]) for r in out} == {("P26", "Funding"), ("P26", "Staff")}

    def test_template_23_alone_drops_midyear(self):
        out = imp._filter_rows(self._rows(), template_ids=[23])
        assert {(r["Round"], r["Section"]) for r in out} == {("AR25", "Funding")}

    def test_never_includes_live_rounds(self):
        out = imp._filter_rows(self._rows(), template_ids=[24, 22, 33, 23])
        assert "P27" not in {r["Round"] for r in out}

    def test_t23_reported_set_ignores_midyear_rows(self):
        ctx = imp.UprImportContext(template_ids=[23])
        ctx.ns_home_country_iso3 = {"austrian red cross": "AUT"}
        ctx.assignment_by_template = {23: {("2025", "AUT"): 1, ("Jan-Jun 2025", "AUT"): 2}}
        base = {
            "ISO3": "SYR", "Section": "Funding", "Entity": "PNS", "NS": "Austrian Red Cross",
            "Source": "PNS Data",
        }
        rows = [{**base, "Round": "AR25"}, {**base, "Round": "MYR25"}]
        _t22, t23 = imp._build_pns_reported_yes_sets(rows, ctx, [23])
        assert t23 == {(1, "SYR")}


class TestWorkbookRoundStats:
    def test_country_and_pns_templates_are_counted_separately(self):
        rows = [
            {"Round": "P26", "Section": "NS Data", "ISO3": "JOR", "Entity": "NS", "Source": "Country Data"},
            {"Round": "P26", "Section": "Funding", "ISO3": "JOR", "Entity": "PNS", "NS": "Austrian Red Cross",
             "Source": "PNS Data"},
            {"Round": "P26", "Section": "Funding", "ISO3": "JOR", "Entity": "HNS", "NS": "Country",
             "Source": "Country Data"},
            {"Round": "AR25", "Section": "Funding", "ISO3": "SYR", "Entity": "PNS", "NS": "Austrian Red Cross",
             "Source": "PNS Data"},
            {"Round": "AR25", "Section": "Funding", "ISO3": "SYR", "Entity": "PNS", "NS": "Austrian Red Cross",
             "Source": "Country Data"},
        ]
        stats = workbook_round_stats(rows, {"austrian red cross": "AUT"})
        assert stats["P26"][24]["rows"] == 3 and stats["P26"][24]["iso3"] == {"JOR"}
        assert stats["P26"][22]["rows"] == 1 and stats["P26"][22]["ns_names"] == {"austrian red cross"}
        assert stats["P26"][22]["ns_display"]["austrian red cross"] == "Austrian Red Cross"
        assert stats["AR25"][23]["rows"] == 1  # only Source = PNS Data counts for T23
        assert stats["AR25"][33]["iso3"] == {"SYR"}  # Country Data row keeps the host in scope
        assert 23 not in stats.get("MYR25", {})

    def test_entities_without_country_or_pns_data_are_not_import_targets(self):
        rows = [
            # France the host: partner and IFRC figures only. Not a country-form target.
            {"Round": "AR25", "Section": "Funding", "ISO3": "FRA", "Entity": "PNS",
             "NS": "Spanish Red Cross", "Source": "PNS Data"},
            {"Round": "AR25", "Section": "Funding", "ISO3": "FRA", "Entity": "IFRC Secretariat",
             "NS": "IFRC Secretariat", "Source": "IFRC System"},
            # Host-reported mention of French Red Cross does not make France a PNS submission.
            {"Round": "AR25", "Section": "Funding", "ISO3": "COD", "Entity": "PNS",
             "NS": "French Red Cross", "Source": "Country Data"},
            # French Red Cross on PNS Data does.
            {"Round": "AR25", "Section": "Funding", "ISO3": "COM", "Entity": "PNS",
             "NS": "French Red Cross", "Source": "PNS Data"},
            {"Round": "AR25", "Section": "NS Data", "ISO3": "JOR", "Entity": "HNS", "Source": "Country Data"},
        ]
        stats = workbook_round_stats(rows, {
            "spanish red cross": "ESP",
            "french red cross": "FRA",
        })
        assert "FRA" not in stats["AR25"].get(33, {}).get("iso3", set())
        assert stats["AR25"][33]["iso3"] == {"JOR", "COD"}
        assert stats["AR25"][23]["ns_names"] == {"spanish red cross", "french red cross"}
        # Planning PNS counts a society only on its own PNS Data row, not a host's Country Data mention.
        planning = [
            {"Round": "P26", "Section": "Funding", "ISO3": "COM", "Entity": "PNS",
             "NS": "French Red Cross", "Source": "Country Data"},
            {"Round": "P26", "Section": "Funding", "ISO3": "COM", "Entity": "PNS",
             "NS": "French Red Cross", "Source": "PNS Data"},
        ]
        planning_stats = workbook_round_stats(planning, {"french red cross": "FRA"})
        assert planning_stats["P26"][22]["ns_names"] == {"french red cross"}
        assert planning_stats["P26"][22]["rows"] == 1


class TestBuildImportPlan:
    def _plan(self, **kwargs):
        defaults = dict(
            round_stats=_stats("P26", 24, rows=10, iso3={"JOR", "SYR"}),
            af_index=[_af(1, 24, "2026", iso3s={"JOR", "SYR", "LBN"})],
            readiness=_ready(22, 23, 24, 33),
            ns_home_iso3={},
            workbook_rounds=["P26"],
        )
        defaults.update(kwargs)
        return build_import_plan(**defaults)

    def test_clean_target_is_ready_and_mapped_to_one_form(self):
        item = _item(self._plan(), "24:P26")
        assert item["status"] == "ok"
        assert item["assigned_form_id"] == 1
        assert item["selectable"] is True
        assert item["entities_matched"] == 2 and item["entities_in_workbook"] == 2

    def test_missing_assigned_form_blocks(self):
        item = _item(self._plan(af_index=[]), "24:P26")
        assert item["status"] == "blocked" and not item["selectable"]
        assert any(i["code"] == "no_assigned_form" for i in item["issues"])

    def test_duplicate_assigned_forms_block(self):
        item = _item(
            self._plan(af_index=[_af(1, 24, "2026", iso3s={"JOR"}), _af(2, 24, "2026 Annual", iso3s={"JOR"})]),
            "24:P26",
        )
        assert item["status"] == "blocked"
        assert item["assigned_form_id"] is None
        assert any(i["code"] == "multiple_assigned_forms" for i in item["issues"])

    def test_other_template_or_period_is_never_matched(self):
        item = _item(
            self._plan(af_index=[_af(1, 33, "2026", iso3s={"JOR"}), _af(2, 24, "2025", iso3s={"JOR"})]),
            "24:P26",
        )
        assert item["status"] == "blocked"

    def test_unmatched_entities_warn_but_stay_selectable(self):
        item = _item(self._plan(af_index=[_af(1, 24, "2026", iso3s={"JOR"})]), "24:P26")
        assert item["status"] == "warning" and item["selectable"]
        assert item["entities_unmatched"] == ["SYR"]

    def test_unmatched_entities_are_country_names_and_not_capped(self):
        isos = [f"X{i:02d}" for i in range(30)]
        names = {iso: f"Country {iso}" for iso in isos}
        item = _item(
            self._plan(
                round_stats=_stats("P26", 24, rows=30, iso3=set(isos) | {"JOR"}),
                af_index=[_af(1, 24, "2026", iso3s={"JOR"})],
                country_names=names,
            ),
            "24:P26",
        )
        issue = next(i for i in item["issues"] if i["code"] == "unmatched_entities")
        assert issue["items"] == [f"Country {iso}" for iso in sorted(isos)]
        assert item["entities_unmatched"] == issue["items"]
        assert "form #" not in issue["message"]
        assert "ISO" not in " ".join(issue["items"])

    def test_pns_unmatched_uses_country_name_not_iso_code(self):
        stats = _stats("AR25", 23, rows=2, ns_names={"austrian red cross", "swiss red cross"})
        stats["AR25"][23]["ns_display"] = {
            "austrian red cross": "Austrian Red Cross",
            "swiss red cross": "Swiss Red Cross",
        }
        item = _item(
            self._plan(
                round_stats=stats,
                af_index=[_af(9, 23, "2025", iso3s={"CHE"})],
                ns_home_iso3={"austrian red cross": "AUT", "swiss red cross": "CHE"},
                country_names={"AUT": "Austria", "CHE": "Switzerland"},
                workbook_rounds=["AR25"],
            ),
            "23:AR25",
        )
        assert item["entities_unmatched"] == ["Austrian Red Cross (Austria)"]
        issue = next(i for i in item["issues"] if i["code"] == "unmatched_entities")
        assert issue["message"] == "1 workbook entity has no assignment and will be skipped."

    def test_no_matching_entities_blocks(self):
        item = _item(self._plan(af_index=[_af(1, 24, "2026", iso3s={"LBN"})]), "24:P26")
        assert item["status"] == "blocked"
        assert any(i["code"] == "no_matching_entities" for i in item["issues"])

    def test_existing_progress_warns_about_overwrite(self):
        form = _af(1, 24, "2026", iso3s={"JOR", "SYR"}, counts={"pending": 0, "submitted": 2})
        item = _item(self._plan(af_index=[form]), "24:P26")
        assert item["status"] == "warning"
        issue = next(i for i in item["issues"] if i["code"] == "existing_progress")
        assert "will replace those saved values" in issue["message"]

    def test_round_without_workbook_rows_is_empty_not_selectable(self):
        item = _item(self._plan(round_stats={}), "24:P26")
        assert item["status"] == "empty" and not item["selectable"]

    def test_unresolved_template_items_block(self):
        ready = _ready(22, 23, 24, 33)
        ready[24] = {**ready[24], "missing": ["bilateral_support_matrix"], "ready": False}
        item = _item(self._plan(readiness=ready), "24:P26")
        assert item["status"] == "blocked"
        assert any(i["code"] == "template_not_ready" for i in item["issues"])

    def test_live_and_unknown_rounds_are_listed_not_offered(self):
        plan = self._plan(workbook_rounds=["P26", "P27", "MYR26", "AR26", "XYZ1"])
        keys = {i["key"] for i in plan["targets"]}
        assert not any(k.endswith(("P27", "MYR26", "AR26")) for k in keys)
        assert {r["round"] for r in plan["not_importable_rounds"]} == {"P27", "MYR26", "AR26"}
        assert plan["unrecognised_rounds"] == ["XYZ1"]

    def test_midyear_is_only_offered_for_template_33(self):
        plan = self._plan(
            round_stats=_stats("MYR25", 33, rows=4, iso3={"JOR"}),
            af_index=[_af(5, 33, "Jan-Jun 2025", iso3s={"JOR"})],
            workbook_rounds=["MYR25"],
        )
        assert [i["key"] for i in plan["targets"]] == ["33:MYR25"]
        assert plan["targets"][0]["assigned_form_id"] == 5
        assert plan["targets"][0]["period"] == "Jan-Jun 2025"

    def test_pns_target_matches_by_reporting_ns_home_country(self):
        plan = self._plan(
            round_stats=_stats("AR25", 23, rows=3, ns_names={"austrian red cross", "ghost society"}),
            af_index=[_af(9, 23, "2025", iso3s={"AUT"})],
            ns_home_iso3={"austrian red cross": "AUT"},
            workbook_rounds=["AR25"],
        )
        item = _item(plan, "23:AR25")
        assert item["entities_matched"] == 1
        assert item["status"] == "warning"
        assert "ghost society (no home country)" in item["entities_unmatched"]

    def test_pns_clear_warns_when_data_would_be_cleared(self):
        plan = self._plan(
            round_stats=_stats("AR25", 23, rows=3, ns_names={"austrian red cross"}),
            af_index=[_af(9, 23, "2025", iso3s={"AUT", "FRA"})],
            ns_home_iso3={"austrian red cross": "AUT"},
            workbook_rounds=["AR25"],
            pns_clear={"23:AR25": {"aes_total": 2, "aes_to_clear": 1, "aes_with_data": 1}},
        )
        item = _item(plan, "23:AR25")
        assert item["status"] == "warning"
        assert any(i["code"] == "pns_clear" for i in item["issues"])

    def test_reported_pns_assignments_are_described_as_approved(self):
        plan = self._plan(
            round_stats=_stats("AR25", 23, rows=3, ns_names={"austrian red cross"}),
            af_index=[_af(9, 23, "2025", iso3s={"AUT"})],
            ns_home_iso3={"austrian red cross": "AUT"},
            workbook_rounds=["AR25"],
            pns_clear={"23:AR25": {"aes_total": 1, "aes_to_clear": 0, "aes_with_data": 0, "aes_to_approve": 4}},
        )
        item = _item(plan, "23:AR25")
        issue = next(i for i in item["issues"] if i["code"] == "pns_approve")
        assert "4 PNS assignments" in issue["message"]
        assert "marked approved" in issue["message"]


class TestVerifyTargets:
    def test_blocked_target_is_refused(self):
        plan = build_import_plan(
            round_stats=_stats("P26", 24, rows=5, iso3={"JOR"}),
            af_index=[],
            readiness=_ready(24),
            ns_home_iso3={},
            workbook_rounds=["P26"],
        )
        with pytest.raises(ImportTargetError) as exc:
            verify_targets(plan, [ImportTarget(24, "P26")])
        assert "24:P26" in str(exc.value)

    def test_target_absent_from_workbook_is_refused(self):
        plan = build_import_plan(
            round_stats={},
            af_index=[],
            readiness=_ready(24),
            ns_home_iso3={},
            workbook_rounds=[],
        )
        with pytest.raises(ImportTargetError):
            verify_targets(plan, [ImportTarget(24, "P26")])

    def test_ready_target_resolves_to_plan_item(self):
        plan = build_import_plan(
            round_stats=_stats("P26", 24, rows=5, iso3={"JOR"}),
            af_index=[_af(1, 24, "2026", iso3s={"JOR"})],
            readiness=_ready(24),
            ns_home_iso3={},
            workbook_rounds=["P26"],
        )
        resolved = verify_targets(plan, [ImportTarget(24, "P26")])
        assert resolved["24:P26"]["assigned_form_id"] == 1


class TestTargetAesIds:
    def test_only_selected_round_periods_are_writable(self):
        ctx = imp.UprImportContext(template_ids=[24, 33])
        ctx.assignment_by_template = {
            24: {("2026", "JOR"): 1, ("2025", "JOR"): 2},
            33: {("2025", "JOR"): 3, ("Jan-Jun 2025", "JOR"): 4, ("Jan-Jun 2026", "JOR"): 5},
        }
        assert imp.target_aes_ids(ctx, [24], {"P26"}) == {1}
        assert imp.target_aes_ids(ctx, [33], {"AR25"}) == {3}
        assert imp.target_aes_ids(ctx, [33], {"MYR25"}) == {4}
        # MYR26 is live: never addressable, even though an assignment exists.
        assert imp.target_aes_ids(ctx, [33], {"MYR26"}) == {5}  # raw lookup; scope check blocks it earlier
        with pytest.raises(ValueError):
            imp.assert_import_scope([33], {"MYR26"})
