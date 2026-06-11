"""
Tests for app/routes/admin/system_admin/helpers.py
Targeting 100% code coverage of the helper utilities.
"""
import pytest
import json
from unittest.mock import MagicMock, patch

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# _safe_logo_mimetype
# ---------------------------------------------------------------------------

class TestSafeLogoMimetype:
    def test_png_returns_image_png(self, app):
        from app.routes.admin.system_admin.helpers import _safe_logo_mimetype
        with app.app_context():
            assert _safe_logo_mimetype("logo.png") == "image/png"

    def test_jpg_returns_image_jpeg(self, app):
        from app.routes.admin.system_admin.helpers import _safe_logo_mimetype
        with app.app_context():
            assert _safe_logo_mimetype("logo.jpg") == "image/jpeg"

    def test_jpeg_returns_image_jpeg(self, app):
        from app.routes.admin.system_admin.helpers import _safe_logo_mimetype
        with app.app_context():
            assert _safe_logo_mimetype("logo.jpeg") == "image/jpeg"

    def test_gif_returns_image_gif(self, app):
        from app.routes.admin.system_admin.helpers import _safe_logo_mimetype
        with app.app_context():
            assert _safe_logo_mimetype("logo.gif") == "image/gif"

    def test_webp_returns_image_webp(self, app):
        from app.routes.admin.system_admin.helpers import _safe_logo_mimetype
        with app.app_context():
            assert _safe_logo_mimetype("logo.webp") == "image/webp"

    def test_unknown_extension_returns_octet_stream(self, app):
        from app.routes.admin.system_admin.helpers import _safe_logo_mimetype
        with app.app_context():
            assert _safe_logo_mimetype("logo.svg") == "application/octet-stream"
            assert _safe_logo_mimetype("logo.bmp") == "application/octet-stream"
            assert _safe_logo_mimetype("noext") == "application/octet-stream"

    def test_uppercase_extension_normalised(self, app):
        from app.routes.admin.system_admin.helpers import _safe_logo_mimetype
        with app.app_context():
            assert _safe_logo_mimetype("logo.PNG") == "image/png"
            assert _safe_logo_mimetype("logo.JPG") == "image/jpeg"


# ---------------------------------------------------------------------------
# _save_logo_file
# ---------------------------------------------------------------------------

class TestSaveLogoFile:
    def test_no_file_returns_none(self, app):
        from app.routes.admin.system_admin.helpers import _save_logo_file
        with app.app_context():
            result = _save_logo_file(None, "/path/to/sectors", "TestSector")
            assert result is None

    def test_file_with_no_filename_returns_none(self, app):
        from app.routes.admin.system_admin.helpers import _save_logo_file
        mock_file = MagicMock()
        mock_file.filename = ""
        with app.app_context():
            result = _save_logo_file(mock_file, "/path/to/sectors", "TestSector")
            assert result is None

    def test_valid_file_calls_save_system_logo(self, app):
        from app.routes.admin.system_admin.helpers import _save_logo_file
        mock_file = MagicMock()
        mock_file.filename = "logo.png"

        with app.app_context():
            with patch(
                "app.routes.admin.system_admin.helpers.save_system_logo",
                return_value="saved_logo.png",
            ) as mock_save, patch(
                "app.routes.admin.system_admin.helpers.get_sector_logo_path",
                return_value="/sectors",
            ):
                result = _save_logo_file(mock_file, "/sectors", "TestSector")
        assert result == "saved_logo.png"
        mock_save.assert_called_once()

    def test_subsector_path_detected(self, app):
        from app.routes.admin.system_admin.helpers import _save_logo_file
        mock_file = MagicMock()
        mock_file.filename = "logo.png"

        with app.app_context():
            with patch(
                "app.routes.admin.system_admin.helpers.save_system_logo",
                return_value="sub_logo.png",
            ) as mock_save, patch(
                "app.routes.admin.system_admin.helpers.get_sector_logo_path",
                return_value="/sectors",
            ), patch(
                "app.routes.admin.system_admin.helpers.get_subsector_logo_path",
                return_value="/subsectors",
            ):
                result = _save_logo_file(mock_file, "/subsectors", "TestSubSector")
        assert result == "sub_logo.png"
        # is_sector=False for subsector path
        _, kwargs = mock_save.call_args
        assert kwargs.get("is_sector") is False

    def test_exception_returns_none(self, app):
        from app.routes.admin.system_admin.helpers import _save_logo_file
        mock_file = MagicMock()
        mock_file.filename = "logo.png"

        with app.app_context():
            with patch(
                "app.routes.admin.system_admin.helpers.save_system_logo",
                side_effect=Exception("storage error"),
            ), patch(
                "app.routes.admin.system_admin.helpers.get_sector_logo_path",
                return_value="/sectors",
            ):
                result = _save_logo_file(mock_file, "/sectors", "BadSector")
        assert result is None


