"""Unit tests for plugins/fdrs/services/fdrs_publication_service.py.

Uses real DB fixtures (factories + db_session), since the service is mostly
DB joins/aggregation. FDRS_TEMPLATE_ID is monkeypatched to the freshly-created
test template's id in every module that imports it, so a plain (non-21) test
template behaves as "the FDRS template" for the duration of each test.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.exceptions import NotFound

from app.models import AssignmentEntityStatus, FormData
from plugins.fdrs.services import fdrs_publication_service as svc
from tests.factories import (
    create_test_assignment_entity_status,
    create_test_country,
    create_test_item,
    create_test_section,
    create_test_template,
    create_test_user,
)

pytestmark = [pytest.mark.unit]


def _patch_fdrs_template_id(monkeypatch, template_id: int) -> None:
    """Make `template_id` look like the FDRS template to every module that cached it."""
    import plugins.fdrs.public_api_routes as public_api_routes
    import plugins.fdrs.publication_routes as publication_routes

    monkeypatch.setattr(svc, "FDRS_TEMPLATE_ID", template_id)
    monkeypatch.setattr(publication_routes, "FDRS_TEMPLATE_ID", template_id)
    monkeypatch.setattr(public_api_routes, "FDRS_TEMPLATE_ID", template_id)


def _set_form_data(db_session, aes, item, *, value=None, published_value=None, numeric_value=None):
    row = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=item.id,
        value=value,
        numeric_value=numeric_value,
        published_value=published_value,
    )
    db_session.add(row)
    return row


@pytest.fixture
def fdrs_scenario(db_session, monkeypatch):
    """Two-country FDRS assignment with a public/private item split and one
    pending change of each kind (new/changed/removed/unchanged/empty) spread
    across the two countries, on the public items only."""
    template = create_test_template(db_session, name="FDRS Test Template")
    _patch_fdrs_template_id(monkeypatch, template.id)

    section = create_test_section(db_session, template)
    item_pub1 = create_test_item(db_session, section, template, label="Public Item 1")
    item_pub2 = create_test_item(db_session, section, template, label="Public Item 2")
    item_pub3 = create_test_item(db_session, section, template, label="Public Item 3 (never reported)")
    item_private = create_test_item(db_session, section, template, label="Internal Item")
    # default privacy is 'ifrc_network' — item_private is left untouched intentionally.
    # `config` is a plain JSON column (no MutableDict tracking), so an in-place
    # dict mutation via set_privacy() needs flag_modified() to be persisted.
    for item in (item_pub1, item_pub2, item_pub3):
        item.set_privacy("public")
        flag_modified(item, "config")
    db_session.commit()

    country_a = create_test_country(db_session, name="Alpha")
    country_b = create_test_country(db_session, name="Beta")

    aes_a = create_test_assignment_entity_status(
        db_session, country=country_a, template=template, period_name="2024",
    )
    aes_b = AssignmentEntityStatus(
        assigned_form_id=aes_a.assigned_form_id,
        entity_type="country",
        entity_id=country_b.id,
        status=aes_a.status,
    )
    db_session.add(aes_b)
    db_session.commit()
    db_session.refresh(aes_b)

    # Country A: item_pub1 -> new, item_pub2 -> changed, item_pub3 -> empty
    _set_form_data(db_session, aes_a, item_pub1, value="10", numeric_value=10, published_value=None)
    _set_form_data(db_session, aes_a, item_pub2, value="20", numeric_value=20, published_value="15")
    _set_form_data(db_session, aes_a, item_pub3, value=None, published_value=None)
    _set_form_data(db_session, aes_a, item_private, value="secret-a", published_value=None)

    # Country B: item_pub1 -> unchanged, item_pub2 -> removed, item_pub3 -> empty
    _set_form_data(db_session, aes_b, item_pub1, value="5", numeric_value=5, published_value="5")
    _set_form_data(db_session, aes_b, item_pub2, value=None, published_value="99")
    _set_form_data(db_session, aes_b, item_pub3, value=None, published_value=None)
    _set_form_data(db_session, aes_b, item_private, value="secret-b", published_value=None)

    db_session.commit()

    publisher = create_test_user(db_session, email="publisher@example.com")

    return {
        "template": template,
        "assigned_form_id": aes_a.assigned_form_id,
        "aes_a": aes_a,
        "aes_b": aes_b,
        "country_a": country_a,
        "country_b": country_b,
        "item_pub1": item_pub1,
        "item_pub2": item_pub2,
        "item_pub3": item_pub3,
        "item_private": item_private,
        "publisher": publisher,
    }


class TestListFdrsAssignments:
    def test_returns_assignment_for_fdrs_template_only(self, db_session, fdrs_scenario):
        assignments = svc.list_fdrs_assignments()
        ids = [a.id for a in assignments]
        assert fdrs_scenario["assigned_form_id"] in ids

    def test_excludes_assignments_for_other_templates(self, db_session, fdrs_scenario):
        other_template = create_test_template(db_session, name="Not FDRS")
        other_aes = create_test_assignment_entity_status(
            db_session, template=other_template, period_name="2024-other",
        )
        assignments = svc.list_fdrs_assignments()
        ids = [a.id for a in assignments]
        assert other_aes.assigned_form_id not in ids


class TestGetAssignmentPublicationSummary:
    def test_totals_and_country_counts(self, db_session, fdrs_scenario):
        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])

        assert summary["countries_total"] == 2
        assert summary["countries_with_pending_changes"] == 2
        assert summary["totals"] == {
            "new": 1, "changed": 1, "removed": 1, "unchanged": 1, "empty": 2,
        }
        assert summary["pending_total"] == 3

    def test_private_item_never_counted(self, db_session, fdrs_scenario):
        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        # 3 public items per country, private item excluded -> 3, not 4.
        for country in summary["countries"]:
            assert country["total_public_items"] == 3

    def test_most_pending_country_sorted_first(self, db_session, fdrs_scenario):
        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        assert summary["countries"][0]["country_id"] == fdrs_scenario["country_a"].id
        assert summary["countries"][0]["pending_count"] == 2
        assert summary["countries"][1]["country_id"] == fdrs_scenario["country_b"].id
        assert summary["countries"][1]["pending_count"] == 1

    def test_never_published_country_has_no_published_at(self, db_session, fdrs_scenario):
        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        assert all(c["published_at"] is None for c in summary["countries"])

    def test_404_for_non_fdrs_assignment(self, db_session, fdrs_scenario):
        other_template = create_test_template(db_session, name="Not FDRS 2")
        other_aes = create_test_assignment_entity_status(
            db_session, template=other_template, period_name="2024-other-2",
        )
        with pytest.raises(NotFound):
            svc.get_assignment_publication_summary(other_aes.assigned_form_id)

    def test_404_for_nonexistent_assignment(self, db_session, fdrs_scenario):
        with pytest.raises(NotFound):
            svc.get_assignment_publication_summary(999_999_999)


class TestGetCountryChangeDetail:
    def test_items_for_country_a_exclude_empty_and_private(self, db_session, fdrs_scenario):
        detail = svc.get_country_change_detail(
            fdrs_scenario["assigned_form_id"], fdrs_scenario["aes_a"].id
        )
        assert detail["country_name"] == "Alpha"
        kinds = [item["kind"] for item in detail["items"]]
        assert set(kinds) == {"new", "changed"}
        labels = [item["label"] for item in detail["items"]]
        assert "Internal Item" not in labels
        assert "Public Item 3 (never reported)" not in labels

    def test_changed_sorted_before_new(self, db_session, fdrs_scenario):
        detail = svc.get_country_change_detail(
            fdrs_scenario["assigned_form_id"], fdrs_scenario["aes_a"].id
        )
        kinds = [item["kind"] for item in detail["items"]]
        assert kinds.index("changed") < kinds.index("new")

    def test_country_b_shows_removed_and_unchanged(self, db_session, fdrs_scenario):
        detail = svc.get_country_change_detail(
            fdrs_scenario["assigned_form_id"], fdrs_scenario["aes_b"].id
        )
        kinds = {item["kind"] for item in detail["items"]}
        assert kinds == {"removed", "unchanged"}

    def test_current_and_published_values_are_reported(self, db_session, fdrs_scenario):
        detail = svc.get_country_change_detail(
            fdrs_scenario["assigned_form_id"], fdrs_scenario["aes_a"].id
        )
        changed_item = next(i for i in detail["items"] if i["kind"] == "changed")
        assert changed_item["current_value"] == "20"
        assert changed_item["published_value"] == "15"

    def test_404_for_aes_from_a_different_assignment(self, db_session, fdrs_scenario):
        other_country = create_test_country(db_session, name="Gamma")
        other_aes = create_test_assignment_entity_status(
            db_session, country=other_country, template=fdrs_scenario["template"], period_name="2025",
        )
        with pytest.raises(NotFound):
            svc.get_country_change_detail(fdrs_scenario["assigned_form_id"], other_aes.id)


class TestPublishAssignment:
    def test_publishes_all_countries_by_default(self, db_session, fdrs_scenario):
        stats = svc.publish_assignment(
            fdrs_scenario["assigned_form_id"], user_id=fdrs_scenario["publisher"].id
        )

        assert stats["published_countries"] == 2
        assert stats["totals"] == {
            "new": 1, "changed": 1, "removed": 1, "unchanged": 1, "empty": 2,
        }
        assert stats["pending_total"] == 3

    def test_public_rows_copied_to_published_snapshot(self, db_session, fdrs_scenario):
        svc.publish_assignment(fdrs_scenario["assigned_form_id"], user_id=fdrs_scenario["publisher"].id)

        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_a"].id,
            form_item_id=fdrs_scenario["item_pub1"].id,
        ).one()
        assert row.published_value == "10"
        assert row.published_numeric_value == 10
        assert row.published_at is not None
        assert row.published_by_user_id == fdrs_scenario["publisher"].id

    def test_removed_row_is_cleared_on_publish(self, db_session, fdrs_scenario):
        svc.publish_assignment(fdrs_scenario["assigned_form_id"], user_id=fdrs_scenario["publisher"].id)

        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_b"].id,
            form_item_id=fdrs_scenario["item_pub2"].id,
        ).one()
        # Was published_value="99" with no current value -> publishing clears it.
        assert row.published_value is None

    def test_private_item_never_touched(self, db_session, fdrs_scenario):
        svc.publish_assignment(fdrs_scenario["assigned_form_id"], user_id=fdrs_scenario["publisher"].id)

        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_a"].id,
            form_item_id=fdrs_scenario["item_private"].id,
        ).one()
        assert row.published_value is None
        assert row.published_at is None

    def test_assignment_entity_status_audit_fields_set(self, db_session, fdrs_scenario):
        svc.publish_assignment(fdrs_scenario["assigned_form_id"], user_id=fdrs_scenario["publisher"].id)

        db_session.refresh(fdrs_scenario["aes_a"])
        db_session.refresh(fdrs_scenario["aes_b"])
        assert fdrs_scenario["aes_a"].published_at is not None
        assert fdrs_scenario["aes_a"].published_by_user_id == fdrs_scenario["publisher"].id
        assert fdrs_scenario["aes_b"].published_at is not None

    def test_scoped_publish_only_touches_selected_country(self, db_session, fdrs_scenario):
        stats = svc.publish_assignment(
            fdrs_scenario["assigned_form_id"],
            assignment_entity_status_ids=[fdrs_scenario["aes_a"].id],
            user_id=fdrs_scenario["publisher"].id,
        )
        assert stats["published_countries"] == 1

        db_session.refresh(fdrs_scenario["aes_a"])
        db_session.refresh(fdrs_scenario["aes_b"])
        assert fdrs_scenario["aes_a"].published_at is not None
        assert fdrs_scenario["aes_b"].published_at is None

        untouched = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_b"].id,
            form_item_id=fdrs_scenario["item_pub1"].id,
        ).one()
        assert untouched.published_value == "5"  # unchanged from setup, not re-touched

    def test_foreign_aes_id_is_silently_dropped(self, db_session, fdrs_scenario):
        stats = svc.publish_assignment(
            fdrs_scenario["assigned_form_id"],
            assignment_entity_status_ids=[999_999_999],
            user_id=fdrs_scenario["publisher"].id,
        )
        assert stats["published_countries"] == 0
        assert stats["totals"] == {"new": 0, "changed": 0, "removed": 0, "unchanged": 0, "empty": 0}

    def test_404_for_non_fdrs_assignment(self, db_session, fdrs_scenario):
        other_template = create_test_template(db_session, name="Not FDRS 3")
        other_aes = create_test_assignment_entity_status(
            db_session, template=other_template, period_name="2024-other-3",
        )
        with pytest.raises(NotFound):
            svc.publish_assignment(other_aes.assigned_form_id, user_id=fdrs_scenario["publisher"].id)
