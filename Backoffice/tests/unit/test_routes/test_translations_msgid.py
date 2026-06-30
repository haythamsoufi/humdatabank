"""Tests for translation route msgid handling."""

import base64
import json
import os
import tempfile

import polib
import pytest

from app.routes.admin.utilities.translations import _msgid_from_payload, _purge_obsolete_po_entries


class TestMsgidFromPayload:
    def test_preserves_trailing_whitespace(self):
        msgid = '<i class="fas fa-file-excel"></i> '
        data = {"msgid": msgid}
        assert _msgid_from_payload(data) == msgid

    def test_empty_when_missing(self):
        assert _msgid_from_payload({}) == ""

    def test_coerces_non_string(self):
        assert _msgid_from_payload({"msgid": 42}) == "42"


class TestDeleteRemovedTranslationMsgidMatch:
    def test_stripped_msgid_does_not_match_po_entry(self):
        msgid = '<i class="fas fa-file-excel w-6 h-6 mr-2 text-green-600"></i> '
        with tempfile.TemporaryDirectory() as tmp:
            po_path = os.path.join(tmp, "messages.po")
            po = polib.POFile()
            entry = polib.POEntry(
                msgid=msgid,
                msgstr="",
                obsolete=1,
            )
            po.append(entry)
            po.save(po_path)

            loaded = polib.pofile(po_path)
            stripped = msgid.strip()
            matches_stripped = [
                e for e in loaded if e.msgid == stripped and getattr(e, "obsolete", False)
            ]
            matches_exact = [
                e for e in loaded if e.msgid == msgid and getattr(e, "obsolete", False)
            ]
            assert not matches_stripped
            assert len(matches_exact) == 1

    def test_payload_roundtrip_preserves_trailing_space(self):
        msgid = '<i class="fas fa-file-excel w-6 h-6 mr-2 text-green-600"></i> '
        payload_obj = {"msgid": msgid, "csrf_token": "test"}
        payload_b64 = base64.b64encode(json.dumps(payload_obj).encode("utf-8")).decode("ascii")
        decoded_obj = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
        assert _msgid_from_payload(decoded_obj) == msgid


class TestPurgeObsoletePoEntries:
    def test_purge_single_msgid(self, app):
        msgid = "Obsolete string"
        with tempfile.TemporaryDirectory() as tmp:
            po_path = os.path.join(tmp, "messages.po")
            po = polib.POFile()
            po.append(polib.POEntry(msgid=msgid, msgstr="old", obsolete=1))
            po.append(polib.POEntry(msgid="Active string", msgstr="keep"))
            po.save(po_path)

            import app.routes.admin.utilities.translations as translations_module

            original_path = translations_module._translations_po_path
            translations_module._translations_po_path = lambda _lang: po_path
            try:
                with app.app_context():
                    app.config["SUPPORTED_LANGUAGES"] = ["en"]
                    files_updated, entries_removed, file_errors = _purge_obsolete_po_entries(msgid=msgid)
            finally:
                translations_module._translations_po_path = original_path

            assert file_errors == []
            assert files_updated == 1
            assert entries_removed == 1
            loaded = polib.pofile(po_path)
            assert len(loaded) == 1
            assert loaded[0].msgid == "Active string"

    def test_purge_all_obsolete(self, app):
        with tempfile.TemporaryDirectory() as tmp:
            po_path = os.path.join(tmp, "messages.po")
            po = polib.POFile()
            po.append(polib.POEntry(msgid="Obsolete one", msgstr="", obsolete=1))
            po.append(polib.POEntry(msgid="Obsolete two", msgstr="", obsolete=1))
            po.append(polib.POEntry(msgid="Active string", msgstr="keep"))
            po.save(po_path)

            import app.routes.admin.utilities.translations as translations_module

            original_path = translations_module._translations_po_path
            translations_module._translations_po_path = lambda _lang: po_path
            try:
                with app.app_context():
                    app.config["SUPPORTED_LANGUAGES"] = ["en"]
                    files_updated, entries_removed, file_errors = _purge_obsolete_po_entries()
            finally:
                translations_module._translations_po_path = original_path

            assert file_errors == []
            assert files_updated == 1
            assert entries_removed == 2
            loaded = polib.pofile(po_path)
            assert len(loaded) == 1
            assert loaded[0].msgid == "Active string"