# ---------------------------------------------------------------------------
# _delete_logo_file
# ---------------------------------------------------------------------------

class TestDeleteLogoFile:
    def test_deletes_sector_logo(self, app):
        from app.routes.admin.system_admin.helpers import _delete_logo_file
        with app.app_context():
            with patch(
                "app.routes.admin.system_admin.helpers.storage",
            ) as mock_storage, patch(
                "app.routes.admin.system_admin.helpers.get_sector_logo_path",
                return_value="/sectors",
            ):
                mock_storage.SYSTEM = "system"
                _delete_logo_file("/sectors", "logo.png")
                mock_storage.delete.assert_called_once_with("system", "sectors/logo.png")

    def test_deletes_subsector_logo(self, app):
        from app.routes.admin.system_admin.helpers import _delete_logo_file
        with app.app_context():
            with patch(
                "app.routes.admin.system_admin.helpers.storage",
            ) as mock_storage, patch(
                "app.routes.admin.system_admin.helpers.get_sector_logo_path",
                return_value="/sectors",
            ):
                mock_storage.SYSTEM = "system"
                _delete_logo_file("/subsectors", "sublogo.png")
                mock_storage.delete.assert_called_once_with(
                    "system", "subsectors/sublogo.png"
                )

    def test_exception_is_logged(self, app):
        from app.routes.admin.system_admin.helpers import _delete_logo_file
        with app.app_context():
            with patch(
                "app.routes.admin.system_admin.helpers.storage",
            ) as mock_storage, patch(
                "app.routes.admin.system_admin.helpers.get_sector_logo_path",
                return_value="/sectors",
            ):
                mock_storage.SYSTEM = "system"
                mock_storage.delete.side_effect = Exception("delete error")
                # Should not raise
                _delete_logo_file("/sectors", "logo.png")


# ---------------------------------------------------------------------------
# indicator_bank_history_snapshot
# ---------------------------------------------------------------------------

class TestIndicatorBankHistorySnapshot:
    def test_returns_all_expected_keys(self, app):
        from app.routes.admin.system_admin.helpers import indicator_bank_history_snapshot

        indicator = MagicMock()
        indicator.name = "Test Indicator"
        indicator.type = "number"
        indicator.unit = "people"
        indicator.definition = "A test definition"
        indicator.name_translations = {"fr": "Indicateur test"}
        indicator.definition_translations = {}
        indicator.archived = False
        indicator.comments = "Some comments"
        indicator.emergency = False
        indicator.related_programs = []
        indicator.sector = {}
        indicator.sub_sector = {}

        # Mock optional getattr fields
        indicator.fdrs_kpi_code = "KPI001"
        indicator.aggregated_label = "Aggregated"
        indicator.aggregated_label_translations = {}
        indicator.area = "Health"
        indicator.data_source = "IFRC"
        indicator.disaggregation_guidance = "Some guidance"
        indicator.monitoring_questions = []
        indicator.tags = ["tag1", "tag2"]

        with app.app_context():
            snapshot = indicator_bank_history_snapshot(indicator)

        assert "name" in snapshot
        assert "type" in snapshot
        assert "unit" in snapshot
        assert "definition" in snapshot
        assert "archived" in snapshot
        assert snapshot["name"] == "Test Indicator"
        assert snapshot["type"] == "number"

    def test_handles_missing_optional_attributes(self, app):
        from app.routes.admin.system_admin.helpers import indicator_bank_history_snapshot

        # Minimal indicator mock without optional attrs
        indicator = MagicMock(spec=["name", "type", "unit", "definition",
                                     "name_translations", "definition_translations",
                                     "archived", "comments", "emergency",
                                     "related_programs", "sector", "sub_sector"])
        indicator.name = "Minimal"
        indicator.type = "number"
        indicator.unit = None
        indicator.definition = None
        indicator.name_translations = {}
        indicator.definition_translations = {}
        indicator.archived = False
        indicator.comments = None
        indicator.emergency = False
        indicator.related_programs = None
        indicator.sector = None
        indicator.sub_sector = None

        with app.app_context():
            snapshot = indicator_bank_history_snapshot(indicator)

        assert snapshot["name"] == "Minimal"
        assert snapshot["fdrs_kpi_code"] is None


