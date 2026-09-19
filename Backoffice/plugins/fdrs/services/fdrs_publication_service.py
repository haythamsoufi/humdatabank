"""FDRS publication service — preview and run the publish-to-public-website step.

Copies the publishable current value into the published snapshot
(``FormData.published_value`` / ``published_disagg_data`` /
``published_numeric_value`` / ``published_source``)
for one FDRS assignment (``AssignedForm``, template 21) at a time: the reported
"main" value (``value`` / ``disagg_data`` / ``numeric_value``) when present, or
the imputed value (``imputed_value`` / ``imputed_disagg_data`` /
``imputed_numeric_value``) when the reported value is missing. Scoped to form
items marked ``privacy='public'`` in the Form Builder — the same gate
``GET /api/v1/data`` uses for unauthenticated readers (see
``app.services.data_retrieval.shared.form_item_privacy_is_public_expr``).

Nothing here writes automatically: publishing only happens when an admin runs
``publish_assignment()`` from the FDRS "Manage Publication" admin page
(``plugins/fdrs/publication_routes.py``). Until then, ``published_*`` stays exactly
as it was after the last publish (or ``NULL`` if never published), and
``GET /api/v1/fdrs/published-data`` (``plugins/fdrs/public_api_routes.py``) only ever
reads that snapshot — never the live ``value``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from flask import abort
from sqlalchemy.orm import contains_eager

from app.extensions import db
from app.models import AssignedForm, AssignmentEntityStatus, Country, FormData, FormItem, User
from app.services.data_retrieval.shared import form_item_privacy_is_public_expr
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from app.utils.datetime_helpers import utcnow

# 'empty' = nothing to publish (no reported, no imputed) and nothing published
# (not actionable, but tallied for transparency so counts always add up to
# total_public_items).
ALL_DIFF_KINDS = ('new', 'changed', 'removed', 'source', 'unchanged', 'empty')
PENDING_DIFF_KINDS = ('new', 'changed', 'removed', 'source')


def _empty_counts() -> Dict[str, int]:
    return {kind: 0 for kind in ALL_DIFF_KINDS}


def list_fdrs_assignments() -> List[AssignedForm]:
    """FDRS (template 21) assignments, most recent reporting period first."""
    return (
        AssignedForm.query
        .filter(AssignedForm.template_id == FDRS_TEMPLATE_ID)
        .order_by(
            AssignedForm.period_end.desc().nullslast(),
            AssignedForm.period_start.desc().nullslast(),
            AssignedForm.id.desc(),
        )
        .all()
    )


def _get_fdrs_assigned_form_or_404(assigned_form_id: int) -> AssignedForm:
    """Fetch an AssignedForm, 404ing if it does not belong to the FDRS template.

    This tool is FDRS-specific (template 21) — without this check, a caller with
    generic template edit/view permission could pass an ``assigned_form_id`` that
    belongs to a different template (e.g. UPR) and read/publish through this
    FDRS-only surface.
    """
    assigned_form = AssignedForm.query.get_or_404(assigned_form_id)
    if assigned_form.template_id != FDRS_TEMPLATE_ID:
        abort(404)
    return assigned_form


def _public_form_item_ids() -> List[int]:
    """All FormItem ids on the FDRS template marked privacy='public'."""
    return [
        row.id for row in (
            FormItem.query
            .filter(FormItem.template_id == FDRS_TEMPLATE_ID)
            .filter(form_item_privacy_is_public_expr())
            .with_entities(FormItem.id)
            .all()
        )
    ]


def _public_form_data_query(assigned_form_id: int):
    """FormData rows for one FDRS assignment's country entities, public items only."""
    return (
        FormData.query
        .join(AssignmentEntityStatus, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(FormItem, FormData.form_item_id == FormItem.id)
        .filter(AssignmentEntityStatus.assigned_form_id == assigned_form_id)
        .filter(AssignmentEntityStatus.entity_type == 'country')
        .filter(form_item_privacy_is_public_expr())
    )


def get_assignment_publication_summary(assigned_form_id: int) -> Dict[str, Any]:
    """
    Preview what publishing this assignment would change, without writing anything.

    Returns a dict with the assignment, one row per country (AssignmentEntityStatus),
    and assignment-wide totals. Countries are sorted with the most "actionable" ones
    (biggest pending change count) first.
    """
    assigned_form = _get_fdrs_assigned_form_or_404(assigned_form_id)

    aes_rows = (
        AssignmentEntityStatus.query
        .filter_by(assigned_form_id=assigned_form_id, entity_type='country')
        .all()
    )
    counts_by_aes: Dict[int, Dict[str, int]] = {aes.id: _empty_counts() for aes in aes_rows}

    for row in _public_form_data_query(assigned_form_id).all():
        counts = counts_by_aes.get(row.assignment_entity_status_id)
        if counts is None:
            continue
        counts[row.publication_diff_kind()] += 1

    country_ids = {aes.entity_id for aes in aes_rows}
    countries_by_id = (
        {c.id: c for c in Country.query.filter(Country.id.in_(country_ids)).all()}
        if country_ids else {}
    )
    publisher_ids = {aes.published_by_user_id for aes in aes_rows if aes.published_by_user_id}
    publishers_by_id = (
        {u.id: u for u in User.query.filter(User.id.in_(publisher_ids)).all()}
        if publisher_ids else {}
    )

    countries: List[Dict[str, Any]] = []
    totals = _empty_counts()
    for aes in aes_rows:
        counts = counts_by_aes[aes.id]
        for kind, n in counts.items():
            totals[kind] += n
        pending = sum(counts[kind] for kind in PENDING_DIFF_KINDS)
        country = countries_by_id.get(aes.entity_id)
        publisher = publishers_by_id.get(aes.published_by_user_id) if aes.published_by_user_id else None
        countries.append({
            'assignment_entity_status_id': aes.id,
            'country_id': aes.entity_id,
            'country_name': country.name if country else f'Country {aes.entity_id}',
            'country_iso3': country.iso3 if country else None,
            'status': aes.status.value if hasattr(aes.status, 'value') else aes.status,
            'counts': counts,
            'pending_count': pending,
            'has_pending_changes': pending > 0,
            'total_public_items': sum(counts.values()),
            'published_at': aes.published_at.isoformat() if aes.published_at else None,
            'published_by_name': publisher.name if publisher else None,
        })

    # Most actionable first, then alphabetical for a stable secondary order.
    countries.sort(key=lambda c: (-c['pending_count'], c['country_name'] or ''))

    pending_total = sum(totals[kind] for kind in PENDING_DIFF_KINDS)
    return {
        'assignment': {
            'id': assigned_form.id,
            'period_name': assigned_form.period_name,
            'display_name': assigned_form.display_name,
            'is_active': assigned_form.is_active,
            'is_closed': assigned_form.is_closed,
        },
        'totals': totals,
        'pending_total': pending_total,
        'countries_with_pending_changes': sum(1 for c in countries if c['has_pending_changes']),
        'countries_total': len(countries),
        'countries': countries,
    }


def get_country_change_detail(assigned_form_id: int, assignment_entity_status_id: int) -> Dict[str, Any]:
    """Item-level diff for one country in one assignment (lazy-loaded by the admin UI)."""
    _get_fdrs_assigned_form_or_404(assigned_form_id)
    aes = AssignmentEntityStatus.query.filter_by(
        id=assignment_entity_status_id,
        assigned_form_id=assigned_form_id,
        entity_type='country',
    ).first_or_404()

    country = Country.query.get(aes.entity_id)

    rows = (
        _public_form_data_query(assigned_form_id)
        # Reuse the FormItem join _public_form_data_query already does for filtering
        # to also populate row.form_item (below), instead of one lazy-load query per row.
        .options(contains_eager(FormData.form_item))
        .filter(FormData.assignment_entity_status_id == assignment_entity_status_id)
        .all()
    )

    items = []
    for row in rows:
        kind = row.publication_diff_kind()
        if kind == 'empty':
            continue  # nothing to publish and nothing published — no point showing it
        current_value, current_disagg, _ = row.publication_current_payload()
        items.append({
            'form_item_id': row.form_item_id,
            'label': row.form_item.label if row.form_item else f'Item {row.form_item_id}',
            'kind': kind,
            'current_value': current_value,
            'current_disagg_data': current_disagg,
            'current_is_imputed': row.publication_uses_imputed(),
            'published_value': row.published_value,
            'published_disagg_data': row.published_disagg_data,
            'published_source': row.published_source,
        })

    kind_order = {'changed': 0, 'removed': 1, 'new': 2, 'source': 3, 'unchanged': 4}
    items.sort(key=lambda i: (kind_order.get(i['kind'], 9), i['label'] or ''))

    return {
        'assignment_entity_status_id': aes.id,
        'country_name': country.name if country else f'Country {aes.entity_id}',
        'country_iso3': country.iso3 if country else None,
        'items': items,
    }


def publish_assignment(
    assigned_form_id: int,
    *,
    assignment_entity_status_ids: Optional[List[int]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Copy the publishable current value (reported, or imputed when reported is
    missing) into the published snapshot for one FDRS assignment.

    ``assignment_entity_status_ids``: scope to these countries only (per-assignment,
    per-country publication). ``None``/omitted publishes every country in the
    assignment. Ids that do not belong to this assignment are silently dropped.

    Only countries with at least one ``FormData`` row on a public-privacy item are
    counted as published: ``published_countries`` and each country's
    ``AssignmentEntityStatus.published_at`` / ``published_by_user_id`` are left
    untouched for a selected country that has nothing to publish (e.g. the FDRS
    template has zero ``privacy='public'`` items, or that country has never had
    any data reported/imported for one) — so "last published" never claims an
    action that did not actually happen.

    Returns the counts of rows moved into each diff bucket (see
    ``FormData.publication_diff_kind``) plus how many countries were touched.
    """
    assigned_form = _get_fdrs_assigned_form_or_404(assigned_form_id)

    valid_aes_ids = [
        aes_id for (aes_id,) in (
            AssignmentEntityStatus.query
            .filter_by(assigned_form_id=assigned_form_id, entity_type='country')
            .with_entities(AssignmentEntityStatus.id)
            .all()
        )
    ]
    if assignment_entity_status_ids:
        valid_set = set(valid_aes_ids)
        target_aes_ids = [aid for aid in assignment_entity_status_ids if aid in valid_set]
    else:
        target_aes_ids = valid_aes_ids

    if not target_aes_ids:
        return {
            'assignment_id': assigned_form.id,
            'published_countries': 0,
            'totals': _empty_counts(),
            'pending_total': 0,
        }

    public_item_ids = _public_form_item_ids()
    totals = _empty_counts()
    # Only aes ids that actually own >=1 public FormData row get marked as
    # published below — an aes with zero rows in scope has nothing to publish,
    # regardless of whether it was explicitly selected.
    touched_aes_ids: Set[int] = set()

    if public_item_ids:
        scoped_rows = (
            FormData.query
            .filter(FormData.assignment_entity_status_id.in_(target_aes_ids))
            .filter(FormData.form_item_id.in_(public_item_ids))
        )
        now = utcnow()
        for row in scoped_rows.all():
            # Classify against the existing snapshot *before* overwriting it.
            totals[row.publication_diff_kind()] += 1
            touched_aes_ids.add(row.assignment_entity_status_id)
            src_value, src_disagg, src_numeric = row.publication_current_payload()
            row.published_value = src_value
            row.published_disagg_data = src_disagg
            row.published_numeric_value = src_numeric
            row.published_source = row.publication_source_kind()
            row.published_at = now
            row.published_by_user_id = user_id

        if touched_aes_ids:
            (
                AssignmentEntityStatus.query
                .filter(AssignmentEntityStatus.id.in_(touched_aes_ids))
                .update(
                    {
                        AssignmentEntityStatus.published_at: now,
                        AssignmentEntityStatus.published_by_user_id: user_id,
                    },
                    synchronize_session=False,
                )
            )

    db.session.commit()

    pending_total = sum(totals[kind] for kind in PENDING_DIFF_KINDS)
    return {
        'assignment_id': assigned_form.id,
        'published_countries': len(touched_aes_ids),
        'totals': totals,
        'pending_total': pending_total,
    }
