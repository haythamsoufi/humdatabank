from plugins.upr.extracts.master_wide import compute_new_totals, melt_master_long, pivot_master_wide


def _row(**kw):
    base = {
        "ISO3": "KEN",
        "Country": "Kenya",
        "Round": "P27",
        "Source": "Country Data",
        "Data status": "Approved",
        "Section": None,
        "Entity": "HNS",
        "NS": "Kenya Red Cross Society",
        "Area": "Total",
        "Indicator": None,
        "indicatorId": None,
        "ValueNum": None,
        "EA Code": None,
        "Year": 2027,
    }
    base.update(kw)
    return base


def _context(**overrides):
    base = {
        "ns_key_by_iso_year": {
            ("KEN", 2026): {
                "Volunteers": 100,
                "Staff": 10,
                "Branches": 5,
                "LocalUnits": 20,
                "Source": "FDRS",
            }
        },
        "planning_bundle": {"KEN": "Test Bundle"},
        "population": {"KEN": 50000000},
        "income_groups": {"KEN": "Lower middle income"},
        "inform_risk": {"KEN": "High"},
        "inform_severity": {},
        "inform_climate": {},
        "poverty": {"KEN": 0.36},
        "hdi": {"KEN": {"score": 0.6, "rank": 100, "tier": "Medium"}},
        "multilateral": {"P27": {"KEN": ["Swedish RC"]}},
        "eas_sprm": {"P27": {"KEN": 250}},
    }
    base.update(overrides)
    return base


def test_pivot_builds_one_ordered_row_per_country():
    rows = [
        _row(Section="Reach", Area="SP2", Indicator="People to be reached", ValueNum=5),
        _row(Section="Reach", Area="SP1", Indicator="People to be reached", ValueNum=7),
        _row(Section="Reach", Area="EA1", Indicator="People to be reached", ValueNum=3, **{"EA Code": "MDRXX001"}),
        _row(Section="Reach", Area="EA2", Indicator="People to be reached", ValueNum=7, **{"EA Code": "MDRXX002"}),
        _row(Section="Support", Entity="PNS", NS="Danish RC", Area="SP1", Indicator="Bilateral Support"),
        _row(Section="Funding", Indicator="Funding Requirement", ValueNum=1000),
        _row(Section="Funding", Indicator="Funding Requirement", Entity="HNS", Area="SP1", ValueNum=40),
        _row(Section="Funding", Indicator="Funding Requirement", Entity="HNS", Area="EA2", ValueNum=10),
        _row(Section="Funding", Indicator="Funding Requirement", Entity="IFRC Secretariat", ValueNum=200),
        _row(Section="Funding", Indicator="Funding Requirement", Entity="IFRC Secretariat", Area="EA1", ValueNum=50),
        _row(Section="Funding", Indicator="Funding Requirement", Entity="PNS", NS="Danish RC", Area="SP2", ValueNum=100),
        _row(Section="Funding", Indicator="Funding Requirement", Entity="PNS", NS="Danish RC", Area="SP3", ValueNum=300),
        _row(Section="Funding", Indicator="Funding Requirement", Entity="PNS", NS="Norwegian RC", Area="SP3", ValueNum=50),
        _row(Section="Funding", Indicator="Funding Requirement", Entity="PNS", NS="Austrian RC", ValueNum=570),
        _row(Section="Funding", Indicator="Funding Requirement", Entity="PNS", NS="Austrian RC", Area="SP1", ValueNum=1),
    ]
    columns, wide = pivot_master_wide(rows, region_by_iso={"KEN": "Africa"}, context=_context())

    assert len(wide) == 1
    out = wide[0]
    assert out["Region"] == "Africa"
    assert out["Part of Bundle"] == "Test Bundle"
    assert out["Volunteers"] == 100 and out["Staff"] == 10
    assert out["Latest data available"] == "FDRS"
    assert out["Total Population"] == 50000000
    assert out["INFORM Risk Class"] == "High"
    assert columns.index("Reach 2027 EAs") < columns.index("Reach 2027 SP1")
    assert columns.index("Reach 2027 SP1") < columns.index("Reach 2027 SP2")
    assert "Reach 2027 EA1" not in columns and "Reach 2027 EA2" not in columns
    assert out["Reach 2027 EAs"] == 10
    assert columns.index("HNS 2027 EAs") < columns.index("HNS 2027 SP1")
    assert columns.index("HNS 2027 SP1") < columns.index("HNS 2027 Total")
    assert columns.index("IFRC 2027 EAs") < columns.index("IFRC 2027 Total")
    assert out["Activities SP1"] == "Danish RC"
    assert "Swedish RC*" in out["Activities Combined"]
    assert out["HNS 2027 Total"] == 1000
    assert out["HNS 2027 SP1"] == 40
    assert out["HNS 2027 EAs"] == 10
    assert out["IFRC 2027 EAs"] == 50
    assert out["IFRC 2027 Total"] == 200
    assert out["IFRC 2027 EAs SPRM/OPS"] == 250
    assert out["IFRC 2027 New Total"] == 450
    assert out["Danish RC 2027"] == 400
    assert out["Norwegian RC 2027"] == 50
    assert out["Austrian RC 2027"] == 570
    assert out["Total PNSs 2027"] == 1020
    assert out["Total FR 2027"] == 2220
    assert out["2027 New Total"] == 1000 + 450 + 1020
    assert columns.index("HNS 2027 Total") < columns.index("IFRC 2027 Total")
    assert columns.index("IFRC 2027 EAs SPRM/OPS") < columns.index("IFRC 2027 New Total")
    assert columns.index("IFRC 2027 New Total") < columns.index("Austrian RC 2027")
    assert columns.index("Total FR 2027") < columns.index("2027 New Total")


