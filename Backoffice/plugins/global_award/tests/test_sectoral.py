"""Sectoral Interventions workbook: parsing, regional fallback and the two upload slots. No database."""

from __future__ import annotations

import datetime as dt

import openpyxl
import pytest

from plugins.global_award.importer import files
from plugins.global_award.importer.contacts import (
    SOURCE_COUNTRY,
    SOURCE_NONE,
    SOURCE_REGIONAL,
    resolve_contacts,
)
from plugins.global_award.importer.countries import CountryIndex, CountryRef
from plugins.global_award.importer.sectoral import parse_workbook, region_key, split_people

pytestmark = pytest.mark.unit

SECTORS = ["Preparedness", "Health", "WASH"]


def _workbook():
    book = openpyxl.Workbook()
    sectors = book.active
    sectors.title = "Sectoral interventions"
    sectors.append([None, None, None, "Updated on", dt.datetime(2026, 11, 12)])
    sectors.append([])
    sectors.append([None, "Region", "Country", None, *SECTORS, "Pillar", None, None])
    sectors.append([None, "Africa", "CAR", None, None, "X", "X", 2, "Source:", "award narrative"])
    sectors.append([None, None, "Zimbabwe", None, "X", None, "x", 1, "Source:", "missing data"])
    sectors.append([None, "Asia Pacific", "Pacific Islands", "Fiji", "X", "X", None, 1, "Source:", "award narrative"])
    sectors.append([None, None, None, "Samoa", "X", None, None, 1, "Source:", "award narrative"])
    sectors.append([None, None, "Pakistan", None, "X", None, None, 1, "Source:", "award narrative"])
    sectors.append([None, "Americas", "Panama", None, "X", None, None, "1 - activation", "Source:", "x"])

    pmer = book.create_sheet("PMER Focal Points ")
    pmer.append(["Sequence", "Region / Country", "Name", "Email", "Entity / Office", "Pillar", "Remark"])
    pmer.append([1, "Geneva", "Hq Person", "hq.person@ifrc.org", "HQ", None, None])
    pmer.append([2, "Africa – Regional", "Reg Africa", "Reg.Africa@ifrc.org", "Office", None, None])
    pmer.append([3, "Asia Pacific – Regional", "Reg Asia", "reg.asia@ifrc.org", "Office", None, None])
    pmer.append([4, "Central African Republic", "Car Focal", "car.focal@ifrc.org", None, "Pillar 2", None])
    pmer.append([5, "Zimbabwe", None, None, None, "Pillar 1", None])
    pmer.append([6, "Fiji", "Am Warachit", "am@ifrc.org ", None, "Pillar 1", None])
    pmer.append([7, "Samoa", "Am Warachit", "am@ifrc.org", None, "Pillar 1", None])
    pmer.append([8, "Pakistan", "Anna Lee Kwanta Ng", "anna.lee@ifrc.org, kwanta.ng@ifrc.org", None, "Pillar 1", None])

    managers = book.create_sheet("Project Managers")
    managers.append([])
    managers.append(["Pillar", "Region", "SubRegion", "Country", "project manager", "email"])
    managers.append(["Pillar 1", "Africa", "Regional", "Region Office - AF", "Africa Boss", "africa.boss@ifrc.org"])
    managers.append(["Pillar 1", "Africa", "Africa", "Zimbabwe", "Zim Pm", "zim.pm@ifrc.org"])
    managers.append(["Pillar 1", "AsiaPac", "Pacific", "Pacific Islands", "Pac Pm", "pac.pm@ifrc.org"])
    managers.append(["Pillar 1", "AsiaPac", "South Asia", "Pakistan/RESERVES", "Pak Pm", "pak.pm@ifrc.org"])
    managers.append(["Pillar 1", "AsiaPac", "South Asia", "Pakistan", "Pak Pm", "pak.pm@ifrc.org"])
    managers.append(["Pillar 1", "Global", "Global Headquarters", "Global Coordination", "Glo Bal", "glo.bal@ifrc.org"])
    return book


def _countries():
    refs = [
        CountryRef(1, "Central African Republic", "CAF"),
        CountryRef(2, "Zimbabwe", "ZWE"),
        CountryRef(3, "Fiji", "FJI"),
        CountryRef(4, "Samoa", "WSM"),
        CountryRef(5, "Pakistan", "PAK"),
        CountryRef(6, "Panama", "PAN"),
    ]
    return CountryIndex(refs)


