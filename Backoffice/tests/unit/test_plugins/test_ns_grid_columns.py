"""Plugin columns on the National Societies table."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.plugins.base import NationalSocietyGridColumn
from app.plugins.manager import _national_society_column_value

pytestmark = [pytest.mark.unit]


def test_column_value_formats_dates_numbers_and_blanks():
    society = SimpleNamespace(admission_date=date(1965, 8, 26), website="  ", latitude=0.0, longitude="nope")
    assert (
        _national_society_column_value(
            society, NationalSocietyGridColumn("admission_date", "Admission date", kind="date")
        )
        == "1965-08-26"
    )
    assert (
        _national_society_column_value(society, NationalSocietyGridColumn("website", "Website", kind="url")) is None
    )
    assert (
        _national_society_column_value(society, NationalSocietyGridColumn("latitude", "Latitude", kind="number"))
        == 0.0
    )
    assert (
        _national_society_column_value(society, NationalSocietyGridColumn("longitude", "Longitude", kind="number"))
        is None
    )


def test_manager_drops_reserved_and_invalid_fields(app):
    manager = app.plugin_manager
    plugin = manager.get_plugin("fdrs")
    original = plugin.get_national_society_columns

    def _extra():
        return [
            NationalSocietyGridColumn("name", "Name"),
            NationalSocietyGridColumn("not a field", "Bad"),
            NationalSocietyGridColumn("fdrs_don_code", "DON code"),
        ]

    plugin.get_national_society_columns = _extra
    try:
        with app.app_context():
            columns, values = manager.national_society_columns(
                [SimpleNamespace(id=4, fdrs_don_code="DKEN001")]
            )
    finally:
        plugin.get_national_society_columns = original

    assert [column["field"] for column in columns] == ["fdrs_don_code"]
    assert values[4]["fdrs_don_code"] == "DKEN001"
