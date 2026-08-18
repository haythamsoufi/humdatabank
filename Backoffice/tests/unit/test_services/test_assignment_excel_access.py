from types import SimpleNamespace

from app.services.imports.assignment_excel_access import (
    assignment_uses_export_excel,
    assignment_uses_import_excel,
    assignment_uses_unified_country_plan_excel,
    assignment_uses_upr_country_reporting_excel,
    populate_standard_excel_flags_from_legacy,
    resolve_assignment_excel_ui,
    sync_assignment_custom_excel_flags,
)
from app.utils.data_quality_constants import (
    UPR_PLANNING_TEMPLATE_ID,
    UPR_REPORTING_TEMPLATE_ID,
)


def _assignment(**kwargs):
    defaults = {
        "template_id": 21,
        "enable_export_excel": False,
        "enable_import_excel": False,
        "enable_upr_country_reporting_excel": False,
        "enable_unified_country_plan_excel": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestAssignmentExcelAccess:
    def test_generic_export_for_standard_template(self):
        assigned = _assignment(enable_export_excel=True)
        assert assignment_uses_export_excel(assigned) is True
        assert assignment_uses_upr_country_reporting_excel(assigned) is False
        assert resolve_assignment_excel_ui(assigned) == {
            "mode": "generic",
            "show_export": True,
            "show_import": False,
        }

    def test_template_33_uses_upr_workbook(self):
        assigned = _assignment(
            template_id=UPR_REPORTING_TEMPLATE_ID,
            enable_export_excel=True,
            enable_import_excel=True,
        )
        assert assignment_uses_upr_country_reporting_excel(assigned) is True
        assert assignment_uses_export_excel(assigned) is False
        assert assignment_uses_import_excel(assigned) is False
        assert resolve_assignment_excel_ui(assigned)["mode"] == "upr"

    def test_template_24_uses_ucp_workbook(self):
        assigned = _assignment(
            template_id=UPR_PLANNING_TEMPLATE_ID,
            enable_import_excel=True,
        )
        assert assignment_uses_unified_country_plan_excel(assigned) is True
        assert assignment_uses_import_excel(assigned) is False
        ui = resolve_assignment_excel_ui(assigned)
        assert ui["mode"] == "ucp"
        assert ui["show_export"] is False
        assert ui["show_import"] is True

    def test_legacy_upr_flag_still_enables_template_33(self):
        assigned = _assignment(
            template_id=UPR_REPORTING_TEMPLATE_ID,
            enable_upr_country_reporting_excel=True,
        )
        assert assignment_uses_upr_country_reporting_excel(assigned) is True
        assert resolve_assignment_excel_ui(assigned)["show_export"] is True
        assert resolve_assignment_excel_ui(assigned)["show_import"] is True

    def test_template_33_without_excel_flags_is_off(self):
        assigned = _assignment(template_id=UPR_REPORTING_TEMPLATE_ID)
        assert assignment_uses_upr_country_reporting_excel(assigned) is False
        assert resolve_assignment_excel_ui(assigned)["mode"] is None

    def test_sync_writes_legacy_columns_from_standard_flags(self):
        assigned = _assignment(
            template_id=UPR_REPORTING_TEMPLATE_ID,
            enable_export_excel=True,
        )
        sync_assignment_custom_excel_flags(assigned)
        assert assigned.enable_upr_country_reporting_excel is True
        assert assigned.enable_unified_country_plan_excel is False

    def test_populate_standard_flags_from_legacy(self):
        assigned = _assignment(
            template_id=UPR_PLANNING_TEMPLATE_ID,
            enable_unified_country_plan_excel=True,
        )
        form = SimpleNamespace(
            enable_export_excel=SimpleNamespace(data=False),
            enable_import_excel=SimpleNamespace(data=False),
        )
        populate_standard_excel_flags_from_legacy(assigned, form)
        assert form.enable_export_excel.data is True
        assert form.enable_import_excel.data is True
