"""Tests for catalog_service's human-approval protection guard and batched upserts.

Two tiers:
- ``_apply_row_update``/``_is_human_protected`` are pure decision logic (no DB, no
  files) and are tested directly against fake row objects for speed and thorough
  edge-case coverage.
- ``upsert_string``/``upsert_batch`` are the public, DB-backed API used by the rest
  of the app; a small number of true integration tests (via the ``db_session``
  fixture) exercise them end-to-end, with PO-file syncing mocked out so tests never
  touch real .po files on disk.
"""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.translation.catalog_service import (
    PROVENANCE_HUMAN,
    PROVENANCE_MACHINE,
    STATUS_APPROVED,
    STATUS_UNREVIEWED,
    _apply_row_update,
    _is_human_protected,
    build_locale_catalog,
)


def _fake_row(*, provenance, msgstr, status="approved", version=1, msgstr_plural=None):
    return SimpleNamespace(
        provenance=provenance,
        msgstr=msgstr,
        msgstr_plural=msgstr_plural,
        status=status,
        actor_user_id=None,
        version=version,
        updated_at=None,
    )


# ---------------------------------------------------------------------------
# _is_human_protected
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestIsHumanProtected:
    def test_none_row_is_not_protected(self):
        assert _is_human_protected(None) is False

    def test_human_row_with_text_is_protected(self):
        row = _fake_row(provenance=PROVENANCE_HUMAN, msgstr="Bonjour")
        assert _is_human_protected(row) is True

    def test_human_row_with_empty_text_is_not_protected(self):
        row = _fake_row(provenance=PROVENANCE_HUMAN, msgstr="")
        assert _is_human_protected(row) is False

    def test_human_row_with_whitespace_only_text_is_not_protected(self):
        row = _fake_row(provenance=PROVENANCE_HUMAN, msgstr="   ")
        assert _is_human_protected(row) is False

    def test_machine_row_is_not_protected(self):
        row = _fake_row(provenance=PROVENANCE_MACHINE, msgstr="Bonjour")
        assert _is_human_protected(row) is False

    def test_imported_row_is_not_protected(self):
        row = _fake_row(provenance="imported", msgstr="Bonjour")
        assert _is_human_protected(row) is False


# ---------------------------------------------------------------------------
# _apply_row_update — the core guard, using fake (non-DB) rows
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestApplyRowUpdateGuard:
    def test_machine_cannot_overwrite_human_approved_row(self):
        row = _fake_row(provenance=PROVENANCE_HUMAN, msgstr="Bonjour")
        result_row, changed, protected = _apply_row_update(
            row,
            locale="fr",
            msgid="Hello",
            new_msgstr="Salut (machine)",
            provenance=PROVENANCE_MACHINE,
            engine="google",
            status=None,
            actor=None,
        )
        assert protected is True
        assert changed is False
        assert result_row.msgstr == "Bonjour"  # untouched

    def test_imported_provenance_cannot_overwrite_human_approved_row(self):
        row = _fake_row(provenance=PROVENANCE_HUMAN, msgstr="Bonjour")
        _row, changed, protected = _apply_row_update(
            row,
            locale="fr",
            msgid="Hello",
            new_msgstr="Salut (import)",
            provenance="imported",
            engine=None,
            status=None,
            actor=None,
        )
        assert protected is True
        assert changed is False

    def test_force_true_overrides_protection(self):
        row = _fake_row(provenance=PROVENANCE_HUMAN, msgstr="Bonjour")
        result_row, changed, protected = _apply_row_update(
            row,
            locale="fr",
            msgid="Hello",
            new_msgstr="Salut (forced)",
            provenance=PROVENANCE_MACHINE,
            engine="google",
            status=None,
            actor=None,
            force=True,
        )
        assert protected is False
        assert changed is True
        assert result_row.msgstr == "Salut (forced)"
        assert result_row.provenance == PROVENANCE_MACHINE

    def test_human_can_overwrite_human_approved_row(self):
        row = _fake_row(provenance=PROVENANCE_HUMAN, msgstr="Bonjour")
        result_row, changed, protected = _apply_row_update(
            row,
            locale="fr",
            msgid="Hello",
            new_msgstr="Bonjour (corrected)",
            provenance=PROVENANCE_HUMAN,
            engine=None,
            status=None,
            actor=7,
        )
        assert protected is False
        assert changed is True
        assert result_row.msgstr == "Bonjour (corrected)"
        assert result_row.actor_user_id == 7

    def test_machine_overwriting_empty_human_row_is_allowed(self):
        # A human-provenance row with blank text (e.g. explicitly cleared) is not
        # "approved work" and must not block machine translation from filling it.
        row = _fake_row(provenance=PROVENANCE_HUMAN, msgstr="")
        _row, changed, protected = _apply_row_update(
            row,
            locale="fr",
            msgid="Hello",
            new_msgstr="Salut",
            provenance=PROVENANCE_MACHINE,
            engine="google",
            status=None,
            actor=None,
        )
        assert protected is False
        assert changed is True

    def test_machine_overwriting_machine_row_is_allowed(self):
        row = _fake_row(provenance=PROVENANCE_MACHINE, msgstr="Old machine text", version=3)
        result_row, changed, protected = _apply_row_update(
            row,
            locale="fr",
            msgid="Hello",
            new_msgstr="New machine text",
            provenance=PROVENANCE_MACHINE,
            engine="libretranslate",
            status=None,
            actor=None,
        )
        assert protected is False
        assert changed is True
        assert result_row.msgstr == "New machine text"
        assert result_row.version == 4


