"""Tests for the bulk UPR Excel importer's entity-activity-log writes.

``run_upr_import`` never wrote ``entity_activity_log`` — the per-assignment
importer in ``assignment_routes.py`` always did (``summary_key``
``activity.upr_excel_import``), so a focal point's activity feed stayed empty
after a bulk import (see
``docs/investigations/2026-09-18-bilateral-matrix-overwrite.md``, "Still
open"). ``_log_bulk_import_activity`` closes that gap; these tests cover it in
isolation (no real DB — ``AssignmentEntityStatus`` and
``log_entity_activities_bulk`` are mocked at their import sites).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_HERE = Path(__file__).resolve()
_plugin_scripts = _HERE.parents[1] / "scripts"
if str(_plugin_scripts) not in sys.path:
    sys.path.insert(0, str(_plugin_scripts))

import import_upr_excel_data as imp  # noqa: E402


@pytest.mark.unit
class TestLogBulkImportActivity:
    def test_no_user_id_is_a_silent_noop(self):
        # CLI / background runs with no acting user: EntityActivityLog.user_id is
        # required, so this must no-op rather than raise or warn-spam logs.
        assert imp._log_bulk_import_activity({1, 2}, {1: 3, 2: 1}, [24], user_id=None) == 0

    def test_no_touched_aes_ids_is_a_noop(self):
        assert imp._log_bulk_import_activity(set(), {}, [24], user_id=7) == 0

    def test_builds_one_entry_per_touched_aes_with_correct_counts(self):
        fake_rows = [
            (101, "country", 55),
            (102, "ns_branch", 9),
        ]
        mock_aes_cls = MagicMock()
        mock_aes_cls.query.filter.return_value.with_entities.return_value.all.return_value = fake_rows

        with patch("app.models.assignments.AssignmentEntityStatus", mock_aes_cls), \
             patch("app.services.notification.core.log_entity_activities_bulk") as mock_bulk:
            mock_bulk.return_value = 2
            result = imp._log_bulk_import_activity(
                {101, 102}, {101: 5, 102: 2}, [24, 22], user_id=42
            )

        assert result == 2
        mock_bulk.assert_called_once()
        entries = mock_bulk.call_args[0][0]
        assert len(entries) == 2
        by_aes = {e["assignment_id"]: e for e in entries}

        assert by_aes[101]["entity_type"] == "country"
        assert by_aes[101]["entity_id"] == 55
        assert by_aes[101]["summary_params"]["count"] == 5

        assert by_aes[102]["entity_type"] == "ns_branch"
        assert by_aes[102]["entity_id"] == 9
        assert by_aes[102]["summary_params"]["count"] == 2

        assert all(e["user_id"] == 42 for e in entries)
        assert all(e["summary_key"] == "activity.upr_excel_import" for e in entries)
        assert all(e["activity_category"] == "form" for e in entries)
        names = by_aes[101]["summary_params"]["template"]
        assert "Unified Country Plan" in names
        assert "Annual Planning" in names

    def test_db_lookup_failure_is_swallowed_not_raised(self):
        mock_aes_cls = MagicMock()
        mock_aes_cls.query.filter.side_effect = RuntimeError("db down")

        with patch("app.models.assignments.AssignmentEntityStatus", mock_aes_cls):
            # Must not raise — a notification/activity-log failure must never
            # fail the import itself.
            result = imp._log_bulk_import_activity({1}, {1: 1}, [24], user_id=5)

        assert result == 0

    def test_only_touched_templates_are_named(self):
        mock_aes_cls = MagicMock()
        mock_aes_cls.query.filter.return_value.with_entities.return_value.all.return_value = [
            (1, "country", 10)
        ]

        with patch("app.models.assignments.AssignmentEntityStatus", mock_aes_cls), \
             patch("app.services.notification.core.log_entity_activities_bulk") as mock_bulk:
            imp._log_bulk_import_activity({1}, {1: 1}, [33], user_id=1)

        entries = mock_bulk.call_args[0][0]
        assert entries[0]["summary_params"]["template"] == "Reporting - Country"


@pytest.mark.unit
class TestRunUprImportActivityLoggingGate:
    """Source tripwire: ``run_upr_import`` must gate the activity-log call on
    ``not dry_run`` and must route it through the ``change_recorder`` wrapper
    (not the raw caller-supplied one) so touched AES ids are actually tracked.

    A full real-DB ``run_upr_import()`` integration test does not exist anywhere
    in this suite today (every existing UPR import test exercises
    ``transform_to_import_rows`` or lower, never the full upsert); this is a
    lightweight regression check in lieu of that heavier fixture work.
    """

    def test_activity_logging_call_is_gated_on_not_dry_run(self):
        import inspect

        source = inspect.getsource(imp.run_upr_import)
        assert "if not dry_run and touched_aes_ids:" in source
        assert "_log_bulk_import_activity(" in source

    def test_change_recorder_passed_to_upsert_is_the_tracking_wrapper(self):
        import inspect

        source = inspect.getsource(imp.run_upr_import)
        # The caller-supplied change_recorder must still be invoked (regression
        # guard for the undo/audit change log), just via the wrapper that also
        # records touched_aes_ids/aes_row_counts for activity logging.
        assert "change_recorder=_track_and_record," in source
        assert "if change_recorder:" in source
        assert "change_recorder(entry)" in source
