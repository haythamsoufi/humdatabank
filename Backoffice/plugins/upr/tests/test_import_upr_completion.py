"""UPR Excel import recomputes completion for every assignment in scope."""

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_plugin_scripts = _HERE.parents[1] / "scripts"
if str(_plugin_scripts) not in sys.path:
    sys.path.insert(0, str(_plugin_scripts))

import import_upr_excel_data as imp  # noqa: E402


def _patch_writers(monkeypatch, ctx, refreshed):
    monkeypatch.setattr(imp, "prepare_upr_transform", lambda *_a, **_k: ([], ctx, False))
    monkeypatch.setattr(
        "app.utils.stable_key.published_form_item_id_set_for_templates",
        lambda _tids: set(),
    )
    monkeypatch.setattr(imp, "sync_non_reported_pns_assignments", lambda *_a, **_k: {})
    monkeypatch.setattr(
        imp,
        "_refresh_completion_for_aes_ids",
        lambda ids: refreshed.append(set(ids)) or len(ids),
    )


@pytest.mark.unit
class TestUprImportCompletion:
    def test_refreshes_country_and_pns_assignments_in_scope(self, monkeypatch):
        ctx = imp.UprImportContext(template_ids=[24, 22])
        ctx.assignment_by_template = {
            24: {("2026", "BFA"): 101, ("2025", "BFA"): 999},
            22: {("2026", "GBR"): 202, ("2026", "FRA"): 203},
        }
        refreshed = []
        _patch_writers(monkeypatch, ctx, refreshed)

        stats = imp.run_upr_import(
            "unused.xlsx",
            template_ids=[24, 22],
            rounds=["P26"],
        )

        assert refreshed == [{101, 202, 203}]
        assert stats["completion_refreshed"] == 3

    def test_refreshes_country_reporting_without_pns_templates(self, monkeypatch):
        ctx = imp.UprImportContext(template_ids=[33])
        ctx.assignment_by_template = {33: {("2025", "KEN"): 401}}
        refreshed = []
        pns_sync_calls = []
        _patch_writers(monkeypatch, ctx, refreshed)
        monkeypatch.setattr(
            imp,
            "sync_non_reported_pns_assignments",
            lambda *_a, **_k: pns_sync_calls.append(True) or {},
        )

        stats = imp.run_upr_import(
            "unused.xlsx",
            template_ids=[33],
            rounds=["AR25"],
        )

        assert refreshed == [{401}]
        assert stats["completion_refreshed"] == 1
        assert pns_sync_calls == []

    def test_dry_run_does_not_recalculate(self, monkeypatch):
        ctx = imp.UprImportContext(template_ids=[24, 22])
        ctx.assignment_by_template = {
            24: {("2026", "BFA"): 101},
            22: {("2026", "GBR"): 202},
        }
        refreshed = []
        _patch_writers(monkeypatch, ctx, refreshed)

        stats = imp.run_upr_import(
            "unused.xlsx",
            template_ids=[24, 22],
            rounds=["P26"],
            dry_run=True,
        )

        assert refreshed == []
        assert stats["completion_refreshed"] == 0