@pytest.mark.unit
class TestApplyRowUpdateMutationLogic:
    def test_same_text_no_op_when_provenance_unchanged(self):
        row = _fake_row(provenance=PROVENANCE_MACHINE, msgstr="Bonjour", version=2)
        result_row, changed, protected = _apply_row_update(
            row,
            locale="fr",
            msgid="Hello",
            new_msgstr="Bonjour",
            provenance=PROVENANCE_MACHINE,
            engine="google",
            status=None,
            actor=None,
        )
        assert changed is False
        assert protected is False
        assert result_row.version == 2  # untouched

    def test_same_text_upgrades_provenance_when_human_confirms(self):
        row = _fake_row(provenance=PROVENANCE_MACHINE, msgstr="Bonjour", status="unreviewed")
        result_row, changed, protected = _apply_row_update(
            row,
            locale="fr",
            msgid="Hello",
            new_msgstr="Bonjour",
            provenance=PROVENANCE_HUMAN,
            engine=None,
            status=None,
            actor=3,
        )
        assert changed is True
        assert protected is False
        assert result_row.provenance == PROVENANCE_HUMAN
        assert result_row.status == STATUS_APPROVED
        assert result_row.actor_user_id == 3

    def test_msgstr_plural_change_is_detected_even_if_msgstr_same(self):
        row = _fake_row(provenance=PROVENANCE_MACHINE, msgstr="1 item", msgstr_plural={"0": "1 item", "1": "N items"})
        _row, changed, protected = _apply_row_update(
            row,
            locale="fr",
            msgid="item",
            new_msgstr="1 item",
            provenance=PROVENANCE_MACHINE,
            engine=None,
            status=None,
            actor=None,
            is_plural=True,
            msgstr_plural={"0": "1 item", "1": "N updated items"},
        )
        assert changed is True

    def test_explicit_status_overrides_provenance_default(self):
        row = _fake_row(provenance=PROVENANCE_MACHINE, msgstr="Old")
        result_row, changed, _protected = _apply_row_update(
            row,
            locale="fr",
            msgid="Hello",
            new_msgstr="New",
            provenance=PROVENANCE_MACHINE,
            engine=None,
            status=STATUS_APPROVED,  # explicit override even though provenance != human
            actor=None,
        )
        assert changed is True
        assert result_row.status == STATUS_APPROVED

    def test_version_increments_on_change(self):
        row = _fake_row(provenance=PROVENANCE_MACHINE, msgstr="Old", version=5)
        result_row, _changed, _protected = _apply_row_update(
            row,
            locale="fr",
            msgid="Hello",
            new_msgstr="New",
            provenance=PROVENANCE_MACHINE,
            engine=None,
            status=None,
            actor=None,
        )
        assert result_row.version == 6


