"""Tests for reporting_period_service."""

from datetime import date

import pytest

from app.models.assignments import AssignedForm, ReportingPeriod
from app.services.reporting_period_service import (
    backfill_assigned_forms_missing_period,
    get_or_create_reporting_period,
    parse_period_label,
    sync_assigned_form_reporting_period,
)
from tests.factories import create_test_template

pytestmark = pytest.mark.unit


class TestParsePeriodLabel:
    def test_annual_single_year(self):
        assert parse_period_label("2024") == (
            "annual",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )

    def test_custom_year_span(self):
        assert parse_period_label("2023-2024") == (
            "custom",
            date(2023, 1, 1),
            date(2024, 12, 31),
        )

    def test_quarterly_label(self):
        assert parse_period_label("Q1 2024") == (
            "quarterly",
            date(2024, 1, 1),
            date(2024, 3, 31),
        )

    def test_unparseable_labels(self):
        assert parse_period_label("Self-Reported") is None
        assert parse_period_label("[LOADTEST] run") is None
        assert parse_period_label("") is None


class TestSyncAssignedFormReportingPeriod:
    def test_sync_annual_period(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            sync_assigned_form_reporting_period(assigned_form)
            db_session.add(assigned_form)
            db_session.commit()

            assert assigned_form.period_id is not None
            assert assigned_form.period_start == date(2024, 1, 1)
            assert assigned_form.period_end == date(2024, 12, 31)
            catalog = ReportingPeriod.query.get(assigned_form.period_id)
            assert catalog is not None
            assert catalog.name == "2024"
            assert catalog.period_type == "annual"

    def test_sync_clears_unparseable(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="Self-Reported")
            sync_assigned_form_reporting_period(assigned_form)
            db_session.add(assigned_form)
            db_session.commit()

            assert assigned_form.period_id is None
            assert assigned_form.period_start is None
            assert assigned_form.period_end is None

    def test_reuses_existing_catalog_row(self, db_session, app):
        with app.app_context():
            first_catalog = get_or_create_reporting_period("2025")
            second_catalog = get_or_create_reporting_period("2025")
            db_session.commit()

            assert first_catalog is not None
            assert second_catalog is not None
            assert first_catalog.id == second_catalog.id

    def test_get_or_create_updates_changed_bounds(self, db_session, app):
        with app.app_context():
            catalog = ReportingPeriod(
                name="2024",
                period_type="custom",
                period_start=date(2020, 1, 1),
                period_end=date(2020, 12, 31),
            )
            db_session.add(catalog)
            db_session.commit()

            updated = get_or_create_reporting_period("2024")
            assert updated.id == catalog.id
            assert updated.period_type == "annual"
            assert updated.period_start == date(2024, 1, 1)
            assert updated.period_end == date(2024, 12, 31)


class TestBackfillAssignedFormsMissingPeriod:
    def test_backfill_syncs_rows_without_period_id(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2022")
            db_session.add(assigned_form)
            db_session.commit()

            stats = backfill_assigned_forms_missing_period()
            db_session.refresh(assigned_form)

            assert stats["synced"] >= 1
            assert assigned_form.period_id is not None
            assert assigned_form.period_start == date(2022, 1, 1)

    def test_backfill_dry_run_does_not_write(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2021")
            db_session.add(assigned_form)
            db_session.commit()

            stats = backfill_assigned_forms_missing_period(dry_run=True)
            db_session.refresh(assigned_form)

            assert stats["synced"] == 1
            assert assigned_form.period_id is None
