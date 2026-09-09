"""
Tests for app/utils/audit_context.py.

These helpers let a view enrich the single ``UserActivityLog`` row that the
activity middleware writes, instead of adding a second ``AdminActionLog`` row.
"""
from __future__ import annotations

import pytest
from flask import Flask, g

from app.utils.audit_context import (
    AUDIT_DETAILS_ATTR,
    CURATED_DESCRIPTION_KEY,
    apply_audit_details_to_context,
    has_curated_description,
    reset_request_audit_context,
    set_audit_description,
    set_audit_details,
)


@pytest.fixture
def request_ctx():
    app = Flask(__name__)
    with app.test_request_context("/admin/assignments/edit/1", method="POST"):
        yield


class TestSetAuditDetails:
    def test_fields_are_stored_on_g(self, request_ctx):
        set_audit_details(assignment_title="Annual Report", entities_updated=3)
        assert getattr(g, AUDIT_DETAILS_ATTR) == {
            "assignment_title": "Annual Report",
            "entities_updated": 3,
        }

    def test_repeated_calls_merge(self, request_ctx):
        set_audit_details(assignment_title="Annual Report")
        set_audit_details(new_status="Approved")
        stored = getattr(g, AUDIT_DETAILS_ATTR)
        assert stored["assignment_title"] == "Annual Report"
        assert stored["new_status"] == "Approved"

    def test_later_call_wins_for_same_key(self, request_ctx):
        set_audit_details(new_status="Pending")
        set_audit_details(new_status="Approved")
        assert getattr(g, AUDIT_DETAILS_ATTR)["new_status"] == "Approved"

    @pytest.mark.parametrize("empty", [None, "", [], {}])
    def test_empty_values_are_dropped(self, request_ctx, empty):
        set_audit_details(status_changes=empty)
        assert getattr(g, AUDIT_DETAILS_ATTR, {}) == {}

    def test_zero_and_false_are_kept(self, request_ctx):
        set_audit_details(entities_updated=0, requires_review=False)
        stored = getattr(g, AUDIT_DETAILS_ATTR)
        assert stored["entities_updated"] == 0
        assert stored["requires_review"] is False

    def test_outside_request_context_is_a_no_op(self):
        set_audit_details(assignment_title="Annual Report")


class TestSetAuditDescription:
    def test_description_is_stored(self, request_ctx):
        set_audit_description("Updated an assignment 'X': changed Due date")
        assert g.audit_activity_description == "Updated an assignment 'X': changed Due date"

    def test_description_is_stripped(self, request_ctx):
        set_audit_description("  Updated an assignment  ")
        assert g.audit_activity_description == "Updated an assignment"

    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_blank_description_ignored(self, request_ctx, blank):
        set_audit_description(blank)
        assert not hasattr(g, "audit_activity_description")

    def test_outside_request_context_is_a_no_op(self):
        set_audit_description("Updated an assignment")


class TestApplyAuditDetailsToContext:
    def test_details_merged_into_context(self, request_ctx):
        set_audit_details(assignment_title="Annual Report")
        context = {"endpoint": "assignment_management.edit_assignment", "method": "POST"}
        apply_audit_details_to_context(context)
        assert context["assignment_title"] == "Annual Report"
        assert context["endpoint"] == "assignment_management.edit_assignment"

    def test_view_details_override_middleware_inference(self, request_ctx):
        """A bulk action's real target beats the single entity the middleware guessed."""
        set_audit_details(entity_name="Kenya, Chad, Peru")
        context = {"entity_name": "Kenya"}
        apply_audit_details_to_context(context)
        assert context["entity_name"] == "Kenya, Chad, Peru"

    def test_curated_marker_added_when_requested(self, request_ctx):
        context = {}
        apply_audit_details_to_context(context, description_curated=True)
        assert context[CURATED_DESCRIPTION_KEY] is True

    def test_no_marker_by_default(self, request_ctx):
        context = {}
        apply_audit_details_to_context(context)
        assert CURATED_DESCRIPTION_KEY not in context

    def test_non_dict_context_returned_unchanged(self, request_ctx):
        assert apply_audit_details_to_context(None) is None

    def test_no_details_leaves_context_alone(self, request_ctx):
        context = {"method": "POST"}
        apply_audit_details_to_context(context)
        assert context == {"method": "POST"}


class TestResetRequestAuditContext:
    def test_pending_details_and_description_are_dropped(self, request_ctx):
        set_audit_details(assignment_title="Annual Report")
        set_audit_description("Updated an assignment")
        reset_request_audit_context()
        assert getattr(g, AUDIT_DETAILS_ATTR, None) is None
        assert getattr(g, "audit_activity_description", None) is None

    def test_safe_when_nothing_pending(self, request_ctx):
        reset_request_audit_context()
        assert getattr(g, AUDIT_DETAILS_ATTR, None) is None

    def test_outside_request_context_is_a_no_op(self):
        reset_request_audit_context()


class TestHasCuratedDescription:
    def test_true_when_marker_set(self):
        assert has_curated_description({CURATED_DESCRIPTION_KEY: True}) is True

    def test_false_when_marker_absent(self):
        assert has_curated_description({"method": "POST"}) is False

    @pytest.mark.parametrize("payload", [None, {}, "not a dict", 5])
    def test_false_for_non_dict_or_empty(self, payload):
        assert has_curated_description(payload) is False
