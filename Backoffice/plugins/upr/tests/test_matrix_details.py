"""Matrix cells expand into labeled validation lines (no database)."""

from plugins.upr.ai.matrix_details import build_matrix_line_verdicts, upr_matrix_detail_lines


def test_funding_matrix_lists_each_cell_and_skips_headers():
    lines = upr_matrix_detail_lines(
        disagg_data={
            "HNS_SP1": 2200000,
            "IFRC Secretariat_EA1": 12000000,
            "col_header|EA1": "MDRAF018 Afghanistan - Population mvt from Pakistan",
            "49_SP2": 350000,
        },
        template_id=24,
        item_label="Funding Requirements for 2026",
        section_name="Funding requirements (CHF)",
        row_labels={"49": "Danish Red Cross"},
    )
    by_key = {line["key"]: line for line in lines}
    assert "col_header|EA1" not in by_key
    assert by_key["HNS_SP1"]["label"] == "Host National Society — Climate and environment"
    assert by_key["HNS_SP1"]["value"] == 2200000
    assert by_key["HNS_SP1"]["unit"] == "chf"
    assert by_key["IFRC Secretariat_EA1"]["column_label"] == "MDRAF018 Afghanistan - Population mvt from Pakistan"
    assert by_key["49_SP2"]["row_label"] == "Danish Red Cross"
    assert by_key["49_SP2"]["column_label"] == "Disasters and crises"


def test_people_and_bilateral_and_emergency_lines():
    people = upr_matrix_detail_lines(
        disagg_data={"2026_SP1": 600000, "2026_SP3": 2800000},
        template_id=24,
        item_label="Longer term programmes",
        section_name="People to be reached",
    )
    assert people[0]["row_label"] == "2026"
    assert people[0]["column_label"] == "Climate and environment"
    assert people[0]["unit"] == "people"
    assert people[0]["value"] == 600000

    bilateral = upr_matrix_detail_lines(
        disagg_data={"49_SP1": 1, "49_EFs": 1},
        template_id=24,
        item_label="List National Societies supporting bilaterally",
        row_labels={"49": "Danish Red Cross"},
    )
    assert bilateral[0]["value_display"] == "Yes"
    assert bilateral[0]["value_is_text"] is True
    assert bilateral[0]["unit"] == "tick"
    assert "Enabling Functions" in bilateral[1]["label"]

    emergency = upr_matrix_detail_lines(
        disagg_data={
            "MDRAF018 Afghanistan - Population mvt from Pakistan_Total People to be reached": 875000,
        },
        template_id=24,
        item_label="Emergency Appeals in 2026",
    )
    assert emergency[0]["value"] == 875000
    assert emergency[0]["unit"] == "people"
    assert emergency[0]["row_label"].startswith("MDRAF018")
    assert emergency[0]["column_label"] == "Total People to be reached"


def test_line_verdicts_flag_tiny_people_targets_and_keep_ticks_out_of_chf():
    people = upr_matrix_detail_lines(
        disagg_data={"2026_SP1": 5},
        template_id=24,
        item_label="Longer term programmes",
    )
    verdicts = build_matrix_line_verdicts(people, parent_verdict="good", parent_opinion="Looks filled in.")
    assert verdicts[0]["verdict"] == "discrepancy"
    assert "too small" in verdicts[0]["opinion"]

    ticks = upr_matrix_detail_lines(
        disagg_data={"49_SP1": 1},
        template_id=24,
        item_label="List National Societies supporting bilaterally",
        row_labels={"49": "Danish Red Cross"},
    )
    tick_verdicts = build_matrix_line_verdicts(
        ticks,
        parent_verdict="discrepancy",
        parent_opinion="Treated the ticks as CHF.",
    )
    assert tick_verdicts[0]["verdict"] == "uncertain"
    assert "support tick" in tick_verdicts[0]["opinion"]

    funding = upr_matrix_detail_lines(
        disagg_data={"HNS_SP1": 2200000},
        template_id=24,
        item_label="Funding Requirements for 2026",
    )
    accepted = build_matrix_line_verdicts(funding, parent_verdict="good", parent_confidence=0.8)
    assert accepted[0]["verdict"] == "good"
    assert "2,200,000 CHF" in accepted[0]["opinion"]
