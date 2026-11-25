"""An Emergency Appeal plan takes its indicators from the bank, and every plan previews its schedule."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.extensions import db
from plugins.dref_monitoring.models import DrefIndicator, DrefOperation, DrefPeriod
from plugins.dref_monitoring.services import go_sync
from plugins.dref_monitoring.services.schedule import (
    frequency_editable,
    lock_schedule_start,
    schedule_preview,
    schedule_start,
    set_plan_frequency,
    valid_frequency,
)
from plugins.dref_monitoring.tests.test_emergency_appeals import _appeal, _feed, _loan
from tests.factories import create_test_country, create_test_user

TODAY = date(2026, 11, 24)


def _operation(**overrides):
    values = {
        "id": 1,
        "appeal_type": "DREF",
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 6, 30),
        "reporting_frequency": "monthly",
        "reporting_start": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# --- the schedule, no database -----------------------------------------------------------------


@pytest.mark.unit
def test_only_biweekly_and_monthly_are_frequencies():
    assert valid_frequency(" Monthly ") == "monthly"
    assert valid_frequency("biweekly") == "biweekly"
    assert valid_frequency("weekly") is None
    assert valid_frequency(None) is None


@pytest.mark.unit
def test_a_dref_counts_its_periods_from_its_start_date_even_when_it_began_long_ago():
    operation = _operation(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    assert schedule_start(operation, TODAY) == date(2026, 1, 1)
    preview = schedule_preview(operation, today=TODAY)
    assert preview["count"] == 12
    assert preview["starts_at_confirmation"] is False
    assert preview["rows"][0]["start"] == date(2026, 1, 1)
    assert preview["rows"][0]["state"] == "past"
    assert preview["rows"][-1]["state"] == "upcoming"


@pytest.mark.unit
def test_an_appeal_that_is_already_running_reports_from_now_on():
    appeal = _operation(appeal_type="EA", start_date=date(2026, 9, 11), end_date=date(2027, 10, 31))
    assert schedule_start(appeal, TODAY) == date(2026, 11, 1)
    assert schedule_start(appeal, TODAY, "biweekly") == TODAY
    preview = schedule_preview(appeal, today=TODAY)
    assert preview["count"] == 12
    assert preview["rows"][0]["start"] == date(2026, 11, 1)
    assert preview["rows"][-1]["end"] == date(2027, 10, 31)
    assert preview["starts_at_confirmation"] is True


@pytest.mark.unit
def test_an_appeal_that_has_not_started_keeps_its_start_date():
    appeal = _operation(appeal_type="EA", start_date=date(2027, 1, 15), end_date=date(2027, 12, 31))
    assert schedule_start(appeal, TODAY) == date(2027, 1, 15)
    assert schedule_preview(appeal, today=TODAY)["starts_at_confirmation"] is False


@pytest.mark.unit
def test_the_day_reporting_began_is_not_recomputed_once_stored():
    appeal = _operation(
        appeal_type="EA",
        start_date=date(2026, 9, 11),
        end_date=date(2027, 10, 31),
        reporting_start=date(2026, 11, 1),
    )
    assert schedule_start(appeal, date(2027, 3, 3)) == date(2026, 11, 1)
    assert schedule_preview(appeal, today=date(2027, 3, 3))["starts_at_confirmation"] is False


@pytest.mark.unit
def test_a_previewed_frequency_changes_the_rows_without_being_saved():
    operation = _operation(start_date=date(2026, 1, 1), end_date=date(2026, 3, 31))
    monthly = schedule_preview(operation, today=TODAY)
    biweekly = schedule_preview(operation, "biweekly", TODAY)
    assert monthly["frequency"] == "monthly" and monthly["count"] == 3
    assert biweekly["frequency"] == "biweekly" and biweekly["count"] > monthly["count"]
    assert operation.reporting_frequency == "monthly"
    assert schedule_preview(operation, "weekly", TODAY)["frequency"] == "monthly"


@pytest.mark.unit
def test_a_missing_date_gives_no_schedule_and_a_long_operation_is_cut_off():
    assert schedule_preview(_operation(end_date=None), today=TODAY)["missing_dates"] is True
    assert schedule_preview(_operation(start_date=None), today=TODAY)["rows"] == []
    long_run = schedule_preview(_operation(start_date=date(2026, 1, 1), end_date=date(2035, 12, 31)), today=TODAY)
    assert long_run["truncated"] is True
    assert long_run["count"] == len(long_run["rows"])


# --- the plan from the bank --------------------------------------------------------------------


@pytest.fixture
def seeded(db_session):
    import plugins.dref_monitoring.models  # noqa: F401

    return create_test_country(db_session, name="Zedland", iso3="ZZZ", region="Test")


def _bank():
    from app.models import IndicatorBank, Sector

    health = Sector(name="Health", display_order=1, is_active=True)
    wash = Sector(name="Water, sanitation and hygiene", display_order=2, is_active=True)
    db.session.add_all([health, wash])
    db.session.flush()

    def _row(name, sector, emergency=True):
        return IndicatorBank(
            name=name, type="number", unit="People", emergency=emergency, archived=False, sector={"primary": sector.id}
        )

    rows = {
        "clinics": _row("EA test clinics supported", health),
        "reached": _row("EA test people reached with care", health),
        "water": _row("EA test people with safe water", wash),
        "ordinary": _row("EA test routine indicator", health, emergency=False),
    }
    db.session.add_all(rows.values())
    db.session.commit()
    return rows


def _actor(email="ea-planner@example.com"):
    from plugins.dref_monitoring.access import Actor

    user = create_test_user(db.session, email=email)
    return Actor(user.id, True, frozenset(), frozenset(), {})


def _appeal_plan():
    from plugins.dref_monitoring.services.plans import latest_plan

    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    return operation, latest_plan(operation.id)


def _rows_by_group(plan):
    from plugins.dref_monitoring.services.plans import groups_for, indicators_for_group

    return {group.key: (group, indicators_for_group(group.id)) for group in groups_for(plan.id)}


@pytest.mark.db
def test_an_appeal_plan_lists_the_emergency_indicators_of_the_bank_all_switched_on(seeded):
    bank = _bank()
    go_sync.sync_from_go(_feed([_appeal()]))
    operation, plan = _appeal_plan()

    groups = _rows_by_group(plan)
    assert set(groups) == {"operation", "health", "water_sanitation_and_hygiene"}
    health_group, health_rows = groups["health"]
    assert health_group.budget_chf is None
    assert {row.title for row in health_rows} == {"EA test clinics supported", "EA test people reached with care"}
    assert {row.indicator_bank_id for row in health_rows} == {bank["clinics"].id, bank["reached"].id}
    assert all(row.enabled for _group, rows in groups.values() for row in rows)
    assert not any(row.indicator_bank_id == bank["ordinary"].id for _group, rows in groups.values() for row in rows)
    assert str(groups["operation"][0].budget_chf) == "15000000.00"


@pytest.mark.db
def test_a_dref_plan_does_not_take_the_bank_indicators(seeded):
    _bank()
    go_sync.sync_from_go(_feed([], loans=[_loan(appeal_type="DREF", allocation_type="Grant")]))
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    assert operation.appeal_type == "DREF"
    assert DrefIndicator.query.filter(DrefIndicator.indicator_bank_id.isnot(None)).count() == 0


@pytest.mark.db
def test_a_draft_appeal_plan_made_earlier_gets_the_indicators_on_the_next_sync(seeded):
    go_sync.sync_from_go(_feed([_appeal()]))
    assert DrefIndicator.query.filter(DrefIndicator.indicator_bank_id.isnot(None)).count() == 0
    _bank()
    go_sync.sync_from_go(_feed([_appeal()]))
    _operation_row, plan = _appeal_plan()
    assert DrefIndicator.query.filter(DrefIndicator.indicator_bank_id.isnot(None)).count() == 3
    assert set(_rows_by_group(plan)) == {"operation", "health", "water_sanitation_and_hygiene"}


def _bank_rows(plan):
    return [row for _group, rows in _rows_by_group(plan).values() for row in rows if row.indicator_bank_id]


def _switch(operation, actor, state: dict):
    """Post the plan form with indicator ids mapped to on or off, as the plan table does."""
    from werkzeug.datastructures import MultiDict

    from plugins.dref_monitoring.services.plans import save_plan_activities

    form = MultiDict({"justification": "Scope of the appeal"})
    for indicator_id, on in state.items():
        form.add("indicator_listed", str(indicator_id))
        if on:
            form.add("indicator_on", str(indicator_id))
    return save_plan_activities(operation, form, actor)


@pytest.mark.db
def test_a_switch_survives_the_next_sync_and_no_row_is_added_twice(seeded):
    bank = _bank()
    go_sync.sync_from_go(_feed([_appeal()]))
    operation, plan = _appeal_plan()
    health = _rows_by_group(plan)["health"][1]
    actor = _actor()
    assert _switch(operation, actor, {row.id: False for row in health})["ok"] is True

    go_sync.sync_from_go(_feed([_appeal()]))
    go_sync.sync_from_go(_feed([_appeal(amount_requested=16000000.0)]))
    _operation_row, plan = _appeal_plan()
    health = _rows_by_group(plan)["health"][1]
    assert {row.indicator_bank_id for row in health} == {bank["clinics"].id, bank["reached"].id}
    assert not any(row.enabled for row in health)
    assert DrefIndicator.query.filter(DrefIndicator.indicator_bank_id.isnot(None)).count() == 3


@pytest.mark.db
def test_switched_off_indicators_leave_the_reporting_form_but_stay_on_the_plan_screen(seeded):
    from plugins.dref_monitoring.services.entry_activities import plan_indicator_filter
    from plugins.dref_monitoring.services.plans import plan_sections

    bank = _bank()
    go_sync.sync_from_go(_feed([_appeal()]))
    operation, plan = _appeal_plan()
    health = _rows_by_group(plan)["health"][1]
    keep = next(row for row in health if row.indicator_bank_id == bank["clinics"].id)
    actor = _actor()

    assert _switch(operation, actor, {row.id: row.id == keep.id for row in health})["ok"] is True
    scope = plan_indicator_filter(operation)
    assert bank["clinics"].id in scope["indicator_bank_ids"]
    assert bank["reached"].id not in scope["indicator_bank_ids"]
    assert bank["water"].id in scope["indicator_bank_ids"]

    assert _switch(operation, actor, {keep.id: False})["ok"] is True
    scope = plan_indicator_filter(operation)
    assert "health" not in scope["sector_keys"]
    assert "water_sanitation_and_hygiene" in scope["sector_keys"]
    shown = [section["group"].key for section in plan_sections(plan.id)]
    assert "health" not in shown
    assert "water_sanitation_and_hygiene" in shown

    # The plan screen still lists the switched-off rows so they can be switched back on.
    sections = {section["group"].key: section for section in plan_sections(plan.id, include_disabled=True)}
    assert sections["health"]["indicators_total"] == 2 and sections["health"]["indicators_on"] == 0
    assert [block["enabled"] for block in sections["health"]["blocks"]] == [False, False]


@pytest.mark.db
def test_saving_with_no_indicator_change_is_not_a_change(seeded):
    _bank()
    go_sync.sync_from_go(_feed([_appeal()]))
    operation, plan = _appeal_plan()
    state = {row.id: True for row in _bank_rows(plan)}
    assert _switch(operation, _actor(), state)["error"] == "There is nothing to save."


@pytest.mark.db
def test_confirming_needs_one_indicator_and_fixes_the_day_reporting_starts(seeded):
    from plugins.dref_monitoring.services.plans import validate_plan

    _bank()
    go_sync.sync_from_go(_feed([_appeal()]))
    operation, plan = _appeal_plan()
    actor = _actor()
    rows = _bank_rows(plan)
    assert _switch(operation, actor, {row.id: False for row in rows})["ok"] is True
    assert validate_plan(operation, actor, TODAY) == "Switch on at least one indicator before confirming the plan."
    assert operation.reporting_start is None

    assert _switch(operation, actor, {row.id: True for row in rows})["ok"] is True
    assert validate_plan(operation, actor, TODAY) is None
    operation = db.session.get(DrefOperation, operation.id)
    assert operation.reporting_start == date(2026, 11, 1)
    periods = DrefPeriod.query.filter_by(operation_id=operation.id).order_by(DrefPeriod.sequence).all()
    assert len(periods) == 12
    assert periods[0].start_date == date(2026, 11, 1)
    assert periods[-1].end_date == date(2027, 10, 31)


@pytest.mark.db
def test_switching_an_indicator_on_a_confirmed_plan_opens_a_new_draft(seeded):
    from plugins.dref_monitoring.services.plans import latest_plan, validate_plan

    bank = _bank()
    go_sync.sync_from_go(_feed([_appeal()]))
    operation, plan = _appeal_plan()
    actor = _actor()
    assert validate_plan(operation, actor, TODAY) is None
    clinics = next(row for row in _bank_rows(plan) if row.indicator_bank_id == bank["clinics"].id)

    assert _switch(operation, actor, {clinics.id: False})["ok"] is True
    newer = latest_plan(operation.id)
    assert newer.version == plan.version + 1 and newer.status == "draft"
    assert db.session.get(DrefOperation, operation.id).workflow_status == "plan_draft"
    copied = {row.indicator_bank_id: row.enabled for row in _bank_rows(newer)}
    assert copied == {bank["clinics"].id: False, bank["reached"].id: True, bank["water"].id: True}
    # The confirmed version keeps its own switches.
    assert all(row.enabled for row in _bank_rows(plan))


@pytest.mark.db
def test_the_frequency_is_chosen_on_the_draft_and_locked_once_cycles_exist(seeded):
    from plugins.dref_monitoring.services.plans import validate_plan

    _bank()
    go_sync.sync_from_go(_feed([_appeal()]))
    operation, _plan = _appeal_plan()
    actor = _actor()
    assert frequency_editable(operation) is True
    assert set_plan_frequency(operation, "weekly", actor) == "Choose biweekly or monthly."
    assert set_plan_frequency(operation, "biweekly", actor) is None
    assert db.session.get(DrefOperation, operation.id).reporting_frequency == "biweekly"

    assert validate_plan(operation, actor, TODAY) is None
    operation = db.session.get(DrefOperation, operation.id)
    assert operation.reporting_start == TODAY
    assert frequency_editable(operation) is False
    assert set_plan_frequency(operation, "monthly", actor).startswith("The plan is confirmed")
    assert operation.reporting_frequency == "biweekly"


@pytest.mark.db
def test_a_dref_keeps_counting_from_its_start_date_when_confirmed(seeded):
    from plugins.dref_monitoring.services.plans import validate_plan

    go_sync.sync_from_go(_feed([], loans=[_loan(appeal_type="DREF", allocation_type="Grant")]))
    operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
    lock_schedule_start(operation, TODAY)
    assert operation.reporting_start is None
    assert validate_plan(operation, _actor(), TODAY) is None
    operation = db.session.get(DrefOperation, operation.id)
    assert operation.reporting_start is None
    first = DrefPeriod.query.filter_by(operation_id=operation.id).order_by(DrefPeriod.sequence).first()
    assert first.start_date == operation.start_date


# --- the plan screen ---------------------------------------------------------------------------


@pytest.mark.db
def test_the_plan_tab_previews_the_schedule_and_lists_the_indicators(app, seeded, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"dref_monitoring"}))
    app.plugin_manager.sync_activation_state()
    try:
        _bank()
        go_sync.sync_from_go(_feed([_appeal()]))
        operation, plan = _appeal_plan()
        url = f"/dref-monitoring/operations/{operation.id}"

        page = logged_in_sm_client.get(f"{url}?tab=plan")
        assert page.status_code == 200
        body = page.get_data(as_text=True)
        assert 'id="dref-plan-subtab-schedule"' in body
        assert 'id="dref-plan-subtab-indicators"' in body
        assert "dref-plan-flat" in body
        assert 'data-dref-fold="indicator"' not in body
        assert "data-dref-plan-schedule" in body
        monthly_rows = schedule_preview(operation)["count"]
        assert monthly_rows >= 1
        assert body.count("data-dref-schedule-row") == monthly_rows
        assert "Reporting frequency" in body
        assert "data-dref-schedule-frequency" in body
        assert "/plan/schedule/preview" in body
        assert "Preview" not in body.split('id="dref-plan-schedule"', 1)[1].split("</section>", 1)[0]
        assert "First period starts" in body and "when the plan is confirmed" in body
        # The indicators sit in the same sector table as everything else, each with its own switch.
        assert "data-dref-plan-indicators" not in body
        assert body.count('name="indicator_on"') == 3
        assert "2 of 2 on" in body and "1 of 1 on" in body
        assert "EA test clinics supported" in body
        assert "EA test routine indicator" not in body
        assert "data-dref-indicators-set" in body

        preview = logged_in_sm_client.get(f"{url}?tab=plan&frequency=biweekly")
        preview_body = preview.get_data(as_text=True)
        assert "Saved frequency:" in preview_body
        assert preview_body.count("data-dref-schedule-row") > monthly_rows
        assert db.session.get(DrefOperation, operation.id).reporting_frequency == "monthly"

        fragment = logged_in_sm_client.get(f"{url}/plan/schedule/preview?frequency=biweekly")
        assert fragment.status_code == 200
        fragment_body = fragment.get_data(as_text=True)
        assert 'id="dref-plan-schedule"' in fragment_body
        assert "dref-operation-tabs" not in fragment_body
        assert "Saved frequency:" in fragment_body
        assert fragment_body.count("data-dref-schedule-row") > monthly_rows
        assert "Use this frequency" in fragment_body
        assert db.session.get(DrefOperation, operation.id).reporting_frequency == "monthly"

        saved = logged_in_sm_client.post(
            f"{url}/plan/schedule", data={"frequency": "biweekly", "tab": "plan"}, follow_redirects=True
        )
        assert "The reporting frequency was saved." in saved.get_data(as_text=True)
        assert db.session.get(DrefOperation, operation.id).reporting_frequency == "biweekly"

        ids = [row.id for row in DrefIndicator.query.filter(DrefIndicator.indicator_bank_id.isnot(None))]
        form = {"justification": "Scope", "tab": "plan", "indicator_listed": [str(i) for i in ids], "indicator_on": [str(ids[0])]}
        off = logged_in_sm_client.post(f"{url}/plan", data=form, follow_redirects=True)
        off_body = off.get_data(as_text=True)
        assert "Plan saved." in off_body
        states = {row.id: row.enabled for row in DrefIndicator.query.filter(DrefIndicator.indicator_bank_id.isnot(None))}
        assert [i for i, on in states.items() if on] == [ids[0]]
        assert "Not monitored" in off_body
    finally:
        app.plugin_manager.active_plugins = previous


@pytest.mark.db
def test_opening_an_older_draft_appeal_plan_lists_the_indicators(app, seeded, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"dref_monitoring"}))
    app.plugin_manager.sync_activation_state()
    try:
        go_sync.sync_from_go(_feed([_appeal()]))
        operation, _plan = _appeal_plan()
        assert DrefIndicator.query.filter(DrefIndicator.indicator_bank_id.isnot(None)).count() == 0
        url = f"/dref-monitoring/operations/{operation.id}?tab=plan"
        assert 'name="indicator_on"' not in logged_in_sm_client.get(url).get_data(as_text=True)

        _bank()
        body = logged_in_sm_client.get(url).get_data(as_text=True)
        assert body.count('name="indicator_on"') == 3
        assert "EA test clinics supported" in body
    finally:
        app.plugin_manager.active_plugins = previous


@pytest.mark.db
def test_a_dref_plan_tab_previews_the_schedule_but_offers_no_bank_indicators(app, seeded, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"dref_monitoring"}))
    app.plugin_manager.sync_activation_state()
    try:
        _bank()
        go_sync.sync_from_go(_feed([], loans=[_loan(appeal_type="DREF", allocation_type="Grant")]))
        operation = DrefOperation.query.filter_by(appeal_code="MDRZZ018").one()
        body = logged_in_sm_client.get(f"/dref-monitoring/operations/{operation.id}?tab=plan").get_data(as_text=True)
        assert "data-dref-plan-schedule" in body
        assert "data-dref-schedule-row" in body
        assert 'name="indicator_on"' not in body
        assert "when the plan is confirmed" not in body
    finally:
        app.plugin_manager.active_plugins = previous