@pytest.mark.unit
class TestApplyRowUpdateNewRow:
    """The `row is None` branch touches db.session.add(), so it needs an app context."""

    def test_new_row_with_text_is_created_and_changed(self, app):
        with app.app_context():
            row, changed, protected = _apply_row_update(
                None,
                locale="fr",
                msgid="Hello",
                new_msgstr="Bonjour",
                provenance=PROVENANCE_MACHINE,
                engine="google",
                status=None,
                actor=None,
            )
        assert changed is True
        assert protected is False
        assert row.msgstr == "Bonjour"
        assert row.provenance == PROVENANCE_MACHINE
        assert row.status == STATUS_UNREVIEWED

    def test_new_row_with_empty_text_is_created_but_not_changed(self, app):
        with app.app_context():
            row, changed, protected = _apply_row_update(
                None,
                locale="fr",
                msgid="Hello",
                new_msgstr="",
                provenance=PROVENANCE_MACHINE,
                engine=None,
                status=None,
                actor=None,
            )
        assert changed is False
        assert protected is False
        assert row.msgstr == ""

    def test_new_human_row_defaults_to_approved(self, app):
        with app.app_context():
            row, changed, _protected = _apply_row_update(
                None,
                locale="fr",
                msgid="Hello",
                new_msgstr="Bonjour",
                provenance=PROVENANCE_HUMAN,
                engine=None,
                status=None,
                actor=1,
            )
        assert changed is True
        assert row.status == STATUS_APPROVED


# ---------------------------------------------------------------------------
# upsert_string / upsert_batch — DB-backed integration tests (PO sync mocked)
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestUpsertStringIntegration:
    def test_insert_then_machine_cannot_overwrite_human_row(self, db_session):
        from app.services.translation.catalog_service import upsert_string

        with patch("app.services.translation.catalog_service._sync_po_entry") as mock_sync, \
             patch("app.utils.po_persistence.finalize_translation_writes"):
            created = upsert_string(
                locale="fr", msgid="Hello", msgstr="Bonjour",
                provenance=PROVENANCE_HUMAN,
            )
            assert created is True
            mock_sync.reset_mock()

            overwritten = upsert_string(
                locale="fr", msgid="Hello", msgstr="Salut (machine)",
                provenance=PROVENANCE_MACHINE, engine="google",
            )
            assert overwritten is False
            mock_sync.assert_not_called()

        from app.models.translation_quality import TranslationString
        row = TranslationString.query.filter_by(locale="fr", msgid="Hello").first()
        assert row.msgstr == "Bonjour"
        assert row.provenance == PROVENANCE_HUMAN

    def test_force_true_overrides_protection_end_to_end(self, db_session):
        from app.services.translation.catalog_service import upsert_string

        with patch("app.services.translation.catalog_service._sync_po_entry"), \
             patch("app.utils.po_persistence.finalize_translation_writes"):
            upsert_string(locale="fr", msgid="Hello", msgstr="Bonjour", provenance=PROVENANCE_HUMAN)
            overwritten = upsert_string(
                locale="fr", msgid="Hello", msgstr="Salut (forced)",
                provenance=PROVENANCE_MACHINE, engine="google", force=True,
            )
        assert overwritten is True

        from app.models.translation_quality import TranslationString
        row = TranslationString.query.filter_by(locale="fr", msgid="Hello").first()
        assert row.msgstr == "Salut (forced)"
        assert row.provenance == PROVENANCE_MACHINE

    def test_source_locale_is_not_written(self, db_session):
        from app.models.translation_quality import TranslationString
        from app.services.translation.catalog_service import upsert_string

        with patch("app.services.translation.catalog_service._sync_po_entry"), \
             patch("app.utils.po_persistence.finalize_translation_writes"):
            wrote = upsert_string(
                locale="en", msgid="Hello", msgstr="Hello",
                provenance=PROVENANCE_HUMAN,
            )
        assert wrote is False
        assert TranslationString.query.filter_by(locale="en").count() == 0


