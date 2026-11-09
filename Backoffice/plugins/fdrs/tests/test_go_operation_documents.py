"""Parser tests for IFRC GO operation documents. No network."""

from plugins.fdrs.services.go_operation_documents import (
    apply_appeal_names,
    event_ids_for_country,
    events_for_country,
    parse_appeal_documents,
    parse_situation_reports,
    public_document_url,
)

APPEAL_URL = "https://go-api.ifrc.org/api/DownloadFile/1/MDRAF001ea"
SITREP_URL = (
    "https://prddsgofilestorage.blob.core.windows.net/api/sitreps/10/abc/update.pdf"
)


def test_public_document_url_rejects_other_hosts():
    assert public_document_url(APPEAL_URL) == APPEAL_URL
    assert public_document_url("http://go-api.ifrc.org/api/DownloadFile/1/x") is None
    assert public_document_url("https://evil.example/file.pdf") is None
    assert public_document_url("https://user:pass@go-api.ifrc.org/file.pdf") is None


def test_parse_appeal_documents_keeps_matching_iso_only():
    docs = parse_appeal_documents(
        [
            {
                "iso": "AF",
                "name": "Afghanistan Floods",
                "type": "Emergency Appeal",
                "document_url": APPEAL_URL,
                "created_at": "2024-03-01T00:00:00Z",
            },
            {
                "iso": "ch",
                "name": "Secretariat copy",
                "type": "Operations Update",
                "document_url": "https://go-api.ifrc.org/api/DownloadFile/2/other",
                "created_at": "2024-01-01T00:00:00Z",
            },
            {
                "iso": "AF",
                "name": "Missing file",
                "type": "DREF Operation",
                "document_url": "",
                "document": None,
            },
            "not-a-row",
        ],
        "af",
    )
    assert len(docs) == 1
    assert docs[0]["title"] == "Afghanistan Floods"
    assert docs[0]["document_type"] == "Emergency Appeal"
    assert docs[0]["year"] == 2024
    assert docs[0]["url"] == APPEAL_URL
    assert docs[0]["emergency_code"] is None
    assert docs[0]["emergency"] is None


def test_appeal_documents_keep_the_appeal_code_for_grouping():
    docs = parse_appeal_documents(
        [
            {
                "iso": "BF",
                "name": "Burkina Faso - Floods (MDRBF019)",
                "type": "DREF Operation",
                "document_url": APPEAL_URL,
                "created_at": "2024-08-01T00:00:00Z",
                "appeal": {"id": 19, "code": "MDRBF019"},
            },
            {
                "iso": "BF",
                "name": "Burkina Faso - Floods final report (MDRBF019)",
                "type": "DREF Operation Final Report",
                "document_url": "https://go-api.ifrc.org/api/DownloadFile/2/MDRBF019fr",
                "created_at": "2025-01-01T00:00:00Z",
                "appeal": {"code": "MDRBF019"},
            },
        ],
        "BF",
    )
    assert [doc["emergency_code"] for doc in docs] == ["MDRBF019", "MDRBF019"]
    apply_appeal_names(docs, {"MDRBF019": "Burkina Faso - Floods"})
    assert {doc["emergency"] for doc in docs} == {"Burkina Faso - Floods"}


def test_apply_appeal_names_falls_back_to_the_code():
    docs = [{"emergency_code": "MDRBF019", "emergency": None}]
    apply_appeal_names(docs, {})
    assert docs[0]["emergency"] == "MDRBF019"


def test_situation_reports_require_public_visibility_and_known_event():
    events = event_ids_for_country(
        [
            {"id": "10", "countries": [{"iso3": "AFG"}]},
            {"id": 11, "countries": [{"iso3": "KEN"}]},
            {"id": 12, "countries": []},
        ],
        "AFG",
    )
    assert events == {10}
    assert events_for_country(
        [{"id": "10", "name": "Burkina Faso - Floods", "countries": [{"iso3": "AFG"}]}],
        "AFG",
    ) == {10: "Burkina Faso - Floods"}

    docs = parse_situation_reports(
        [
            {
                "event": 10,
                "visibility": 3,
                "name": "Operation update 1",
                "document": SITREP_URL,
                "type": {"type": "Situation Reports"},
                "created_at": "2025-06-02T00:00:00Z",
            },
            {
                "event": 10,
                "visibility": 1,
                "name": "Members only",
                "document_url": "https://go-api.ifrc.org/api/DownloadFile/9/private",
                "created_at": "2025-06-02T00:00:00Z",
            },
            {
                "event": 99,
                "visibility": 3,
                "name": "Other country",
                "document_url": "https://go-api.ifrc.org/api/DownloadFile/8/other",
                "created_at": "2025-06-02T00:00:00Z",
            },
        ],
        events,
    )
    assert len(docs) == 1
    assert docs[0]["title"] == "Operation update 1"
    assert docs[0]["document_type"] == "Situation Reports"
    assert docs[0]["year"] == 2025
    assert docs[0]["emergency_code"] == "event:10"
    assert docs[0]["emergency"] is None

    named = parse_situation_reports(
        [
            {
                "event": 10,
                "visibility": 3,
                "name": "Operation update 1",
                "document": SITREP_URL,
                "type": {"type": "Situation Reports"},
                "created_at": "2025-06-02T00:00:00Z",
            }
        ],
        {10: "Burkina Faso - Floods"},
    )
    assert named[0]["emergency"] == "Burkina Faso - Floods"
    assert named[0]["emergency_code"] == "event:10"


def test_unfiltered_event_page_yields_no_ids():
    assert event_ids_for_country(
        [{"id": 1, "countries": [{"iso3": "KEN"}]}],
        "AFG",
    ) == set()
