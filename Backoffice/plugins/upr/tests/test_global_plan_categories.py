"""Unit tests for Global Plan NS category helpers."""

from __future__ import annotations

from plugins.upr.analysis import global_plan_categories as cats


def test_resolve_category_names_matches_catalog(monkeypatch):
    monkeypatch.setattr(
        cats,
        "load_part_of_category_catalog",
        lambda: {"NSIF focus": "checkbox", "ODA": "checkbox", "Bundle": "text"},
    )
    assert "NSIF focus" in cats.nsif_category_names()
    assert "ODA" in cats.oda_category_names()


def test_has_flag_reads_ns_map():
    flags = {"KEN": {"nsif": True, "oda": False}}
    assert cats.has_flag(flags, "ken", "nsif") is True
    assert cats.has_flag(flags, "KEN", "oda") is False
    assert cats.has_flag(flags, "UGA", "nsif") is False
