"""Tests for payload building when Mapping has rows without Final data."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.layouts import SECTION_COLUMN  # noqa: E402
from pb_figures.payload import build_ef_payload  # noqa: E402


@pytest.mark.unit
def test_ef_payload_uses_full_mapping_without_final_rows():
    mapping = pd.DataFrame(
        [
            {
                SECTION_COLUMN: "EF2",
                "ID": "642",
                "Type": "Cumulative",
                "Unit": None,
                "English": "EF2 test indicator",
                "_mapping_order": 0,
            }
        ]
    )
    model = pd.DataFrame(columns=["section", "ID", "Value", "Year", "Source"])

    payload = build_ef_payload(model, "EF2", "English", mapping=mapping)

    assert payload["section"] == "EF2"
    assert len(payload["cumulative"]) == 1
    assert payload["cumulative"][0]["unavailable"] is True
