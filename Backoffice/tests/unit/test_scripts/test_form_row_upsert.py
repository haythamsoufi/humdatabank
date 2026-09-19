"""Unit tests for scripts/imports/form_row_upsert.py (shared FDRS/UPR upsert).

Covers the "unchanged row" skip added to avoid rewriting form_data rows whose
value/disagg/flags haven't actually changed (the common case when FDRS/UPR
re-sync the same recent periods), and the adaptive prefetch query (two-column
IN fastpath vs. the exact tuple_ IN fallback) — both must resolve to the same
existing rows.
"""
from __future__ import annotations

import os
import sys

import pytest

_SCRIPTS_IMPORTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "scripts",
    "imports",
)
if _SCRIPTS_IMPORTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_IMPORTS_DIR)

import form_row_upsert as form_row_upsert_mod  # noqa: E402
from form_row_upsert import upsert_form_data_rows  # noqa: E402

from app.models.forms import FormData  # noqa: E402
from tests.factories import (  # noqa: E402
    create_test_assignment_entity_status,
    create_test_item,
    create_test_section,
    create_test_template,
)

pytestmark = [pytest.mark.unit]


def _make_aes_and_item(db_session):
    """Create a fresh template/section/item + assignment so each pair is independent."""
    template = create_test_template(db_session)
    section = create_test_section(db_session, template)
    item = create_test_item(db_session, section, template)
    aes = create_test_assignment_entity_status(db_session, template=template)
    return aes, item


def _row(aes_id, item_id, value, **extra):
    row = {
        "assignment_entity_status_id": str(aes_id),
        "item_id": str(item_id),
        "value": value,
    }
    row.update(extra)
    return row


class TestUpsertFormDataRowsUnchangedDetection:
    def test_identical_value_is_marked_unchanged_and_not_rewritten(self, db_session, app):
        with app.app_context():
            aes, item = _make_aes_and_item(db_session)
            # disagg_type="simple" mirrors what this same upsert function would have set on
            # the row's original import (payload.get("value") not in (None, "") -> "simple").
            existing = FormData(
                assignment_entity_status_id=aes.id, form_item_id=item.id, value="42", disagg_type="simple"
            )
            existing._sync_numeric_value_from_string()
            db_session.add(existing)
            db_session.commit()
            existing_id = existing.id

            stats = upsert_form_data_rows([_row(aes.id, item.id, "42")], batch_size=100)

            assert stats["unchanged"] == 1
            assert stats["updated"] == 0
            assert stats["inserted"] == 0
            assert stats["errors"] == 0

            db_session.expire_all()
            reloaded = db_session.get(FormData, existing_id)
            assert reloaded.value == "42"

    def test_change_recorder_skips_unchanged_rows(self, db_session, app):
        with app.app_context():
            aes_same, item_same = _make_aes_and_item(db_session)
            aes_changed, item_changed = _make_aes_and_item(db_session)
            aes_new, item_new = _make_aes_and_item(db_session)
            same_row = FormData(
                assignment_entity_status_id=aes_same.id,
                form_item_id=item_same.id,
                value="42",
                disagg_type="simple",
            )
            same_row._sync_numeric_value_from_string()
            changed_row = FormData(
                assignment_entity_status_id=aes_changed.id,
                form_item_id=item_changed.id,
                value="10",
                disagg_type="simple",
            )
            changed_row._sync_numeric_value_from_string()
            db_session.add_all([same_row, changed_row])
            db_session.commit()

            recorded = []
            stats = upsert_form_data_rows(
                [
                    _row(aes_same.id, item_same.id, "42"),
                    _row(aes_changed.id, item_changed.id, "11"),
                    _row(aes_new.id, item_new.id, "7"),
                ],
                batch_size=100,
                change_recorder=recorded.append,
            )

            assert stats["unchanged"] == 1
            assert stats["updated"] == 1
            assert stats["inserted"] == 1
            assert [row["op"] for row in recorded] == ["update", "insert"]
            assert recorded[0]["old_value"] == "10"
            assert recorded[0]["new_value"] == "11"

    def test_changed_value_is_updated(self, db_session, app):
        with app.app_context():
            aes, item = _make_aes_and_item(db_session)
            existing = FormData(
                assignment_entity_status_id=aes.id, form_item_id=item.id, value="42", disagg_type="simple"
            )
            existing._sync_numeric_value_from_string()
            db_session.add(existing)
            db_session.commit()
            existing_id = existing.id

            stats = upsert_form_data_rows([_row(aes.id, item.id, "99")], batch_size=100)

            assert stats["updated"] == 1
            assert stats["unchanged"] == 0
            assert stats["errors"] == 0

            db_session.expire_all()
            reloaded = db_session.get(FormData, existing_id)
            assert reloaded.value == "99"
            assert reloaded.numeric_value == 99.0

    def test_new_pair_is_inserted(self, db_session, app):
        with app.app_context():
            aes, item = _make_aes_and_item(db_session)

            stats = upsert_form_data_rows([_row(aes.id, item.id, "7")], batch_size=100)

            assert stats["inserted"] == 1
            assert stats["updated"] == 0
            assert stats["unchanged"] == 0

            row = (
                db_session.query(FormData)
                .filter_by(assignment_entity_status_id=aes.id, form_item_id=item.id)
                .one()
            )
            assert row.value == "7"

    def test_dry_run_distinguishes_updated_from_unchanged_without_writing(self, db_session, app):
        with app.app_context():
            aes1, item1 = _make_aes_and_item(db_session)
            aes2, item2 = _make_aes_and_item(db_session)
            unchanged_row = FormData(
                assignment_entity_status_id=aes1.id, form_item_id=item1.id, value="1", disagg_type="simple"
            )
            unchanged_row._sync_numeric_value_from_string()
            changed_row = FormData(
                assignment_entity_status_id=aes2.id, form_item_id=item2.id, value="2", disagg_type="simple"
            )
            changed_row._sync_numeric_value_from_string()
            db_session.add_all([unchanged_row, changed_row])
            db_session.commit()
            changed_row_id = changed_row.id

            stats = upsert_form_data_rows(
                [_row(aes1.id, item1.id, "1"), _row(aes2.id, item2.id, "999")],
                dry_run=True,
                batch_size=100,
            )

            assert stats["unchanged"] == 1
            assert stats["updated"] == 1
            assert stats["inserted"] == 0

            db_session.expire_all()
            # Dry run must never write, even for the row it correctly classifies as "updated".
            assert db_session.get(FormData, changed_row_id).value == "2"


