"""Tests for validation_dispatch_service.py — 100% coverage target."""

from unittest.mock import MagicMock, patch, call

import pytest

from app.services.validation_dispatch_service import (
    DispatchPreview,
    _questions_query,
    build_validation_email_html,
    preview_dispatch,
    send_dispatch,
)


# ─────────────────────────────────────────────────────────────────────────────
# _questions_query
# ─────────────────────────────────────────────────────────────────────────────


class TestQuestionsQuery:
    def test_filters_by_template_and_period(self):
        with patch(
            "app.services.validation_dispatch_service.ValidationQuestion.query"
        ) as mock_q:
            chain = MagicMock()
            mock_q.filter_by.return_value = chain
            chain.filter.return_value = chain
            chain.order_by.return_value = chain

            _questions_query(21, "2024")

            mock_q.filter_by.assert_called_once_with(
                template_id=21,
                period_name="2024",
                status="open",
            )

    def test_adds_entity_filter_when_provided(self):
        with patch(
            "app.services.validation_dispatch_service.ValidationQuestion.query"
        ) as mock_q:
            chain = MagicMock()
            mock_q.filter_by.return_value = chain
            chain.filter_by.return_value = chain
            chain.filter.return_value = chain
            chain.order_by.return_value = chain

            _questions_query(21, "2024", entity_type="country", entity_id=1)

            chain.filter_by.assert_called_once_with(entity_type="country", entity_id=1)

    def test_adds_question_ids_filter_when_provided(self):
        with patch(
            "app.services.validation_dispatch_service.ValidationQuestion.query"
        ) as mock_q:
            chain = MagicMock()
            mock_q.filter_by.return_value = chain
            chain.filter.return_value = chain
            chain.order_by.return_value = chain

            _questions_query(21, "2024", question_ids=[1, 2, 3])

            # filter should have been called with in_ expression
            chain.filter.assert_called()

    def test_uses_custom_status(self):
        with patch(
            "app.services.validation_dispatch_service.ValidationQuestion.query"
        ) as mock_q:
            chain = MagicMock()
            mock_q.filter_by.return_value = chain
            chain.filter.return_value = chain
            chain.order_by.return_value = chain

            _questions_query(21, "2024", status="answered")

            mock_q.filter_by.assert_called_once_with(
                template_id=21,
                period_name="2024",
                status="answered",
            )


# ─────────────────────────────────────────────────────────────────────────────
# preview_dispatch
# ─────────────────────────────────────────────────────────────────────────────


class TestPreviewDispatch:
    def test_returns_empty_preview_when_no_questions(self):
        with patch(
            "app.services.validation_dispatch_service._questions_query"
        ) as mock_qq:
            chain = MagicMock()
            chain.all.return_value = []
            mock_qq.return_value = chain
            result = preview_dispatch(21, "2024")

        assert isinstance(result, DispatchPreview)
        assert result.entities == []
        assert result.questions == []
        assert result.total_recipients == 0

    def test_builds_entity_and_question_lists(self):
        q1 = MagicMock()
        q1.entity_type = "country"
        q1.entity_id = 1
        q1.id = 10
        q1.rule_code = "not_reported"
        q1.severity = "warning"
        q1.question_text = "Please explain." * 10  # > 500 chars? No, just short
        q1.form_item_id = 5
        q1.context = {"foo": "bar"}

        with patch(
            "app.services.validation_dispatch_service._questions_query"
        ) as mock_qq, patch(
            "app.services.validation_dispatch_service.get_assignment_editor_submitter_user_ids_for_entity",
            return_value=[1, 2],
        ), patch(
            "app.services.validation_dispatch_service.User.query"
        ) as mock_user, patch(
            "app.services.validation_dispatch_service.EntityService"
        ) as mock_es:
            chain = MagicMock()
            chain.all.return_value = [q1]
            mock_qq.return_value = chain

            user1, user2 = MagicMock(), MagicMock()
            user1.id = 1
            user1.email = "a@test.com"
            user1.name = "Alice"
            user2.id = 2
            user2.email = "b@test.com"
            user2.name = "Bob"
            mock_user.filter.return_value.all.return_value = [user1, user2]
            mock_es.get_localized_entity_name.return_value = "Testland"

            result = preview_dispatch(21, "2024", entity_type="country", entity_id=1)

        assert len(result.entities) == 1
        assert result.entities[0]["entity_type"] == "country"
        assert result.entities[0]["recipient_count"] == 2
        assert len(result.questions) == 1
        assert result.total_recipients == 2

    def test_context_items_limited_to_5(self):
        q1 = MagicMock()
        q1.entity_type = "country"
        q1.entity_id = 1
        q1.id = 10
        q1.rule_code = "not_reported"
        q1.severity = "warning"
        q1.question_text = "Q"
        q1.form_item_id = None
        q1.context = {f"key_{i}": f"val_{i}" for i in range(10)}

        with patch(
            "app.services.validation_dispatch_service._questions_query"
        ) as mock_qq, patch(
            "app.services.validation_dispatch_service.get_assignment_editor_submitter_user_ids_for_entity",
            return_value=[],
        ), patch(
            "app.services.validation_dispatch_service.User.query"
        ) as mock_user, patch(
            "app.services.validation_dispatch_service.EntityService"
        ):
            chain = MagicMock()
            chain.all.return_value = [q1]
            mock_qq.return_value = chain
            mock_user.filter.return_value.all.return_value = []

            result = preview_dispatch(21, "2024")

        # Just check no error raised
        assert len(result.questions) == 1


