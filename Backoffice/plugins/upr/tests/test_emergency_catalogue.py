"""UPR emergency catalogue: applicable appeals marked covered or not."""

from plugins.upr.validation.emergency_catalogue import (
    _section_figures,
    annualised_amounts,
    appeal_duration_years,
    assemble_catalogue,
    attach_group_names,
    funding_check_status,
    people_reached_amounts,
    positive_requested,
)
from plugins.upr.validation.emergency_coverage import EmergencyCoverage, EmergencyRef, FieldEmergencyCoverage


def _coverage(applicable, missing=(), not_applicable=(), no_longer=()):
    return EmergencyCoverage(
        applicable=tuple(applicable),
        missing=tuple(missing),
        not_applicable=tuple(not_applicable),
        no_longer_applicable=tuple(no_longer),
    )


def test_each_applicable_appeal_is_marked_on_every_list_that_includes_it():
    appeals = FieldEmergencyCoverage(
        section_name="Emergency Appeals in 2027",
        coverage=_coverage(
            [
                EmergencyRef("MDRAF019", "MDRAF019 Afghanistan - Earthquake"),
                EmergencyRef("MDRAF018", "MDRAF018 Afghanistan - Population mvt from Pakistan"),
            ],
            missing=[EmergencyRef("MDRAF018", "MDRAF018 Afghanistan - Population mvt from Pakistan")],
        ),
    )
    funding = FieldEmergencyCoverage(
        section_name="Funding Requirements for 2027",
        coverage=_coverage(
            [EmergencyRef("MDRAF019", "MDRAF019 Afghanistan - Earthquake")],
        ),
    )

    result = assemble_catalogue([{
        "country_id": 1,
        "country_name": "Afghanistan",
        "iso3": "AFG",
        "fields": [appeals, funding],
    }])
    by_code = {row["code"]: row for row in result["rows"]}

    assert result["sections"] == [
        "Emergency Appeals in 2027",
        "Funding Requirements for 2027",
    ]
    assert by_code["MDRAF019"]["name"] == "Afghanistan - Earthquake"
    assert by_code["MDRAF019"]["status"] == "covered"
    assert by_code["MDRAF019"]["marks"] == {
        "Emergency Appeals in 2027": "covered",
        "Funding Requirements for 2027": "covered",
    }
    assert by_code["MDRAF018"]["status"] == "missing"
    assert by_code["MDRAF018"]["marks"] == {"Emergency Appeals in 2027": "missing"}
    assert result["summary"] == {"applicable": 2, "covered": 1, "missing": 1, "countries": 1}


def test_an_appeal_saved_outside_the_calculated_list_stays_out_of_the_applicable_count():
    field = FieldEmergencyCoverage(
        section_name="Emergency Appeals in 2027",
        coverage=_coverage(
            [EmergencyRef("MDRUG052", "MDRUG052 Uganda - Mpox Epidemic")],
            not_applicable=[EmergencyRef("MDRS1001", "Sudan Crisis (MDRS1001)")],
        ),
    )

    result = assemble_catalogue([{
        "country_id": 2,
        "country_name": "Uganda",
        "iso3": "UGA",
        "fields": [field],
    }])
    by_code = {row["code"]: row for row in result["rows"]}

    assert by_code["MDRUG052"]["status"] == "covered"
    assert by_code["MDRS1001"]["status"] == "not_applicable"
    assert by_code["MDRS1001"]["part_of"] == ""
    assert result["summary"]["applicable"] == 1
    assert result["summary"]["covered"] == 1
    assert result["summary"]["missing"] == 0


def test_child_appeals_keep_their_grouped_parent():
    field = FieldEmergencyCoverage(
        section_name="People to be reached in 2027",
        coverage=_coverage([
            EmergencyRef("MDRAF019", "MDRAF019 Afghanistan - Earthquake"),
            EmergencyRef(
                "MDRCD051",
                "MDRCD051 DR Congo - Ebola Virus Disease Outbreak (part of MDRS1007)",
            ),
            EmergencyRef("MDRUG058", "MDRUG058 Uganda - Ebola Virus Disease Outbreak (part of MDRS1007)"),
        ]),
    )
    result = assemble_catalogue([
        {"country_id": 1, "country_name": "Afghanistan", "iso3": "AFG", "fields": [field]},
        {"country_id": 3, "country_name": "Uganda", "iso3": "UGA", "fields": [field]},
    ])
    attach_group_names(result["rows"], {"MDRS1007": "EVD Regional Appeal"})
    by_code = {row["code"]: row for row in result["rows"]}

    assert by_code["MDRAF019"]["appeal_kind"] == "single"
    assert by_code["MDRCD051"]["appeal_kind"] == "child"
    assert by_code["MDRCD051"]["group_code"] == "MDRS1007"
    assert by_code["MDRCD051"]["group_name"] == "EVD Regional Appeal"
    assert by_code["MDRUG058"]["group_code"] == "MDRS1007"


def test_section_columns_keep_the_amount_or_an_empty_report():
    marks = {
        "People to be reached in 2027": "covered",
        "Funding Requirements for 2027": "missing",
    }

    figures = _section_figures(
        marks,
        "People to be reached in 2027",
        12000,
        "Funding Requirements for 2027",
        None,
    )

    assert figures == {
        "People to be reached in 2027": 12000,
        "Funding Requirements for 2027": None,
    }


def test_people_reached_amount_is_the_total_on_the_appeal_row():
    cells = {
        "MDRAF019_Total People to be reached": 200,
        "MDRAF018 Afghanistan - Population mvt from Pakistan_Total People to be reached": 100,
        "MDRAF017_Total People to be reached": 0,
    }

    amounts = people_reached_amounts(cells)

    assert amounts["MDRAF019"] == 200
    assert amounts["MDRAF018"] == 100
    assert "MDRAF017" not in amounts


def test_annualised_funding_is_the_sum_of_every_row_on_the_appeal_column():
    cells = {
        "col_header|EA1": "MDRAF018 Afghanistan - Population mvt from Pakistan",
        "IFRC Secretariat_EA1": 11_500_000,
        "HNS_EA1": 500_000,
        "col_header|EA2": "MDRAF019 Afghanistan - Earthquake",
        "IFRC Secretariat_EA2": 100,
        "Total_EA2": 999,
    }

    amounts = annualised_amounts(cells, ["EA1", "EA2", "EA3"])

    assert amounts["MDRAF018"] == 12_000_000
    assert amounts["MDRAF019"] == 100
    # A one-year appeal may hold its whole request in that year.
    assert appeal_duration_years("2027-01-01", "2027-12-31") == 1
    assert funding_check_status(
        12_000_000, {"2027": 12_000_000, "2028": None, "2029": None}, 1
    ) == "entered"
    # 16m of a 27m request is a partial year, not a failure to annualise.
    assert funding_check_status(
        27_000_000, {"2027": 16_000_000, "2028": None, "2029": None}, 3
    ) == "entered"
    # A three-year appeal with the whole request in 2027 was not annualised.
    assert appeal_duration_years("2026-06-01", "2028-12-31") == 3
    assert funding_check_status(
        27_000_000, {"2027": 27_000_000, "2028": None, "2029": None}, 3
    ) == "not_annualised"
    assert funding_check_status(None, {"2027": 40, "2028": None, "2029": None}, 3) == "entered"
    assert funding_check_status(100, {"2027": None, "2028": None, "2029": None}, 3) == "not_entered"
    # A child stored as 0 keeps an empty request. The group total stays on the parent.
    assert positive_requested(0) is None
    assert positive_requested(800_000_000) == 800_000_000
