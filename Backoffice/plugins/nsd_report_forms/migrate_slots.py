"""Migrate shared NSD CBF slot assignments onto per-project cycle assignments.

For each AES on a bare ``Y*Q*`` / ``Final`` slot with ``entity_type=project``:
1. Create or find the per-project ``AssignedForm`` (scope=project_cycle).
2. Copy audience / active / closed state.
3. Repoint ``aes.assigned_form_id`` (FormData stays on the same AES id).
4. Delete empty shared slot assignments afterwards.

Safe to re-run. Use ``dry_run=True`` to count without writing.
"""
from __future__ import annotations

import logging
import re
from typing import Dict

from app import db
from app.models import AssignedForm, AssignmentEntityStatus, FormData, RepeatGroupInstance
from app.models.assignments import assigned_form_allowed_role
from app.models.enums import AssignmentScope
from app.models.projects import Project
from app.services.projects.service import (
    CYCLE_PERIOD_SEP,
    cycle_period_name,
    ensure_project_cycle_assignment,
    parse_cycle_slot,
)
from app.utils.datetime_helpers import utcnow

from plugins.nsd_report_forms.constants import ENTITY_TYPE
from plugins.nsd_report_forms.overview import data as overview_data
from plugins.nsd_report_forms import schedule as nsd_schedule

log = logging.getLogger(__name__)

_SHARED_SLOT = re.compile(r'^(Y\d+Q\d+|Final)$')


def _is_shared_slot_period(period_name: str) -> bool:
    return bool(_SHARED_SLOT.match((period_name or '').strip()))


def _aes_has_data(aes_id: int) -> bool:
    if FormData.query.filter_by(assignment_entity_status_id=aes_id).first() is not None:
        return True
    return (
        RepeatGroupInstance.query.filter_by(assignment_entity_status_id=aes_id).first() is not None
    )


def _copy_audience(source_af_id: int, target_af_id: int) -> None:
    if source_af_id == target_af_id:
        return
    existing = {
        int(r[0])
        for r in db.session.execute(
            db.select(assigned_form_allowed_role.c.role_id).where(
                assigned_form_allowed_role.c.assigned_form_id == int(target_af_id)
            )
        ).all()
    }
    source_roles = [
        int(r[0])
        for r in db.session.execute(
            db.select(assigned_form_allowed_role.c.role_id).where(
                assigned_form_allowed_role.c.assigned_form_id == int(source_af_id)
            )
        ).all()
    ]
    for role_id in source_roles:
        if role_id in existing:
            continue
        db.session.execute(
            assigned_form_allowed_role.insert().values(
                assigned_form_id=int(target_af_id),
                role_id=role_id,
                created_at=utcnow(),
            )
        )


def migrate_shared_slots_to_project_cycles(*, dry_run: bool = False) -> Dict[str, int]:
    """Repoint shared-slot project AES rows onto per-project cycle assignments."""
    try:
        nsd_schedule.ensure_cbf_templates_ready()
    except RuntimeError as exc:
        log.warning('NSD migrate-slots: %s', exc)
        return {'error': 1}

    tpl_ids = set()
    for key in ('CBF quarter', 'CBF final report'):
        tid = overview_data._template_items(key)[0]
        if tid:
            tpl_ids.add(tid)
    stats = {
        'examined': 0,
        'already_cycle': 0,
        'repointed': 0,
        'skipped_no_project': 0,
        'skipped_not_shared': 0,
        'skipped_conflict': 0,
        'shared_slots_deleted': 0,
        'assignments_created': 0,
    }
    if not tpl_ids:
        return stats

    rows = (
        AssignmentEntityStatus.query
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            AssignedForm.template_id.in_(tpl_ids),
            AssignmentEntityStatus.entity_type == ENTITY_TYPE,
        )
        .all()
    )
    shared_af_ids = set()
    for aes in rows:
        stats['examined'] += 1
        af = aes.assigned_form
        if af is None:
            continue
        if (af.scope or '') == AssignmentScope.project_cycle.value and af.project_id:
            stats['already_cycle'] += 1
            continue
        period = (af.period_name or '').strip()
        if not _is_shared_slot_period(period):
            # Already named "<ref> · Y1Q2" but missing scope/project_id — fix metadata only
            slot = parse_cycle_slot(period)
            if slot and CYCLE_PERIOD_SEP in period:
                project = db.session.get(Project, aes.entity_id)
                if project is None:
                    stats['skipped_no_project'] += 1
                    continue
                if dry_run:
                    stats['repointed'] += 1
                    continue
                af.scope = AssignmentScope.project_cycle.value
                af.project_id = project.id
                af.custom_name = af.custom_name or f'{project.reference}{CYCLE_PERIOD_SEP}{slot}'
                stats['repointed'] += 1
                continue
            stats['skipped_not_shared'] += 1
            continue

        slot = period
        project = db.session.get(Project, aes.entity_id)
        if project is None:
            stats['skipped_no_project'] += 1
            continue

        shared_af_ids.add(af.id)
        if dry_run:
            stats['repointed'] += 1
            continue

        existed = AssignedForm.query.filter_by(
            template_id=af.template_id,
            period_name=cycle_period_name(project.reference, slot),
        ).first()
        target_af, placeholder_aes = ensure_project_cycle_assignment(
            project,
            af.template_id,
            slot,
            period_start=af.period_start,
            period_end=af.period_end,
            due_date=aes.due_date,
            is_active=af.is_active,
        )
        if existed is None:
            stats['assignments_created'] += 1
        target_af.is_closed = bool(af.is_closed) or (not project.is_open)
        target_af.is_active = bool(af.is_active)
        _copy_audience(af.id, target_af.id)

        if placeholder_aes.id != aes.id:
            if _aes_has_data(placeholder_aes.id):
                stats['skipped_conflict'] += 1
                log.warning(
                    'NSD migrate-slots: conflict AES %s (has data) vs %s for project %s on %s',
                    placeholder_aes.id, aes.id, project.reference, slot,
                )
                continue
            db.session.delete(placeholder_aes)
            db.session.flush()
            aes.assigned_form_id = target_af.id
        stats['repointed'] += 1

    if not dry_run:
        db.session.flush()
        for af_id in shared_af_ids:
            af = db.session.get(AssignedForm, af_id)
            if af is None:
                continue
            remaining = AssignmentEntityStatus.query.filter_by(assigned_form_id=af.id).count()
            if remaining == 0 and _is_shared_slot_period(af.period_name or ''):
                db.session.execute(
                    assigned_form_allowed_role.delete().where(
                        assigned_form_allowed_role.c.assigned_form_id == af.id
                    )
                )
                db.session.delete(af)
                stats['shared_slots_deleted'] += 1
        db.session.commit()

    return stats


def run_slot_migration(*, dry_run: bool = False) -> dict:
    return {'slots': migrate_shared_slots_to_project_cycles(dry_run=dry_run), 'dry_run': dry_run}
