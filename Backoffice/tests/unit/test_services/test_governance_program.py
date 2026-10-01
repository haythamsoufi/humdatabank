"""Controls and the governance issue register."""

from datetime import timedelta

import pytest

from tests.factories import create_test_user
from app.models import GovernanceIssue
from app.services.platform.governance_program import (
    accept_governance_issue,
    evaluate_controls,
    reopen_governance_issue,
    sync_issues,
    validate_acceptance,
)
from app.utils.datetime_helpers import utcnow

pytestmark = [pytest.mark.unit]


def _ctx(**overrides):
    base = {
        "errors": set(),
        "assignments_without_owner_count": 0,
        "assignments_without_owner": [],
        "templates_without_owner_count": 0,
        "templates_without_owner": [],
        "countries_on_open_assignment_without_focal": [],
        "ghost_users_count": 0,
        "ghost_users": [],
        "entity_without_role_count": 0,
        "entity_without_role": [],
        "recent_approvals_without_approver": 0,
        "critical_overdue_count": 0,
        "critical_overdue": [],
        "unstarted_past_due": [],
        "fdrs_applicable": False,
        "fdrs_periods": [],
        "fdrs_non_compliant_count": 0,
        "fdrs_non_compliant": [],
        "indicators_missing_definition": 0,
        "indicators_active": 0,
        "stale_suggestions_count": 0,
        "stale_suggestions": [],
        "public_links_without_expiry_count": 0,
        "public_links_without_expiry": [],
    }
    base.update(overrides)
    return base


def _by_code(results):
    return {row["code"]: row for row in results}


class TestEvaluateControls:
    def test_clean_environment_passes_and_skips_fdrs(self, app):
        results = _by_code(evaluate_controls(_ctx()))
        assert len(results) == 12
        assert results["CMP-01"]["status"] == "not_applicable"
        for code, row in results.items():
            if code == "CMP-01":
                continue
            assert row["status"] == "effective", code

    def test_open_assignment_without_owner_is_a_gap(self, app):
        results = _by_code(evaluate_controls(_ctx(
            assignments_without_owner_count=2,
            assignments_without_owner=[{"label": "FDRS — 2024", "href": "/admin/assignments/9/edit"}],
        )))
        row = results["OWN-01"]
        assert row["status"] == "gap"
        assert row["failing_count"] == 2
        assert row["evidence"][0]["label"] == "FDRS — 2024"

    def test_capped_ghost_list_uses_the_full_count(self, app):
        results = _by_code(evaluate_controls(_ctx(
            ghost_users_count=40,
            ghost_users=[{"label": "Ada", "href": "/admin/users/1/edit"}],
        )))
        assert results["ACC-01"]["failing_count"] == 40
        assert len(results["ACC-01"]["evidence"]) == 1

    def test_fdrs_gap_names_the_period(self, app):
        results = _by_code(evaluate_controls(_ctx(
            fdrs_applicable=True,
            fdrs_periods=["2024", "2023"],
            fdrs_non_compliant_count=3,
            fdrs_non_compliant=[{"label": "Testland", "href": None}],
        )))
        row = results["CMP-01"]
        assert row["status"] == "gap"
        assert row["failing_count"] == 3
        assert "2024" in row["summary"]

    def test_failed_check_is_unknown_not_a_pass(self, app):
        results = _by_code(evaluate_controls(_ctx(errors={"public_links"})))
        assert results["LIF-01"]["status"] == "unknown"
        assert results["OWN-01"]["status"] == "effective"

    def test_public_link_without_expiry_is_a_gap(self, app):
        results = _by_code(evaluate_controls(_ctx(
            public_links_without_expiry_count=1,
            public_links_without_expiry=[{"label": "Appeal — 2026", "href": "/admin/assignments/3/edit"}],
        )))
        assert results["LIF-01"]["status"] == "gap"


class TestAcceptanceValidation:
    def test_requires_a_real_reason_and_a_future_date(self, app):
        with app.app_context():
            today = utcnow().date()
            _until, error = validate_acceptance("too short", today.isoformat(), today=today)
            assert error
            _until, error = validate_acceptance("Regional office will assign owners next quarter.", today.isoformat(), today=today)
            assert error
            until, error = validate_acceptance(
                "Regional office will assign owners next quarter.",
                (today + timedelta(days=30)).isoformat(),
                today=today,
            )
            assert error is None
            assert until == today + timedelta(days=30)
            _until, error = validate_acceptance(
                "Regional office will assign owners next quarter.",
                (today + timedelta(days=400)).isoformat(),
                today=today,
            )
            assert error


class TestIssueSync:
    def test_gap_opens_then_acceptance_holds_until_it_expires(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            gap = evaluate_controls(_ctx(assignments_without_owner_count=1))
            sync_issues(gap)
            issue = GovernanceIssue.query.filter_by(control_code="OWN-01").one()
            assert issue.status == "open"

            until = utcnow().date() + timedelta(days=14)
            accept_governance_issue(
                issue,
                user_id=user.id,
                reason="Owners will be named at the next secretariat meeting.",
                until=until,
            )
            db_session.commit()

            sync_issues(gap)
            issue = GovernanceIssue.query.filter_by(control_code="OWN-01").one()
            assert issue.status == "accepted"

            issue.accepted_until = utcnow().date() - timedelta(days=1)
            db_session.commit()
            sync_issues(gap)
            issue = GovernanceIssue.query.filter_by(control_code="OWN-01").one()
            assert issue.status == "open"
            assert issue.acceptance_reason

    def test_passing_check_resolves_an_open_issue(self, app, db_session):
        with app.app_context():
            sync_issues(evaluate_controls(_ctx(public_links_without_expiry_count=1)))
            issue = GovernanceIssue.query.filter_by(control_code="LIF-01").one()
            assert issue.status == "open"
            sync_issues(evaluate_controls(_ctx()))
            issue = GovernanceIssue.query.filter_by(control_code="LIF-01").one()
            assert issue.status == "resolved"
            assert issue.resolution == "control_passed"

    def test_unknown_check_does_not_clear_an_open_issue(self, app, db_session):
        with app.app_context():
            sync_issues(evaluate_controls(_ctx(templates_without_owner_count=2)))
            sync_issues(evaluate_controls(_ctx(errors={"templates"})))
            issue = GovernanceIssue.query.filter_by(control_code="OWN-02").one()
            assert issue.status == "open"

    def test_reopen_clears_the_acceptance(self, app, db_session):
        with app.app_context():
            user = create_test_user(db_session)
            sync_issues(evaluate_controls(_ctx(recent_approvals_without_approver=1)))
            issue = GovernanceIssue.query.filter_by(control_code="ACC-03").one()
            accept_governance_issue(
                issue,
                user_id=user.id,
                reason="Legacy approvals are being backfilled this month.",
                until=utcnow().date() + timedelta(days=20),
            )
            reopen_governance_issue(issue)
            assert issue.status == "open"
            assert issue.acceptance_reason is None