@pytest.mark.unit
class TestUpsertBatchIntegration:
    def test_empty_items_is_a_noop(self, db_session):
        from app.services.translation.catalog_service import upsert_batch

        result = upsert_batch([], provenance=PROVENANCE_MACHINE)
        assert result == {"updated": 0, "updated_locales": [], "updated_pairs": [], "skipped_protected": 0}

    def test_po_sync_is_called_once_per_locale_not_once_per_item(self, db_session):
        """Regression guard for the O(n) -> O(distinct locales) batching fix."""
        from app.services.translation.catalog_service import upsert_batch

        items = [
            ("Hello", "fr", "Bonjour"),
            ("Goodbye", "fr", "Au revoir"),
            ("Thanks", "fr", "Merci"),
            ("Hello", "es", "Hola"),
            ("Goodbye", "es", "Adiós"),
        ]
        with patch("app.services.translation.catalog_service._sync_po_entries_bulk") as mock_bulk_sync, \
             patch("app.utils.po_persistence.finalize_translation_writes") as mock_finalize:
            result = upsert_batch(items, provenance=PROVENANCE_MACHINE, engine="google")

        assert result["updated"] == 5
        assert sorted(result["updated_locales"]) == ["es", "fr"]
        # 5 items across 2 locales -> exactly 2 PO sync calls, not 5.
        assert mock_bulk_sync.call_count == 2
        mock_finalize.assert_called_once()

    def test_protected_rows_are_skipped_and_reported(self, db_session):
        from app.services.translation.catalog_service import upsert_batch, upsert_string

        with patch("app.services.translation.catalog_service._sync_po_entry"), \
             patch("app.services.translation.catalog_service._sync_po_entries_bulk"), \
             patch("app.utils.po_persistence.finalize_translation_writes"):
            upsert_string(locale="fr", msgid="Hello", msgstr="Bonjour (human)", provenance=PROVENANCE_HUMAN)

            result = upsert_batch(
                [("Hello", "fr", "Salut (machine)"), ("Goodbye", "fr", "Au revoir")],
                provenance=PROVENANCE_MACHINE,
                engine="google",
            )

        assert result["skipped_protected"] == 1
        assert result["updated"] == 1
        assert ("fr", "Goodbye") in result["updated_pairs"]
        assert ("fr", "Hello") not in result["updated_pairs"]

        from app.models.translation_quality import TranslationString
        protected_row = TranslationString.query.filter_by(locale="fr", msgid="Hello").first()
        assert protected_row.msgstr == "Bonjour (human)"

    def test_force_true_allows_batch_to_override_human_rows(self, db_session):
        from app.services.translation.catalog_service import upsert_batch, upsert_string

        with patch("app.services.translation.catalog_service._sync_po_entry"), \
             patch("app.services.translation.catalog_service._sync_po_entries_bulk"), \
             patch("app.utils.po_persistence.finalize_translation_writes"):
            upsert_string(locale="fr", msgid="Hello", msgstr="Bonjour (human)", provenance=PROVENANCE_HUMAN)

            result = upsert_batch(
                [("Hello", "fr", "Salut (forced)")],
                provenance=PROVENANCE_MACHINE,
                force=True,
            )

        assert result["skipped_protected"] == 0
        assert result["updated"] == 1

    def test_source_locale_items_are_ignored(self, db_session):
        from app.models.translation_quality import TranslationString
        from app.services.translation.catalog_service import upsert_batch

        with patch("app.services.translation.catalog_service._sync_po_entries_bulk") as mock_bulk, \
             patch("app.utils.po_persistence.finalize_translation_writes"):
            result = upsert_batch(
                [("Hello", "en", "Hello"), ("Hello", "fr", "Bonjour")],
                provenance=PROVENANCE_HUMAN,
            )

        assert result["updated"] == 1
        assert result["updated_locales"] == ["fr"]
        mock_bulk.assert_called_once()
        assert TranslationString.query.filter_by(locale="en").count() == 0
        assert TranslationString.query.filter_by(locale="fr", msgid="Hello").first().msgstr == "Bonjour"


