"""Service-income estimate: average of the two prior years, then the residual."""

from plugins.fdrs.services.service_income_analysis import (
    collapse_observations,
    service_income_from_disagg,
    summarize_service_income,
)


def test_service_cell_reads_matrix_funding_column():
    disagg = {
        "mode": "matrix",
        "values": {
            "Home Government_Funding": 10,
            "Service income_Funding": 42,
            "Income generating activity_Funding": 7,
        },
    }
    assert service_income_from_disagg(disagg) == 42
    assert service_income_from_disagg({"mode": "matrix", "values": {}}) is None


def test_imputed_total_keeps_a_reported_service_cell_and_blank_service_is_zero():
    rows = collapse_observations(
        [
            {
                "country_id": 1,
                "country_name": "Example",
                "year": 2025,
                "kind": "income",
                "value": None,
                "numeric_value": None,
                "imputed_value": "1000",
                "imputed_numeric_value": 1000,
            },
            {
                "country_id": 1,
                "country_name": "Example",
                "year": 2025,
                "kind": "service_matrix",
                "disagg_data": {"mode": "matrix", "values": {"Service income_Funding": 999}},
            },
        ]
    )
    assert rows[0]["income_source"] == "imputed"
    assert rows[0]["total_income"] == 1000
    assert rows[0]["service_income"] == 999
    assert rows[0]["service_reported"] is True

    blank = collapse_observations(
        [
            {
                "country_id": 3,
                "country_name": "Imputed only",
                "year": 2025,
                "kind": "income",
                "value": "",
                "imputed_value": "250",
                "imputed_numeric_value": 250,
            }
        ]
    )
    assert blank[0]["income_source"] == "imputed"
    assert blank[0]["service_income"] == 0
    assert blank[0]["service_reported"] is False


def test_blank_service_counts_as_zero_and_reported_total_wins():
    rows = collapse_observations(
        [
            {
                "country_id": 2,
                "country_name": "Reported NS",
                "year": 2024,
                "kind": "income",
                "value": "500",
                "numeric_value": 500,
                "imputed_value": "9999",
                "imputed_numeric_value": 9999,
            }
        ]
    )
    assert rows[0]["income_source"] == "reported"
    assert rows[0]["total_income"] == 500
    assert rows[0]["service_income"] == 0
    assert rows[0]["service_reported"] is False


def test_closed_round_average_is_a_reference_not_an_open_year_estimate():
    """The 2023–2024 average is the closed-round reference; 2025 keeps its reported service."""
    yearly = [
        (2023, 34_862_895_440, 9_337_282_941),
        (2024, 35_482_004_041, 9_329_175_482),
        (2025, 31_780_348_035, 8_041_778_673),
    ]
    rows = [
        {
            "country_id": year,
            "year": year,
            "total_income": total,
            "income_source": "reported",
            "expenditure": None,
            "service_income": service,
            "service_reported": True,
        }
        for year, total, service in yearly
    ]
    summary = summarize_service_income(rows)
    reference = summary["reference"]
    expected_reference = (9_337_282_941 + 9_329_175_482) / 2
    assert reference["open_year"] == 2025
    assert reference["baseline_years"] == [2023, 2024]
    assert reference["reference_service_income"] == expected_reference
    assert reference["income_minus_reference"] == 31_780_348_035 - expected_reference
    assert reference["reported_service_income"] == 8_041_778_673
    assert reference["service_difference"] == 8_041_778_673 - expected_reference
    assert "estimated_service_income" not in reference

    by_year = {row["year"]: row for row in summary["years"]}
    assert by_year[2024]["other_income"] == 35_482_004_041 - 9_329_175_482
    assert by_year[2025]["is_open_round"] is True
    assert by_year[2024]["is_open_round"] is False
    assert by_year[2025]["service_change"] == 8_041_778_673 - 9_329_175_482


def test_published_only_uses_the_published_matrix_snapshot():
    observations = [
        {
            "country_id": 1,
            "country_name": "Example",
            "year": 2025,
            "kind": "income",
            "value": "1000",
            "numeric_value": 1000,
        },
        {
            "country_id": 1,
            "country_name": "Example",
            "year": 2025,
            "kind": "service_matrix",
            "disagg_data": {"Service income_Funding": 999, "Home Government_Funding": 1},
            "published_disagg_data": {"Service income_Funding": 100},
        },
    ]
    live = collapse_observations(observations)
    published = collapse_observations(observations, published_only=True)
    assert live[0]["service_income"] == 999
    assert published[0]["service_income"] == 100
    assert published[0]["total_income"] == 1000

    unpublished = collapse_observations(
        [
            observations[0],
            {
                "country_id": 1,
                "country_name": "Example",
                "year": 2025,
                "kind": "service_matrix",
                "disagg_data": {"Service income_Funding": 999},
                "published_disagg_data": None,
            },
        ],
        published_only=True,
    )
    assert unpublished[0]["service_income"] == 0
    assert unpublished[0]["service_reported"] is False
