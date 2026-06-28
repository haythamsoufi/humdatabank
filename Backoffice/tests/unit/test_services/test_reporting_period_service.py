"""Tests for reporting_period_service."""

from datetime import date, datetime

import pytest

from app.models.assignments import AssignedForm, ReportingPeriod
from app.services.reporting_period_service import (
    backfill_assigned_forms_missing_period,
    dashboard_assignment_period_sort_key,
    get_reporting_period,
    period_chronology_sort_key,
    resync_all_reporting_periods,
    sort_period_names,
    sync_assigned_form_reporting_period,
    upsert_reporting_period,
)
from tests.factories import create_test_template

pytestmark = pytest.mark.unit


def _seed_period(name: str, *, period_type: str, period_start: date, period_end: date) -> ReportingPeriod:
    return upsert_reporting_period(
        name,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
    )


class TestUpsertReportingPeriod:
    def test_creates_and_reuses_catalog_row(self, db_session, app):
        with app.app_context():
            first = _seed_period(
                "2025",
                period_type="annual",
                period_start=date(2025, 1, 1),
                period_end=date(2025, 12, 31),
            )
            db_session.commit()
            second = get_reporting_period("2025")
            assert second is not None
            assert first.id == second.id

    def test_updates_existing_bounds(self, db_session, app):
        with app.app_context():
            _seed_period(
                "2024",
                period_type="custom",
                period_start=date(2020, 1, 1),
                period_end=date(2020, 12, 31),
            )
            db_session.commit()

            updated = upsert_reporting_period(
                "2024",
                period_type="annual",
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
            )
            assert updated.period_type == "annual"
            assert updated.period_start == date(2024, 1, 1)
            assert updated.period_end == date(2024, 12, 31)


