"""Unit tests for Unified Country Plan Excel template helpers."""

from __future__ import annotations

import os
import sys

import pytest

BACKOFFICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
IMPORTS_DIR = os.path.join(BACKOFFICE_DIR, "scripts", "imports")
if IMPORTS_DIR not in sys.path:
    sys.path.insert(0, IMPORTS_DIR)

from unified_country_plan_excel_template import (  # noqa: E402
    _cell_is_tick,
    _parse_funding_row_entity,
    _parse_emergency_row_id,
    _quiet_openpyxl_io,
    funding_column_header,
    parse_funding_column_header,
    parse_version,
    period_to_workbook_version,
    planning_year_triplet,
    read_named_table,
    rewrite_planning_year_headers,
    validate_unified_country_plan_import_file,
)

TEMPLATE_PATH = os.path.join(
    BACKOFFICE_DIR,
    "app",
    "static",
    "templates",
    "unified_country_plan.xlsx",
)


@pytest.fixture(scope="module")
def ucp_workbook():
    if not os.path.isfile(TEMPLATE_PATH):
        pytest.skip("Unified Country Plan template file not present")
    import openpyxl

    wb = openpyxl.load_workbook(TEMPLATE_PATH, data_only=True)
    yield wb
    wb.close()


def test_period_to_workbook_version():
    assert period_to_workbook_version("2027") == "P27.V1.0"
    assert period_to_workbook_version("2030") == "P30.V1.0"


def test_planning_year_triplet():
    assert planning_year_triplet("2027") == (2027, 2028, 2029)


def test_funding_header_round_trip():
    assert funding_column_header("SP1", 2028) == "SP1_2028"
    assert parse_funding_column_header("EA2_2027") == ("EA2", 2027)
    assert parse_funding_column_header("NS") is None


def test_parse_funding_row_entity():
    assert _parse_funding_row_entity("IFRC Secretariat") == ("ifrc", "IFRC Secretariat")
    assert _parse_funding_row_entity("Host National Society\nCameroon Red Cross") == ("hns", "HNS")
    assert _parse_funding_row_entity("Netherlands Red Cross") == ("pns", "Netherlands Red Cross")


def test_parse_emergency_row_id():
    assert _parse_emergency_row_id("Flood response (MDR123)") == ("Flood response", "MDR123")
    assert _parse_emergency_row_id("Appeal only") == ("Appeal only", "")


def test_cell_is_tick():
    assert _cell_is_tick(1)
    assert _cell_is_tick("1")
    assert _cell_is_tick("x")
    assert not _cell_is_tick(0)
    assert not _cell_is_tick(None)


def test_validate_template_structure(ucp_workbook):
    result = validate_unified_country_plan_import_file(
        ucp_workbook,
        expected_country="",
        expected_period="",
    )
    assert result["valid"] is True
    assert result["preview"]["round_code"] == "P27"


def test_rewrite_planning_year_headers(ucp_workbook):
    import openpyxl
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        path = tmp.name
    try:
        with _quiet_openpyxl_io():
            wb = openpyxl.load_workbook(TEMPLATE_PATH)
        rewrite_planning_year_headers(wb, "2029")
        with _quiet_openpyxl_io():
            wb.save(path)
        wb.close()

        wb2 = openpyxl.load_workbook(path, data_only=True)
        _, people_rows = read_named_table(wb2, "People to be reached", "Data_People")
        years = [row.get("Year") for row in people_rows]
        assert years[:3] == [2029, 2030, 2031]
        headers, _ = read_named_table(wb2, "Funding requirements", "Data_FR")
        funding_years = sorted(
            {parse_funding_column_header(h)[1] for h in headers if parse_funding_column_header(h)}
        )
        assert funding_years == [2029, 2030, 2031]
        wb2.close()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def test_parse_version(ucp_workbook):
    round_code, period = parse_version(ucp_workbook)
    assert round_code == "P27"
    assert period == "2027"
