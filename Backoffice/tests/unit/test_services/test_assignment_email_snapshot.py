"""Tests for assignment submit/approve email PDF and Excel snapshots."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import patch

from app.services.forms.assignment_email_snapshot import (
    MAX_EMAIL_ATTACHMENT_BYTES,
    attachments_for_assignment_notification,
    build_assignment_email_attachments,
)
import pytest

from app.services.imports import structured_excel_routes as structured_excel_mod
from app.services.imports.structured_excel_routes import (
    register_structured_excel_builder,
    reset_structured_excel_builders,
    resolve_structured_excel_builder,
)


@pytest.fixture
def isolated_excel_registry():
    original = list(structured_excel_mod._STRUCTURED_EXCEL_BUILDERS)
    reset_structured_excel_builders()
    try:
        yield
    finally:
        reset_structured_excel_builders()
        for uses, builder in original:
            register_structured_excel_builder(uses, builder)


def _assigned(**kwargs):
    defaults = {
        "template_id": 99,
        "email_attach_pdf": False,
        "email_attach_excel": False,
        "enable_export_excel": False,
        "enable_import_excel": False,
        "enable_upr_country_reporting_excel": False,
        "enable_unified_country_plan_excel": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _aes(assigned, aes_id=1):
    return SimpleNamespace(id=aes_id, assigned_form=assigned)


class TestBuildAssignmentEmailAttachments:
    def test_flags_off_produces_no_attachments(self, app):
        with app.app_context():
            attachments = build_assignment_email_attachments(
                _aes(_assigned(email_attach_pdf=False, email_attach_excel=False))
            )
        assert attachments == []

    def test_plugin_builder_used_when_predicate_claims(self, app, isolated_excel_registry):
        claimed = _assigned(email_attach_excel=True)
        other = _assigned(email_attach_excel=True)

        def uses(assigned):
            return assigned is claimed

        def builder(aes):
            return io.BytesIO(b"custom-xlsx"), "plugin.xlsx"

        register_structured_excel_builder(uses, builder)
        with app.app_context():
            with patch(
                "app.services.forms.assignment_email_snapshot.build_assignment_generic_excel_bytes",
                return_value=(b"generic-xlsx", "generic.xlsx"),
            ) as mock_generic:
                attachments = build_assignment_email_attachments(_aes(claimed, aes_id=11))
                unused = build_assignment_email_attachments(_aes(other, aes_id=12))
        assert attachments == [
            ("plugin.xlsx", b"custom-xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        ]
        assert unused == [
            (
                "generic.xlsx",
                b"generic-xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        ]
        mock_generic.assert_called_once()

    def test_unclaimed_assignment_uses_generic_builder(self, app, isolated_excel_registry):
        assigned = _assigned(email_attach_excel=True)
        with app.app_context():
            with patch(
                "app.services.forms.assignment_email_snapshot.build_assignment_generic_excel_bytes",
                return_value=(b"generic-xlsx", "generic.xlsx"),
            ) as mock_generic:
                attachments = build_assignment_email_attachments(_aes(assigned, aes_id=21))
        mock_generic.assert_called_once()
        assert attachments == [
            (
                "generic.xlsx",
                b"generic-xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        ]

    def test_pdf_failure_still_returns_excel(self, app):
        assigned = _assigned(email_attach_pdf=True, email_attach_excel=True)
        with app.app_context():
            with patch(
                "app.routes.forms.export.build_assignment_pdf_bytes",
                side_effect=RuntimeError("weasyprint down"),
            ), patch(
                "app.services.forms.assignment_email_snapshot.build_assignment_generic_excel_bytes",
                return_value=(b"excel-ok", "data.xlsx"),
            ):
                attachments = build_assignment_email_attachments(_aes(assigned, aes_id=31))
        assert len(attachments) == 1
        assert attachments[0][0] == "data.xlsx"
        assert attachments[0][1] == b"excel-ok"

    def test_plugin_builder_failure_does_not_fall_back_to_generic(self, app, isolated_excel_registry):
        claimed = _assigned(email_attach_excel=True)

        def uses(assigned):
            return assigned is claimed

        def builder(_aes_obj):
            raise FileNotFoundError("template missing")

        register_structured_excel_builder(uses, builder)
        with app.app_context():
            with patch(
                "app.services.forms.assignment_email_snapshot.build_assignment_generic_excel_bytes"
            ) as mock_generic:
                attachments = build_assignment_email_attachments(_aes(claimed, aes_id=41))
        assert attachments == []
        mock_generic.assert_not_called()

    def test_skips_oversized_file(self, app):
        assigned = _assigned(email_attach_excel=True)
        huge = b"x" * (MAX_EMAIL_ATTACHMENT_BYTES + 1)
        with app.app_context():
            with patch(
                "app.services.forms.assignment_email_snapshot.build_assignment_generic_excel_bytes",
                return_value=(huge, "huge.xlsx"),
            ):
                attachments = build_assignment_email_attachments(_aes(assigned, aes_id=51))
        assert attachments == []


class TestAttachmentsForAssignmentNotification:
    def test_ignores_other_notification_types(self, app):
        notification = SimpleNamespace(
            related_object_type="assignment",
            related_object_id=1,
            notification_type=SimpleNamespace(value="assignment_created"),
        )
        with app.app_context():
            assert attachments_for_assignment_notification(notification) == []

    def test_ignores_non_assignment_related_objects(self, app):
        notification = SimpleNamespace(
            related_object_type="user",
            related_object_id=1,
            notification_type=SimpleNamespace(value="assignment_submitted"),
        )
        with app.app_context():
            assert attachments_for_assignment_notification(notification) == []

    def test_loads_aes_for_submitted_notification(self, app):
        assigned = _assigned(email_attach_excel=True)
        aes = _aes(assigned, aes_id=77)
        notification = SimpleNamespace(
            related_object_type="assignment",
            related_object_id=77,
            notification_type=SimpleNamespace(value="assignment_submitted"),
        )
        with app.app_context():
            with patch(
                "app.models.AssignmentEntityStatus"
            ) as mock_aes, patch(
                "app.services.forms.assignment_email_snapshot.build_assignment_generic_excel_bytes",
                return_value=(b"snap", "snap.xlsx"),
            ):
                mock_aes.query.get.return_value = aes
                attachments = attachments_for_assignment_notification(notification)
        assert attachments[0][1] == b"snap"


class TestStructuredExcelRegistry:
    def test_resolve_returns_first_claiming_builder(self, isolated_excel_registry):
        assigned = _assigned()

        def skip(_assigned):
            return False

        def claim(_assigned):
            return True

        def unused_builder(_aes):
            return io.BytesIO(b"no"), "no.xlsx"

        def used_builder(_aes):
            return io.BytesIO(b"yes"), "yes.xlsx"

        register_structured_excel_builder(skip, unused_builder)
        register_structured_excel_builder(claim, used_builder)
        assert resolve_structured_excel_builder(assigned) is used_builder