def test_melt_long_uses_combined_attribute_names():
    rows = [
        _row(Section="Funding", Indicator="Funding Requirement", Entity="HNS", Area="SP1", ValueNum=40),
        _row(Section="Funding", Indicator="Funding Requirement", Entity="PNS", NS="Danish RC", Area="SP2", ValueNum=10),
        _row(ISO3="UGA", Country="Uganda", Section="Funding", Indicator="Funding Requirement", Entity="PNS", NS="Danish RC", Area="SP1", ValueNum=5),
    ]
    columns, long_rows = melt_master_long(
        rows,
        region_by_iso={"KEN": "Africa", "UGA": "Africa"},
        context=_context(
            ns_key_by_iso_year={
                ("KEN", 2026): {"Volunteers": 100, "Source": "FDRS"},
                ("UGA", 2026): {"Volunteers": 1, "Source": "Planning 2027"},
            },
            planning_bundle={},
            eas_sprm={},
            multilateral={},
        ),
    )

    assert columns[:6] == [
        "Round",
        "ISO3",
        "Region",
        "Country",
        "Part of Bundle",
        "Data status",
    ]
    assert "Attribute order" in columns and "Attribute" in columns and "Value" in columns
    by_attr = {row["Attribute"]: row["Value"] for row in long_rows if row["ISO3"] == "KEN"}
    assert by_attr["Volunteers"] == 100
    assert by_attr["HNS 2027 SP1"] == 40
    assert by_attr["Danish RC 2027"] == 10

    orders = [row["Attribute order"] for row in long_rows]
    assert orders == sorted(orders)
    first_seen = []
    for row in long_rows:
        if row["Attribute"] not in first_seen:
            first_seen.append(row["Attribute"])
    assert first_seen.index("Volunteers") < first_seen.index("HNS 2027 SP1")
    assert first_seen.index("HNS 2027 SP1") < first_seen.index("Danish RC 2027")


def test_compute_new_totals_without_sprm_keeps_ifrc_total():
    ifrc_new, year_new = compute_new_totals(
        hns_total=100,
        ifrc_total=200,
        ifrc_subtotal=200,
        pns_total=50,
        eas_sprm=None,
    )
    assert ifrc_new == 200
    assert year_new == 350


def test_compute_new_totals_with_sprm_adds_to_subtotal():
    ifrc_new, year_new = compute_new_totals(
        hns_total=100,
        ifrc_total=200,
        ifrc_subtotal=200,
        pns_total=50,
        eas_sprm=25,
    )
    assert ifrc_new == 225
    assert year_new == 375