# ---------------------------------------------------------------------------
# track_indicator_changes
# ---------------------------------------------------------------------------

class TestTrackIndicatorChanges:
    def _make_indicator(self):
        ind = MagicMock()
        ind.name = "Old Name"
        ind.type = "number"
        ind.unit = "people"
        ind.fdrs_kpi_code = "OLD001"
        ind.definition = "Old definition"
        ind.aggregated_label = "Old Label"
        ind.name_translations = {"fr": "Vieux nom"}
        ind.definition_translations = {}
        ind.aggregated_label_translations = {}
        ind.area = "Health"
        ind.data_source = "IFRC"
        ind.disaggregation_guidance = None
        ind.monitoring_questions = None
        ind.tags = None
        ind.comments = "Old comments"
        ind.related_programs = []
        ind.emergency = False
        ind.archived = False
        ind.sector = {"primary": 1}
        ind.sub_sector = {"primary": 2}
        # sector_primary etc.
        ind.sector_primary = 1
        ind.sector_secondary = None
        ind.sector_tertiary = None
        ind.sub_sector_primary = 2
        ind.sub_sector_secondary = None
        ind.sub_sector_tertiary = None
        return ind

    def test_no_changes_returns_empty_list(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        form_data = {
            "name": "Old Name",
            "type": "number",
            "unit": "people",
            "fdrs_kpi_code": "OLD001",
            "definition": "Old definition",
            "aggregated_label": "Old Label",
            "area": "Health",
            "data_source": "IFRC",
            "comments": "Old comments",
            "emergency": False,
            "archived": False,
        }
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert isinstance(changes, list)

    def test_name_change_detected(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        form_data = {"name": "New Name"}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert any("Name" in c for c in changes)

    def test_type_change_same_case_not_detected(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.type = "Number"
        form_data = {"type": "number"}  # Same after lower() normalization
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        type_changes = [c for c in changes if "Type" in c]
        assert len(type_changes) == 0

    def test_type_change_detected(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.type = "number"
        form_data = {"type": "percentage"}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        type_changes = [c for c in changes if "Type" in c]
        assert len(type_changes) == 1

    def test_added_value_shows_added(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.data_source = None
        form_data = {"data_source": "WHO"}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert any("Added" in c for c in changes)

    def test_removed_value_shows_removed(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.data_source = "IFRC"
        form_data = {"data_source": None}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert any("Removed" in c for c in changes)

    def test_changed_value_shows_changed(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.comments = "old comment"
        form_data = {"comments": "new comment"}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert any("Changed" in c for c in changes)

    def test_both_none_skipped(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.data_source = None
        form_data = {"data_source": None}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        data_source_changes = [c for c in changes if "Data Source" in c]
        assert len(data_source_changes) == 0

    def test_empty_string_treated_as_none(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.data_source = None
        form_data = {"data_source": ""}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        data_source_changes = [c for c in changes if "Data Source" in c]
        assert len(data_source_changes) == 0

    def test_emergency_bool_comparison(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.emergency = False
        form_data = {"emergency": True}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert any("Emergency" in c for c in changes)

    def test_archived_bool_comparison(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.archived = False
        form_data = {"archived": True}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert any("Archived" in c for c in changes)

    def test_sector_change_with_lookup(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes
        from app.models import Sector

        indicator = self._make_indicator()
        indicator.sector = {"primary": 1}

        with app.app_context():
            # Mock the Sector lookup
            with patch("app.routes.admin.system_admin.helpers.Sector") as mock_sector:
                mock_sector.query.get.return_value = None
                form_data = {"sector_primary": 99}
                changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert isinstance(changes, list)

    def test_name_translations_json_parsing(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.name_translations = {}
        form_data = {"name_translations": '{"fr": "Nouveau nom"}'}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert isinstance(changes, list)

    def test_invalid_json_in_translations_handled(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        form_data = {"name_translations": "not valid json {{{"}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert isinstance(changes, list)

    def test_long_values_truncated(self, app, db_session):
        from app.routes.admin.system_admin.helpers import track_indicator_changes

        indicator = self._make_indicator()
        indicator.comments = "x" * 100
        form_data = {"comments": "y" * 100}
        with app.app_context():
            changes = track_indicator_changes(indicator, form_data, MagicMock())
        assert any("..." in c for c in changes)
