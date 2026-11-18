"""Unit tests for project monitoring (pure computation, no database)."""

import datetime as dt

import pytest

from app.services.projects import monitoring as m

TODAY = dt.date(2026, 6, 15)


def _project(pid=1, **over):
    base = {
        "id": pid,
        "reference": f"P{pid}",
        "title": f"Project {pid}",
        "country": "Kenya",
        "region": "Africa",
        "ns": "Kenya Red Cross",
        "portfolio": "NSD",
        "fund": "CBF",
        "status": "Open",
        "granted": 100000.0,
        "base": 100000.0,
        "start": dt.date(2026, 1, 1),
        "end": dt.date(2026, 12, 31),
        "pm": "Pat Manager",
        "pm_email": "pat@example.org",
        "focal": "Fran Focal",
        "focal_email": "fran@example.org",
    }
    base.update(over)
    return base


def _report(pid=1, aes_id=1, **over):
    base = {
        "aes_id": aes_id,
        "assignment_id": aes_id,
        "project_id": pid,
        "template_id": 1,
        "period": "Y1Q1",
        "type": "quarter",
        "status": "pending",
        "due": TODAY + dt.timedelta(days=10),
        "completion": None,
        "submitted_at": None,
        "active": True,
        "closed": False,
        "overall": None,
        "activities": None,
        "actual": None,
    }
    base.update(over)
    return base


# ------------------------------------------------------------------ small rules
def test_statuses_for_filter():
    assert m.statuses_for_filter("open") == m.OPEN_STATUSES
    assert m.statuses_for_filter("") == m.OPEN_STATUSES
    assert m.statuses_for_filter("closed") == m.CLOSED_STATUSES
    assert m.statuses_for_filter("all") is None
    assert m.statuses_for_filter("archived") == ("Archived",)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("On track", "green"),
        ("Partially on track", "amber"),
        ("Not on track", "red"),
        ("", "grey"),
        (None, "grey"),
        ("Fully achieved", "green"),
        ("Not achieved", "red"),
    ],
)
def test_assessment_light(text, expected):
    assert m.assessment_light(text) == expected


def test_slot_sort_key_orders_quarters_before_final():
    slots = ["Final", "Y1Q2", "Y2Q1", "Y1Q1"]
    assert sorted(slots, key=m.slot_sort_key) == ["Y1Q1", "Y1Q2", "Y2Q1", "Final"]


def test_elapsed_pct_clamps_and_handles_missing_dates():
    start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 11)
    assert m.elapsed_pct(start, end, dt.date(2025, 12, 1)) == 0.0
    assert m.elapsed_pct(start, end, dt.date(2026, 1, 6)) == 50.0
    assert m.elapsed_pct(start, end, dt.date(2027, 1, 1)) == 100.0
    assert m.elapsed_pct(None, end, TODAY) is None
    assert m.elapsed_pct(end, start, TODAY) is None


@pytest.mark.parametrize(
    "rate,elapsed,expected",
    [
        (None, 50.0, "no_data"),
        (120.0, 50.0, "overspent"),
        (50.0, 50.0, "on_pace"),
        (34.0, 50.0, "behind"),
        (20.0, 50.0, "far_behind"),
        (80.0, 50.0, "ahead"),
        (None, None, "no_data"),
        (30.0, None, "far_behind"),
        (60.0, None, "behind"),
        (80.0, None, "on_pace"),
    ],
)
def test_pace_state(rate, elapsed, expected):
    assert m.pace_state(rate, elapsed) == expected


# ------------------------------------------------------------------ classify
@pytest.mark.parametrize(
    "over,project_open,expected",
    [
        ({"status": "submitted"}, True, "done"),
        ({"status": "approved"}, False, "done"),
        ({"status": "cancelled"}, True, "cancelled"),
        ({"active": False}, True, "paused"),
        ({"closed": True}, True, "closed_unreported"),
        ({}, False, "closed_unreported"),
        ({"due": TODAY - dt.timedelta(days=1)}, True, "overdue"),
        ({"status": "in_progress", "due": TODAY - dt.timedelta(days=1)}, True, "overdue"),
        ({"status": "in_progress"}, True, "in_progress"),
        ({"status": "requires_revision"}, True, "in_progress"),
        ({}, True, "not_started"),
        ({"due": None}, True, "not_started"),
        ({"due": TODAY}, True, "not_started"),
    ],
)
def test_classify_report(over, project_open, expected):
    assert m.classify_report(_report(**over), project_open, TODAY) == expected


# ------------------------------------------------------------------ compute
def test_empty_portfolio_returns_zeroed_payload():
    out = m.compute_monitoring([], [], TODAY)
    assert out["kpis"]["projects_total"] == 0
    assert out["kpis"]["submission_rate"] is None
    assert out["lists"]["overdue"] == []
    assert out["charts"]["pipeline"]["overdue"] == 0
    assert len(out["charts"]["deadlines"]) == m.DEADLINE_MONTHS + 1


