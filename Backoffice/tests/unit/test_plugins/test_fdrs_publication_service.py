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


def _set_form_data(
    db_session,
    aes,
    item,
    *,
    value=None,
    published_value=None,
    published_numeric_value=None,
    published_source=None,
    numeric_value=None,
    imputed_value=None,
    imputed_numeric_value=None,
    imputed_disagg_data=None,
):
    row = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=item.id,
        value=value,
        numeric_value=numeric_value,
        published_value=published_value,
        published_numeric_value=published_numeric_value,
        published_source=published_source,
        imputed_value=imputed_value,
        imputed_numeric_value=imputed_numeric_value,
        imputed_disagg_data=imputed_disagg_data,
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
    _set_form_data(
        db_session, aes_b, item_pub1, value="5", numeric_value=5, published_value="5",
        published_source=FormData.PUBLISHED_SOURCE_REPORTED,
    )
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
            "new": 1, "changed": 1, "removed": 1, "source": 0, "unchanged": 1, "empty": 2,
        }
        assert summary["pending_total"] == 3

    def test_private_item_never_counted(self, db_session, fdrs_scenario):
        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        # 3 public items per country, private item excluded -> 3, not 4.
        for country in summary["countries"]:
            assert country["total_public_items"] == 3

    def test_review_flags_sorted_before_pending_count(self, db_session, fdrs_scenario):
        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        # Beta has a value that will be cleared (review flag); Alpha has more
        # pending rows but only a 33% change, below the 50% variation threshold.
        assert summary["countries"][0]["country_id"] == fdrs_scenario["country_b"].id
        assert summary["countries"][0]["review_count"] == 1
        assert summary["countries"][1]["country_id"] == fdrs_scenario["country_a"].id
        assert summary["countries"][1]["pending_count"] == 2

    def test_analysis_flags_cleared_value(self, db_session, fdrs_scenario):
        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        flags = summary["analysis"]["flags"]
        assert summary["analysis"]["flag_count"] == 1
        assert flags[0]["country_id"] == fdrs_scenario["country_b"].id
        assert flags[0]["kind"] == "removed"
        assert any(r["code"] == "cleared" for r in flags[0]["reasons"])

    def test_analysis_flags_large_change_vs_published(self, db_session, fdrs_scenario):
        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_a"].id,
            form_item_id=fdrs_scenario["item_pub2"].id,
        ).one()
        row.value = "45"
        row.numeric_value = 45
        row.published_numeric_value = 15
        db_session.commit()

        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        flags = [
            f for f in summary["analysis"]["flags"]
            if f["form_item_id"] == fdrs_scenario["item_pub2"].id
            and f["country_id"] == fdrs_scenario["country_a"].id
        ]
        assert flags
        assert flags[0]["severity"] == "high"
        assert any(
            r["code"] == "large_variation" and r["vs"] == "published"
            for r in flags[0]["reasons"]
        )

    def test_analysis_flags_yoy_vs_prior_period(self, db_session, fdrs_scenario):
        prior_aes = create_test_assignment_entity_status(
            db_session,
            country=fdrs_scenario["country_a"],
            template=fdrs_scenario["template"],
            period_name="2023",
        )
        _set_form_data(
            db_session,
            prior_aes,
            fdrs_scenario["item_pub1"],
            value="10",
            numeric_value=10,
            published_value="10",
            published_numeric_value=10,
            published_source=FormData.PUBLISHED_SOURCE_REPORTED,
        )
        db_session.commit()

        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        assert summary["analysis"]["prior_period_name"] == "2023"
        flags = [
            f for f in summary["analysis"]["flags"]
            if f["form_item_id"] == fdrs_scenario["item_pub1"].id
            and f["country_id"] == fdrs_scenario["country_a"].id
        ]
        # Current new value 10 vs prior published 10 → no YoY flag.
        assert flags == []

        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_a"].id,
            form_item_id=fdrs_scenario["item_pub1"].id,
        ).one()
        row.value = "30"
        row.numeric_value = 30
        db_session.commit()

        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        flags = [
            f for f in summary["analysis"]["flags"]
            if f["form_item_id"] == fdrs_scenario["item_pub1"].id
            and f["country_id"] == fdrs_scenario["country_a"].id
        ]
        assert flags
        assert any(
            r["code"] == "large_variation" and r["vs"] == "prior"
            for r in flags[0]["reasons"]
        )

    def test_analysis_flags_already_published_value_vs_prior(self, db_session, fdrs_scenario):
        prior_aes = create_test_assignment_entity_status(
            db_session,
            country=fdrs_scenario["country_b"],
            template=fdrs_scenario["template"],
            period_name="2023",
        )
        _set_form_data(
            db_session,
            prior_aes,
            fdrs_scenario["item_pub1"],
            value="2",
            numeric_value=2,
            published_value="2",
            published_numeric_value=2,
            published_source=FormData.PUBLISHED_SOURCE_REPORTED,
        )
        db_session.commit()

        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        flags = [
            f for f in summary["analysis"]["flags"]
            if f["form_item_id"] == fdrs_scenario["item_pub1"].id
            and f["country_id"] == fdrs_scenario["country_b"].id
        ]
        # Beta's published 5 vs prior 2 is a 150% YoY swing, even though this
        # assignment row is already unchanged/published.
        assert flags
        assert flags[0]["kind"] == "unchanged"
        assert any(
            r["code"] == "large_variation" and r["vs"] == "prior"
            for r in flags[0]["reasons"]
        )

    def test_analysis_uses_unpublished_prior_reported_value(self, db_session, fdrs_scenario):
        prior_aes = create_test_assignment_entity_status(
            db_session,
            country=fdrs_scenario["country_a"],
            template=fdrs_scenario["template"],
            period_name="2023",
        )
        _set_form_data(
            db_session,
            prior_aes,
            fdrs_scenario["item_pub1"],
            value="8",
            numeric_value=8,
        )
        db_session.commit()

        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        flags = [
            f for f in summary["analysis"]["flags"]
            if f["form_item_id"] == fdrs_scenario["item_pub1"].id
            and f["country_id"] == fdrs_scenario["country_a"].id
        ]
        # Current new value 10 vs unpublished prior 8 is only 25% — not flagged.
        assert flags == []

        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_a"].id,
            form_item_id=fdrs_scenario["item_pub1"].id,
        ).one()
        row.value = "20"
        row.numeric_value = 20
        db_session.commit()

        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        flags = [
            f for f in summary["analysis"]["flags"]
            if f["form_item_id"] == fdrs_scenario["item_pub1"].id
            and f["country_id"] == fdrs_scenario["country_a"].id
        ]
        assert flags
        assert any(
            r["code"] == "large_variation" and r["vs"] == "prior"
            for r in flags[0]["reasons"]
        )

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
        assert changed_item["current_is_imputed"] is False

    def test_detail_shows_imputed_as_current_value_when_reported_missing(self, db_session, fdrs_scenario):
        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_a"].id,
            form_item_id=fdrs_scenario["item_pub3"].id,
        ).one()
        row.imputed_value = "42"
        db_session.commit()

        detail = svc.get_country_change_detail(
            fdrs_scenario["assigned_form_id"], fdrs_scenario["aes_a"].id
        )
        imputed_item = next(i for i in detail["items"] if i["form_item_id"] == fdrs_scenario["item_pub3"].id)
        assert imputed_item["current_value"] == "42"
        assert imputed_item["current_is_imputed"] is True
        assert imputed_item["kind"] == "new"
        assert imputed_item["published_source"] is None

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
            "new": 1, "changed": 1, "removed": 1, "source": 0, "unchanged": 1, "empty": 2,
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
        assert row.published_source == FormData.PUBLISHED_SOURCE_REPORTED
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
        assert row.published_source is None

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
        assert stats["totals"] == {
            "new": 0, "changed": 0, "removed": 0, "source": 0, "unchanged": 0, "empty": 0,
        }

    def test_404_for_non_fdrs_assignment(self, db_session, fdrs_scenario):
        other_template = create_test_template(db_session, name="Not FDRS 3")
        other_aes = create_test_assignment_entity_status(
            db_session, template=other_template, period_name="2024-other-3",
        )
        with pytest.raises(NotFound):
            svc.publish_assignment(other_aes.assigned_form_id, user_id=fdrs_scenario["publisher"].id)

    def test_country_with_no_public_form_data_rows_is_not_marked_published(self, db_session, fdrs_scenario):
        """A selected country with zero FormData rows on any public item (nothing
        ever reported/imported for it) has nothing to publish: it must not be
        counted in published_countries, and its audit fields stay untouched."""
        country_c = create_test_country(db_session, name="Gamma")
        aes_c = AssignmentEntityStatus(
            assigned_form_id=fdrs_scenario["aes_a"].assigned_form_id,
            entity_type="country",
            entity_id=country_c.id,
            status=fdrs_scenario["aes_a"].status,
        )
        db_session.add(aes_c)
        db_session.commit()
        db_session.refresh(aes_c)

        stats = svc.publish_assignment(
            fdrs_scenario["assigned_form_id"],
            assignment_entity_status_ids=[aes_c.id],
            user_id=fdrs_scenario["publisher"].id,
        )
        assert stats["published_countries"] == 0
        assert stats["totals"] == {
            "new": 0, "changed": 0, "removed": 0, "source": 0, "unchanged": 0, "empty": 0,
        }

        db_session.refresh(aes_c)
        assert aes_c.published_at is None
        assert aes_c.published_by_user_id is None

    def test_mixed_selection_only_counts_countries_with_data(self, db_session, fdrs_scenario):
        """Selecting one country with data and one without: only the one with
        data is counted/stamped, but the one with data still publishes normally."""
        country_c = create_test_country(db_session, name="Delta")
        aes_c = AssignmentEntityStatus(
            assigned_form_id=fdrs_scenario["aes_a"].assigned_form_id,
            entity_type="country",
            entity_id=country_c.id,
            status=fdrs_scenario["aes_a"].status,
        )
        db_session.add(aes_c)
        db_session.commit()
        db_session.refresh(aes_c)

        stats = svc.publish_assignment(
            fdrs_scenario["assigned_form_id"],
            assignment_entity_status_ids=[fdrs_scenario["aes_a"].id, aes_c.id],
            user_id=fdrs_scenario["publisher"].id,
        )
        assert stats["published_countries"] == 1

        db_session.refresh(fdrs_scenario["aes_a"])
        db_session.refresh(aes_c)
        assert fdrs_scenario["aes_a"].published_at is not None
        assert aes_c.published_at is None

    def test_publishes_imputed_value_when_reported_is_missing(self, db_session, fdrs_scenario):
        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_a"].id,
            form_item_id=fdrs_scenario["item_pub3"].id,
        ).one()
        row.imputed_value = "42"
        row.imputed_numeric_value = 42
        db_session.commit()

        stats = svc.publish_assignment(
            fdrs_scenario["assigned_form_id"],
            assignment_entity_status_ids=[fdrs_scenario["aes_a"].id],
            user_id=fdrs_scenario["publisher"].id,
        )
        assert stats["totals"]["new"] == 2  # item_pub1 reported + item_pub3 imputed
        assert stats["totals"]["empty"] == 0

        db_session.refresh(row)
        assert row.published_value == "42"
        assert row.published_numeric_value == 42
        assert row.published_source == FormData.PUBLISHED_SOURCE_IMPUTED

    def test_reported_value_wins_over_imputed_on_publish(self, db_session, fdrs_scenario):
        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_a"].id,
            form_item_id=fdrs_scenario["item_pub1"].id,
        ).one()
        row.imputed_value = "99"
        row.imputed_numeric_value = 99
        db_session.commit()

        svc.publish_assignment(
            fdrs_scenario["assigned_form_id"],
            assignment_entity_status_ids=[fdrs_scenario["aes_a"].id],
        )

        db_session.refresh(row)
        assert row.published_value == "10"
        assert row.published_numeric_value == 10
        assert row.published_source == FormData.PUBLISHED_SOURCE_REPORTED

    def test_stamps_published_source_when_values_already_match(self, db_session, fdrs_scenario):
        row = FormData.query.filter_by(
            assignment_entity_status_id=fdrs_scenario["aes_b"].id,
            form_item_id=fdrs_scenario["item_pub1"].id,
        ).one()
        row.published_source = None
        db_session.commit()

        summary = svc.get_assignment_publication_summary(fdrs_scenario["assigned_form_id"])
        country_b = next(c for c in summary["countries"] if c["country_id"] == fdrs_scenario["country_b"].id)
        assert country_b["counts"]["source"] == 1
        assert country_b["has_pending_changes"] is True

        stats = svc.publish_assignment(
            fdrs_scenario["assigned_form_id"],
            assignment_entity_status_ids=[fdrs_scenario["aes_b"].id],
        )
        assert stats["totals"]["source"] == 1

        db_session.refresh(row)
        assert row.published_value == "5"
        assert row.published_source == FormData.PUBLISHED_SOURCE_REPORTED

    def test_no_public_items_on_template_publishes_nothing(self, db_session, monkeypatch):
        """If the FDRS template has zero privacy='public' items at all, publishing
        must not stamp AssignmentEntityStatus.published_at — nothing was published."""
        template = create_test_template(db_session, name="FDRS No Public Items Template")
        _patch_fdrs_template_id(monkeypatch, template.id)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, label="Internal Only Item")
        # default privacy is 'ifrc_network' — never marked public for this template.
        country = create_test_country(db_session, name="Deltaland")
        aes = create_test_assignment_entity_status(
            db_session, country=country, template=template, period_name="2024",
        )
        db_session.add(FormData(assignment_entity_status_id=aes.id, form_item_id=item.id, value="1"))
        db_session.commit()

        stats = svc.publish_assignment(aes.assigned_form_id)
        assert stats["published_countries"] == 0
        assert stats["totals"] == {
            "new": 0, "changed": 0, "removed": 0, "source": 0, "unchanged": 0, "empty": 0,
        }

        db_session.refresh(aes)
        assert aes.published_at is None
        assert aes.published_by_user_id is None


class TestGetCountryChangeDetailQueryEfficiency:
    def test_form_item_labels_do_not_trigger_n_plus_one_queries(self, db_session, fdrs_scenario):
        """row.form_item must be eager-loaded via the existing FormItem join —
        regression test for the N+1 lazy-load this used to trigger per row."""
        from sqlalchemy import event

        from app.extensions import db as _db

        statements = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(_db.engine, "before_cursor_execute", _capture)
        try:
            statements.clear()
            detail = svc.get_country_change_detail(
                fdrs_scenario["assigned_form_id"], fdrs_scenario["aes_a"].id
            )
        finally:
            event.remove(_db.engine, "before_cursor_execute", _capture)

        # Correctness: labels are still populated correctly.
        assert {i["label"] for i in detail["items"]} == {"Public Item 1", "Public Item 2"}
        # One SELECT for the assignment, one for the aes, one for the country, one
        # for the joined form_data+form_item rows — no per-row form_item lookup.
        select_statements = [s for s in statements if s.strip().upper().startswith("SELECT")]
        assert len(select_statements) <= 4, (
            f"expected form_item to be eager-loaded, got {len(select_statements)} SELECTs:\n"
            + "\n".join(select_statements)
        )
