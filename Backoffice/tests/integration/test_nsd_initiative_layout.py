"""NSD funds plugin: one assignment per reporting period, with one row per initiative (funded project)."""

import datetime as dt
from collections import defaultdict
from types import SimpleNamespace

from app.models import AssignedForm, AssignmentEntityStatus
from app.models.enums import AssignmentEntityStatusValue
from app.models.initiatives import Initiative
from plugins.nsd_report_forms.importer import apply, layout
from tests.factories import create_test_country, create_test_template


def _initiative(db_session, ref, **kwargs):
    ini = Initiative(reference=ref, title=f"Project {ref}", **kwargs)
    db_session.add(ini)
    db_session.flush()
    return ini


def _run(template):
    run = apply.Run.__new__(apply.Run)  # no workbook needed for the assignment logic
    run.lk = SimpleNamespace(templates={"CBF quarter": {"tpl": template}, "profile": {"tpl": template}})
    run.assignments, run.stats = {}, defaultdict(int)
    return run


def _proj(ini, active=True):
    return SimpleNamespace(reference=ini.reference, initiative_id=ini.id, active=active)


def test_projects_share_one_assignment_per_period_with_their_own_due_date(db_session, app):
    tpl = create_test_template(db_session, name="NSD Quarterly report - CBF")
    a, b = _initiative(db_session, "CBF-T1-2401-001"), _initiative(db_session, "CBF-T1-2401-002")
    run = _run(tpl)

    due_a, due_b = dt.datetime(2026, 7, 1), dt.datetime(2026, 9, 1)
    aes_a = run.get_assignment("CBF quarter", "Y1Q2", due_a, _proj(a))
    aes_b = run.get_assignment("CBF quarter", "Y1Q2", due_b, _proj(b))
    aes_next = run.get_assignment("CBF quarter", "Y1Q3", None, _proj(a))

    assert aes_a.assigned_form_id == aes_b.assigned_form_id != aes_next.assigned_form_id
    assert db_session.query(AssignedForm).filter_by(template_id=tpl.id).count() == 2
    assert (aes_a.entity_type, aes_a.entity_id) == ("initiative", a.id)
    assert (aes_a.due_date, aes_b.due_date) == (due_a, due_b)
    assert run.stats["assignments_created"] == 2 and run.stats["entities_created"] == 3

    # running again finds the same rows
    again = run.get_assignment("CBF quarter", "Y1Q2", due_a, _proj(a))
    assert again.id == aes_a.id
    assert db_session.query(AssignmentEntityStatus).filter_by(assigned_form_id=aes_a.assigned_form_id).count() == 2


def test_the_project_record_assignment_is_inactive_and_reports_are_active(db_session, app):
    tpl = create_test_template(db_session, name="NSD Project profile - CBF")
    ini = _initiative(db_session, "CBF-T2-2401-001")
    run = _run(tpl)
    record = run.get_assignment("profile", layout.PROFILE_PERIOD, None, _proj(ini))
    report = run.get_assignment("CBF quarter", "Y1Q1", None, _proj(ini))
    assert record.assigned_form.is_active is False
    assert report.assigned_form.is_active is True


def test_reports_of_a_closed_project_are_cancelled_and_come_back_when_it_reopens(db_session, app):
    tpl = create_test_template(db_session, name="NSD Quarterly report - CBF")
    ini = _initiative(db_session, "CBF-T3-2401-001")
    run = _run(tpl)

    aes = run.get_assignment("CBF quarter", "Y1Q1", None, _proj(ini, active=False))
    assert aes.status == AssignmentEntityStatusValue.cancelled

    aes = run.get_assignment("CBF quarter", "Y1Q1", None, _proj(ini, active=True))
    assert aes.status == AssignmentEntityStatusValue.pending

    # work in progress is never cancelled
    aes.status = AssignmentEntityStatusValue.in_progress
    aes = run.get_assignment("CBF quarter", "Y1Q1", None, _proj(ini, active=False))
    assert aes.status == AssignmentEntityStatusValue.in_progress


def test_old_per_project_assignments_are_found_and_deleted_but_the_new_ones_are_kept(db_session, app):
    tpl = create_test_template(db_session, name="NSD Quarterly report - CBF")
    country = create_test_country(db_session)
    ini = _initiative(db_session, "CBF-T4-2401-001")

    old = AssignedForm(template_id=tpl.id, period_name="CBF-T4-2401-001 Y1Q1")
    by_hand = AssignedForm(template_id=tpl.id, period_name="Autumn 2026")   # made by an admin, not by the importer
    new = AssignedForm(template_id=tpl.id, period_name="Y1Q1")
    db_session.add_all([old, by_hand, new])
    db_session.flush()
    db_session.add_all([
        AssignmentEntityStatus(assigned_form_id=old.id, entity_type="country", entity_id=country.id,
                               status=AssignmentEntityStatusValue.pending),
        AssignmentEntityStatus(assigned_form_id=by_hand.id, entity_type="country", entity_id=country.id,
                               status=AssignmentEntityStatusValue.pending),
        AssignmentEntityStatus(assigned_form_id=new.id, entity_type="initiative", entity_id=ini.id,
                               status=AssignmentEntityStatusValue.pending),
    ])
    db_session.commit()
    old_id, new_id, by_hand_id = old.id, new.id, by_hand.id

    assert apply.legacy_assignment_ids() == [old_id]
    assert apply.retire_legacy() == 1
    assert db_session.get(AssignedForm, old_id) is None
    assert db_session.get(AssignedForm, new_id) is not None
    assert db_session.get(AssignedForm, by_hand_id) is not None
    assert db_session.query(AssignmentEntityStatus).filter_by(assigned_form_id=new_id).count() == 1


def test_old_assignments_are_never_deleted_before_the_new_layout_exists(db_session, app):
    import pytest

    tpl = create_test_template(db_session, name="NSD Quarterly report - CBF")
    country = create_test_country(db_session)
    old = AssignedForm(template_id=tpl.id, period_name="CBF-T5-2401-001 Y1Q1")
    db_session.add(old)
    db_session.flush()
    db_session.add(AssignmentEntityStatus(assigned_form_id=old.id, entity_type="country", entity_id=country.id,
                                          status=AssignmentEntityStatusValue.pending))
    db_session.commit()
    old_id = old.id

    with pytest.raises(ValueError):
        apply.retire_legacy()
    assert db_session.get(AssignedForm, old_id) is not None
