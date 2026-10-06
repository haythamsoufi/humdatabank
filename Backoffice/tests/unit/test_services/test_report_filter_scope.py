"""Report execution stays inside the caller's template and country grants."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.extensions import db
from app.models.assignments import AssignmentEntityStatus
from app.services.data_retrieval.aggregation import _apply_optional_ids
from app.services.reports.asset_service import asset_belongs_to_report, build_asset_key, read_upload
from app.services.reports.data_service import ReportDataService, _bounded_limit
from app.services.reports.definition_service import REPORTS_EDIT, REPORTS_VIEW, user_can_view_report

pytestmark = pytest.mark.unit


def _scope(monkeypatch, template_ids, country_ids):
    monkeypatch.setattr(
        "app.services.reports.data_service.resolve_user_scope",
        lambda user: {"template_ids": template_ids, "country_ids": country_ids},
    )


def _definition(**filters):
    return {
        "schema_version": 2,
        "languages": ["en"],
        "default_language": "en",
        "filters": filters,
        "sections": [],
    }


def test_empty_allow_list_stays_constrained(monkeypatch):
    _scope(monkeypatch, [], [])
    ctx = ReportDataService.build_filter_context(object(), definition=_definition())
    assert ctx.template_ids == []
    assert ctx.country_ids == []
    assert ctx.constrain_templates is True
    assert ctx.constrain_countries is True


def test_unrestricted_empty_filters_are_not_constrained(monkeypatch):
    _scope(monkeypatch, None, None)
    ctx = ReportDataService.build_filter_context(object(), definition=_definition())
    assert ctx.template_ids == []
    assert ctx.country_ids == []
    assert ctx.constrain_templates is False
    assert ctx.constrain_countries is False


def test_empty_request_uses_the_allow_list(monkeypatch):
    _scope(monkeypatch, [3, 4], [7])
    ctx = ReportDataService.build_filter_context(object(), definition=_definition())
    assert set(ctx.template_ids) == {3, 4}
    assert ctx.country_ids == [7]


def test_adhoc_country_cannot_leave_the_allow_list(monkeypatch):
    _scope(monkeypatch, [1], [7])
    outside = ReportDataService.build_filter_context(
        object(),
        definition=_definition(),
        runtime_overrides={"adhoc_filters": {"country_id": 99}},
    )
    assert outside.country_ids == []
    assert outside.constrain_countries is True

    inside = ReportDataService.build_filter_context(
        object(),
        definition=_definition(),
        runtime_overrides={"adhoc_filters": {"country_id": 7}},
    )
    assert inside.country_ids == [7]

    ignored = ReportDataService.build_filter_context(
        object(),
        definition=_definition(),
        runtime_overrides={"adhoc_filters": {"country_id": "Kenya"}},
    )
    assert ignored.country_ids == [7]


def test_runtime_statuses_cannot_widen_past_the_definition(monkeypatch):
    _scope(monkeypatch, None, None)
    ctx = ReportDataService.build_filter_context(
        object(),
        definition=_definition(assignment_statuses=["submitted", "approved"]),
        runtime_overrides={"assignment_statuses": ["pending", "in_progress"]},
    )
    assert ctx.assignment_statuses == ["submitted", "approved"]

    narrowed = ReportDataService.build_filter_context(
        object(),
        definition=_definition(assignment_statuses=["submitted", "approved"]),
        runtime_overrides={"assignment_statuses": ["submitted"]},
    )
    assert narrowed.assignment_statuses == ["submitted"]


def test_preview_without_a_saved_report_uses_caller_scope(monkeypatch):
    _scope(monkeypatch, [], [])
    seen = {}

    def _execute(widget, ctx):
        seen["ctx"] = ctx
        return {"widget_id": widget.get("id"), "type": "kpi", "value": 0}

    monkeypatch.setattr(ReportDataService, "execute_widget", staticmethod(_execute))
    widget = {"id": "w1", "type": "kpi", "data_source": {"kind": "assignment_status_counts"}}
    ReportDataService.execute_preview(
        object(),
        definition={
            **_definition(),
            "sections": [{"id": "s1", "widgets": [widget]}],
        },
        widget=widget,
    )
    assert seen["ctx"].constrain_templates is True
    assert seen["ctx"].template_ids == []
    assert seen["ctx"].constrain_countries is True


def test_bounded_limit_caps_widget_rows():
    assert _bounded_limit("500000", 100) == 1000
    assert _bounded_limit("nope", 25) == 25
    assert _bounded_limit(0, 25) == 25


def test_constrained_empty_id_list_matches_nothing(app):
    with app.app_context():
        query = db.session.query(AssignmentEntityStatus.id)
        denied = _apply_optional_ids(query, AssignmentEntityStatus.entity_id, [], constrained=True)
        sql = str(
            denied.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        ).lower()
        assert "false" in sql

        open_query = _apply_optional_ids(query, AssignmentEntityStatus.entity_id, [], constrained=False)
        open_sql = str(open_query.statement.compile(dialect=postgresql.dialect())).lower()
        assert "entity_id" not in open_sql


def test_asset_keys_stay_inside_the_report():
    assert asset_belongs_to_report(5, "5/assets/photo.png")
    assert not asset_belongs_to_report(5, "6/assets/photo.png")
    assert not asset_belongs_to_report(5, "5/../6/assets/photo.png")

    with pytest.raises(ValueError):
        build_asset_key(5, "../../notes.html")
    key = build_asset_key(5, "My Photo.PNG")
    assert key.startswith("5/assets/")
    assert key.endswith(".png")
    assert asset_belongs_to_report(5, key)


def test_read_upload_rejects_oversized_files():
    class _File:
        def read(self, n):
            return b"x" * n

    with pytest.raises(ValueError):
        read_upload(_File(), max_bytes=4)


def test_owner_with_only_edit_can_view_own_report(monkeypatch):
    monkeypatch.setattr(
        "app.services.reports.definition_service.AuthorizationService.is_system_manager",
        lambda user: False,
    )

    def _has(user, code, *args, **kwargs):
        return code == REPORTS_EDIT

    monkeypatch.setattr(
        "app.services.reports.definition_service.AuthorizationService.has_rbac_permission",
        _has,
    )
    user = SimpleNamespace(id=5)
    own = SimpleNamespace(owner_user_id=5, status="draft")
    other = SimpleNamespace(owner_user_id=9, status="published")
    assert user_can_view_report(user, own) is True
    assert user_can_view_report(user, other) is False


def test_viewer_can_open_published_reports_only(monkeypatch):
    monkeypatch.setattr(
        "app.services.reports.definition_service.AuthorizationService.is_system_manager",
        lambda user: False,
    )

    def _has(user, code, *args, **kwargs):
        return code == REPORTS_VIEW

    monkeypatch.setattr(
        "app.services.reports.definition_service.AuthorizationService.has_rbac_permission",
        _has,
    )
    user = SimpleNamespace(id=5)
    published = SimpleNamespace(owner_user_id=9, status="published")
    draft = SimpleNamespace(owner_user_id=9, status="draft")
    assert user_can_view_report(user, published) is True
    assert user_can_view_report(user, draft) is False
