"""Tests for log_entity_activities_bulk (batch entity-activity-log writes)."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestLogEntityActivitiesBulk:
    def test_empty_entries_is_a_noop(self, app):
        with app.app_context():
            from app.services.notification.core import log_entity_activities_bulk

            assert log_entity_activities_bulk([]) == 0

    def test_skips_entries_missing_user_id_but_logs_the_rest(self, app):
        with app.app_context():
            from app.services.notification.core import log_entity_activities_bulk

            with patch("app.services.notification.core.EntityActivityLog") as MockLog, \
                 patch("app.services.notification.core.db") as mock_db, \
                 patch(
                     "app.services.notification.core.current_user",
                     MagicMock(is_authenticated=False),
                 ):
                result = log_entity_activities_bulk(
                    [
                        {
                            "entity_type": "country",
                            "entity_id": 10,
                            "activity_type": "excel_import",
                            "activity_description": "no user, not authenticated either",
                            "summary_key": "activity.upr_excel_import",
                        },
                        {
                            "entity_type": "country",
                            "entity_id": 11,
                            "activity_type": "excel_import",
                            "activity_description": "has an explicit user",
                            "summary_key": "activity.upr_excel_import",
                            "summary_params": {"template": "Unified Country Plan", "count": 3},
                            "user_id": 42,
                        },
                    ]
                )

            assert result == 1
            MockLog.assert_called_once()
            kwargs = MockLog.call_args.kwargs
            assert kwargs["entity_id"] == 11
            assert kwargs["country_id"] == 11  # country entity: country_id falls back to entity_id
            assert kwargs["user_id"] == 42
            assert kwargs["summary_params"] == {"template": "Unified Country Plan", "count": 3}
            mock_db.session.add_all.assert_called_once()
            mock_db.session.commit.assert_called_once()

    def test_missing_summary_key_is_skipped_without_touching_db(self, app):
        with app.app_context():
            from app.services.notification.core import log_entity_activities_bulk

            with patch("app.services.notification.core.db") as mock_db:
                result = log_entity_activities_bulk(
                    [{"entity_type": "country", "entity_id": 1, "user_id": 1}]
                )

            assert result == 0
            mock_db.session.add_all.assert_not_called()
            mock_db.session.commit.assert_not_called()

    def test_resolves_country_id_for_non_country_entities(self, app):
        with app.app_context():
            from app.services.notification.core import log_entity_activities_bulk

            fake_country = MagicMock(id=99)
            with patch("app.services.notification.core.EntityActivityLog") as MockLog, \
                 patch("app.services.notification.core.db"), \
                 patch(
                     "app.services.organization.entity_service.EntityService.get_country_for_entity",
                     return_value=fake_country,
                 ):
                log_entity_activities_bulk(
                    [
                        {
                            "entity_type": "ns_branch",
                            "entity_id": 5,
                            "activity_type": "excel_import",
                            "activity_description": "x",
                            "summary_key": "activity.upr_excel_import",
                            "user_id": 1,
                        }
                    ]
                )

            assert MockLog.call_args.kwargs["country_id"] == 99
            assert MockLog.call_args.kwargs["entity_type"] == "ns_branch"

    def test_country_lookup_failure_defaults_to_none_not_raise(self, app):
        with app.app_context():
            from app.services.notification.core import log_entity_activities_bulk

            with patch("app.services.notification.core.EntityActivityLog") as MockLog, \
                 patch("app.services.notification.core.db"), \
                 patch(
                     "app.services.organization.entity_service.EntityService.get_country_for_entity",
                     side_effect=RuntimeError("boom"),
                 ):
                result = log_entity_activities_bulk(
                    [
                        {
                            "entity_type": "ns_branch",
                            "entity_id": 5,
                            "activity_type": "excel_import",
                            "activity_description": "x",
                            "summary_key": "activity.upr_excel_import",
                            "user_id": 1,
                        }
                    ]
                )

            assert result == 1
            assert MockLog.call_args.kwargs["country_id"] is None

    def test_commit_failure_rolls_back_and_returns_zero(self, app):
        with app.app_context():
            from app.services.notification.core import log_entity_activities_bulk

            with patch("app.services.notification.core.EntityActivityLog"), \
                 patch("app.services.notification.core.db") as mock_db:
                mock_db.session.commit.side_effect = RuntimeError("db down")
                result = log_entity_activities_bulk(
                    [
                        {
                            "entity_type": "country",
                            "entity_id": 1,
                            "activity_type": "excel_import",
                            "activity_description": "x",
                            "summary_key": "activity.upr_excel_import",
                            "user_id": 1,
                        }
                    ]
                )

            assert result == 0
            mock_db.session.rollback.assert_called_once()

    def test_falls_back_to_current_user_when_authenticated(self, app):
        with app.app_context():
            from app.services.notification.core import log_entity_activities_bulk

            with patch("app.services.notification.core.EntityActivityLog") as MockLog, \
                 patch("app.services.notification.core.db"), \
                 patch(
                     "app.services.notification.core.current_user",
                     MagicMock(is_authenticated=True, id=77),
                 ):
                result = log_entity_activities_bulk(
                    [
                        {
                            "entity_type": "country",
                            "entity_id": 1,
                            "activity_type": "excel_import",
                            "activity_description": "x",
                            "summary_key": "activity.upr_excel_import",
                            # no explicit user_id -> falls back to current_user.id
                        }
                    ]
                )

            assert result == 1
            assert MockLog.call_args.kwargs["user_id"] == 77