def test_parse_reads_sectors_pillar_source_and_the_pacific_group():
    parsed = parse_workbook(_workbook())

    assert parsed.sectors == SECTORS
    assert parsed.updated_on == "2026-11-12"
    by_name = {country.name: country for country in parsed.countries}
    assert by_name["CAR"].sectors == ["Health", "WASH"]
    assert by_name["CAR"].region == "Africa" and by_name["CAR"].pillar == "2"
    assert by_name["Zimbabwe"].missing and by_name["Zimbabwe"].sectors == []
    assert by_name["Fiji"].group == "Pacific Islands" and by_name["Samoa"].group == "Pacific Islands"
    # The group ends with the countries listed under it.
    assert by_name["Pakistan"].group == ""
    assert by_name["Panama"].pillar == "1 - activation"


def test_a_missing_sheet_is_named_in_the_error():
    book = _workbook()
    del book["Project Managers"]
    with pytest.raises(ValueError, match="Project Managers"):
        parse_workbook(book)


def test_people_are_read_from_cells_that_list_several():
    assert [(p.name, p.email) for p in split_people("A One, B Two", "a.one@ifrc.org, B.Two@ifrc.org")] == [
        ("A One", "a.one@ifrc.org"),
        ("B Two", "b.two@ifrc.org"),
    ]
    # Names that do not line up with the addresses are read from the addresses.
    people = split_people("Rommanee K Kwanta N", "rommanee.k@ifrc.org, kwanta.n@ifrc.org ")
    assert [p.name for p in people] == ["Rommanee K", "Kwanta N"]
    assert split_people("No Email", None) == []
    assert split_people(None, "same@ifrc.org, SAME@ifrc.org")[0].email == "same@ifrc.org"


def test_region_names_from_every_sheet_share_one_key():
    for text in ("AsiaPac", "Asia Pacific", "Asia Pacific – Regional"):
        assert region_key(text) == "asia_pacific"
    for text in ("Europe & Central Asia", "Europe", "Europe – Regional"):
        assert region_key(text) == "europe"
    assert region_key("MENA – Regional") == region_key("MENA") == "mena"
    assert region_key("Africa – Regional") == "africa"


def test_a_country_without_a_focal_point_uses_its_regional_office():
    resolved = resolve_contacts(parse_workbook(_workbook()), _countries())
    by_iso = {row.ref.iso3: row for row in resolved.countries}

    car = by_iso["CAF"]
    assert [p.email for p in car.pmer] == ["car.focal@ifrc.org"] and car.pmer_source == SOURCE_COUNTRY

    # Zimbabwe lists nobody for PMER, so Africa's regional office stands in.
    zimbabwe = by_iso["ZWE"]
    assert [p.email for p in zimbabwe.pmer] == ["reg.africa@ifrc.org"]
    assert zimbabwe.pmer_source == SOURCE_REGIONAL
    # Its project manager is listed, so the region office is not used.
    assert [p.email for p in zimbabwe.managers] == ["zim.pm@ifrc.org"]
    assert zimbabwe.managers_source == SOURCE_COUNTRY

    # CAR has no project manager of its own: the regional one.
    assert [p.email for p in car.managers] == ["africa.boss@ifrc.org"]
    assert car.managers_source == SOURCE_REGIONAL

    # Panama has neither a country nor a regional PMER focal point.
    assert by_iso["PAN"].pmer == [] and by_iso["PAN"].pmer_source == SOURCE_NONE
    assert by_iso["PAN"].managers_source == SOURCE_NONE


def test_a_group_row_covers_each_country_under_it_and_duplicates_collapse():
    resolved = resolve_contacts(parse_workbook(_workbook()), _countries())
    by_iso = {row.ref.iso3: row for row in resolved.countries}

    for iso in ("FJI", "WSM"):
        assert [p.email for p in by_iso[iso].managers] == ["pac.pm@ifrc.org"]
    # "Pakistan/RESERVES" and "Pakistan" name the same person once.
    assert [p.email for p in by_iso["PAK"].managers] == ["pak.pm@ifrc.org"]
    assert [p.email for p in by_iso["PAK"].pmer] == ["anna.lee@ifrc.org", "kwanta.ng@ifrc.org"]


