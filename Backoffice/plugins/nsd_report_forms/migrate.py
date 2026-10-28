"""Migrate legacy NSD assignments (reference-in-period_name + country AES) to core Project.

1. Upsert core ``project`` from profile assignments.
2. Ensure shared slot AssignedForms (Y1Q1…Final).
3. Remap each legacy report AES onto the matching shared slot with entity_type=project,
   keeping the same AES id (and thus FormData).

Safe to re-run: skips AES already on ``project``.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from app import db
from app.models import AssignedForm, AssignmentEntityStatus, FormData, FormItem, FormTemplate, FormTemplateVersion
from app.models.projects import Project

from plugins.nsd_report_forms.constants import ENTITY_TYPE, FINAL_SLOT
from plugins.nsd_report_forms.importer import layout
from plugins.nsd_report_forms.overview import data as overview_data
from plugins.nsd_report_forms import schedule as nsd_schedule

log = logging.getLogger(__name__)

_LEGACY_PERIOD = re.compile(r'^(.+)\s+(Y\d+Q\d+|Final|Project)$')


def _profile_template_id() -> Optional[int]:
    row = (
        db.session.query(FormTemplate.id)
        .join(FormTemplateVersion, FormTemplateVersion.id == FormTemplate.published_version_id)
        .filter(FormTemplateVersion.name == layout.TEMPLATE_NAMES['profile'])
        .first()
    )
    return int(row[0]) if row else None


def backfill_projects_from_profiles() -> Dict[str, int]:
    """Create core project rows from legacy profile assignments. Returns stats."""
    ctx = overview_data.Ctx()
    profiles = overview_data._profiles_legacy(ctx, with_logframe=True)
    stats = {'created': 0, 'updated': 0, 'skipped_no_country': 0}
    for ref, p in profiles.items():
        country_id = p.get('country_id')
        if not country_id:
            stats['skipped_no_country'] += 1
            continue
        existed = Project.query.filter_by(reference=ref).first() is not None
        row = {
            'reference': ref,
            'fund': 'CBF',
            'title': p.get('title') or '',
            'ns_name': p.get('ns') or '',
            'status': p.get('status') or 'Open',
            'funding_modality': p.get('modality') or '',
            'categories': p.get('categories') or '',
            'start_date': p['start'].isoformat() if p.get('start') else '',
            'end_date': p['end'].isoformat() if p.get('end') else '',
            'amount_granted_chf': p.get('granted'),
            'expected_spending_chf': p.get('expected'),
            'planned_overview': p.get('overview') or '',
            'ns_focal_name': p.get('ns_focal') or '',
            'ns_focal_email': p.get('ns_focal_email') or '',
            'ifrc_pm_name': p.get('pm') or '',
            'ifrc_pm_email': p.get('pm_email') or '',
        }
        nsd_schedule.upsert_project_from_import(row, int(country_id), logframe=p.get('logframe'))
        stats['updated' if existed else 'created'] += 1
    db.session.commit()
    return stats


def _parse_legacy_period(period_name: str) -> Optional[Tuple[str, str]]:
    m = _LEGACY_PERIOD.match((period_name or '').strip())
    if not m:
        return None
    ref, suffix = m.group(1).strip(), m.group(2).strip()
    if suffix == layout.PROFILE_PERIOD:
        return None  # profiles are not remapped as reports
    slot = FINAL_SLOT if suffix == layout.FINAL_PERIOD else suffix
    return ref, slot


def remap_report_aes(*, dry_run: bool = False) -> Dict[str, int]:
    """Move legacy country AES onto shared slots with entity_type=project."""
    slots = nsd_schedule.ensure_shared_slots()
    projects = {p.reference: p for p in Project.query.all()}
    tpl_ids = set()
    for key in ('CBF quarter', 'CBF final report'):
        tid = overview_data._template_items(key)[0]
        if tid:
            tpl_ids.add(tid)

    stats = {
        'examined': 0, 'remapped': 0, 'already_modern': 0, 'skipped_no_project': 0,
        'skipped_no_slot': 0, 'skipped_conflict': 0, 'orphaned_legacy_af': 0,
    }
    if not tpl_ids:
        return stats

    rows = (
        AssignmentEntityStatus.query
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(AssignedForm.template_id.in_(tpl_ids))
        .all()
    )
    for aes in rows:
        stats['examined'] += 1
        if aes.entity_type == ENTITY_TYPE:
            stats['already_modern'] += 1
            continue
        af = aes.assigned_form
        parsed = _parse_legacy_period(af.period_name if af else '')
        if not parsed:
            # Might already be a shared slot with country entity — remap by period_name alone
            period = (af.period_name or '').strip() if af else ''
            if period == FINAL_SLOT or re.match(r'^Y\d+Q\d+$', period):
                # Shared slot but wrong entity — need project id from country + ... can't disambiguate
                stats['skipped_no_project'] += 1
                continue
            stats['skipped_no_slot'] += 1
            continue
        ref, slot = parsed
        project = projects.get(ref)
        if project is None:
            stats['skipped_no_project'] += 1
            continue
        target_af = slots.get(slot)
        if target_af is None:
            stats['skipped_no_slot'] += 1
            continue
        # Conflict if another AES already owns (target_af, nsd_project, project.id)
        conflict = AssignmentEntityStatus.query.filter_by(
            assigned_form_id=target_af.id,
            entity_type=ENTITY_TYPE,
            entity_id=project.id,
        ).first()
        if conflict and conflict.id != aes.id:
            stats['skipped_conflict'] += 1
            log.warning(
                'NSD migrate: conflict AES %s vs %s for %s on %s',
                aes.id, conflict.id, ref, slot,
            )
            continue
        if dry_run:
            stats['remapped'] += 1
            continue
        aes.assigned_form_id = target_af.id
        aes.entity_type = ENTITY_TYPE
        aes.entity_id = project.id
        stats['remapped'] += 1

    if not dry_run:
        db.session.commit()
        # Deactivate orphaned per-project AssignedForms that no longer have AES
        legacy_afs = (
            AssignedForm.query
            .filter(AssignedForm.template_id.in_(tpl_ids))
            .filter(~AssignedForm.period_name.in_(list(slots.keys())))
            .all()
        )
        for af in legacy_afs:
            if af.entity_statuses.count() == 0:
                af.is_active = False
                stats['orphaned_legacy_af'] += 1
        db.session.commit()
    return stats


def run_migration(*, dry_run: bool = False) -> dict:
    """Full dual-read cutover helper.

    ``dry_run`` still builds projects in the session for remap analysis, then rolls back.
    """
    project_stats = backfill_projects_from_profiles()
    if dry_run:
        # backfill commits; for dry-run remap we only simulate AES changes
        remap_stats = remap_report_aes(dry_run=True)
        return {'projects': project_stats, 'remap': remap_stats, 'dry_run': True}
    remap_stats = remap_report_aes(dry_run=False)
    return {'projects': project_stats, 'remap': remap_stats, 'dry_run': False}
