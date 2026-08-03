"""Unit tests for hierarchy CRUD helpers in system_admin/helpers.py."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.unit
class TestGetTranslatableLanguages:
    def test_uses_app_config_first(self, app):
        with app.app_context():
            app.config["TRANSLATABLE_LANGUAGES"] = ["fr", "es"]
            from app.routes.admin.system_admin.helpers import get_translatable_languages

            assert get_translatable_languages() == ["fr", "es"]

    def test_falls_back_to_empty_list(self, app):
        with app.app_context():
            app.config["TRANSLATABLE_LANGUAGES"] = None
            with patch("app.routes.admin.system_admin.helpers.Config") as mock_cfg:
                mock_cfg.TRANSLATABLE_LANGUAGES = None
                from app.routes.admin.system_admin.helpers import get_translatable_languages

                assert get_translatable_languages() == []


@pytest.mark.unit
class TestApplyNameTranslationsFromForm:
    def test_applies_translation_fields(self, app):
        entity = MagicMock()
        form = MagicMock()
        form.name_fr = MagicMock(data="Secteur")
        form.name_es = MagicMock(data="Sector")

        with app.app_context():
            app.config["TRANSLATABLE_LANGUAGES"] = ["fr", "es"]
            from app.routes.admin.system_admin.helpers import apply_name_translations_from_form

            apply_name_translations_from_form(entity, form)

        entity.set_name_translation.assert_any_call("fr", "Secteur")
        entity.set_name_translation.assert_any_call("es", "Sector")

    def test_skips_missing_language_fields(self, app):
        entity = MagicMock()
        form = MagicMock(spec=[])

        with app.app_context():
            app.config["TRANSLATABLE_LANGUAGES"] = ["fr"]
            from app.routes.admin.system_admin.helpers import apply_name_translations_from_form

            apply_name_translations_from_form(entity, form)

        entity.set_name_translation.assert_not_called()


@pytest.mark.unit
class TestFlashFormErrors:
    def test_flashes_each_error(self, app):
        form = MagicMock()
        form.errors = {"name": ["Required"], "sector_id": ["Invalid choice"]}

        with app.app_context():
            from app.routes.admin.system_admin.helpers import flash_form_errors

            with patch("app.routes.admin.system_admin.helpers.flash") as mock_flash:
                flash_form_errors(form)

        assert mock_flash.call_count == 2
        mock_flash.assert_any_call("Error in name: Required", "danger")
        mock_flash.assert_any_call("Error in sector_id: Invalid choice", "danger")


@pytest.mark.unit
class TestUpdateEntityNameTranslationsJson:
    def test_updates_valid_name_fields(self, app, db_session):
        entity = MagicMock()
        entity.name_translations = {}

        with app.app_context():
            from app.routes.admin.system_admin.helpers import update_entity_name_translations_json

            with patch("app.routes.admin.system_admin.helpers.db") as mock_db:
                response = update_entity_name_translations_json(
                    entity,
                    {"name_fr": "French", "name_es": "Spanish", "ignored": "x"},
                    success_message="Updated",
                )

        entity.set_name_translation.assert_any_call("fr", "French")
        entity.set_name_translation.assert_any_call("es", "Spanish")
        assert response.status_code == 200

    def test_rejects_empty_payload(self, app):
        with app.app_context():
            from app.routes.admin.system_admin.helpers import update_entity_name_translations_json

            response = update_entity_name_translations_json(
                MagicMock(), None, success_message="Updated"
            )

        assert response.status_code == 400

    def test_rejects_no_translation_fields(self, app):
        with app.app_context():
            from app.routes.admin.system_admin.helpers import update_entity_name_translations_json

            response = update_entity_name_translations_json(
                MagicMock(), {"name": "Only base name"}, success_message="Updated"
            )

        assert response.status_code == 400


@pytest.mark.unit
class TestHandleHierarchyDbError:
    def test_rolls_back_flashes_and_logs(self, app):
        exc = RuntimeError("db failed")

        with app.app_context():
            from app.routes.admin.system_admin.helpers import handle_hierarchy_db_error

            with patch("app.routes.admin.system_admin.helpers.request_transaction_rollback") as mock_rb, \
                 patch("app.routes.admin.system_admin.helpers.flash") as mock_flash, \
                 patch("app.routes.admin.system_admin.helpers.current_app") as mock_app:
                mock_app.logger = MagicMock()
                handle_hierarchy_db_error(
                    exc,
                    log_message="create failed",
                    flash_message="Custom error",
                )

        mock_rb.assert_called_once()
        mock_flash.assert_called_once_with("Custom error", "danger")
        mock_app.logger.error.assert_called_once()