def test_everyone_named_becomes_a_person_even_without_a_country():
    resolved = resolve_contacts(parse_workbook(_workbook()), _countries())

    people = resolved.people
    assert {"hq.person@ifrc.org", "glo.bal@ifrc.org", "reg.asia@ifrc.org"} <= set(people)
    assert people["hq.person@ifrc.org"].country_ids == []
    assert people["reg.asia@ifrc.org"].country_ids == []  # every Asia Pacific country has its own focal point
    assert sorted(people["reg.africa@ifrc.org"].country_ids) == [2]
    assert people["am@ifrc.org"].roles == ["PMER focal point"]
    assert sorted(people["am@ifrc.org"].country_ids) == [3, 4]
    assert resolved.unmatched_countries == []


def test_country_shorthands_in_the_sectoral_sheet_match():
    refs = [
        CountryRef(1, "Central African Republic", "CAF"),
        CountryRef(2, "Congo, the Democratic Republic of the", "COD"),
        CountryRef(3, "Micronesia, Federated States of", "FSM"),
        CountryRef(4, "Viet Nam", "VNM"),
        CountryRef(5, "Türkiye", "TUR"),
    ]
    index = CountryIndex(refs)
    assert index.match("CAR").iso3 == "CAF"
    assert index.match("DRC").iso3 == "COD"
    assert index.match("Democratic Republic Congo").iso3 == "COD"
    assert index.match("Micronesia").iso3 == "FSM"
    assert index.match("Vietnam").iso3 == "VNM"
    assert index.match("Turkiye").iso3 == "TUR"


@pytest.fixture
def folders(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(files, "upload_dir", lambda: uploads)
    monkeypatch.setattr(files, "REPO_ROOT", repo)
    return uploads, repo


def test_each_slot_lists_only_its_own_files(folders):
    _uploads, repo = folders
    (repo / "Annex 4_IFRC Global Award Framework.xlsx").write_bytes(b"PK1")
    (repo / "Sectoral Interventions.xlsx").write_bytes(b"PK2")
    logframe_id = files.store_upload(b"PK-logframe", "Logframe upload.xlsx")
    sectoral_id = files.store_upload(b"PK-sectoral", "Sectoral upload.xlsx", files.SLOT_SECTORAL)

    logframe_names = {row["name"] for row in files.list_disk_files(files.SLOT_LOGFRAME)}
    sectoral_names = {row["name"] for row in files.list_disk_files(files.SLOT_SECTORAL)}

    assert logframe_names == {"Logframe upload.xlsx", "Annex 4_IFRC Global Award Framework.xlsx"}
    assert sectoral_names == {"Sectoral upload.xlsx", "Sectoral Interventions.xlsx"}
    # A file of one slot cannot be imported through the other.
    assert files.resolve_ref(f"stored:{sectoral_id}", files.SLOT_LOGFRAME) is None
    assert files.resolve_ref(f"stored:{logframe_id}", files.SLOT_SECTORAL) is None
    assert files.resolve_ref("repo:Sectoral Interventions.xlsx", files.SLOT_LOGFRAME) is None
    assert files.resolve_ref("repo:Sectoral Interventions.xlsx", files.SLOT_SECTORAL) is not None
    assert files.resolve_ref(f"stored:{sectoral_id}", files.SLOT_SECTORAL)[1] == "Sectoral upload.xlsx"


def test_the_same_bytes_are_kept_once_per_slot_and_old_uploads_are_logframes(folders):
    uploads, _repo = folders
    first = files.store_upload(b"PK-same", "A.xlsx")
    assert files.store_upload(b"PK-same", "B.xlsx") == first
    other = files.store_upload(b"PK-same", "A.xlsx", files.SLOT_SECTORAL)
    assert other != first
    assert len(list(uploads.glob("*.xlsx"))) == 2

    # An upload kept before slots existed has no slot in its meta file.
    legacy = "a" * 32
    (uploads / f"{legacy}.xlsx").write_bytes(b"PK-old")
    (uploads / f"{legacy}.meta.json").write_text('{"filename": "Old.xlsx", "size": 6}', encoding="utf-8")
    assert files.resolve_ref(f"stored:{legacy}", files.SLOT_LOGFRAME) is not None
    assert files.resolve_ref(f"stored:{legacy}", files.SLOT_SECTORAL) is None
