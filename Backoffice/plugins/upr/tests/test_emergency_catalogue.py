"""UPR emergency catalogue: applicable appeals marked covered or not."""

from plugins.upr.validation.emergency_catalogue import assemble_catalogue
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
