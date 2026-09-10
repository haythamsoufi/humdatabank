"""
Tests for app/services/audit/assignment_audit.py.

Covers the reviewer-facing details and descriptions recorded by
``edit_assignment`` and ``bulk_update_entity_status``. Fakes stand in for the
ORM so these stay pure unit tests: the snapshot helpers only read attributes,
and template/data-owner lookups short-circuit when the loaded relationship
already matches the foreign key.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.models.assignments import (
    SUBMISSION_REVIEW_RECIPIENT_FDS,
    SUBMISSION_REVIEW_RECIPIENT_SPECIFIC,
)
from app.models.enums import AssignmentEntityStatusValue
from app.services.audit.assignment_audit import (
    EMPTY_VALUE_TEXT,
    MAX_AUDIT_CHANGE_LINES,
    assignment_settings_snapshot,
    build_assignment_update_audit,
    build_entity_status_update_audit,
    country_due_dates_snapshot,
)


class _FakeTemplate:
    def __init__(self, id_, name):
        self.id = id_
        self.name = name


class _FakeUser:
    def __init__(self, id_, name, email):
        self.id = id_
        self.name = name
        self.email = email


class _FakeDynamicRelation:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeCountryStatus:
    def __init__(self, due_date=None):
        self.due_date = due_date


def _make_assignment(**overrides):
    template = overrides.pop("template", _FakeTemplate(7, "UPR Country Reporting"))
    owner = overrides.pop("data_owner_user", None)
    country_statuses = overrides.pop("country_statuses", [])
    assignment = type("FakeAssignment", (), {})()
    assignment.id = 42
    assignment.template = template
    assignment.template_id = template.id if template else None
    assignment.period_name = "2025"
    assignment.custom_name = None
    assignment.custom_name_translations = None
    assignment.expiry_date = None
    assignment.data_owner_user = owner
    assignment.data_owner_id = owner.id if owner else None
    assignment.requires_delegation_review = False
    assignment.enable_export_excel = False
    assignment.enable_import_excel = False
    assignment.enable_export_pdf = False
    assignment.submission_review_recipient_mode = SUBMISSION_REVIEW_RECIPIENT_FDS
    assignment.submission_review_recipient_users = []
    assignment.country_statuses = _FakeDynamicRelation(country_statuses)
    for key, value in overrides.items():
        setattr(assignment, key, value)
    return assignment


# ---------------------------------------------------------------------------
# assignment_settings_snapshot
# ---------------------------------------------------------------------------
class TestAssignmentSettingsSnapshot:
    def test_captures_editable_fields(self):
        owner = _FakeUser(3, "Ada Lovelace", "ada@example.org")
        assignment = _make_assignment(
            data_owner_user=owner,
            expiry_date=date(2025, 12, 31),
            enable_export_excel=True,
        )
        snapshot = assignment_settings_snapshot(assignment)
        assert snapshot["template"] == "UPR Country Reporting"
        assert snapshot["period_name"] == "2025"
        assert snapshot["expiry_date"] == "2025-12-31"
        assert snapshot["data_owner"] == "Ada Lovelace (ada@example.org)"
        assert snapshot["enable_export_excel"] is True
        assert snapshot["enable_import_excel"] is False
        assert snapshot["submission_review_mode"].startswith("Designated FDS member")

    def test_recipients_sorted_and_labelled(self):
        assignment = _make_assignment(
            submission_review_recipient_mode=SUBMISSION_REVIEW_RECIPIENT_SPECIFIC,
            submission_review_recipient_users=[
                _FakeUser(2, "Zoe", "zoe@example.org"),
                _FakeUser(1, "Amir", "amir@example.org"),
            ],
        )
        snapshot = assignment_settings_snapshot(assignment)
        assert snapshot["submission_review_recipients"] == [
            "Amir (amir@example.org)",
            "Zoe (zoe@example.org)",
        ]
        assert snapshot["submission_review_mode"] == "Specific IFRC admin(s)"

    def test_none_assignment_returns_empty(self):
        assert assignment_settings_snapshot(None) == {}

    def test_datetime_due_and_expiry_reduced_to_iso_date(self):
        assignment = _make_assignment(expiry_date=datetime(2025, 6, 1, 13, 45))
        assert assignment_settings_snapshot(assignment)["expiry_date"] == "2025-06-01"


# ---------------------------------------------------------------------------
# country_due_dates_snapshot
# ---------------------------------------------------------------------------
class TestCountryDueDatesSnapshot:
    def test_single_shared_due_date(self):
        assignment = _make_assignment(
            country_statuses=[
                _FakeCountryStatus(datetime(2025, 3, 1)),
                _FakeCountryStatus(datetime(2025, 3, 1)),
            ]
        )
        assert country_due_dates_snapshot(assignment) == "2025-03-01"

    def test_mixed_due_dates_reported_as_mixed(self):
        assignment = _make_assignment(
            country_statuses=[
                _FakeCountryStatus(datetime(2025, 3, 1)),
                _FakeCountryStatus(None),
            ]
        )
        result = country_due_dates_snapshot(assignment)
        assert result.startswith("mixed (")
        assert "2025-03-01" in result
        assert EMPTY_VALUE_TEXT in result

    def test_no_countries_returns_none(self):
        assert country_due_dates_snapshot(_make_assignment()) is None


# ---------------------------------------------------------------------------
# build_assignment_update_audit
# ---------------------------------------------------------------------------
class TestBuildAssignmentUpdateAudit:
    def test_changed_fields_listed_with_before_and_after(self):
        assignment = _make_assignment()
        before = assignment_settings_snapshot(assignment)
        after = dict(before, enable_export_excel=True, period_name="2026")
        details, description = build_assignment_update_audit(assignment, before, after)

        assert details["assignment_title"] == "UPR Country Reporting \u2013 2025"
        assert details["template_name"] == "UPR Country Reporting"
        assert "Reporting period: 2025 → 2026" in details["changes"]
        assert "Excel export: No → Yes" in details["changes"]
        assert description.startswith("Updated an assignment")
        assert "Reporting period" in description
        assert "Excel export" in description

    def test_unchanged_fields_are_not_listed(self):
        assignment = _make_assignment()
        before = assignment_settings_snapshot(assignment)
        after = dict(before, period_name="2026")
        details, _ = build_assignment_update_audit(assignment, before, after)
        assert details["changes"] == ["Reporting period: 2025 → 2026"]

    def test_no_changes_says_so(self):
        assignment = _make_assignment()
        before = assignment_settings_snapshot(assignment)
        details, description = build_assignment_update_audit(assignment, before, dict(before))
        assert details["changes"] == ["No assignment fields changed"]
        assert description.endswith("no fields changed")

    def test_description_keeps_catalog_text_as_prefix(self):
        """The audit trail treats the row as a richer catalog line via this prefix."""
        assignment = _make_assignment()
        before = assignment_settings_snapshot(assignment)
        _, description = build_assignment_update_audit(
            assignment, before, dict(before, period_name="2026")
        )
        assert description.startswith("Updated an assignment")

    def test_data_owner_change_shows_both_labels(self):
        assignment = _make_assignment()
        before = assignment_settings_snapshot(assignment)
        after = dict(before, data_owner="Ada Lovelace (ada@example.org)")
        details, _ = build_assignment_update_audit(assignment, before, after)
        assert f"Data owner: {EMPTY_VALUE_TEXT} → Ada Lovelace (ada@example.org)" in details["changes"]

    def test_translation_changes_reported_per_language(self):
        assignment = _make_assignment()
        before = assignment_settings_snapshot(assignment)
        after = dict(before, custom_name_translations={"fr": "Rapport annuel"})
        details, description = build_assignment_update_audit(assignment, before, after)
        assert f"Custom name (fr): {EMPTY_VALUE_TEXT} → Rapport annuel" in details["changes"]
        assert "Custom name translations" in description

    def test_identical_translations_not_reported(self):
        assignment = _make_assignment()
        before = dict(
            assignment_settings_snapshot(assignment),
            custom_name_translations={"fr": "Rapport"},
        )
        after = dict(before, custom_name_translations={"fr": "Rapport"})
        details, _ = build_assignment_update_audit(assignment, before, after)
        assert details["changes"] == ["No assignment fields changed"]

    def test_country_due_date_change_reported(self):
        assignment = _make_assignment()
        before = assignment_settings_snapshot(assignment)
        details, description = build_assignment_update_audit(
            assignment,
            before,
            dict(before),
            country_due_date_before="2025-01-01",
            country_due_date_after="2025-03-01",
        )
        assert "Due date (all countries): 2025-01-01 → 2025-03-01" in details["changes"]
        assert "Due date" in description

    def test_unchanged_country_due_date_not_reported(self):
        assignment = _make_assignment()
        before = assignment_settings_snapshot(assignment)
        details, _ = build_assignment_update_audit(
            assignment,
            before,
            dict(before),
            country_due_date_before="2025-03-01",
            country_due_date_after="2025-03-01",
        )
        assert details["changes"] == ["No assignment fields changed"]

    def test_custom_name_used_in_title(self):
        assignment = _make_assignment(custom_name="Annual Report")
        before = assignment_settings_snapshot(assignment)
        details, description = build_assignment_update_audit(
            assignment, before, dict(before, period_name="2026")
        )
        assert details["assignment_title"] == "Annual Report (2025)"
        assert "'Annual Report (2025)'" in description


# ---------------------------------------------------------------------------
# build_entity_status_update_audit
# ---------------------------------------------------------------------------
def _change(name, entity_type="country", before=None, after=None, due_before=None, due_after=None):
    return {
        "entity_type": entity_type,
        "entity_id": 1,
        "name": name,
        "status_before": before or AssignmentEntityStatusValue.pending,
        "status_after": after or AssignmentEntityStatusValue.approved,
        "due_before": due_before,
        "due_after": due_after,
    }


class TestBuildEntityStatusUpdateAudit:
    def test_single_country_names_the_entity(self):
        assignment = _make_assignment()
        details, description = build_entity_status_update_audit(
            assignment,
            [_change("Kenya")],
            new_status=AssignmentEntityStatusValue.approved,
        )
        assert details["new_status"] == "Approved"
        assert details["entities_updated"] == 1
        assert details["status_changes"] == ["Kenya: Pending → Approved"]
        assert description == (
            "Updated assignment status to Approved for Kenya "
            "in 'UPR Country Reporting \u2013 2025'"
        )

    def test_multiple_countries_are_counted_and_pluralised(self):
        assignment = _make_assignment()
        changes = [_change("Kenya"), _change("Chad"), _change("Peru")]
        details, description = build_entity_status_update_audit(
            assignment, changes, new_status=AssignmentEntityStatusValue.approved
        )
        assert details["entities_updated"] == 3
        assert len(details["status_changes"]) == 3
        assert "for 3 countries" in description

    def test_mixed_entity_types_use_generic_noun(self):
        assignment = _make_assignment()
        changes = [_change("Kenya"), _change("Nairobi Branch", entity_type="ns_branch")]
        _, description = build_entity_status_update_audit(
            assignment, changes, new_status=AssignmentEntityStatusValue.submitted
        )
        assert "for 2 entities" in description

    def test_single_entity_type_uses_its_plural(self):
        assignment = _make_assignment()
        changes = [
            _change("Branch A", entity_type="ns_branch"),
            _change("Branch B", entity_type="ns_branch"),
        ]
        _, description = build_entity_status_update_audit(
            assignment, changes, new_status=AssignmentEntityStatusValue.submitted
        )
        assert "for 2 NS branches" in description

    def test_rows_already_at_target_status_listed_separately(self):
        assignment = _make_assignment()
        changes = [
            _change("Kenya"),
            _change(
                "Chad",
                before=AssignmentEntityStatusValue.approved,
                after=AssignmentEntityStatusValue.approved,
            ),
        ]
        details, _ = build_entity_status_update_audit(
            assignment, changes, new_status=AssignmentEntityStatusValue.approved
        )
        assert details["status_changes"] == ["Kenya: Pending → Approved"]
        assert details["already_at_this_status"] == ["Chad"]

    def test_due_date_changes_reported_when_due_date_supplied(self):
        assignment = _make_assignment()
        changes = [
            _change("Kenya", due_before=None, due_after=date(2025, 3, 1)),
            _change("Chad", due_before=date(2025, 3, 1), due_after=date(2025, 3, 1)),
        ]
        details, description = build_entity_status_update_audit(
            assignment,
            changes,
            new_status=AssignmentEntityStatusValue.approved,
            new_due_date=date(2025, 3, 1),
        )
        assert details["new_due_date"] == "2025-03-01"
        assert details["due_date_changes"] == [f"Kenya: {EMPTY_VALUE_TEXT} → 2025-03-01"]
        assert "due date set to 2025-03-01" in description

    def test_no_due_date_keys_when_due_date_absent(self):
        assignment = _make_assignment()
        details, description = build_entity_status_update_audit(
            assignment, [_change("Kenya")], new_status=AssignmentEntityStatusValue.approved
        )
        assert "new_due_date" not in details
        assert "due_date_changes" not in details
        assert "due date" not in description

    def test_status_labels_are_human_readable(self):
        assignment = _make_assignment()
        details, description = build_entity_status_update_audit(
            assignment,
            [
                _change(
                    "Kenya",
                    before=AssignmentEntityStatusValue.in_progress,
                    after=AssignmentEntityStatusValue.sent_for_review,
                )
            ],
            new_status=AssignmentEntityStatusValue.sent_for_review,
        )
        assert details["status_changes"] == ["Kenya: In Progress → Sent for Review"]
        assert "to Sent for Review" in description

    def test_change_lines_are_capped(self):
        assignment = _make_assignment()
        changes = [_change(f"Country {i}") for i in range(MAX_AUDIT_CHANGE_LINES + 5)]
        details, _ = build_entity_status_update_audit(
            assignment, changes, new_status=AssignmentEntityStatusValue.approved
        )
        assert len(details["status_changes"]) == MAX_AUDIT_CHANGE_LINES + 1
        assert details["status_changes"][-1] == "… and 5 more"
        assert details["entities_updated"] == MAX_AUDIT_CHANGE_LINES + 5

    def test_missing_entity_name_falls_back_to_id(self):
        assignment = _make_assignment()
        change = _change(None)
        change["entity_id"] = 99
        details, _ = build_entity_status_update_audit(
            assignment, [change], new_status=AssignmentEntityStatusValue.approved
        )
        assert details["status_changes"] == ["Entity #99: Pending → Approved"]

    @pytest.mark.parametrize("changes", [[], ()])
    def test_empty_change_set_is_safe(self, changes):
        assignment = _make_assignment()
        details, description = build_entity_status_update_audit(
            assignment, changes, new_status=AssignmentEntityStatusValue.approved
        )
        assert details["entities_updated"] == 0
        assert details["status_changes"] == []
        assert "0 entities" in description
