"""UPR emergency coverage: missing, not applicable, and no longer applicable."""

from types import SimpleNamespace

from plugins.upr.validation.emergency_coverage import (
    RULE_MISSING,
    RULE_NOT_APPLICABLE,
    RULE_NO_LONGER_APPLICABLE,
    EmergencyRef,
    FieldEmergencyCoverage,
    _ref_from_label,
    checks_from_fields,
    classify_emergency_coverage,
    selected_matrix_header_labels,
    selected_matrix_row_labels,
    _COVERAGE_BATCH,
    load_field_coverages,
    tracker_status,
)


def _ref(code, label=None):
    return EmergencyRef(code=code, label=label or code)


UG_APPLICABLE = (
    _ref("MDRUG052", "MDRUG052 Uganda - Mpox Epidemic"),
    _ref("MDRUG051", "MDRUG051 Uganda - Population Movement"),
    _ref("MDRUG058", "MDRUG058 Uganda - Ebola Virus Disease Outbreak"),
)


def test_uganda_report_missed_country_emergencies_and_saved_a_regional_appeal():
    """Assignment 1608 shape: three Uganda appeals apply, and the saved row is the regional parent."""
    coverage = classify_emergency_coverage(
        UG_APPLICABLE,
        [_ref("MDRS1001", "Sudan Crisis: Cross-Regional Population Movement (MDRS1001)")],
        {"MDRUG052", "MDRUG051", "MDRUG058"},
    )

    assert [op.code for op in coverage.missing] == ["MDRUG052", "MDRUG051", "MDRUG058"]
    assert [op.code for op in coverage.not_applicable] == ["MDRS1001"]
    assert coverage.no_longer_applicable == ()


def test_country_operation_outside_the_current_filters_is_no_longer_applicable():
    coverage = classify_emergency_coverage(
        UG_APPLICABLE,
        [_ref("MDRUG040", "MDRUG040 Uganda - Older Appeal")],
        {"MDRUG052", "MDRUG051", "MDRUG058", "MDRUG040"},
    )

    assert coverage.missing and not coverage.not_applicable
    assert [op.code for op in coverage.no_longer_applicable] == ["MDRUG040"]


def test_selecting_every_applicable_emergency_is_clear():
    coverage = classify_emergency_coverage(
        UG_APPLICABLE,
        list(UG_APPLICABLE),
        {"MDRUG052", "MDRUG051", "MDRUG058"},
    )

    assert not coverage.has_issues


def test_warnings_name_the_gaps_and_do_not_read_as_a_block():
    field = FieldEmergencyCoverage(
        section_name="Emergency Appeals Indicators",
        coverage=classify_emergency_coverage(
            UG_APPLICABLE,
            [_ref("MDRS1001", "Sudan Crisis (MDRS1001)")],
            {"MDRUG052", "MDRUG051", "MDRUG058"},
        ),
    )

    messages = checks_from_fields([field])
    by_code = {row["rule_code"]: row["message"] for row in messages}

    assert RULE_MISSING in by_code
    assert RULE_NOT_APPLICABLE in by_code
    assert RULE_NO_LONGER_APPLICABLE not in by_code
    assert "does not block submission" in by_code[RULE_MISSING]
    assert "MDRUG052" in by_code[RULE_MISSING]
    assert "MDRS1001" in by_code[RULE_NOT_APPLICABLE]


def test_tracker_marks_a_country_that_has_both_gaps():
    field = FieldEmergencyCoverage(
        section_name="Emergency Appeals Indicators",
        coverage=classify_emergency_coverage(
            UG_APPLICABLE,
            [_ref("MDRS1001", "Sudan Crisis (MDRS1001)")],
            {"MDRUG052"},
        ),
    )

    status = tracker_status([field])

    assert status["state"] == "mixed"
    assert status["label"].startswith("Missing 3")
    assert "Not applicable" in status["label"]
    assert "MDRS1001" in status["detail"]


def test_rule_label_comes_from_the_upr_pack():
    from app.services.validation.rule_labels import format_rule_label
    from plugins.upr.validation.register import register_upr_validation_pack

    register_upr_validation_pack()

    assert format_rule_label(RULE_MISSING) == "Applicable emergency not added"
    assert format_rule_label(RULE_NOT_APPLICABLE) == "Emergency not applicable"


def test_dashboard_question_uses_the_warning_text():
    from app.services.validation.question_assembler import assemble_question_for_kpi
    from app.services.validation.types import CheckResult

    draft = assemble_question_for_kpi(
        [CheckResult(
            rule_code=RULE_MISSING,
            form_item_id=None,
            fired=True,
            severity="warning",
            context={"message": "3 applicable emergencies were not added. This does not block submission."},
        )],
        definition_text=None,
        language="en",
        rule_pack="core",
    )

    assert draft is not None
    assert draft.severity == "warning"
    assert draft.question_text.startswith("3 applicable emergencies")


def test_tracker_is_complete_when_every_applicable_emergency_was_added():
    field = FieldEmergencyCoverage(
        section_name="Emergency Appeals Indicators",
        coverage=classify_emergency_coverage(UG_APPLICABLE, list(UG_APPLICABLE), set()),
    )

    assert tracker_status([field])["state"] == "ok"
    assert tracker_status([])["state"] == "not_used"
    assert tracker_status(None)["state"] == "unknown"


def test_planning_matrices_keep_emergency_rows_and_funding_headers():
    """Emergency Appeals stores a row. Funding Requirements stores the column header."""
    rows = selected_matrix_row_labels(
        {
            "MDRUG058 Uganda - Ebola Virus Disease Outbreak_Total People to be reached": 10,
            "row_go_unmatched|Sudan Crisis (MDRS1001)": 1,
            "col_header|EA1": "not a row",
        },
        ["Total People to be reached"],
    )
    headers = selected_matrix_header_labels(
        {
            "HNS_SP1": 5,
            "IFRC Secretariat_SP1": 9,
            "col_header|EA1": "MDRUG052 Uganda - Mpox Epidemic",
            "col_header|EA2": "",
        },
        ["EA1", "EA2", "EA3"],
    )

    assert rows == [
        "MDRUG058 Uganda - Ebola Virus Disease Outbreak",
        "Sudan Crisis (MDRS1001)",
    ]
    assert headers == ["MDRUG052 Uganda - Mpox Epidemic"]
    assert _ref_from_label(headers[0]).code == "MDRUG052"
    assert _ref_from_label(rows[1]).code == "MDRS1001"


def test_both_planning_lists_are_named_in_the_warning():
    appeals = FieldEmergencyCoverage(
        section_name="Emergency Appeals in 2027",
        coverage=classify_emergency_coverage(UG_APPLICABLE, [], set(op.code for op in UG_APPLICABLE)),
    )
    funding = FieldEmergencyCoverage(
        section_name="Funding Requirements for 2027",
        coverage=classify_emergency_coverage(
            UG_APPLICABLE,
            [_ref("MDRS1001", "Sudan Crisis (MDRS1001)")],
            set(op.code for op in UG_APPLICABLE),
        ),
    )

    messages = checks_from_fields([appeals, funding])
    missing = next(row["message"] for row in messages if row["rule_code"] == RULE_MISSING)

    assert "Emergency Appeals in 2027" in missing
    assert "Funding Requirements for 2027" in missing


def test_tracker_batch_answers_without_another_catalogue_lookup():
    class Batch:
        def coverages(self, aes):
            return []

    token = _COVERAGE_BATCH.set(Batch())
    try:
        assert load_field_coverages(SimpleNamespace(id=4)) == []
    finally:
        _COVERAGE_BATCH.reset(token)
