from unittest.mock import patch

import pytest

from app.models import AssignmentEntityStatus, FormData
from app.models.enums import EntityType
from app.services.public.analytics_service import (
    aggregate_submission_coverage,
    resolve_country_query,
    resolve_indicator_query,
)
from app.services.security.public_data_access import (
    public_include_dimensions,
    slim_public_data_rows,
)
from tests.factories import (
    create_test_assignment_entity_status,
    create_test_country,
    create_test_item,
    create_test_section,
    create_test_template,
)


class TestPublicDataSlimHelpers:
    def test_public_include_dimensions_default_false(self):
        assert not public_include_dimensions({})
        assert not public_include_dimensions({"indicator_bank_id": "1"})
        assert public_include_dimensions({"include_dimensions": "true"})

    def test_slim_public_data_rows(self):
        rows = slim_public_data_rows(
            [
                {
                    "id": 1,
                    "period_name": "Annual 2023",
                    "country_id": 5,
                    "num_value": 10,
                    "data_status": "available",
                    "disaggregation_data": {"big": "payload"},
                }
            ]
        )
        assert rows == [
            {
                "id": 1,
                "period_name": "Annual 2023",
                "country_id": 5,
                "num_value": 10,
                "data_status": "available",
            }
        ]


@pytest.mark.unit
class TestResolveIndicatorQuery:
    def test_volunteers_maps_to_canonical_id(self, app):
        with app.app_context():
            out = resolve_indicator_query("Number of volunteers")
        assert out["best_match"]["id"] == 724


@pytest.mark.unit
class TestAggregateSubmissionCoverageValidation:
    def test_requires_a_scope(self, app):
        with app.app_context():
            with pytest.raises(ValueError, match="Provide template_id"):
                aggregate_submission_coverage()


@pytest.mark.unit
class TestAggregateSubmissionCoverageSecurity:
    """
    End-to-end security check: aggregate_submission_coverage must only ever count
    countries via publicly-visible (privacy=public) form items, even when a
    non-public form item on the *same template and period* has a submission from
    a different country. This exercises the real, unpatched privacy gate in
    app.services.data_retrieval.form.query_form_data (no auth/session, no
    can_view_non_public_form_items patch) via the same internal request path
    production traffic uses.
    """

    def test_excludes_countries_whose_only_submission_is_non_public(self, app, db_session):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)

            public_item = create_test_item(db_session, section, template, item_type="question")
            public_item.config = {"privacy": "public"}
            private_item = create_test_item(db_session, section, template, item_type="question")
            private_item.config = {"privacy": "ifrc_network"}
            db_session.commit()

            country_public = create_test_country(db_session)
            country_private = create_test_country(db_session)

            # AssignedForm has a unique (template_id, period_name) constraint — one shared
            # assignment round, two countries reporting into it via separate AES rows.
            aes_public = create_test_assignment_entity_status(
                db_session,
                country=country_public,
                template=template,
                status="submitted",
                period_name="Annual 2024",
            )
            aes_private = AssignmentEntityStatus(
                assigned_form_id=aes_public.assigned_form_id,
                entity_type=EntityType.country.value,
                entity_id=country_private.id,
                status="submitted",
            )
            db_session.add(aes_private)
            db_session.commit()
            db_session.refresh(aes_private)

            db_session.add(
                FormData(assignment_entity_status_id=aes_public.id, form_item_id=public_item.id, value="10")
            )
            db_session.add(
                FormData(assignment_entity_status_id=aes_private.id, form_item_id=private_item.id, value="20")
            )
            db_session.commit()

            result = aggregate_submission_coverage(template_id=template.id, period_name="Annual 2024")

        # Only the public-item country counts — the private-item country must never leak in.
        assert result["countries_submitted_total"] == 1
        assert result["by_period"] == [{"period_name": "Annual 2024", "countries_submitted": 1}]
        assert result["template_id"] == template.id

    def test_all_years_breakdown_counts_each_period_independently(self, app, db_session):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template, item_type="question")
            item.config = {"privacy": "public"}
            db_session.commit()

            country_a = create_test_country(db_session)
            country_b = create_test_country(db_session)

            aes_2023 = create_test_assignment_entity_status(
                db_session, country=country_a, template=template, status="submitted", period_name="Annual 2023"
            )
            aes_2024_a = create_test_assignment_entity_status(
                db_session, country=country_a, template=template, status="submitted", period_name="Annual 2024"
            )
            # Same (template, "Annual 2024") assignment round as aes_2024_a — country_b reports
            # into the same AssignedForm via its own AssignmentEntityStatus row.
            aes_2024_b = AssignmentEntityStatus(
                assigned_form_id=aes_2024_a.assigned_form_id,
                entity_type=EntityType.country.value,
                entity_id=country_b.id,
                status="submitted",
            )
            db_session.add(aes_2024_b)
            db_session.commit()
            db_session.refresh(aes_2024_b)

            db_session.add_all(
                [
                    FormData(assignment_entity_status_id=aes_2023.id, form_item_id=item.id, value="1"),
                    FormData(assignment_entity_status_id=aes_2024_a.id, form_item_id=item.id, value="2"),
                    FormData(assignment_entity_status_id=aes_2024_b.id, form_item_id=item.id, value="3"),
                ]
            )
            db_session.commit()

            # No period_name filter — breakdown across every period in scope.
            result = aggregate_submission_coverage(template_id=template.id)

        assert result["countries_submitted_total"] == 2  # country_a + country_b, deduped across periods
        by_period = {b["period_name"]: b["countries_submitted"] for b in result["by_period"]}
        assert by_period["Annual 2023"] == 1
        assert by_period["Annual 2024"] == 2