def test_overdue_and_due_soon_counts_and_worklists():
    projects = [_project(1), _project(2)]
    reports = [
        _report(1, 1, due=TODAY - dt.timedelta(days=30)),
        _report(1, 2, period="Y1Q2", due=TODAY + dt.timedelta(days=5)),
        _report(2, 3, status="submitted", due=TODAY - dt.timedelta(days=3),
                submitted_at=dt.datetime(2026, 6, 10)),
    ]
    out = m.compute_monitoring(projects, reports, TODAY)
    k = out["kpis"]
    assert k["reports_overdue"] == 1
    assert k["reports_due_soon"] == 1
    assert k["reports_done"] == 1
    assert k["avg_days_overdue"] == 30
    # 1 submitted out of 2 already-due reports
    assert k["submission_rate"] == 50.0
    assert k["ontime_rate"] == 100.0
    overdue = out["lists"]["overdue"]
    assert [r["reference"] for r in overdue] == ["P1"]
    assert overdue[0]["days_overdue"] == 30
    assert [r["period"] for r in out["lists"]["upcoming"]] == ["Y1Q2"]
    # deadline timeline: overdue bucket first, then the current month
    assert out["charts"]["deadlines"][0] == {"bucket": "overdue", "count": 1}
    assert out["charts"]["deadlines"][1] == {"bucket": "2026-06", "count": 1}


def test_severe_overdue_makes_project_critical():
    out = m.compute_monitoring(
        [_project(1)], [_report(1, 1, due=TODAY - dt.timedelta(days=m.SEVERE_OVERDUE_DAYS + 1))], TODAY
    )
    s = out["lists"]["attention"][0]
    assert s["severity"] == "red"
    assert s["reporting_light"] == "red"
    assert {"key": "overdue_reports", "level": "red", "count": 1} in s["flags"]


def test_mild_overdue_is_amber():
    out = m.compute_monitoring([_project(1)], [_report(1, 1, due=TODAY - dt.timedelta(days=2))], TODAY)
    assert out["lists"]["attention"][0]["severity"] == "amber"


def test_assessment_and_spending_pace_drive_severity():
    # 5 months into a 12-month project with only 10 % spent: far behind (red).
    project = _project(1, start=dt.date(2026, 1, 15), end=dt.date(2026, 12, 15))
    reports = [
        _report(1, 1, status="submitted", due=TODAY - dt.timedelta(days=30),
                submitted_at=dt.datetime(2026, 5, 1), overall="Partially on track",
                activities="On track", actual=10000.0),
    ]
    out = m.compute_monitoring([project], reports, TODAY, answers_available=True)
    s = out["lists"]["attention"][0]
    assert s["overall"] == "amber"
    assert s["activities"] == "green"
    assert s["spending_rate"] == 10.0
    assert s["pace"] == "far_behind"
    assert s["severity"] == "red"
    assert out["charts"]["assessment"]["amber"] == 1
    assert out["charts"]["pace"]["far_behind"] == 1
    assert out["charts"]["pace_points"][0]["reference"] == "P1"
    assert out["answers_available"] is True
    keys = {f["key"] for f in s["flags"]}
    assert {"partially_on_track", "underspending"} <= keys


def test_healthy_project_is_not_listed_for_attention():
    project = _project(1, start=dt.date(2026, 1, 1), end=dt.date(2026, 12, 31))
    reports = [
        _report(1, 1, status="approved", due=TODAY - dt.timedelta(days=40),
                submitted_at=dt.datetime(2026, 5, 1), overall="On track",
                activities="On track", actual=45000.0),
        _report(1, 2, period="Y1Q3", due=TODAY + dt.timedelta(days=60)),
    ]
    out = m.compute_monitoring([project], reports, TODAY)
    assert out["lists"]["attention"] == []
    assert out["kpis"]["projects_green"] == 1


def test_closed_projects_do_not_count_as_overdue_and_are_excluded_from_open_charts():
    closed = _project(1, status="Closed")
    out = m.compute_monitoring([closed], [_report(1, 1, due=TODAY - dt.timedelta(days=90))], TODAY)
    assert out["kpis"]["projects_open"] == 0
    assert out["kpis"]["projects_closed"] == 1
    assert out["kpis"]["reports_overdue"] == 0
    assert out["charts"]["pipeline"]["closed_unreported"] == 1
    assert out["lists"]["overdue"] == []
    assert sum(out["charts"]["assessment"].values()) == 0


def test_paused_and_cancelled_reports_are_ignored():
    reports = [_report(1, 1, active=False), _report(1, 2, status="cancelled", period="Y1Q2")]
    out = m.compute_monitoring([_project(1)], reports, TODAY)
    assert out["kpis"]["reports_total"] == 0
    assert out["report_rows"] == []
    flags = {f["key"] for f in out["lists"]["attention"][0]["flags"]} if out["lists"]["attention"] else set()
    assert "no_reporting" in flags


