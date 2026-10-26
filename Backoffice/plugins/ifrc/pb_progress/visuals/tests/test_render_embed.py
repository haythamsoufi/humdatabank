"""Tests for chart asset reference helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.render_embed import expected_asset_refs  # noqa: E402


@pytest.mark.unit
def test_expected_asset_refs_includes_line_and_donut_pngs() -> None:
    payload = {
        "type": "sp",
        "cumulative": [
            {"unavailable": False},
            {"unavailable": True},
            {"unavailable": False},
        ],
        "donut_pairs": [
            [{"unavailable": False}, {"unavailable": True}],
        ],
    }

    refs = expected_asset_refs(payload)

    assert refs == {
        "line_0": "line_0.png",
        "line_2": "line_2.png",
        "pair_0_0_donut": "pair_0_0_donut.png",
    }