class TestUpsertFormDataRowsDisaggComparison:
    def test_identical_disagg_dict_is_unchanged(self, db_session, app):
        with app.app_context():
            aes, item = _make_aes_and_item(db_session)
            existing = FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                disagg_data={"Home Government_Funding": 1000, "Corporations_Funding": 250},
                disagg_type="matrix",
            )
            db_session.add(existing)
            db_session.commit()

            row = _row(
                aes.id,
                item.id,
                None,
                disagg_data='{"Home Government_Funding": 1000, "Corporations_Funding": 250}',
                _debug_disagg_type="matrix",
            )
            stats = upsert_form_data_rows([row], batch_size=100)

            assert stats["unchanged"] == 1
            assert stats["updated"] == 0

    def test_changed_disagg_value_is_updated(self, db_session, app):
        with app.app_context():
            aes, item = _make_aes_and_item(db_session)
            existing = FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                disagg_data={"Home Government_Funding": 1000},
                disagg_type="matrix",
            )
            db_session.add(existing)
            db_session.commit()
            existing_id = existing.id

            row = _row(
                aes.id,
                item.id,
                None,
                disagg_data='{"Home Government_Funding": 2000}',
                _debug_disagg_type="matrix",
            )
            stats = upsert_form_data_rows([row], batch_size=100)

            assert stats["updated"] == 1
            assert stats["unchanged"] == 0

            db_session.expire_all()
            reloaded = db_session.get(FormData, existing_id)
            assert reloaded.disagg_data == {"Home Government_Funding": 2000}


class TestUpsertFormDataRowsPrefetchFastpath:
    def test_fastpath_and_fallback_resolve_the_same_existing_rows(self, db_session, app, monkeypatch):
        """The two-column IN() fastpath must match exactly what the tuple_ IN() fallback finds."""
        with app.app_context():
            pairs = []
            for _ in range(4):
                aes, item = _make_aes_and_item(db_session)
                existing = FormData(
                    assignment_entity_status_id=aes.id, form_item_id=item.id, value="10", disagg_type="simple"
                )
                existing._sync_numeric_value_from_string()
                db_session.add(existing)
                pairs.append((aes.id, item.id))
            db_session.commit()

            rows = [_row(aes_id, item_id, "20") for aes_id, item_id in pairs]

            # Force the fastpath (item cardinality is tiny in this test) and confirm every
            # pre-existing row is found and updated, not mistaken for a new insert.
            monkeypatch.setattr(form_row_upsert_mod, "_PREFETCH_ITEM_FASTPATH_MAX", 300)
            stats_fastpath = upsert_form_data_rows(list(rows), batch_size=100)
            assert stats_fastpath["updated"] == len(pairs)
            assert stats_fastpath["inserted"] == 0

            # Reset values, then force the exact tuple_ IN() fallback and confirm parity.
            for aes_id, item_id in pairs:
                fd = (
                    db_session.query(FormData)
                    .filter_by(assignment_entity_status_id=aes_id, form_item_id=item_id)
                    .one()
                )
                fd.value = "10"
                fd._sync_numeric_value_from_string()
            db_session.commit()

            monkeypatch.setattr(form_row_upsert_mod, "_PREFETCH_ITEM_FASTPATH_MAX", 0)
            stats_fallback = upsert_form_data_rows(list(rows), batch_size=100)
            assert stats_fallback["updated"] == len(pairs)
            assert stats_fallback["inserted"] == 0

    def test_fastpath_does_not_leak_unrelated_pairs(self, db_session, app, monkeypatch):
        """A shared form_item_id across unrelated assignments must not cross-match."""
        with app.app_context():
            aes_a, item = _make_aes_and_item(db_session)
            template_b = create_test_template(db_session)
            section_b = create_test_section(db_session, template_b)
            aes_b = create_test_assignment_entity_status(db_session, template=template_b)

            # Only aes_a has an existing row for `item`; aes_b has never reported it.
            existing = FormData(
                assignment_entity_status_id=aes_a.id, form_item_id=item.id, value="10", disagg_type="simple"
            )
            existing._sync_numeric_value_from_string()
            db_session.add(existing)
            db_session.commit()

            monkeypatch.setattr(form_row_upsert_mod, "_PREFETCH_ITEM_FASTPATH_MAX", 300)
            stats = upsert_form_data_rows(
                [_row(aes_a.id, item.id, "10"), _row(aes_b.id, item.id, "30")],
                batch_size=100,
            )

            # aes_a/item is truly unchanged; aes_b/item must be a fresh insert, not
            # mistaken for aes_a's row just because the fastpath query fetched both.
            assert stats["unchanged"] == 1
            assert stats["inserted"] == 1
            assert stats["updated"] == 0

            row_b = (
                db_session.query(FormData)
                .filter_by(assignment_entity_status_id=aes_b.id, form_item_id=item.id)
                .one()
            )
            assert row_b.value == "30"