def test_ending_soon_flags_final_report_state():
    project = _project(1, end=TODAY + dt.timedelta(days=30))
    out = m.compute_monitoring([project], [_report(1, 1, period="Y1Q1")], TODAY)
    ending = out["lists"]["ending_soon"]
    assert [s["reference"] for s in ending] == ["P1"]
    assert ending[0]["final_state"] == "none"
    assert "ending_final_pending" in {f["key"] for f in ending[0]["flags"]}

    final = _report(1, 2, period="Final", type="final", status="submitted",
                    due=TODAY - dt.timedelta(days=1), submitted_at=dt.datetime(2026, 6, 1))
    out = m.compute_monitoring([project], [final], TODAY)
    assert out["lists"]["ending_soon"][0]["final_state"] == "done"
    assert "ending_final_pending" not in {f["key"] for f in out["lists"]["ending_soon"][0]["flags"]}


def test_past_end_date_is_flagged():
    project = _project(1, end=TODAY - dt.timedelta(days=5))
    out = m.compute_monitoring([project], [_report(1, 1)], TODAY)
    assert "past_end_date" in {f["key"] for f in out["lists"]["attention"][0]["flags"]}


def test_data_quality_lists_missing_fields_for_open_projects_only():
    gaps = _project(1, pm_email="", focal_email="", start=None, granted=None, base=None)
    closed_gaps = _project(2, status="Closed", pm_email="")
    out = m.compute_monitoring([gaps, closed_gaps, _project(3)], [], TODAY)
    quality = out["lists"]["data_quality"]
    assert [q["reference"] for q in quality] == ["P1"]
    assert set(quality[0]["missing"]) == {"manager", "focal", "dates", "amount"}


def test_pm_workload_groups_by_manager_email():
    projects = [
        _project(1, pm_email="a@x.org", pm="A"),
        _project(2, pm_email="A@x.org", pm="A"),
        _project(3, pm_email="b@x.org", pm="B"),
    ]
    reports = [
        _report(1, 1, due=TODAY - dt.timedelta(days=20)),
        _report(2, 2, due=TODAY - dt.timedelta(days=1)),
        _report(3, 3),
    ]
    out = m.compute_monitoring(projects, reports, TODAY)
    workload = out["lists"]["pm_workload"]
    assert workload[0]["pm"] == "A"
    assert workload[0]["projects"] == 2
    assert workload[0]["overdue"] == 2
    assert workload[0]["red"] == 1
    assert workload[1]["pm"] == "B"
    assert workload[1]["overdue"] == 0


def test_region_breakdown_and_funding():
    projects = [
        _project(1, region="Africa", portfolio="NSD", granted=100.0),
        _project(2, region="Asia Pacific", portfolio="NSD", granted=50.0),
        _project(3, region="", portfolio="", fund="ESF", granted=25.0),
    ]
    reports = [
        _report(1, 1, status="submitted", due=TODAY - dt.timedelta(days=1)),
        _report(2, 2, due=TODAY - dt.timedelta(days=1)),
        _report(3, 3),
    ]
    out = m.compute_monitoring(projects, reports, TODAY)
    regions = {r["region"]: r for r in out["charts"]["regions"]}
    assert regions["Africa"]["done"] == 1
    assert regions["Asia Pacific"]["overdue"] == 1
    assert regions["—"]["in_progress"] == 1
    funding = {f["portfolio"]: f for f in out["charts"]["funding"]}
    assert funding["NSD"] == {"portfolio": "NSD", "granted": 150.0, "projects": 2}
    assert funding["ESF"]["granted"] == 25.0
    assert out["kpis"]["granted_open"] == 175.0


class _FakeManager:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def get_project_report_answers(self, reports):
        self.calls.append([r["aes_id"] for r in reports])
        return self.answers


def _app_with_manager(manager):
    from flask import Flask

    app = Flask(__name__)
    app.plugin_manager = manager
    return app


def test_attach_plugin_answers_merges_hook_result_into_reports():
    reports = [_report(1, 10), _report(1, 11, period="Y1Q2")]
    manager = _FakeManager({10: {"overall": "On track", "activities": "", "actual": "2500.5"}})
    with _app_with_manager(manager).app_context():
        assert m.attach_plugin_answers(reports) is True
    assert manager.calls == [[10, 11]]
    assert reports[0]["overall"] == "On track"
    assert reports[0]["activities"] is None
    assert reports[0]["actual"] == 2500.5
    assert reports[1]["overall"] is None


def test_attach_plugin_answers_without_answers_or_manager():
    reports = [_report(1, 10)]
    with _app_with_manager(_FakeManager({})).app_context():
        assert m.attach_plugin_answers(reports) is False
    with _app_with_manager(None).app_context():
        assert m.attach_plugin_answers(reports) is False
    assert m.attach_plugin_answers([]) is False


def test_attach_plugin_answers_survives_a_failing_manager():
    class _Boom:
        def get_project_report_answers(self, reports):
            raise RuntimeError("boom")

    with _app_with_manager(_Boom()).app_context():
        assert m.attach_plugin_answers([_report(1, 10)]) is False


def test_reports_for_unknown_projects_are_ignored():
    out = m.compute_monitoring([_project(1)], [_report(99, 1)], TODAY)
    assert out["kpis"]["reports_total"] == 0
