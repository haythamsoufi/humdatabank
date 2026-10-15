"""UPR Excel imports must not write entity activity log rows.

Those rows showed up in the dashboard Recent Activities feed. The import still
records an undo/audit change log; it does not write ``EntityActivityLog``.
"""

import inspect
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_plugin_scripts = _HERE.parents[1] / "scripts"
if str(_plugin_scripts) not in sys.path:
    sys.path.insert(0, str(_plugin_scripts))

import import_upr_excel_data as imp  # noqa: E402


@pytest.mark.unit
class TestUprImportDoesNotLogEntityActivity:
    def test_bulk_import_does_not_write_entity_activity(self):
        source = inspect.getsource(imp.run_upr_import)
        assert "_log_bulk_import_activity" not in source
        assert "log_entity_activity" not in source
        assert "change_recorder=change_recorder," in source

    def test_assignment_import_routes_do_not_write_entity_activity(self):
        routes = (_HERE.parents[1] / "excel" / "assignment_routes.py").read_text(encoding="utf-8")
        assert "log_entity_activity" not in routes
        assert "activity.upr_excel_import" not in routes
