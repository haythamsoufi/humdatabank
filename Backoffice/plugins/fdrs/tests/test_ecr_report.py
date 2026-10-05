"""Catalogue and calculations for the Everyone Counts chapter pages."""

from plugins.fdrs.services.ecr_analysis import build_everyone_counts, build_panel
from plugins.fdrs.services.ecr_report import build_chapters

PRINTED = {
    "c2-wgi-income",
    "c3-volglobshare",
    "c3-volsn",
    "c3-volsroll-total-n",
    "c3-volsglob-excl",
    "c3-volsperpop",
    "c3-volsperpop-wgi",
    "c3-voltarget-area",
    "c3-volpop-top10",
    "c3-vsratio-4inc",
    "c3-pyramidyear-ns",
    "c3-pyramidyear-staff-ns",
    "c3-leaderssex",
    "c3-agedist-ns",
    "c3-volage-bar-pop-4inc",
    "c3-3rresp-combined",
    "c3-3rresil-combined",
    "c3-3rrespect-combined",
    "c3-reach2025-cross",
    "c3-reach2025-response",
    "c3-reach2025-resilience",
    "c3-reach2025-respect",
    "c3-volreach-dumbbell",
    "c3-branchreach-dumbbell",
    "c3-branchreach-adj-dumbbell",
    "c3-treemig",
    "c3-treemig-health",
    "c3-treemig-wash",
    "c4-polycrisis-mix",
    "c4-polycrisis-share",
    "c4-vpm-ocac-bands",
    "c6-eng-model",
    "c5-volvalglobalbasis",
    "c6-awsdtrend",
    "c6-deathsmech",
    "c6-deathsources",
    "c6-deathsmechera",
    "c6-insurance",
    "c6-insurancetrend",
    "c4-tab-polycrisis-who",
    "c5-tab-volvalamericas",
    "c5-tab-volvalamericastot",
    "c5-tab-volvalglobaltot",
    "c3-tab-reach-slopes",
}


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


def _find(chapters, output_id):
    for chapter in chapters:
        for output in chapter["outputs"]:
            if output["id"] == output_id:
                return output
    raise AssertionError(output_id)


def _world_bank():
    return {
        "fetched_at": "2026-10-05T00:00:00+00:00",
        "population": [
            {"iso3": "KEN", "year": 2020, "population": 10_000_000},
            {"iso3": "KEN", "year": 2024, "population": 10_000_000},
            {"iso3": "IND", "year": 2024, "population": 1_000_000_000},
            {"iso3": "UGA", "year": 2024, "population": 10_000_000},
        ],
        "income_groups": [
            {"iso3": "KEN", "income_group": "L"},
            {"iso3": "IND", "income_group": "LM"},
            {"iso3": "UGA", "income_group": "L"},
        ],
        "gni_per_capita": [],
    }


def test_catalogue_lists_every_printed_output():
    chapters = build_chapters([])
    printed = [
        output["id"]
        for chapter in chapters
        for output in chapter["outputs"]
        if str(output["number"]).startswith(("Figure", "Table"))
    ]
    assert len(printed) == 44
    assert set(printed) == PRINTED
    assert len(chapters) == 8
    assert _find(chapters, "c2-wgi-income")["available"] is False
    assert _find(chapters, "c3-branchreach-adj-dumbbell")["available"] is False
    assert _find(chapters, "c6-eng-model")["available"] is False
    assert _find(chapters, "c6-deathsmech")["available"] is False


def test_figure_2_4_leaves_out_the_five_largest_societies():
    panel = build_panel([
        _cell(iso3="KEN", country_name="Kenya"),
        _cell(
            iso3="IND",
            country_name="India",
            value="500",
            numeric_value=500,
            published_value="500",
            published_numeric_value=500,
        ),
    ])
    figure = _find(build_chapters(panel), "c3-volsglob-excl")
    by_name = {series["name"]: series["points"][-1]["value"] for series in figure["series"]}
    assert by_name["All reporting Societies"] == 600
    assert by_name["Without India, China, Iran, the Philippines and Nigeria"] == 100


