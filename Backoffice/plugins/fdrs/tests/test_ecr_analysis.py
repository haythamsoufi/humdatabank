"""Everyone Counts panel rules, translated from the 2026 report pipeline."""

from plugins.fdrs.services.ecr_analysis import build_everyone_counts, build_panel


def _cell(**overrides):
    row = {
        "iso3": "KEN",
        "country_name": "Kenya",
        "region": "Africa",
        "year": 2024,
        "kpi_code": "KPI_PeopleVol",
        "value": "100",
        "numeric_value": 100,
        "imputed_value": None,
        "imputed_numeric_value": None,
        "published_value": "100",
        "published_numeric_value": 100,
        "published_source": "reported",
        "disagg_data": None,
        "published_disagg_data": None,
        "data_not_available": False,
        "not_applicable": False,
    }
    row.update(overrides)
    return row


def test_published_value_is_used_for_a_closed_year():
    panel = build_panel([
        _cell(value="80", numeric_value=80, published_value="100", published_numeric_value=100),
    ])
    assert panel[0]["value"] == 100
    assert panel[0]["provisional"] is False
    assert panel[0]["imputed"] is False


def test_late_submission_prefers_the_reported_value():
    panel = build_panel([
        _cell(
            value="27900000",
            numeric_value=27_900_000,
            published_value="50000",
            published_numeric_value=50_000,
            published_source="imputed",
            kpi_code="KPI_ReachDRR",
        ),
    ])
    assert panel[0]["value"] == 27_900_000
    assert panel[0]["late"] is True
    assert panel[0]["imputed"] is False


def test_open_year_uses_reported_then_imputed_fill():
    reported = build_panel([
        _cell(year=2025, published_value=None, published_numeric_value=None, value="40", numeric_value=40),
    ])
    assert reported[0]["value"] == 40
    assert reported[0]["provisional"] is True
    assert reported[0]["imp_fill"] is False

    filled = build_panel([
        _cell(
            year=2025,
            value=None,
            numeric_value=None,
            published_value=None,
            published_numeric_value=None,
            imputed_value="15",
            imputed_numeric_value=15,
        ),
    ])
    assert filled[0]["value"] == 15
    assert filled[0]["imp_fill"] is True
    assert filled[0]["provisional"] is True


def test_protection_indicators_are_not_filled_from_imputation():
    panel = build_panel([
        _cell(
            kpi_code="KPI_noVolCoveredAI",
            value=None,
            numeric_value=None,
            published_value=None,
            published_numeric_value=None,
            imputed_value="9",
            imputed_numeric_value=9,
        ),
    ])
    assert panel == []


def test_data_not_available_does_not_count_as_reported():
    panel = build_panel([
        _cell(
            year=2025,
            data_not_available=True,
            value="100",
            numeric_value=100,
            published_value=None,
            published_numeric_value=None,
            imputed_value="8",
            imputed_numeric_value=8,
        ),
    ])
    assert panel[0]["value"] == 8
    assert panel[0]["imp_fill"] is True


def test_rolling_mean_needs_three_positive_years_and_latest_official_override():
    rows = []
    for year, value in ((2022, 3), (2023, 6), (2024, 9)):
        rows.append(_cell(
            year=year,
            value=str(value),
            numeric_value=value,
            published_value=str(value),
            published_numeric_value=value,
        ))
    rows.append(_cell(
        year=2024,
        kpi_code="KPI_PeopleVol_RollAvg",
        value="100",
        numeric_value=100,
        published_value="100",
        published_numeric_value=100,
    ))
    panel = build_panel(rows)
    by_year = {row["year"]: row for row in panel}
    assert by_year[2022]["value_roll3"] is None
    assert by_year[2023]["value_roll3"] is None
    assert by_year[2024]["value_roll3"] == 100

    without_official = build_panel(rows[:-1])
    assert next(row["value_roll3"] for row in without_official if row["year"] == 2024) == 6


