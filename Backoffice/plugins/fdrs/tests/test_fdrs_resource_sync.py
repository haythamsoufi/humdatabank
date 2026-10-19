"""Planning tests for the FDRS global resource sync."""
from plugins.fdrs.services.fdrs_resource_sync import (
    FdrsResourceDoc,
    StoredTranslation,
    build_plan,
    dedupe_documents,
    group_documents,
    normalize_filename,
)


def _doc(document_type, name, url, language="en", year=None):
    return FdrsResourceDoc(
        document_type=document_type,
        year=year,
        language=language,
        name=name,
        description="",
        url=url,
        thumbnail="",
    )


def test_filename_match_ignores_case_and_underscores():
    assert normalize_filename("FDRS User Guide 2024_EN.pdf") == normalize_filename(
        "fdrs user guide 2024 en.pdf"
    )


def test_duplicate_file_suffix_and_repeated_youtube_are_dropped():
    docs = [
        _doc("DocumentGuide", "Technical Note On Counting People Reached.pdf", "https://data-api.ifrc.org/documents/noiso/Technical Note On Counting People Reached.pdf"),
        _doc("DocumentGuide", "Technical Note On Counting People Reached_1.pdf", "https://data-api.ifrc.org/documents/noiso/Technical Note On Counting People Reached_1.pdf"),
        _doc("FrontendVideo", "FDRS - User Guide", "https://youtu.be/s8gWS22wpro"),
        _doc("VideoGuide", "FDRS - User Guide", "https://www.youtube.com/watch?v=s8gWS22wpro"),
    ]
    kept, skipped = dedupe_documents(docs)
    names = {doc.name for doc in kept}
    assert "Technical Note On Counting People Reached.pdf" in names
    assert "Technical Note On Counting People Reached_1.pdf" not in names
    assert len([doc for doc in kept if doc.is_video]) == 1
    assert kept[[doc.is_video for doc in kept].index(True)].document_type == "FrontendVideo"
    assert len(skipped) == 2


def test_everyone_counts_languages_share_one_resource_even_when_filenames_differ():
    docs = [
        _doc("EveryoneCounts", "Everyone Counts_Special Edition Mid-Term Review of Strategy 2030_English.pdf", "https://data-api.ifrc.org/a.pdf", "en", 2024),
        _doc("EveryoneCounts", "EveryoneCounts2024_AR_LR.pdf", "https://data-api.ifrc.org/b.pdf", "ar", 2024),
        _doc("EveryoneCounts", "Everyone Counts Report 2019 EN.pdf", "https://data-api.ifrc.org/c.pdf", "en", 2019),
    ]
    groups = group_documents(docs)
    by_year = {group.year: group for group in groups}
    assert set(by_year) == {2019, 2024}
    assert {doc.language for doc in by_year[2024].docs} == {"en", "ar"}
    assert by_year[2024].title.startswith("Everyone Counts")


def test_plan_keeps_existing_files_and_lists_databank_only_copies():
    docs = [
        _doc("Analysis", "COVID-19, 16 month overview.pdf", "https://data-api.ifrc.org/covid.pdf", year=2021),
        _doc("EveryoneCounts", "Everyone_counts_2014_EN.pdf", "https://data-api.ifrc.org/2014.pdf", year=2014),
    ]
    stored = [
        StoredTranslation(3, "COVID-19, 16 month overview", "publication", "COVID-19", "en", "COVID-19, 16 month overview.pdf", ""),
        StoredTranslation(3, "COVID-19, 16 month overview", "publication", "COVID-19", "hu", "COVID-19_16_hu.pdf", ""),
    ]
    plan = build_plan(docs, stored)
    statuses = {(row["name"], row["status"]) for row in plan["files"]}
    assert ("COVID-19, 16 month overview.pdf", "in_databank") in statuses
    assert ("Everyone_counts_2014_EN.pdf", "missing") in statuses
    assert plan["create_resources"] == 1
    assert plan["attach_to_existing"] == 0
    assert plan["verify_resources"] == 2
    assert plan["only_databank_files"][0]["language"] == "hu"
    assert plan["only_databank_files"][0]["resource_id"] == 3
    stored_group = next(action for action in plan["sync"] if action["resource_id"] == 3)
    assert stored_group["files"][0]["url"] == "https://data-api.ifrc.org/covid.pdf"
    assert {action["resource_id"] for action in plan["sync"]} == {3, None}
