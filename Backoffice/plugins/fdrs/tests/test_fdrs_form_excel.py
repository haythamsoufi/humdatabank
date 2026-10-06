"""Workbook mapping for the FDRS data-collection Excel form."""

from __future__ import annotations

import os

from openpyxl import load_workbook

from plugins.fdrs.excel.fdrs_form_excel import (
    INCOME_ROW_LABELS,
    read_fdrs_workbook,
    workbook_has_fdrs_structure,
    write_fdrs_answers,
    write_fdrs_identity,
)

TEMPLATE = os.path.join(
    os.path.dirname(__file__), "..", "static", "templates", "fdrs_form.xlsx"
)


def _workbook():
    return load_workbook(TEMPLATE, read_only=False, data_only=False)


def test_template_is_the_fdrs_collection_form():
    wb = _workbook()
    try:
        assert workbook_has_fdrs_structure(wb)
        assert wb["Indicator Data"]["E10"].value == 2025
    finally:
        wb.close()


def test_scalar_and_sex_age_round_trip():
    wb = _workbook()
    try:
        write_fdrs_identity(wb, ns_name="Kenya Red Cross Society", year=2024)
        write_fdrs_answers(
            wb,
            {
                "scalars": {"KPI_noBranches": 12, "KPI_noLocalUnits": 40},
                "disagg": {
                    "KPI_GB": {
                        "mode": "sex_age",
                        "values": {"direct": {"male_5_17": 5, "female_18_49": 2}, "indirect": None},
                    }
                },
                "income": {"Home Government": 1000, "Individuals": 25},
            },
        )
        parsed = read_fdrs_workbook(wb)
    finally:
        wb.close()

    assert parsed["scalars"]["KPI_noBranches"] == 12
    assert parsed["scalars"]["KPI_noLocalUnits"] == 40
    direct = parsed["disagg"]["KPI_GB"]["values"]["direct"]
    assert direct["male_5_17"] == 5
    assert direct["female_18_49"] == 2
    assert parsed["income"]["Home Government"] == 1000
    assert parsed["income"]["Individuals"] == 25
    assert "Home Government" in INCOME_ROW_LABELS