def test_a_zero_year_breaks_the_rolling_window():
    rows = []
    for year, value in ((2022, 3), (2023, 0), (2024, 9)):
        rows.append(_cell(
            year=year,
            value=str(value),
            numeric_value=value,
            published_value=str(value),
            published_numeric_value=value,
        ))
    panel = {row["year"]: row for row in build_panel(rows)}
    assert panel[2024]["value_roll3"] is None


def test_duplicate_and_extreme_share_and_covid_flags():
    rows = []
    for index, code in enumerate(("KPI_ReachH", "KPI_ReachWASH", "KPI_ReachM")):
        rows.append(_cell(
            kpi_code=code,
            value="8900000",
            numeric_value=8_900_000,
            published_value="8900000",
            published_numeric_value=8_900_000,
        ))
        other = 1_000 + index
        rows.append(_cell(
            iso3="UGA",
            country_name="Uganda",
            kpi_code=code,
            value=str(other),
            numeric_value=other,
            published_value=str(other),
            published_numeric_value=other,
        ))
    rows.append(_cell(
        iso3="CHN",
        country_name="China",
        region="Asia Pacific",
        year=2020,
        kpi_code="KPI_ReachDRER",
        value="64",
        numeric_value=64,
        published_value="64",
        published_numeric_value=64,
    ))
    rows.append(_cell(
        iso3="KEN",
        year=2020,
        kpi_code="KPI_ReachDRER",
        value="36",
        numeric_value=36,
        published_value="36",
        published_numeric_value=36,
    ))
    panel = build_panel(rows)
    duplicates = [row for row in panel if row["flag_duplicate_within_ns"] and row["iso3"] == "KEN"]
    assert len(duplicates) == 3
    extreme = [row for row in panel if row["flag_extreme_share"] and row["kpi_code"] == "KPI_ReachDRER"]
    assert {(row["iso3"], row["year"]) for row in extreme} == {("CHN", 2020)}
    assert any(row["flag_covid_year"] and row["iso3"] == "KEN" for row in panel)


def test_summary_keeps_the_open_year_out_of_the_settled_snapshot():
    observations = []
    for year, value in ((2022, 30), (2023, 30), (2024, 30)):
        observations.append(_cell(
            year=year,
            value=str(value),
            numeric_value=value,
            published_value=str(value),
            published_numeric_value=value,
            published_disagg_data={"mode": "sex", "values": {"female": 10, "male": 20}},
        ))
    observations.append(_cell(
        iso3="UGA",
        country_name="Uganda",
        year=2024,
        value="10",
        numeric_value=10,
        published_value="10",
        published_numeric_value=10,
        published_disagg_data={"mode": "sex", "values": {"female": 8, "male": 2}},
    ))
    for year, value in ((2022, 5), (2023, 5)):
        observations.append(_cell(
            iso3="UGA",
            country_name="Uganda",
            year=year,
            value=str(value),
            numeric_value=value,
            published_value=str(value),
            published_numeric_value=value,
        ))
    observations.append(_cell(
        year=2024,
        kpi_code="KPI_PStaff",
        value="3",
        numeric_value=3,
        published_value="3",
        published_numeric_value=3,
    ))
    observations.append(_cell(
        year=2025,
        value="12",
        numeric_value=12,
        published_value=None,
        published_numeric_value=None,
    ))
    observations.append(_cell(
        year=2024,
        kpi_code="KPI_ReachH",
        value="0",
        numeric_value=0,
        published_value="0",
        published_numeric_value=0,
    ))
    observations.append(_cell(
        iso3="UGA",
        country_name="Uganda",
        year=2024,
        kpi_code="KPI_ReachH",
        value="20",
        numeric_value=20,
        published_value="20",
        published_numeric_value=20,
    ))
    observations.append(_cell(
        iso3="RWA",
        country_name="Rwanda",
        region="Africa",
        year=2024,
        kpi_code="KPI_ReachH",
        value="40",
        numeric_value=40,
        published_value="40",
        published_numeric_value=40,
    ))

    summary = build_everyone_counts(observations, template_id=21)
    assert summary["scope"]["settled_year"] == 2024
    assert summary["scope"]["open_year"] == 2025
    assert summary["snapshot"]["year"] == 2024
    assert summary["snapshot"]["provisional"] is False
    assert summary["snapshot"]["rolling_volunteers"] == 30 + (5 + 5 + 10) / 3
    assert summary["snapshot"]["median_female_share"] == (10 / 30 + 8 / 10) / 2
    assert summary["snapshot"]["societies_with_sex"] == 2
    assert summary["snapshot"]["median_volunteers_per_staff"] == 10
    health = next(item for item in summary["reach"] if item["code"] == "KPI_ReachH")
    assert health["societies"] == 2
    assert health["median"] == 30
    assert summary["years"][-1]["provisional"] is True