# ---------------------------------------------------------------------------
# Concurrency: two workers racing to create the same (locale, msgid) row.
#
# Both sides' initial SELECT misses (no row yet), so both build an INSERT; the
# loser's flush hits the real `uq_translation_string_locale_msgid` unique
# constraint. upsert_string/upsert_batch must recover via a SAVEPOINT retry
# (re-SELECT + update) instead of surfacing an IntegrityError.
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestUpsertStringConcurrency:
    def test_retries_as_update_after_concurrent_insert_race(self, db_session):
        from app.models.translation_quality import TranslationString
        from app.services.translation.catalog_service import msgid_hash, upsert_string

        locale, msgid = "fr", "Race condition test string"

        # A "concurrent worker" already committed this row before our call started.
        db_session.add(TranslationString(
            locale=locale,
            msgid=msgid,
            msgid_hash=msgid_hash(msgid),
            msgstr="Ecriture concurrente",
            provenance=PROVENANCE_MACHINE,
            status=STATUS_UNREVIEWED,
            version=1,
        ))
        db_session.commit()

        calls = {"n": 0}

        class _MissFirstThenReal:
            def filter_by(self, **kwargs):
                calls["n"] += 1
                if calls["n"] == 1:
                    # Pretend this call's SELECT ran before the row above existed,
                    # so it will (wrongly) attempt to INSERT a duplicate.
                    return SimpleNamespace(first=lambda: None)
                return db_session.query(TranslationString).filter_by(**kwargs)

        with patch.object(TranslationString, "query", _MissFirstThenReal()), \
             patch("app.services.translation.catalog_service._sync_po_entry") as mock_sync, \
             patch("app.utils.po_persistence.finalize_translation_writes"):
            changed = upsert_string(
                locale=locale, msgid=msgid, msgstr="Traduction gagnante",
                provenance=PROVENANCE_MACHINE, engine="google",
            )

        assert changed is True
        assert calls["n"] == 2  # raced attempt, then a winning retry
        mock_sync.assert_called_once()

        row = db_session.query(TranslationString).filter_by(locale=locale, msgid=msgid).one()
        assert row.msgstr == "Traduction gagnante"

    def test_persistent_conflict_beyond_one_retry_propagates(self, db_session):
        """A second consecutive failure is not silently swallowed -- only one
        retry is attempted, matching a genuinely stuck/unexpected conflict."""
        from app.models.translation_quality import TranslationString
        from app.services.translation.catalog_service import msgid_hash, upsert_string

        locale, msgid = "fr", "Persistent conflict test string"
        db_session.add(TranslationString(
            locale=locale, msgid=msgid, msgid_hash=msgid_hash(msgid),
            msgstr="Existant", provenance=PROVENANCE_MACHINE, status=STATUS_UNREVIEWED, version=1,
        ))
        db_session.commit()

        class _AlwaysMiss:
            def filter_by(self, **kwargs):
                return SimpleNamespace(first=lambda: None)

        with patch.object(TranslationString, "query", _AlwaysMiss()), \
             patch("app.services.translation.catalog_service._sync_po_entry"), \
             patch("app.utils.po_persistence.finalize_translation_writes"):
            with pytest.raises(IntegrityError):
                upsert_string(
                    locale=locale, msgid=msgid, msgstr="Nouvelle traduction",
                    provenance=PROVENANCE_MACHINE, engine="google",
                )
        db_session.rollback()