@pytest.mark.unit
class TestAggregateSubmissionCoverageAggregationLogic:
    """Unit tests for the grouping/dedup/labelling logic, independent of the DB/query layer."""

    def _run(self, rows, truncated=False, **kwargs):
        with patch(
            "app.services.public.analytics_service.fetch_public_scoped_rows",
            return_value=(rows, truncated),
        ):
            return aggregate_submission_coverage(**kwargs)

    def test_only_available_rows_are_counted(self, app):
        rows = [
            {"country_id": 1, "period_name": "Annual 2024", "data_status": "available"},
            {"country_id": 2, "period_name": "Annual 2024", "data_status": "data_not_available"},
            {"country_id": 3, "period_name": "Annual 2024", "data_status": "not_applicable"},
        ]
        with app.app_context():
            result = self._run(rows, template_id=21)
        assert result["countries_submitted_total"] == 1

    def test_duplicate_rows_same_country_period_count_once(self, app):
        rows = [
            {"country_id": 1, "period_name": "Annual 2024", "data_status": "available"},
            {"country_id": 1, "period_name": "Annual 2024", "data_status": "available"},
        ]
        with app.app_context():
            result = self._run(rows, template_id=21)
        assert result["countries_submitted_total"] == 1
        assert result["by_period"] == [{"period_name": "Annual 2024", "countries_submitted": 1}]

    def test_periods_sorted_chronologically(self, app):
        rows = [
            {"country_id": 1, "period_name": "Annual 2024", "data_status": "available"},
            {"country_id": 2, "period_name": "Annual 2021", "data_status": "available"},
            {"country_id": 3, "period_name": "Annual 2023", "data_status": "available"},
        ]
        with app.app_context():
            result = self._run(rows, template_id=21)
        assert [b["period_name"] for b in result["by_period"]] == [
            "Annual 2021",
            "Annual 2023",
            "Annual 2024",
        ]

    def test_template_21_labelled_fdrs_and_22_labelled_upr(self, app):
        with app.app_context():
            fdrs = self._run([], template_id=21)
            upr = self._run([], template_id=22)
            unscoped = self._run(
                [{"country_id": 1, "period_name": "Annual 2024", "data_status": "available"}],
                indicator_bank_id=724,
            )
        assert fdrs["programme"] == "FDRS"
        assert upr["programme"] == "UPR"
        assert unscoped["programme"] is None

    def test_truncated_flag_surfaces_as_note(self, app):
        with app.app_context():
            result = self._run(
                [{"country_id": 1, "period_name": "Annual 2024", "data_status": "available"}],
                truncated=True,
                template_id=21,
                max_pages=1,
            )
        assert result["truncated"] is True
        assert any("Stopped after" in note for note in result["notes"])

    def test_query_resolves_indicator_before_fetching(self, app):
        with app.app_context():
            result = self._run(
                [{"country_id": 1, "period_name": "Annual 2024", "data_status": "available"}],
                query="volunteers",
            )
        assert result["indicator_bank_id"] == 724
        assert result["resolved_from"] == "canonical:volunteers"


@pytest.mark.unit
class TestResolveCountryQuery:
    def test_empty_query_returns_no_match(self, app):
        with app.app_context():
            out = resolve_country_query("")
        assert out["best_match"] is None
        assert out["alternatives"] == []

    def test_unmatched_query_returns_no_match(self, app, db_session):
        create_test_country(db_session)
        with app.app_context():
            out = resolve_country_query("zzq_definitely_not_a_country_zzq")
        assert out["best_match"] is None

    def test_numeric_id_resolves_to_country(self, app, db_session):
        country = create_test_country(db_session)
        with app.app_context():
            out = resolve_country_query(str(country.id))
        assert out["best_match"]["id"] == country.id
        assert out["best_match"]["match_reason"] == "numeric_id"
        assert out["best_match"]["iso3"] == country.iso3

    def test_numeric_id_not_found_returns_no_match(self, app, db_session):
        create_test_country(db_session)
        with app.app_context():
            out = resolve_country_query("999999999")
        assert out["best_match"] is None

    def test_exact_iso3_match(self, app, db_session):
        country = create_test_country(db_session)
        with app.app_context():
            out = resolve_country_query(country.iso3)
        assert out["best_match"]["id"] == country.id
        assert out["best_match"]["match_reason"] == "search_ranked"

    def test_exact_name_match_ranks_above_partial_match(self, app, db_session):
        exact = create_test_country(db_session, name="Sudan Test Exact")
        partial = create_test_country(db_session, name="South Sudan Test Exact Extra")
        with app.app_context():
            out = resolve_country_query("Sudan Test Exact")
        assert out["best_match"]["id"] == exact.id
        alt_ids = {alt["id"] for alt in out["alternatives"]}
        assert partial.id in alt_ids

    def test_limit_caps_alternatives(self, app, db_session):
        base = create_test_country(db_session, name="Limitland")
        for i in range(5):
            create_test_country(db_session, name=f"Limitland Extra {i}")
        with app.app_context():
            out = resolve_country_query("Limitland", limit=2)
        assert out["best_match"]["id"] == base.id
        assert len(out["alternatives"]) <= 2
