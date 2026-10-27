"""Unit tests for AI knowledge-base duplicate detection and dedupe."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.ai.documents import duplicates as dup


pytestmark = pytest.mark.unit


def _doc(**kwargs):
    d = MagicMock()
    d.id = kwargs.get("id", 1)
    d.title = kwargs.get("title", "Doc")
    d.filename = kwargs.get("filename", "doc.pdf")
    d.content_hash = kwargs.get("content_hash")
    d.source_url = kwargs.get("source_url")
    d.submitted_document_id = kwargs.get("submitted_document_id")
    d.guidance_document_id = kwargs.get("guidance_document_id")
    d.processing_status = kwargs.get("processing_status", "completed")
    d.total_chunks = kwargs.get("total_chunks", 0)
    d.extra_metadata = kwargs.get("extra_metadata")
    d.storage_path = kwargs.get("storage_path")
    return d


class TestNormalizeDedupeSourceUrl:
    def test_normalizes_host_and_default_port(self):
        assert dup.normalize_dedupe_source_url(
            "HTTPS://Example.COM:443/path//file.pdf#frag"
        ) == "https://example.com/path/file.pdf"

    def test_empty(self):
        assert dup.normalize_dedupe_source_url("") == ""
        assert dup.normalize_dedupe_source_url(None) == ""


class TestChooseKeeper:
    def test_prefers_linked_submitted_document(self):
        standalone = _doc(id=1, processing_status="completed", total_chunks=99)
        linked = _doc(id=2, submitted_document_id=55, processing_status="pending", total_chunks=1)
        assert dup.choose_keeper([standalone, linked]).id == 2

    def test_prefers_completed_then_chunks(self):
        a = _doc(id=1, processing_status="failed", total_chunks=50)
        b = _doc(id=2, processing_status="completed", total_chunks=2)
        assert dup.choose_keeper([a, b]).id == 2
        c = _doc(id=3, processing_status="completed", total_chunks=10)
        assert dup.choose_keeper([b, c]).id == 3


class TestFindDuplicateGroups:
    def test_groups_by_content_hash(self):
        a = _doc(id=1, content_hash="abc", submitted_document_id=10)
        b = _doc(id=2, content_hash="abc")
        c = _doc(id=3, content_hash="zzz")
        groups = dup.find_duplicate_groups([a, b, c])
        assert len(groups) == 1
        assert groups[0]["match_type"] == "hash"
        assert groups[0]["keeper_id"] == 1
        assert set(groups[0]["document_ids"]) == {1, 2}

    def test_groups_by_url_only_when_hash_missing(self):
        a = _doc(id=1, source_url="https://example.com/a.pdf")
        b = _doc(id=2, source_url="HTTPS://Example.com/a.pdf")
        c = _doc(id=3, content_hash="same", source_url="https://example.com/a.pdf")
        d = _doc(id=4, content_hash="same", source_url="https://other.example/x.pdf")
        groups = dup.find_duplicate_groups([a, b, c, d])
        # hash group for c+d; url group for a+b (c has hash so not in url buckets)
        assert len(groups) == 2
        by_type = {g["match_type"]: g for g in groups}
        assert set(by_type["url"]["document_ids"]) == {1, 2}
        assert set(by_type["hash"]["document_ids"]) == {3, 4}

    def test_title_alone_is_not_a_duplicate(self):
        a = _doc(id=1, title="Same Title", content_hash="h1")
        b = _doc(id=2, title="Same Title", content_hash="h2")
        assert dup.find_duplicate_groups([a, b]) == []


class TestAnnotateDocumentDicts:
    def test_annotates_duplicates(self):
        docs = [
            {"id": 1, "content_hash": "abc", "submitted_document_id": 9, "processing_status": "completed", "total_chunks": 1},
            {"id": 2, "content_hash": "abc", "submitted_document_id": None, "processing_status": "completed", "total_chunks": 5},
            {"id": 3, "content_hash": "other", "submitted_document_id": None, "processing_status": "completed", "total_chunks": 1},
        ]
        out = dup.annotate_document_dicts(docs)
        by_id = {d["id"]: d for d in out}
        assert by_id[1]["is_duplicate"] is True
        assert by_id[1]["is_duplicate_keeper"] is True
        assert by_id[2]["is_duplicate"] is True
        assert by_id[2]["is_duplicate_keeper"] is False
        assert by_id[2]["duplicate_keeper_id"] == 1
        assert by_id[3]["is_duplicate"] is False


class TestDedupeDocuments:
    def test_explicit_keep_remove(self, app):
        keeper = _doc(id=10, content_hash="abc", submitted_document_id=1)
        loser = _doc(id=11, content_hash="abc", storage_path="ai/tmp.pdf")

        with app.app_context():
            with patch.object(dup.AIDocument, "query") as mock_query:
                mock_query.get.return_value = keeper
                mock_query.filter.return_value.all.return_value = [loser]
                with patch.object(dup, "delete_ai_document_for_dedupe") as mock_delete:
                    with patch.object(dup.db.session, "commit"):
                        result = dup.dedupe_documents(
                            keep_id=10,
                            remove_ids=[11],
                            dry_run=False,
                        )
        assert result["ok"] is True
        assert result["kept"] == [10]
        assert result["removed"] == [11]
        mock_delete.assert_called_once_with(loser)

    def test_dry_run_all_groups(self, app):
        a = _doc(id=1, content_hash="abc", submitted_document_id=5)
        b = _doc(id=2, content_hash="abc")
        with app.app_context():
            with patch.object(dup, "find_duplicate_groups", return_value=[{
                "group_id": "hash:abc",
                "match_type": "hash",
                "match_value": "abc",
                "keeper_id": 1,
                "document_ids": [1, 2],
                "documents": [],
            }]):
                with patch.object(dup.AIDocument, "query") as mock_query:
                    mock_query.get.return_value = a
                    mock_query.filter.return_value.all.return_value = [b]
                    result = dup.dedupe_documents(all_groups=True, dry_run=True)
        assert result["ok"] is True
        assert result["removed"] == [2]
        assert result["dry_run"] is True


class TestFindReclaimableAiDocument:
    def test_reclaims_unlinked_by_hash(self, app):
        existing = _doc(id=99, content_hash="deadbeef", submitted_document_id=None)
        with app.app_context():
            with patch.object(dup.AIDocument, "query") as mock_query:
                mock_query.filter.return_value.order_by.return_value.all.return_value = [existing]
                found = dup.find_reclaimable_ai_document(content_hash="deadbeef")
        assert found is existing

    def test_skips_already_linked_to_other_submitted(self, app):
        existing = _doc(id=99, content_hash="deadbeef", submitted_document_id=7)
        with app.app_context():
            with patch.object(dup.AIDocument, "query") as mock_query:
                mock_query.filter.return_value.order_by.return_value.all.return_value = [existing]
                found = dup.find_reclaimable_ai_document(
                    content_hash="deadbeef",
                    exclude_submitted_document_id=99,
                )
        assert found is None