@pytest.mark.unit
class TestUpsertBatchConcurrency:
    def test_retries_whole_batch_once_after_concurrent_insert_race(self, db_session):
        from app.models.translation_quality import TranslationString
        from app.services.translation.catalog_service import msgid_hash, upsert_batch

        locale, msgid = "fr", "Race condition test string"

        db_session.add(TranslationString(
            locale=locale,
            msgid=msgid,
            msgid_hash=msgid_hash(msgid),
            msgstr="Ecriture concurrente",
            provenance=PROVENANCE_MACHINE,
            status=STATUS_UNREVIEWED,
            version=1,
        ))
        db_session.commit()

        calls = {"n": 0}

        class _MissFirstThenReal:
            def filter(self, *args, **kwargs):
                calls["n"] += 1
                if calls["n"] == 1:
                    return SimpleNamespace(all=lambda: [])
                return db_session.query(TranslationString).filter(*args, **kwargs)

        with patch.object(TranslationString, "query", _MissFirstThenReal()), \
             patch("app.services.translation.catalog_service._sync_po_entries_bulk") as mock_bulk, \
             patch("app.utils.po_persistence.finalize_translation_writes"):
            result = upsert_batch(
                [(msgid, locale, "Traduction gagnante")],
                provenance=PROVENANCE_MACHINE,
                engine="google",
            )

        assert result["updated"] == 1
        assert (locale, msgid) in result["updated_pairs"]
        assert calls["n"] == 2  # raced attempt, then a winning retry
        mock_bulk.assert_called_once()

        row = db_session.query(TranslationString).filter_by(locale=locale, msgid=msgid).one()
        assert row.msgstr == "Traduction gagnante"


# ---------------------------------------------------------------------------
# build_locale_catalog — pure catalog construction (no DB, no files)
# ---------------------------------------------------------------------------
def _pot_entry(msgid, *, msgid_plural=None, occurrences=None, flags=None, obsolete=False):
    return SimpleNamespace(
        msgid=msgid,
        msgid_plural=msgid_plural,
        msgctxt=None,
        occurrences=occurrences or [],
        flags=flags or [],
        obsolete=obsolete,
    )


def _db_row(msgstr, *, msgstr_plural=None):
    return SimpleNamespace(msgstr=msgstr, msgstr_plural=msgstr_plural)