class TestSyncAssignedFormReportingPeriod:
    def test_sync_links_existing_catalog(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            _seed_period(
                "2024",
                period_type="annual",
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
            )
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            sync_assigned_form_reporting_period(assigned_form)
            db_session.add(assigned_form)
            db_session.commit()

            assert assigned_form.period_id is not None
            assert assigned_form.period_start == date(2024, 1, 1)
            assert assigned_form.period_end == date(2024, 12, 31)

    def test_sync_clears_when_catalog_missing(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="Self-Reported")
            sync_assigned_form_reporting_period(assigned_form)
            db_session.add(assigned_form)
            db_session.commit()

            assert assigned_form.period_id is None
            assert assigned_form.period_start is None
            assert assigned_form.period_end is None


class TestBackfillAssignedFormsMissingPeriod:
    def test_backfill_syncs_rows_without_period_id(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            _seed_period(
                "2022",
                period_type="annual",
                period_start=date(2022, 1, 1),
                period_end=date(2022, 12, 31),
            )
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
            _seed_period(
                "2021",
                period_type="annual",
                period_start=date(2021, 1, 1),
                period_end=date(2021, 12, 31),
            )
            assigned_form = AssignedForm(template_id=template.id, period_name="2021")
            db_session.add(assigned_form)
            db_session.commit()

            stats = backfill_assigned_forms_missing_period(dry_run=True)
            db_session.refresh(assigned_form)

            assert stats["synced"] == 1
            assert assigned_form.period_id is None


class TestPeriodChronologySortKey:
    def test_latest_period_first_from_catalog(self, db_session, app):
        with app.app_context():
            _seed_period("2023", period_type="annual", period_start=date(2023, 1, 1), period_end=date(2023, 12, 31))
            _seed_period("2024", period_type="annual", period_start=date(2024, 1, 1), period_end=date(2024, 12, 31))
            _seed_period(
                "Jan-Jun 2026",
                period_type="monthly",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 6, 30),
            )
            _seed_period(
                "Oct 2023 - Mar 2024",
                period_type="monthly",
                period_start=date(2023, 10, 1),
                period_end=date(2024, 3, 31),
            )
            db_session.commit()

            labels = ["2023", "Jan-Jun 2026", "2024", "Oct 2023 - Mar 2024"]
            ordered = sort_period_names(labels)
            assert ordered == ["Jan-Jun 2026", "2024", "Oct 2023 - Mar 2024", "2023"]

    def test_unknown_period_sorts_last(self):
        key = period_chronology_sort_key("Self-Reported")
        assert key[0] == date.min

    def test_dashboard_item_sorts_by_reporting_year_and_assigned_at(self):
        assigned_form = AssignedForm(period_name="2024")
        assigned_form.period_start = date(2024, 1, 1)
        assigned_form.period_end = date(2024, 6, 30)
        assigned_form.assigned_at = datetime(2024, 3, 1)
        aes = type("AES", (), {"assigned_form": assigned_form})()
        item = {"type": "assigned", "item_object": aes}
        assert dashboard_assignment_period_sort_key(item) == (
            2024,
            datetime(2024, 3, 1).timestamp(),
            "2024",
        )

    def test_dashboard_item_tiebreaks_same_period_by_assigned_at(self):
        newer = AssignedForm(period_name="2025")
        newer.period_start = date(2025, 1, 1)
        newer.period_end = date(2025, 12, 31)
        newer.assigned_at = datetime(2025, 6, 1)
        older = AssignedForm(period_name="2025")
        older.period_start = date(2025, 1, 1)
        older.period_end = date(2025, 12, 31)
        older.assigned_at = datetime(2025, 1, 1)

        items = [
            {"type": "assigned", "item_object": type("AES", (), {"assigned_form": older})()},
            {"type": "assigned", "item_object": type("AES", (), {"assigned_form": newer})()},
        ]
        ordered = sorted(items, key=dashboard_assignment_period_sort_key, reverse=True)
        assert ordered[0]["item_object"].assigned_form is newer
        assert ordered[1]["item_object"].assigned_form is older

    def test_dashboard_item_same_period_name_uses_catalog_when_dates_missing(self, db_session, app):
        with app.app_context():
            upsert_reporting_period(
                "2024",
                period_type="annual",
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
            )
            db_session.commit()

            with_dates = AssignedForm(period_name="2024")
            with_dates.period_start = date(2024, 1, 1)
            with_dates.period_end = date(2024, 12, 31)
            with_dates.assigned_at = datetime(2024, 6, 15)
            without_dates = AssignedForm(period_name="2024")
            without_dates.assigned_at = datetime(2023, 7, 1)

            items = [
                {"type": "assigned", "item_object": type("AES", (), {"assigned_form": with_dates})()},
                {"type": "assigned", "item_object": type("AES", (), {"assigned_form": without_dates})()},
            ]
            ordered = sorted(items, key=dashboard_assignment_period_sort_key, reverse=True)
            assert ordered[0]["item_object"].assigned_form is with_dates
            assert ordered[1]["item_object"].assigned_form is without_dates

    def test_dashboard_latest_assigned_first_within_same_reporting_year(self):
        plan = AssignedForm(period_name="2024")
        plan.period_start = date(2024, 1, 1)
        plan.period_end = date(2024, 12, 31)
        plan.assigned_at = datetime(2023, 7, 1)
        midyear = AssignedForm(period_name="Jan-Jun 2024")
        midyear.period_start = date(2024, 1, 1)
        midyear.period_end = date(2024, 6, 30)
        midyear.assigned_at = datetime(2024, 6, 15)
        annual = AssignedForm(period_name="2024")
        annual.period_start = date(2024, 1, 1)
        annual.period_end = date(2024, 12, 31)
        annual.assigned_at = datetime(2025, 1, 15)

        items = [
            {"type": "assigned", "item_object": type("AES", (), {"assigned_form": midyear})()},
            {"type": "assigned", "item_object": type("AES", (), {"assigned_form": annual})()},
            {"type": "assigned", "item_object": type("AES", (), {"assigned_form": plan})()},
        ]
        ordered = sorted(items, key=dashboard_assignment_period_sort_key, reverse=True)
        assert [i["item_object"].assigned_form for i in ordered] == [annual, midyear, plan]


class TestResyncAllReportingPeriods:
    def test_resync_relinks_assigned_form(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            catalog = ReportingPeriod(
                name="Jan-Jun 2026",
                period_type="monthly",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 6, 30),
            )
            assigned_form = AssignedForm(
                template_id=template.id,
                period_name="Jan-Jun 2026",
            )
            db_session.add_all([catalog, assigned_form])
            db_session.commit()

            stats = resync_all_reporting_periods()
            db_session.refresh(assigned_form)

            assert stats["assigned_linked"] >= 1
            assert assigned_form.period_id == catalog.id
            assert assigned_form.period_end == date(2026, 6, 30)
