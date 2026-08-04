import pytest

from app.services.public_analytics_service import resolve_indicator_query
from app.services.security.public_data_access import (
    public_include_dimensions,
    slim_public_data_rows,
)


class TestPublicDataSlimHelpers:
    def test_public_include_dimensions_default_false(self):
        assert not public_include_dimensions({})
        assert not public_include_dimensions({"indicator_bank_id": "1"})
        assert public_include_dimensions({"include_dimensions": "true"})

    def test_slim_public_data_rows(self):
        rows = slim_public_data_rows(
            [
                {
                    "id": 1,
                    "period_name": "Annual 2023",
                    "country_id": 5,
                    "num_value": 10,
                    "data_status": "available",
                    "disaggregation_data": {"big": "payload"},
                }
            ]
        )
        assert rows == [
            {
                "id": 1,
                "period_name": "Annual 2023",
                "country_id": 5,
                "num_value": 10,
                "data_status": "available",
            }
        ]


@pytest.mark.unit
class TestResolveIndicatorQuery:
    def test_volunteers_maps_to_canonical_id(self, app):
        with app.app_context():
            out = resolve_indicator_query("Number of volunteers")
        assert out["best_match"]["id"] == 724