def test_density_band_is_volunteers_per_million():
    observations = []
    for year in (2018, 2019, 2020):
        observations.append(_cell(
            year=year,
            value="200000",
            numeric_value=200_000,
            published_value="200000",
            published_numeric_value=200_000,
        ))
    panel = build_panel(observations)
    figure = _find(build_chapters(panel, world_bank=_world_bank()), "c3-voltarget-area")
    assert figure["available"] is True
    assert figure["rows"][0]["category"] == "Low income"
    assert figure["rows"][0]["counts"]["2% or more"] == 1


def test_insurance_status_and_coverage():
    panel = build_panel([
        _cell(),
        _cell(kpi_code="KPI_noVolCoveredAI", value="40", numeric_value=40, published_value="40", published_numeric_value=40),
        _cell(iso3="UGA", country_name="Uganda", value="50", numeric_value=50),
        _cell(
            iso3="RWA",
            country_name="Rwanda",
            value="10",
            numeric_value=10,
        ),
        _cell(
            iso3="RWA",
            kpi_code="KPI_noVolCoveredAI",
            value="0",
            numeric_value=0,
            published_value="0",
            published_numeric_value=0,
        ),
    ])
    chapters = build_chapters(panel, world_bank=_world_bank())
    status = _find(chapters, "c6-insurance")
    counts = status["rows"][0]["counts"]
    assert counts["Insured"] == 1
    assert counts["Reported none"] == 1
    assert counts["Did not report"] == 1
    coverage = _find(chapters, "c6-insurancetrend")
    low = next(series for series in coverage["series"] if series["name"] == "Low income")
    # Kenya 40/100 and Uganda did not report, so only Kenya remains in the low-income mean.
    # Rwanda has no income group, so its zero cover is left out.
    assert low["points"][0]["value"] == 0.4


def test_leader_sex_is_the_share_of_female_answers():
    panel = build_panel([_cell(year=2020)])
    chapters = build_chapters(
        panel,
        world_bank=_world_bank(),
        leaders=[
            {"iso3": "KEN", "year": 2020, "role": "President", "sex": "Female"},
            {"iso3": "IND", "year": 2020, "role": "Secretary General", "sex": "Male"},
        ],
    )
    figure = _find(chapters, "c3-leaderssex")
    overall = next(series for series in figure["series"] if series["name"] == "All National Societies")
    assert overall["points"][0]["value"] == 0.5


def test_staff_sex_breakdown_is_kept():
    panel = build_panel([
        _cell(
            kpi_code="KPI_PStaff",
            published_disagg_data={"mode": "sex", "values": {"female": 3, "male": 1}},
        ),
    ])
    assert panel[0]["female"] == 3
    assert panel[0]["male"] == 1
    figure = _find(build_chapters(panel), "c3-pyramidyear-staff-ns")
    assert figure["series"][0]["points"][0]["value"] == 0.75


def test_one_unpublished_society_does_not_drop_the_year():
    panel = build_panel([
        _cell(iso3="KEN"),
        _cell(iso3="UGA", country_name="Uganda"),
        _cell(
            iso3="RWA",
            country_name="Rwanda",
            value="10",
            numeric_value=10,
            published_value=None,
            published_numeric_value=None,
        ),
    ])
    summary = build_everyone_counts([
        _cell(iso3="KEN"),
        _cell(iso3="UGA", country_name="Uganda"),
        _cell(
            iso3="RWA",
            country_name="Rwanda",
            value="10",
            numeric_value=10,
            published_value=None,
            published_numeric_value=None,
        ),
    ])
    assert summary["scope"]["settled_year"] == 2024
    figure = _find(build_chapters(panel), "c3-volsglob-excl")
    assert figure["series"][0]["points"][0]["year"] == 2024


def test_summary_includes_chapters():
    summary = build_everyone_counts([_cell()], template_id=21)
    assert summary["chapters"][0]["id"] == "volunteers"
    assert _find(summary["chapters"], "fdrs-deaths-duty")["number"] == "FDRS"
