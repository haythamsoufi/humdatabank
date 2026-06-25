"""Unit tests for UPR Country Reporting Excel template parsing helpers."""

from __future__ import annotations

import os
import sys

import pytest

BACKOFFICE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPTS_DIR = os.path.join(BACKOFFICE_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from upr_country_reporting_excel_template import (  # noqa: E402
    INDICATOR_APPLICABLE_VALUE,
    INDICATOR_DNA_VALUE,
    INDICATOR_ID_HEADER,
    INDICATOR_MATCH_THRESHOLD,
    _build_bank_id_row_locations,
    _build_indicator_row_index,
    _build_kpi_display_map,
    _build_upr_country_reporting_disagg_header_maps,
    _disagg_payload_to_workbook_cells,
    _find_row_for_form_item,
    _find_row_in_indicator_table,
    _merge_non_binary_into_unknown_breakdown,
    _parse_support_matrix_ticks,
    _matrix_cell_is_set,
    _normalize_matrix_cells,
    _export_funding_breakdown,
    _entity_ids_from_matrix_disagg,
    _parse_support_matrix_ns_ids,
    _matrix_cell_scalar,
    _parse_emergency_selection_from_entry,
    _format_emergency_operation_display,
    _upsert_emergency_repeat_choice,
    _workbook_yes_no_value,
    _resolve_indicator_import_value,
    _collect_workbook_indicator_bank_ids,
    _reporting_funding_matrix_column,
    _entry_is_yes_no,
    _is_yes_no_indicator_type,
    _parse_workbook_row_disagg,
    build_kpi_lookup,
    parse_comments,
    parse_funding,
    parse_indicators,
    parse_ns_key_data,
    parse_version,
    period_to_workbook_version,
    _apply_reporting_assignment_label,
    _assignment_display_label,
    _quiet_openpyxl_io,
    ASSIGNMENT_LABEL_NAMED_CELL,
    read_named_cell,
    read_named_table,
    write_table_cell,
    _table_data_row_capacity,
    DATA_OTHER_SHEET,
    DATA_OTHER_TABLE,
)


TEMPLATE_PATH = os.path.join(
    BACKOFFICE_DIR,
    "app",
    "static",
    "templates",
    "upr_country_reporting_template.xlsx",
)


@pytest.fixture(scope="module")
def upr_country_reporting_workbook():
    if not os.path.isfile(TEMPLATE_PATH):
        pytest.skip("UPR Country Reporting template file not present")
    import openpyxl

    wb = openpyxl.load_workbook(TEMPLATE_PATH, data_only=True)
    yield wb
    wb.close()


def test_period_to_workbook_version():
    assert period_to_workbook_version("Jan-Jun 2026") == "MYR26.V1.0"
    assert period_to_workbook_version("2025") == "AR25.V1.0"


def test_parse_version_from_template(upr_country_reporting_workbook):
    round_code, period = parse_version(upr_country_reporting_workbook)
    assert round_code == "MYR26"
    assert period == "Jan-Jun 2026"


def test_build_kpi_lookup_has_entries(upr_country_reporting_workbook):
    lookup = build_kpi_lookup(upr_country_reporting_workbook)
    assert len(lookup) > 100
    sample = next(iter(lookup.values()))
    assert isinstance(sample, int)


def test_read_named_table_data_core(upr_country_reporting_workbook):
    headers, rows = read_named_table(upr_country_reporting_workbook, "Overall action Indicators", "Data_core")
    assert INDICATOR_ID_HEADER in headers
    assert "Indicator" in headers
    assert len(rows) > 5
    assert rows[0].get(INDICATOR_ID_HEADER) is not None


def test_parse_indicators_returns_rows(upr_country_reporting_workbook):
    rows = parse_indicators(upr_country_reporting_workbook)
    assert rows
    assert all("indicator" in row and "sp_ef" in row for row in rows)
    assert all(row.get("bank_id") is not None for row in rows[:5])


def test_find_row_for_form_items_by_bank_id(upr_country_reporting_workbook):
    import openpyxl

    wb = openpyxl.load_workbook(TEMPLATE_PATH, data_only=True)
    bank_locations = _build_bank_id_row_locations(wb)
    core_index = _build_indicator_row_index(wb, tables=(("Overall action Indicators", "Data_core"),))
    kpi = build_kpi_lookup(wb)
    loc = _find_row_for_form_item(
        section_name="Cross Cutting",
        label="Number of people reached with emergency response and early recovery programmes.",
        bank_id=619,
        indicator_row_index=core_index,
        kpi_lookup=kpi,
        bank_id_locations=bank_locations,
    )
    assert loc is not None
    assert loc[1] == "Data_core"
    wb.close()


def test_parse_funding_structure(upr_country_reporting_workbook):
    funding = parse_funding(upr_country_reporting_workbook)
    assert "sources" in funding
    assert "breakdown" in funding
    assert "funding_column" in funding


def test_parse_comments_empty_by_default(upr_country_reporting_workbook):
    assert parse_comments(upr_country_reporting_workbook) == ""


def test_export_import_comments_single_cell():
    import openpyxl

    from upr_country_reporting_excel_template import COMMENTS_NAMED_CELL, write_named_cell

    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    write_named_cell(wb, COMMENTS_NAMED_CELL, "Notes from the NS focal point.")
    assert parse_comments(wb) == "Notes from the NS focal point."
    wb.close()


def test_parse_ns_key_data_reads_named_cells(upr_country_reporting_workbook):
    ns = parse_ns_key_data(upr_country_reporting_workbook)
    assert set(ns.keys()) == {"volunteers", "staff", "local_units", "branches"}


def test_read_named_cell_version(upr_country_reporting_workbook):
    version = read_named_cell(upr_country_reporting_workbook, "Version")
    assert str(version).startswith("MYR")


def test_data_other_table_has_overflow_capacity(upr_country_reporting_workbook):
    capacity = _table_data_row_capacity(upr_country_reporting_workbook, DATA_OTHER_SHEET, DATA_OTHER_TABLE)
    assert capacity >= 4


def test_find_row_for_form_items_in_data_core(upr_country_reporting_workbook):
    """Core T33 indicators should resolve to Data_core rows (not require Data_other)."""
    import openpyxl

    wb = openpyxl.load_workbook(TEMPLATE_PATH, data_only=True)
    kpi = build_kpi_lookup(wb)
    index = _build_indicator_row_index(wb)
    bank_locations = _build_bank_id_row_locations(wb)
    samples = [
        ("Cross Cutting", "Number of people reached with emergency response and early recovery programmes.", 619),
        ("Respect - Values, power and inclusion", "National Society has community engagement and accountability integrated in its strategy or plan with clear goals, designated CEA budget lines, and key performance indicators", 611),
    ]
    for section, label, bank_id in samples:
        loc = _find_row_for_form_item(
            section_name=section,
            label=label,
            bank_id=bank_id,
            indicator_row_index=index,
            kpi_lookup=kpi,
            bank_id_locations=bank_locations,
        )
        assert loc is not None, f"No row for {section!r} bank={bank_id}"
    wb.close()


def test_indicator_match_threshold_allows_truncated_excel_labels():
    assert INDICATOR_MATCH_THRESHOLD <= 0.65


def test_parse_workbook_row_disagg_total_only_uses_total_key():
    row = {"Total Direct": 423.0}
    disagg = _parse_workbook_row_disagg(row)
    assert disagg == {"mode": "total", "values": {"total": 423.0}}


def test_parse_workbook_row_disagg_total_with_indirect_uses_direct_key():
    row = {"Total Direct": 100.0, "Indirectly reached": 25.0}
    disagg = _parse_workbook_row_disagg(row)
    assert disagg == {"mode": "total", "values": {"direct": 100.0, "indirect": 25.0}}


def test_parse_workbook_row_disagg_sex_age(upr_country_reporting_workbook):
    _, rows = read_named_table(upr_country_reporting_workbook, "Overall action Indicators", "Data_core")
    sample = dict(rows[0])
    sample["Male <5"] = 10
    sample["Male 5-17"] = 20
    sample["Female <5"] = 5
    sample["Indirectly reached"] = 3
    disagg = _parse_workbook_row_disagg(sample)
    assert disagg is not None
    assert disagg["mode"] == "sex_age"
    assert disagg["values"]["direct"]["male_5"] == 10
    assert disagg["values"]["direct"]["male_5_17"] == 20
    assert disagg["values"]["direct"]["female_5"] == 5
    assert disagg["values"]["indirect"] == 3


def test_disagg_payload_roundtrip_to_excel_headers(upr_country_reporting_workbook):
    key_to_header, _ = _build_upr_country_reporting_disagg_header_maps(upr_country_reporting_workbook)
    payload = {
        "mode": "total",
        "values": {"direct": 100, "indirect": 25},
    }
    cells = _disagg_payload_to_workbook_cells(payload, key_to_header)
    assert key_to_header["direct"] in cells
    assert cells[key_to_header["direct"]] == 100
    assert key_to_header["indirect"] in cells
    assert cells[key_to_header["indirect"]] == 25
    combined_header = key_to_header.get("combined")
    assert combined_header not in cells


def test_disagg_total_only_writes_total_direct(upr_country_reporting_workbook):
    key_to_header, _ = _build_upr_country_reporting_disagg_header_maps(upr_country_reporting_workbook)
    cells = _disagg_payload_to_workbook_cells({"mode": "total", "values": {"total": 42}}, key_to_header)
    assert cells[key_to_header["direct"]] == 42
    assert key_to_header.get("combined") not in cells


def test_disagg_by_sex_sums_total_direct(upr_country_reporting_workbook):
    key_to_header, _ = _build_upr_country_reporting_disagg_header_maps(upr_country_reporting_workbook)
    cells = _disagg_payload_to_workbook_cells(
        {"mode": "sex", "values": {"male": 345, "female": 534, "unknown": 555}},
        key_to_header,
    )
    assert cells[key_to_header["direct"]] == 1434
    assert cells[key_to_header["male"]] == 345
    assert cells[key_to_header["female"]] == 534
    assert cells[key_to_header["unknown"]] == 555


def test_disagg_by_sex_merges_non_binary_into_unknown(upr_country_reporting_workbook):
    key_to_header, _ = _build_upr_country_reporting_disagg_header_maps(upr_country_reporting_workbook)
    cells = _disagg_payload_to_workbook_cells(
        {
            "mode": "sex",
            "values": {"male": 345, "female": 534, "non_binary": 12, "unknown": 555},
        },
        key_to_header,
    )
    assert cells[key_to_header["unknown"]] == 567
    assert cells[key_to_header["male"]] == 345
    assert cells[key_to_header["female"]] == 534
    assert cells[key_to_header["direct"]] == 1446


def test_merge_non_binary_into_unknown_breakdown():
    merged = _merge_non_binary_into_unknown_breakdown(
        {"male": 1, "non_binary": 2, "unknown": 3, "non_binary_5_17": 4}
    )
    assert merged["male"] == 1
    assert merged["unknown"] == 9


def test_disagg_by_sex_age_sums_total_direct(upr_country_reporting_workbook):
    key_to_header, _ = _build_upr_country_reporting_disagg_header_maps(upr_country_reporting_workbook)
    cells = _disagg_payload_to_workbook_cells(
        {
            "mode": "sex_age",
            "values": {"direct": {"male_5": 10, "female_5": 5, "male_5_17": 20}, "indirect": 3},
        },
        key_to_header,
    )
    assert cells[key_to_header["direct"]] == 35
    assert cells[key_to_header["indirect"]] == 3


def test_applicable_status_constants():
    assert INDICATOR_APPLICABLE_VALUE == "Applicable"
    assert INDICATOR_DNA_VALUE == "Data not available"


def test_emergency_row_lookup_scoped_to_target_table(upr_country_reporting_workbook):
    kpi_lookup = build_kpi_lookup(upr_country_reporting_workbook)
    bank_id_locations = _build_bank_id_row_locations(upr_country_reporting_workbook)
    indicator_row_index = _build_indicator_row_index(upr_country_reporting_workbook)

    # Bank 754 exists in both Data_core and emergency tables — lookup must stay on EA1.
    loc = _find_row_in_indicator_table(
        sheet_name="Emergency Appeal 1",
        table_name="Data_emergency1",
        bank_id=754,
        bank_id_locations=bank_id_locations,
        indicator_row_index=indicator_row_index,
        kpi_lookup=kpi_lookup,
    )
    assert loc is not None
    assert loc[0] == "Emergency Appeal 1"
    assert loc[1] == "Data_emergency1"

    # Bank 611 is not in the emergency template — must not fall back to Data_core.
    loc_other = _find_row_in_indicator_table(
        sheet_name="Emergency Appeal 2",
        table_name="Data_emergency2",
        bank_id=611,
        bank_id_locations=bank_id_locations,
        indicator_row_index=indicator_row_index,
        kpi_lookup=kpi_lookup,
    )
    assert loc_other is None


def test_kpi_display_map_has_labels(upr_country_reporting_workbook):
    display = _build_kpi_display_map(upr_country_reporting_workbook)
    kpi_lookup = build_kpi_lookup(upr_country_reporting_workbook)
    bank_id = next(iter(kpi_lookup.values()))
    assert bank_id in display
    sp_ef, indicator = display[bank_id]
    assert sp_ef
    assert indicator


def test_parse_emergency_selection_from_entry_disagg():
    entry = type("Entry", (), {"disagg_data": {"name": "Afghanistan - Earthquake", "code": "MDRAF019"}, "value": None})()
    meta = _parse_emergency_selection_from_entry(entry)
    assert meta == {
        "code": "MDRAF019",
        "name": "Afghanistan - Earthquake",
        "label": "Afghanistan - Earthquake (MDRAF019)",
    }


def test_parse_emergency_selection_from_entry_display_value():
    entry = type("Entry", (), {"disagg_data": None, "value": "Appeal Name (MDR001)"})()
    meta = _parse_emergency_selection_from_entry(entry)
    assert meta["code"] == "MDR001"
    assert meta["name"] == "Appeal Name"


def test_format_emergency_operation_display():
    assert _format_emergency_operation_display("Afghanistan - Earthquake", "MDRAF019") == (
        "Afghanistan - Earthquake (MDRAF019)"
    )
    assert _format_emergency_operation_display("Appeal", "") == "Appeal"
    assert _format_emergency_operation_display("", "MDR001") == "MDR001"


def test_upsert_emergency_repeat_choice(app):
    from unittest.mock import MagicMock, patch

    inst = MagicMock()
    inst.id = 501

    with app.app_context():
        with patch("app.models.forms.RepeatGroupData") as mock_rgd_cls, patch(
            "app.extensions.db.session.add"
        ):
            mock_entry = MagicMock()
            mock_rgd_cls.query.filter_by.return_value.first.return_value = None
            mock_rgd_cls.return_value = mock_entry

            _upsert_emergency_repeat_choice(
                repeat_instance=inst,
                choice_item_id=1374,
                appeal_name="Afghanistan - Earthquake",
                mdr_code="MDRAF019",
            )

            mock_rgd_cls.assert_called_once_with(repeat_instance_id=501, form_item_id=1374)
            assert mock_entry.value == "Afghanistan - Earthquake (MDRAF019)"
            assert mock_entry.disagg_type == "emergency_operation"
            assert mock_entry.disagg_data == {"name": "Afghanistan - Earthquake", "code": "MDRAF019"}


def test_yes_no_indicator_detected_from_bank():
    entry = type(
        "Entry",
        (),
        {"value": "yes", "indicator_bank": type("Bank", (), {"type": "YesNo"})()},
    )()
    assert _entry_is_yes_no(entry)


def test_is_yes_no_indicator_type():
    assert _is_yes_no_indicator_type("YesNo")
    assert _is_yes_no_indicator_type("yes/no")
    assert not _is_yes_no_indicator_type("Number")


def test_parse_support_matrix_ticks_scalar_and_nested():
    cells = {
        "166_EFs Supported": 1,
        "42_SP1 Supported": {"original": 0, "modified": 1, "isModified": True},
        "99_SP2 Supported": {"original": 0, "modified": 0},
        "not_a_key": 1,
    }
    ticks = _parse_support_matrix_ticks(cells)
    assert ticks == {166: {"EFs": True}, 42: {"SP1": True}}


def test_matrix_cell_is_set():
    assert _matrix_cell_is_set(1)
    assert _matrix_cell_is_set("X")
    assert not _matrix_cell_is_set(0)
    assert not _matrix_cell_is_set({"original": 0, "modified": 0})
    assert _matrix_cell_is_set({"original": 0, "modified": 1})


def test_normalize_matrix_cells():
    raw = {"a": {"original": 0, "modified": 1}, "b": 2}
    assert _normalize_matrix_cells(raw) == {"a": 1, "b": 2}


def test_bilateral_row_index_reads_column_c(upr_country_reporting_workbook):
    from upr_country_reporting_excel_template import _bilateral_ns_name_for_row

    name = _bilateral_ns_name_for_row(upr_country_reporting_workbook, "Bilateral Support", "Data_act", 1)
    assert name


def test_entity_ids_from_matrix_disagg_with_tick_filter():
    disagg = {"166_SP1": 1, "166_SP2": 0, "42_SP1": 1, "42_SP3": 1, "_table": "national_society"}
    assert _entity_ids_from_matrix_disagg(disagg, tick_column_names=["SP1"], require_tick=True) == {166, 42}
    assert _entity_ids_from_matrix_disagg(disagg, require_tick=False) == {166, 42}


def test_export_bilateral_support_splits_planned_and_manual():
    import openpyxl
    from unittest.mock import patch
    from upr_country_reporting_excel_template import (
        BILATERAL_MANUAL_TABLE,
        BILATERAL_PLANNED_TABLE,
        _export_bilateral_support,
        _bilateral_ns_name_for_row,
        read_table_cell,
    )

    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    ctx = type("Ctx", (), {"ns_name_to_id": {"swiss red cross": 166, "norwegian red cross": 42}})()
    support_cells = {
        "166_EFs Supported": 1,
        "99_SP1 Supported": 1,
    }
    id_to_name = {166: "Swiss Red Cross", 99: "Manual NS Example"}

    with patch("upr_country_reporting_excel_template._resolve_autoloaded_bilateral_ns_ids", return_value={166}), patch(
        "app.models.organization.NationalSociety"
    ) as mock_ns:
        mock_ns.query.filter.return_value.all.return_value = [
            type("NS", (), {"id": 166, "name": "Swiss Red Cross"})(),
            type("NS", (), {"id": 99, "name": "Manual NS Example"})(),
        ]
        _export_bilateral_support(wb, ctx, support_cells, aes=type("AES", (), {})())

    planned_sheet, planned_table = BILATERAL_PLANNED_TABLE
    manual_sheet, manual_table = BILATERAL_MANUAL_TABLE
    assert _bilateral_ns_name_for_row(wb, planned_sheet, planned_table, 0) == "Swiss Red Cross"
    assert read_table_cell(wb, planned_sheet, planned_table, 0, "EFs_Supported") == "X"
    assert _bilateral_ns_name_for_row(wb, manual_sheet, manual_table, 0) == "Manual NS Example"
    assert read_table_cell(wb, manual_sheet, manual_table, 0, "SP1_Supported") == "X"
    wb.close()


def test_export_funding_breakdown_writes_excel_columns():
    import openpyxl

    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    cells = {
        "Resilience - Climate and environment_Funding (CHF)": 1000,
        "Resilience - Climate and environment_Expenditure (CHF)": 800,
        "Response - Disasters and crises_Funding (CHF)": {"original": 0, "modified": 500},
    }
    _export_funding_breakdown(wb, cells)
    _, rows = read_named_table(wb, "Funding", "Data_funding2")
    sp1 = next(r for r in rows if r.get("Attribute") == "SP1")
    sp2 = next(r for r in rows if r.get("Attribute") == "SP2")
    assert sp1["Funding"] == 1000
    assert sp1["Expenditure"] == 800
    assert sp2["Funding"] == 500
    wb.close()


def test_parse_funding_breakdown_reads_funding_column():
    import openpyxl

    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    write_table_cell(wb, "Funding", "Data_funding2", 1, "Funding", 12345)
    write_table_cell(wb, "Funding", "Data_funding2", 1, "Expenditure", 6789)
    parsed = parse_funding(wb)
    row = parsed["breakdown"]["Resilience - Climate and environment"]
    assert row["Funding (CHF)"] == 12345
    assert row["Expenditure (CHF)"] == 6789
    wb.close()


def test_assignment_display_label_prefers_custom_name():
    template = type("Template", (), {"name": "Reporting – Country"})()
    assigned_form = type(
        "AssignedForm",
        (),
        {"custom_name": "Afghanistan MYR 2026", "period_name": "Jan-Jun 2026", "template": template},
    )()
    assigned_form.display_name = "Afghanistan MYR 2026"
    aes = type("AES", (), {"assigned_form": assigned_form})()
    assert _assignment_display_label(aes) == "Afghanistan MYR 2026"


def test_assignment_display_label_falls_back_to_template_and_period():
    tpl = type("Template", (), {"name": "Reporting – Country"})()

    class FakeAssignedForm:
        custom_name = None
        period_name = "Jan-Jun 2026"
        template = tpl

        @property
        def display_name(self):
            return f"{self.template.name} – {self.period_name}"

    aes = type("AES", (), {"assigned_form": FakeAssignedForm()})()
    assert _assignment_display_label(aes) == "Reporting – Country – Jan-Jun 2026"


def test_apply_reporting_assignment_label_updates_start_and_headers(upr_country_reporting_workbook):
    import openpyxl

    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    _apply_reporting_assignment_label(wb, "Custom Assignment Label")
    assert read_named_cell(wb, ASSIGNMENT_LABEL_NAMED_CELL) == "Custom Assignment Label"
    assert wb["Start"]["C2"].value == "Custom Assignment Label - Start here"
    assert wb["Start"]["C2"].font.size == 22.0
    assert "Data_AssignmentLabel" in str(wb["Funding"]["B1"].value)
    assert "Midyear Reporting" not in str(wb["Funding"]["B1"].value)
    wb.close()


def test_workbook_yes_no_value_mapping():
    assert _workbook_yes_no_value("Applicable") == "yes"
    assert _workbook_yes_no_value(" applicable ") == "yes"
    assert _workbook_yes_no_value("Data not available") == "no"
    assert _workbook_yes_no_value("") == "no"


def test_collect_workbook_indicator_bank_ids_includes_table_id_column(
    upr_country_reporting_workbook,
):
    kpi = build_kpi_lookup(upr_country_reporting_workbook)
    table_ids = _collect_workbook_indicator_bank_ids(upr_country_reporting_workbook, kpi)
    assert table_ids - set(kpi.values()), "fixture should include table IDs outside Final KPI list"


def test_parse_indicators_yes_no_applicable_not_skipped(upr_country_reporting_workbook):
    """Applicable-only rows must not be dropped when the bank id is known Yes/No."""
    kpi = build_kpi_lookup(upr_country_reporting_workbook)
    baseline = parse_indicators(upr_country_reporting_workbook, yes_no_bank_ids=set(), kpi_lookup=kpi)
    sample = next(r for r in baseline if r.get("bank_id"))
    bank_id = int(sample["bank_id"])
    rows = parse_indicators(
        upr_country_reporting_workbook,
        yes_no_bank_ids={bank_id},
        kpi_lookup=kpi,
    )
    target = next(r for r in rows if int(r["bank_id"]) == bank_id)
    assert target["value"] in ("yes", "no")


def test_parse_indicators_skips_applicable_only_for_numeric_banks(upr_country_reporting_workbook):
    kpi = build_kpi_lookup(upr_country_reporting_workbook)
    rows = parse_indicators(
        upr_country_reporting_workbook,
        yes_no_bank_ids=set(),
        kpi_lookup=kpi,
    )
    applicable_only = [
        r
        for r in rows
        if "applicable" in str(r.get("applicable_text") or "")
        and r.get("value") is None
        and r.get("disagg") is None
        and not r.get("data_not_available")
    ]
    assert not applicable_only


def test_resolve_indicator_import_value_yes_no():
    yes_row = {
        "data_not_available": False,
        "applicable_text": "applicable",
        "value": None,
        "disagg": None,
    }
    value, is_dna, disagg, should_import = _resolve_indicator_import_value(yes_row, 999, {999})
    assert value == "yes"
    assert not is_dna
    assert disagg is None
    assert should_import

    no_row = {
        "data_not_available": False,
        "applicable_text": "",
        "value": None,
        "disagg": None,
    }
    value, is_dna, disagg, should_import = _resolve_indicator_import_value(no_row, 999, {999})
    assert value == "no"
    assert should_import

    dna_row = {
        "data_not_available": True,
        "applicable_text": "data not available",
        "value": None,
        "disagg": None,
    }
    value, is_dna, disagg, should_import = _resolve_indicator_import_value(dna_row, 999, {999})
    assert value == "no"
    assert not is_dna
    assert should_import

    numeric_row = {
        "data_not_available": False,
        "applicable_text": "applicable",
        "value": None,
        "disagg": None,
    }
    value, _, _, should_import = _resolve_indicator_import_value(numeric_row, 123, {999})
    assert value is None
    assert not should_import


def test_reporting_funding_matrix_column_matches_form_item(app):
    with app.app_context():
        assert _reporting_funding_matrix_column() == "tot_fn"


def test_quiet_openpyxl_io_suppresses_pil_debug(capsys):
    import logging

    pil_logger = logging.getLogger("PIL.PngImagePlugin")
    previous = pil_logger.level
    pil_logger.setLevel(logging.DEBUG)
    try:
        with _quiet_openpyxl_io():
            pil_logger.debug("STREAM b'IHDR' 16 13")
        captured = capsys.readouterr()
        assert "IHDR" not in captured.out
        assert "IHDR" not in captured.err
    finally:
        pil_logger.setLevel(previous)