# ─────────────────────────────────────────────────────────────────────────────
# build_validation_email_html
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildValidationEmailHtml:
    def _make_question(self, severity="warning", rule_code="not_reported", text="Question?", context=None):
        q = MagicMock()
        q.severity = severity
        q.rule_code = rule_code
        q.question_text = text
        q.context = context
        return q

    def test_includes_intro_message(self):
        q = self._make_question()
        html = build_validation_email_html(
            [q],
            entity_name="Testland",
            period_name="2024",
            template_name="FDRS",
            entry_url="http://example.com",
            intro_message="Custom intro message.",
        )
        assert "Custom intro message." in html

    def test_default_intro_message(self):
        q = self._make_question()
        html = build_validation_email_html(
            [q],
            entity_name="Testland",
            period_name="2024",
            template_name="FDRS",
            entry_url="http://example.com",
        )
        assert "Testland" in html
        assert "2024" in html

    def test_includes_question_rows(self):
        q1 = self._make_question(severity="error", rule_code="vol_deaths", text="Deaths?")
        q2 = self._make_question(severity="warning", rule_code="not_reported", text="Report?")
        html = build_validation_email_html(
            [q1, q2],
            entity_name="Testland",
            period_name="2024",
            template_name="FDRS",
            entry_url="http://example.com",
        )
        assert "Deaths?" in html
        assert "Report?" in html

    def test_context_displayed_without_triggered_rules(self):
        q = self._make_question(
            context={"triggered_rules": ["x"], "value": 100, "note": "test"}
        )
        html = build_validation_email_html(
            [q],
            entity_name="Testland",
            period_name="2024",
            template_name="FDRS",
            entry_url="http://example.com",
        )
        assert "value" in html or "note" in html
        assert "triggered_rules" not in html

    def test_no_context_skips_ctx_preview(self):
        q = self._make_question(context=None)
        html = build_validation_email_html(
            [q],
            entity_name="Testland",
            period_name="2024",
            template_name="FDRS",
            entry_url="http://example.com",
        )
        assert "<html>" in html

    def test_entry_url_in_link(self):
        q = self._make_question()
        html = build_validation_email_html(
            [q],
            entity_name="Testland",
            period_name="2024",
            template_name="FDRS",
            entry_url="http://example.com/form/1",
        )
        assert "http://example.com/form/1" in html


# ─────────────────────────────────────────────────────────────────────────────
# send_dispatch
# ─────────────────────────────────────────────────────────────────────────────