@pytest.mark.unit
class TestBuildLocaleCatalog:
    def test_uses_db_value_for_translated_msgid(self):
        catalog = build_locale_catalog(
            "fr", [_pot_entry("Hello")], {"Hello": _db_row("Bonjour")}
        )
        assert [(e.msgid, e.msgstr) for e in catalog] == [("Hello", "Bonjour")]

    def test_msgid_without_db_row_is_written_untranslated(self):
        """A brand new extracted string still belongs in the catalog, empty."""
        catalog = build_locale_catalog("fr", [_pot_entry("Hello")], {})
        assert [(e.msgid, e.msgstr) for e in catalog] == [("Hello", "")]

    def test_pot_defines_membership_so_stale_db_rows_are_dropped(self):
        catalog = build_locale_catalog(
            "fr",
            [_pot_entry("Kept")],
            {"Kept": _db_row("Garde"), "Removed": _db_row("Supprime")},
        )
        assert [e.msgid for e in catalog] == ["Kept"]

    def test_obsolete_pot_entries_are_skipped(self):
        catalog = build_locale_catalog(
            "fr", [_pot_entry("Gone", obsolete=True), _pot_entry("Here")], {}
        )
        assert [e.msgid for e in catalog] == ["Here"]

    def test_english_msgstr_is_the_msgid(self):
        """English is the source locale and has no translation_string rows."""
        catalog = build_locale_catalog("en", [_pot_entry("Hello")], {})
        assert [(e.msgid, e.msgstr) for e in catalog] == [("Hello", "Hello")]

    def test_english_plural_uses_both_source_forms(self):
        catalog = build_locale_catalog(
            "en", [_pot_entry("%d file", msgid_plural="%d files")], {}
        )
        entry = list(catalog)[0]
        assert entry.msgstr_plural == {0: "%d file", 1: "%d files"}

    def test_plural_values_come_from_the_row(self):
        catalog = build_locale_catalog(
            "fr",
            [_pot_entry("%d file", msgid_plural="%d files")],
            {"%d file": _db_row("", msgstr_plural={"0": "%d fichier", "1": "%d fichiers"})},
        )
        entry = list(catalog)[0]
        assert entry.msgstr_plural == {0: "%d fichier", 1: "%d fichiers"}

    def test_plural_without_row_still_has_both_forms(self):
        """gettext needs the singular/plural slots present even when untranslated."""
        catalog = build_locale_catalog(
            "fr", [_pot_entry("%d file", msgid_plural="%d files")], {}
        )
        assert list(catalog)[0].msgstr_plural == {0: "", 1: ""}

    def test_source_references_and_flags_are_preserved(self):
        catalog = build_locale_catalog(
            "fr",
            [_pot_entry("Hi %(name)s", occurrences=[("app/x.py", "12")], flags=["python-format"])],
            {},
        )
        entry = list(catalog)[0]
        assert entry.occurrences == [("app/x.py", "12")]
        assert "python-format" in entry.flags

    def test_metadata_is_preserved_and_language_forced(self):
        catalog = build_locale_catalog(
            "ru",
            [_pot_entry("Hello")],
            {},
            metadata={"Plural-Forms": "nplurals=3; plural=(n%10==1);", "Language": "fr"},
        )
        assert catalog.metadata["Plural-Forms"] == "nplurals=3; plural=(n%10==1);"
        assert catalog.metadata["Language"] == "ru"
        assert catalog.metadata["Content-Type"] == "text/plain; charset=utf-8"

    def test_baked_value_survives_a_locale_with_no_rows(self):
        """A database never populated for this locale must not erase the image's
        translations — several shipped locales carry thousands of them."""
        catalog = build_locale_catalog(
            "ar",
            [_pot_entry("Hello")],
            {},
            baseline_by_msgid={"Hello": _db_row("مرحبا")},
        )
        assert [(e.msgid, e.msgstr) for e in catalog] == [("Hello", "مرحبا")]

    def test_db_row_wins_over_the_baked_value(self):
        catalog = build_locale_catalog(
            "fr",
            [_pot_entry("Hello")],
            {"Hello": _db_row("Bonjour")},
            baseline_by_msgid={"Hello": _db_row("Salut (stale)")},
        )
        assert list(catalog)[0].msgstr == "Bonjour"

    def test_row_cleared_in_the_grid_is_not_undone_by_the_baked_value(self):
        """An existing row wins even when empty, so clearing a translation sticks."""
        catalog = build_locale_catalog(
            "fr",
            [_pot_entry("Hello")],
            {"Hello": _db_row("")},
            baseline_by_msgid={"Hello": _db_row("Bonjour")},
        )
        assert list(catalog)[0].msgstr == ""

    def test_baked_plural_survives_when_no_row_exists(self):
        catalog = build_locale_catalog(
            "ru",
            [_pot_entry("%d file", msgid_plural="%d files")],
            {},
            baseline_by_msgid={
                "%d file": _db_row("", msgstr_plural={0: "%d файл", 1: "%d файла"})
            },
        )
        assert list(catalog)[0].msgstr_plural == {0: "%d файл", 1: "%d файла"}

    def test_catalog_compiles_to_mo(self, tmp_path):
        """The generated catalog must survive the .mo path gettext actually reads."""
        catalog = build_locale_catalog(
            "fr", [_pot_entry("Hello")], {"Hello": _db_row("Bonjour")}
        )
        target = tmp_path / "messages.mo"
        catalog.save_as_mofile(str(target))
        assert target.stat().st_size > 0