def test_female_share_uses_the_published_sex_split():
    panel = build_panel([
        _cell(
            published_disagg_data={"mode": "sex", "values": {"female": 30, "male": 70}},
            disagg_data={"mode": "sex", "values": {"female": 1, "male": 1}},
        ),
    ])
    assert panel[0]["female"] == 30
    assert panel[0]["male"] == 70


def test_age_bands_need_five_societies_and_weight_each_society_equally():
    observations = []
    for index in range(5):
        observations.append(_cell(
            iso3=f"A{index:02d}",
            country_name=f"Society {index}",
            published_disagg_data={
                "mode": "sex_age",
                "values": {"female_18_29": 30, "male_18_29": 70, "female_30_39": 0, "male_6_12": 0},
            },
        ))
    observations.append(_cell(
        iso3="B01",
        country_name="Other",
        published_disagg_data={
            "mode": "age",
            "values": {"18-29": 25, "6-12": 75},
        },
    ))
    summary = build_everyone_counts(observations)
    bands = {item["band"]: item["mean_share"] for item in summary["age_bands"]}
    assert summary["age_bands"][0]["societies"] == 6
    assert abs(bands["6–12"] - 0.75 / 6) < 1e-9
    assert abs(bands["18–29"] - (1 + 1 + 1 + 1 + 1 + 0.25) / 6) < 1e-9


def test_density_uses_the_rolling_mean_and_carries_population_only_forward():
    observations = []
    for year in (2021, 2022, 2023, 2024):
        observations.append(_cell(
            year=year,
            value="300",
            numeric_value=300,
            published_value="300",
            published_numeric_value=300,
        ))
    observations.append(_cell(
        year=2025,
        value="300",
        numeric_value=300,
        published_value=None,
        published_numeric_value=None,
    ))
    observations.append(_cell(
        iso3="UGA",
        country_name="Uganda",
        year=2024,
        value="900",
        numeric_value=900,
        published_value="900",
        published_numeric_value=900,
    ))
    world_bank = {
        "fetched_at": "2026-10-05T00:00:00+00:00",
        "population": [
            {"iso3": "KEN", "year": 2022, "population": 1_000_000},
            {"iso3": "KEN", "year": 2024, "population": 1_000_000},
            {"iso3": "UGA", "year": 2024, "population": 2_000_000},
        ],
        "income_groups": [{"iso3": "KEN", "income_group": "LM"}],
        "gni_per_capita": [{"iso3": "KEN", "year": 2024, "gni_per_capita_usd": 2000}],
    }
    summary = build_everyone_counts(observations, world_bank=world_bank)
    by_year = {item["year"]: item for item in summary["volunteer_density"]}
    assert 2023 not in by_year
    assert by_year[2024]["median_per_million"] == 300
    assert by_year[2024]["income_group"] == "LM"
    assert by_year[2024]["societies"] == 1
    assert by_year[2024]["population_carried_forward"] is False
    assert by_year[2025]["population_carried_forward"] is True
    assert by_year[2025]["median_per_million"] == 300
    assert summary["external"]["world_bank"]["available"] is True
    assert summary["external"]["world_bank"]["gni_countries"] == 1