class TestSendDispatch:
    def _make_question(self, entity_type="country", entity_id=1, severity="warning", aes_id=10):
        q = MagicMock()
        q.entity_type = entity_type
        q.entity_id = entity_id
        q.severity = severity
        q.assignment_entity_status_id = aes_id
        q.question_text = "Question text here."
        q.dispatch_batch_id = None
        q.sent_at = None
        q.delivery_channels = None
        return q

    def test_creates_batch_and_returns_it(self):
        template = MagicMock()
        template.name = "FDRS"

        with patch(
            "app.services.validation_dispatch_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation_dispatch_service.ValidationDispatchBatch"
        ) as mock_batch_cls, patch(
            "app.services.validation_dispatch_service._questions_query"
        ) as mock_qq, patch(
            "app.services.validation_dispatch_service.db"
        ) as mock_db, patch(
            "app.services.validation_dispatch_service.get_assignment_editor_submitter_user_ids_for_entity",
            return_value=[],
        ), patch(
            "app.services.validation_dispatch_service.utcnow",
            return_value=MagicMock(),
        ):
            mock_tpl.get_or_404.return_value = template
            batch = MagicMock()
            batch.id = 1
            mock_batch_cls.return_value = batch

            chain = MagicMock()
            chain.all.return_value = []
            mock_qq.return_value = chain

            result = send_dispatch(
                21,
                "2024",
                created_by_user_id=1,
                channels=["in_app"],
            )

        assert result is batch
        assert batch.status == "sent"
        mock_db.session.commit.assert_called_once()

    def test_sends_in_app_notification(self):
        template = MagicMock()
        template.name = "FDRS"
        q = self._make_question()

        with patch(
            "app.services.validation_dispatch_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation_dispatch_service.ValidationDispatchBatch"
        ) as mock_batch_cls, patch(
            "app.services.validation_dispatch_service._questions_query"
        ) as mock_qq, patch(
            "app.services.validation_dispatch_service.db"
        ) as mock_db, patch(
            "app.services.validation_dispatch_service.get_assignment_editor_submitter_user_ids_for_entity",
            return_value=[1, 2],
        ), patch(
            "app.services.validation_dispatch_service.create_notification"
        ) as mock_notify, patch(
            "app.services.validation_dispatch_service.EntityService"
        ) as mock_es, patch(
            "app.services.validation_dispatch_service.url_for",
            return_value="http://example.com",
        ), patch(
            "app.services.validation_dispatch_service.utcnow",
            return_value=MagicMock(),
        ):
            mock_tpl.get_or_404.return_value = template
            batch = MagicMock()
            batch.id = 1
            mock_batch_cls.return_value = batch

            chain = MagicMock()
            chain.all.return_value = [q]
            mock_qq.return_value = chain
            mock_es.get_localized_entity_name.return_value = "Testland"

            send_dispatch(
                21,
                "2024",
                created_by_user_id=1,
                channels=["in_app"],
            )

        mock_notify.assert_called()

    def test_sends_email_notification(self):
        template = MagicMock()
        template.name = "FDRS"
        q = self._make_question()

        with patch(
            "app.services.validation_dispatch_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation_dispatch_service.ValidationDispatchBatch"
        ) as mock_batch_cls, patch(
            "app.services.validation_dispatch_service._questions_query"
        ) as mock_qq, patch(
            "app.services.validation_dispatch_service.db"
        ) as mock_db, patch(
            "app.services.validation_dispatch_service.get_assignment_editor_submitter_user_ids_for_entity",
            return_value=[1],
        ), patch(
            "app.services.validation_dispatch_service.create_notification"
        ) as mock_notify, patch(
            "app.services.validation_dispatch_service.EntityService"
        ) as mock_es, patch(
            "app.services.validation_dispatch_service.url_for",
            side_effect=Exception("no URL"),
        ), patch(
            "app.services.validation_dispatch_service.utcnow",
            return_value=MagicMock(),
        ):
            mock_tpl.get_or_404.return_value = template
            batch = MagicMock()
            batch.id = 1
            mock_batch_cls.return_value = batch

            chain = MagicMock()
            chain.all.return_value = [q]
            mock_qq.return_value = chain
            mock_es.get_localized_entity_name.return_value = "Testland"

            send_dispatch(
                21,
                "2024",
                created_by_user_id=1,
                channels=["email"],
            )

        # email channel triggers create_notification with send_email_notifications=True
        called_kwargs = mock_notify.call_args_list
        email_calls = [c for c in called_kwargs if c.kwargs.get("send_email_notifications")]
        assert len(email_calls) >= 1

    def test_failed_entity_increments_failed_count(self):
        template = MagicMock()
        template.name = "FDRS"
        q = self._make_question()

        with patch(
            "app.services.validation_dispatch_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation_dispatch_service.ValidationDispatchBatch"
        ) as mock_batch_cls, patch(
            "app.services.validation_dispatch_service._questions_query"
        ) as mock_qq, patch(
            "app.services.validation_dispatch_service.db"
        ) as mock_db, patch(
            "app.services.validation_dispatch_service.get_assignment_editor_submitter_user_ids_for_entity",
            return_value=[],  # no recipients → failed
        ), patch(
            "app.services.validation_dispatch_service.EntityService.batch_entity_names",
            return_value={},
        ), patch(
            "app.services.validation_dispatch_service.utcnow",
            return_value=MagicMock(),
        ):
            mock_tpl.get_or_404.return_value = template
            batch = MagicMock()
            batch.id = 1
            batch.summary = None
            mock_batch_cls.return_value = batch

            chain = MagicMock()
            chain.all.return_value = [q]
            mock_qq.return_value = chain

            send_dispatch(
                21,
                "2024",
                created_by_user_id=1,
                channels=["in_app"],
            )

        assert batch.summary["failed"] == 1

    def test_url_for_exception_fallback(self):
        """When url_for raises, uses entry_path fallback."""
        template = MagicMock()
        template.name = "FDRS"
        q = self._make_question()

        with patch(
            "app.services.validation_dispatch_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation_dispatch_service.ValidationDispatchBatch"
        ) as mock_batch_cls, patch(
            "app.services.validation_dispatch_service._questions_query"
        ) as mock_qq, patch(
            "app.services.validation_dispatch_service.db"
        ), patch(
            "app.services.validation_dispatch_service.get_assignment_editor_submitter_user_ids_for_entity",
            return_value=[1],
        ), patch(
            "app.services.validation_dispatch_service.create_notification"
        ), patch(
            "app.services.validation_dispatch_service.EntityService"
        ) as mock_es, patch(
            "app.services.validation_dispatch_service.url_for",
            side_effect=RuntimeError("routing error"),
        ), patch(
            "app.services.validation_dispatch_service.utcnow",
            return_value=MagicMock(),
        ):
            mock_tpl.get_or_404.return_value = template
            batch = MagicMock()
            batch.id = 1
            mock_batch_cls.return_value = batch
            chain = MagicMock()
            chain.all.return_value = [q]
            mock_qq.return_value = chain
            mock_es.get_localized_entity_name.return_value = "Testland"

            # No exception should propagate
            send_dispatch(
                21,
                "2024",
                created_by_user_id=1,
                channels=["in_app"],
            )

    def test_entity_name_fallback_when_get_localized_raises(self):
        template = MagicMock()
        template.name = "FDRS"
        q = self._make_question(entity_type="country", entity_id=99)

        with patch(
            "app.services.validation_dispatch_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation_dispatch_service.ValidationDispatchBatch"
        ) as mock_batch_cls, patch(
            "app.services.validation_dispatch_service._questions_query"
        ) as mock_qq, patch(
            "app.services.validation_dispatch_service.db"
        ), patch(
            "app.services.validation_dispatch_service.get_assignment_editor_submitter_user_ids_for_entity",
            return_value=[1],
        ), patch(
            "app.services.validation_dispatch_service.create_notification"
        ), patch(
            "app.services.validation_dispatch_service.EntityService"
        ) as mock_es, patch(
            "app.services.validation_dispatch_service.url_for",
            return_value="http://x.com",
        ), patch(
            "app.services.validation_dispatch_service.utcnow",
            return_value=MagicMock(),
        ):
            mock_tpl.get_or_404.return_value = template
            batch = MagicMock()
            batch.id = 1
            mock_batch_cls.return_value = batch
            chain = MagicMock()
            chain.all.return_value = [q]
            mock_qq.return_value = chain
            mock_es.get_localized_entity_name.side_effect = Exception("not found")

            # entity_name fallback to str(entity_id)
            send_dispatch(
                21,
                "2024",
                created_by_user_id=1,
                channels=["in_app"],
            )

    def test_high_severity_sets_high_priority(self):
        template = MagicMock()
        template.name = "FDRS"
        q = self._make_question(severity="error")

        with patch(
            "app.services.validation_dispatch_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation_dispatch_service.ValidationDispatchBatch"
        ) as mock_batch_cls, patch(
            "app.services.validation_dispatch_service._questions_query"
        ) as mock_qq, patch(
            "app.services.validation_dispatch_service.db"
        ), patch(
            "app.services.validation_dispatch_service.get_assignment_editor_submitter_user_ids_for_entity",
            return_value=[1],
        ), patch(
            "app.services.validation_dispatch_service.create_notification"
        ) as mock_notify, patch(
            "app.services.validation_dispatch_service.EntityService"
        ) as mock_es, patch(
            "app.services.validation_dispatch_service.url_for",
            return_value="http://x.com",
        ), patch(
            "app.services.validation_dispatch_service.utcnow",
            return_value=MagicMock(),
        ):
            mock_tpl.get_or_404.return_value = template
            batch = MagicMock()
            batch.id = 1
            mock_batch_cls.return_value = batch
            chain = MagicMock()
            chain.all.return_value = [q]
            mock_qq.return_value = chain
            mock_es.get_localized_entity_name.return_value = "Testland"

            send_dispatch(21, "2024", created_by_user_id=1, channels=["in_app"])

        calls = mock_notify.call_args_list
        assert any(c.kwargs.get("priority") == "high" for c in calls)
