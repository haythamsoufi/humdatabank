"""Workbook mapping for the PNS Planning and PNS Reporting Excel forms."""

from __future__ import annotations

import os
import sys

BACKOFFICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PLUGIN_SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
for _path in (BACKOFFICE_DIR, PLUGIN_SCRIPTS):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from openpyxl import load_workbook  # noqa: E402

from pns_form_excel import (  # noqa: E402
    planning_funding_cells,
    read_planning_data_rows,
    read_reporting_funding_rows,
    read_staff_rows,
    reporting_column_map,
    reporting_funding_cells,
    rewrite_planning_year_formula,
    staff_cells,
    workbook_has_planning_structure,
    workbook_has_reporting_structure,
)

PLANNING = os.path.join(
    os.path.dirname(__file__), "..", "static", "templates", "pns_planning_form.xlsx"
)
REPORTING = os.path.join(
    os.path.dirname(__file__), "..", "static", "templates", "pns_reporting_form.xlsx"
)


def test_planning_template_has_funding_tables():
    wb = load_workbook(PLANNING, read_only=False, data_only=False)
    try:
        assert workbook_has_planning_structure(wb)
        formula = wb["Funding Requirement"]["D12"].value
        assert "SP1" in formula
        assert '"2026"' in formula
    finally:
        wb.close()


def test_rewrite_planning_years_shifts_literals_without_collisions():
    formula = 'SUMIFS(PNS_data[Value], PNS_data[Year], "2026") + SUMIFS(PNS_data[Value], PNS_data[Year], "2028")'
    updated = rewrite_planning_year_formula(formula, 2030)
    assert '"2030"' in updated
    assert '"2032"' in updated
    assert '"2026"' not in updated
    assert '"2028"' not in updated


def test_planning_data_rows_become_country_matrix_cells():
    wb = load_workbook(PLANNING, read_only=False, data_only=False)
    try:
        rows = read_planning_data_rows(wb)
    finally:
        wb.close()
    sample = [row for row in rows if row["ns"] == "American Red Cross" and row["country"] == "Bangladesh" and row["year"] == 2026]
    cells, warnings = planning_funding_cells(
        sample,
        ns_name="American Red Cross",
        year=2026,
        country_name_to_id={"bangladesh": 50},
        form_columns=["SP1", "EFs"],
    )
    assert warnings == []
    assert cells["50_EFs"] == 30000
    assert cells["50_SP1"] == 400000
    assert "50_SP2" not in cells


def test_staff_rows_use_host_ns_ids():
    wb = load_workbook(PLANNING, read_only=False, data_only=False)
    try:
        ws = wb["PNS Staff Presence"]
        ws["D2"] = 3
        ws["F2"] = 1
        rows = read_staff_rows(wb)
    finally:
        wb.close()
    cells, warnings = staff_cells(rows, iso3_to_ns_id={"AGO": 80}, form_columns=["intl_delegates_hns", "intl_delegates_ifrc"])
    assert warnings == []
    assert cells["80_intl_delegates_hns"] == 3
    assert cells["80_intl_delegates_ifrc"] == 1


def test_reporting_template_maps_funding_columns():
    wb = load_workbook(REPORTING, read_only=False, data_only=False)
    try:
        assert workbook_has_reporting_structure(wb)
        ws = wb["Funding data"]
        ws["C15"] = "Angola"
        ws["E15"] = 10
        ws["F15"] = 4
        rows = read_reporting_funding_rows(wb)
    finally:
        wb.close()
    column_map = reporting_column_map(["Total Funding", "Total Expenditure", "Total Transferred to HNS"])
    cells, warnings = reporting_funding_cells(
        rows,
        country_name_to_ns_id={"angola": 12},
        column_map=column_map,
    )
    assert warnings == []
    assert cells["12_Total Funding"] == 10
    assert cells["12_Total Expenditure"] == 4