# ---------------------------------------------------------------------------
# Catalog version counter — the cross-container staleness signal
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestCatalogVersion:
    def test_bump_creates_then_increments(self, db_session):
        from app.services.translation.catalog_service import (
            bump_catalog_version,
            read_catalog_version,
        )

        first = bump_catalog_version()
        assert first is not None
        second = bump_catalog_version()
        assert second == first + 1
        assert read_catalog_version() == second

    def test_read_returns_zero_before_any_bump(self, db_session):
        from app.services.translation.catalog_service import read_catalog_version

        assert read_catalog_version() == 0

    def test_materialized_marker_round_trips(self, app, tmp_path):
        from app.services.translation.catalog_service import (
            read_materialized_version,
            write_materialized_version,
        )

        with app.app_context():
            app.config['BACKOFFICE_TRANSLATIONS_DIR'] = str(tmp_path)
            write_materialized_version(12)
            assert read_materialized_version() == 12

    def test_missing_marker_reads_as_behind_everything(self, app, tmp_path):
        from app.services.translation.catalog_service import read_materialized_version

        with app.app_context():
            app.config['BACKOFFICE_TRANSLATIONS_DIR'] = str(tmp_path)
            assert read_materialized_version() == -1

    def test_sync_skips_rebuild_when_marker_is_current(self, app, tmp_path, db_session):
        from app.services.translation import catalog_service

        with app.app_context():
            app.config['BACKOFFICE_TRANSLATIONS_DIR'] = str(tmp_path)
            catalog_service.write_materialized_version(99)
            with patch.object(catalog_service, 'read_catalog_version', return_value=99), \
                 patch.object(catalog_service, 'materialize_catalogs') as mock_mat:
                assert catalog_service.sync_catalogs_if_stale() is None
            mock_mat.assert_not_called()

    def test_sync_rebuilds_when_database_is_ahead(self, app, tmp_path, db_session):
        from app.services.translation import catalog_service

        with app.app_context():
            app.config['BACKOFFICE_TRANSLATIONS_DIR'] = str(tmp_path)
            catalog_service.write_materialized_version(3)
            with patch.object(catalog_service, 'read_catalog_version', return_value=4), \
                 patch.object(catalog_service, 'materialize_catalogs') as mock_mat:
                assert catalog_service.sync_catalogs_if_stale() == 4
            mock_mat.assert_called_once()
            assert catalog_service.read_materialized_version() == 4

    def test_sync_rechecks_inside_the_lock_so_workers_do_not_all_rebuild(self, app, tmp_path, db_session):
        """Every worker polls independently; only the first should do the work."""
        from app.services.translation import catalog_service

        with app.app_context():
            app.config['BACKOFFICE_TRANSLATIONS_DIR'] = str(tmp_path)
            catalog_service.write_materialized_version(3)

            def _peer_wins_the_race(*_args, **_kwargs):
                # Simulate another worker finishing its rebuild while we waited.
                catalog_service.write_materialized_version(4)
                return nullcontext()

            with patch.object(catalog_service, 'read_catalog_version', return_value=4), \
                 patch('app.utils.po_lock.po_file_lock', side_effect=_peer_wins_the_race), \
                 patch.object(catalog_service, 'materialize_catalogs') as mock_mat:
                assert catalog_service.sync_catalogs_if_stale() is None
            mock_mat.assert_not_called()

    def test_sync_backs_off_when_the_lock_is_held(self, app, tmp_path, db_session):
        from app.services.translation import catalog_service

        with app.app_context():
            app.config['BACKOFFICE_TRANSLATIONS_DIR'] = str(tmp_path)
            catalog_service.write_materialized_version(1)
            with patch.object(catalog_service, 'read_catalog_version', return_value=9), \
                 patch('app.utils.po_lock.po_file_lock', side_effect=RuntimeError('held')), \
                 patch.object(catalog_service, 'materialize_catalogs') as mock_mat:
                assert catalog_service.sync_catalogs_if_stale() is None
            mock_mat.assert_not_called()
            assert catalog_service.read_materialized_version() == 1

    def test_sync_does_nothing_when_version_unreadable(self, app, tmp_path):
        from app.services.translation import catalog_service

        with app.app_context():
            app.config['BACKOFFICE_TRANSLATIONS_DIR'] = str(tmp_path)
            with patch.object(catalog_service, 'read_catalog_version', return_value=None), \
                 patch.object(catalog_service, 'materialize_catalogs') as mock_mat:
                assert catalog_service.sync_catalogs_if_stale() is None
            mock_mat.assert_not_called()
