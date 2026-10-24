"""Ensure FDRS AssignedForm + country AES rows exist before KPI/document sync.

The FDRS import maps API rows onto ``assignment_entity_status`` by
``(period_name, iso3)``. Years that were never opened in the Backoffice
(or countries missing from an existing year) would otherwise be skipped.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

logger = logging.getLogger(__name__)


def years_from_fdrs_data(fdrs_data: Iterable[Dict[str, Any]]) -> List[int]:
    """Distinct reporting years present in prepared FDRS Data rows."""
    years: Set[int] = set()
    for row in fdrs_data or []:
        raw = row.get("year")
        if raw is None or str(raw).strip() == "":
            continue
        try:
            years.add(int(str(raw).strip()[:4]))
        except (TypeError, ValueError):
            continue
    return sorted(years)


def plan_missing_fdrs_assignments(
    *,
    years: Sequence[int],
    country_iso3_to_id: Dict[str, int],
    existing_period_names: Set[str],
    existing_period_iso3: Set[Tuple[str, str]],
) -> Dict[str, Any]:
    """Pure plan of AssignedForm periods and AES pairs still needed.

    Returns::

        {
          "periods_to_create": ["2018", ...],
          "aes_to_create": [{"period_name": "2018", "iso3": "KEN", "country_id": 12}, ...],
          "target_pairs": 190,
        }
    """
    periods = [str(int(y)) for y in years]
    periods_to_create = [p for p in periods if p not in existing_period_names]

    aes_to_create: List[Dict[str, Any]] = []
    for period in periods:
        for iso3, country_id in sorted(country_iso3_to_id.items()):
            iso = (iso3 or "").strip().upper()
            if not iso or country_id is None:
                continue
            if (period, iso) in existing_period_iso3:
                continue
            aes_to_create.append(
                {
                    "period_name": period,
                    "iso3": iso,
                    "country_id": int(country_id),
                }
            )

    return {
        "periods_to_create": periods_to_create,
        "aes_to_create": aes_to_create,
        "target_pairs": len(periods) * len(country_iso3_to_id),
    }


def _reference_fdrs_assignment(template_id: int):
    """Most recent existing FDRS assignment to copy feature flags from."""
    from app.models.assignments import AssignedForm

    return (
        AssignedForm.query.filter_by(template_id=int(template_id))
        .order_by(AssignedForm.period_name.desc(), AssignedForm.id.desc())
        .first()
    )


def _ensure_annual_reporting_period(period_name: str) -> None:
    """Create/update catalog row for a calendar year label when missing."""
    from app.services.forms.reporting_period_service import (
        get_reporting_period,
        upsert_reporting_period,
    )
    from app.utils.reporting_period_label_parser import parse_period_label

    name = (period_name or "").strip()
    if not name or get_reporting_period(name) is not None:
        return
    parsed = parse_period_label(name)
    if parsed is not None:
        period_type, period_start, period_end = parsed
        upsert_reporting_period(
            name,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
        )
        return
    try:
        year = int(name)
    except (TypeError, ValueError):
        return
    upsert_reporting_period(
        name,
        period_type="annual",
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
    )


def ensure_fdrs_assignments_for_sync(
    *,
    template_id: int = 21,
    years: Optional[Sequence[int]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Create missing FDRS year assignments and country AES rows.

    For each year: ensure one ``AssignedForm`` (period_name = ``YYYY``) with
    ``enable_page_submission`` on, and one ``AssignmentEntityStatus`` per country
    that has an ISO3 code. Caller should reload assignment rows afterwards.

    Returns a stats dict (``periods_created``, ``aes_created``, …).
    """
    from app.extensions import db
    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.core import Country
    from app.models.enums import AssignmentEntityStatusValue, EntityType
    from app.services.assignments.page_submission_service import apply_page_submission_mode_change
    from app.services.forms.reporting_period_service import sync_assigned_form_reporting_period

    year_list = sorted({int(y) for y in (years or [])})
    stats: Dict[str, Any] = {
        "years_requested": year_list,
        "periods_created": 0,
        "aes_created": 0,
        "page_modes_enabled": 0,
        "dry_run": bool(dry_run),
        "skipped_no_years": False,
        "periods_to_create": [],
        "aes_to_create": 0,
        "countries_considered": 0,
    }
    if not year_list:
        stats["skipped_no_years"] = True
        return stats

    country_iso3_to_id: Dict[str, int] = {}
    for country_id, iso3 in (
        db.session.query(Country.id, Country.iso3)
        .filter(Country.iso3.isnot(None))
        .all()
    ):
        iso = (iso3 or "").strip().upper()
        if iso and len(iso) == 3:
            country_iso3_to_id[iso] = int(country_id)

    existing_forms = (
        AssignedForm.query.filter_by(template_id=int(template_id)).all()
    )
    existing_period_names = {
        (af.period_name or "").strip() for af in existing_forms if (af.period_name or "").strip()
    }
    form_by_period: Dict[str, AssignedForm] = {}
    for af in existing_forms:
        pn = (af.period_name or "").strip()
        if pn and pn not in form_by_period:
            form_by_period[pn] = af

    existing_period_iso3: Set[Tuple[str, str]] = set()
    for period_name, iso3_raw in (
        db.session.query(AssignedForm.period_name, Country.iso3)
        .join(AssignmentEntityStatus, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .join(Country, Country.id == AssignmentEntityStatus.entity_id)
        .filter(
            AssignedForm.template_id == int(template_id),
            AssignmentEntityStatus.entity_type == EntityType.country.value,
        )
        .all()
    ):
        pn = (period_name or "").strip()
        iso = (iso3_raw or "").strip().upper()
        if pn and iso:
            existing_period_iso3.add((pn, iso))

    plan = plan_missing_fdrs_assignments(
        years=year_list,
        country_iso3_to_id=country_iso3_to_id,
        existing_period_names=existing_period_names,
        existing_period_iso3=existing_period_iso3,
    )
    stats["periods_to_create"] = list(plan["periods_to_create"])
    stats["aes_to_create"] = len(plan["aes_to_create"])
    stats["countries_considered"] = len(country_iso3_to_id)

    if dry_run:
        logger.info(
            "FDRS assignment ensure dry-run: periods=%s aes=%s countries=%s years=%s",
            plan["periods_to_create"],
            len(plan["aes_to_create"]),
            len(country_iso3_to_id),
            year_list,
        )
        return stats

    if not plan["periods_to_create"] and not plan["aes_to_create"]:
        logger.info("FDRS assignment ensure: nothing missing for years %s", year_list)
        return stats

    reference = _reference_fdrs_assignment(int(template_id))
    forms_needing_page_seed: List[AssignedForm] = []
    for period_name in plan["periods_to_create"]:
        _ensure_annual_reporting_period(period_name)
        af = AssignedForm(
            template_id=int(template_id),
            period_name=period_name,
            is_active=True,
            is_closed=False,
            enable_page_submission=True,
            enable_export_excel=bool(getattr(reference, "enable_export_excel", True)),
            enable_import_excel=bool(getattr(reference, "enable_import_excel", True)),
            enable_export_pdf=bool(getattr(reference, "enable_export_pdf", False)),
            data_owner_id=getattr(reference, "data_owner_id", None),
            requires_delegation_review=bool(
                getattr(reference, "requires_delegation_review", False)
            ),
        )
        if reference is not None and getattr(reference, "allowed_roles", None) is not None:
            try:
                af.allowed_roles = list(reference.allowed_roles)
            except Exception:
                logger.debug("Could not copy allowed_roles onto new FDRS assignment %s", period_name)
        db.session.add(af)
        db.session.flush()
        sync_assigned_form_reporting_period(af)
        form_by_period[period_name] = af
        forms_needing_page_seed.append(af)
        stats["periods_created"] += 1
        logger.info("Created FDRS AssignedForm period=%s id=%s", period_name, af.id)

    # Turn on page submission for pre-existing target-year forms that lack it.
    for period_name in [str(int(y)) for y in year_list]:
        af = form_by_period.get(period_name)
        if af is None:
            af = (
                AssignedForm.query.filter_by(
                    template_id=int(template_id),
                    period_name=period_name,
                )
                .order_by(AssignedForm.id.asc())
                .first()
            )
            if af is not None:
                form_by_period[period_name] = af
        if af is None:
            continue
        if not af.enable_page_submission:
            af.enable_page_submission = True
            forms_needing_page_seed.append(af)
            stats["page_modes_enabled"] += 1

    for item in plan["aes_to_create"]:
        period_name = item["period_name"]
        af = form_by_period.get(period_name)
        if af is None:
            af = (
                AssignedForm.query.filter_by(
                    template_id=int(template_id),
                    period_name=period_name,
                )
                .order_by(AssignedForm.id.asc())
                .first()
            )
            if af is not None:
                form_by_period[period_name] = af
        if af is None:
            logger.warning(
                "FDRS assignment ensure: no AssignedForm for period=%s; skip AES iso3=%s",
                period_name,
                item["iso3"],
            )
            continue
        aes = AssignmentEntityStatus(
            assigned_form_id=af.id,
            entity_type=EntityType.country.value,
            entity_id=int(item["country_id"]),
            status=AssignmentEntityStatusValue.pending,
        )
        db.session.add(aes)
        stats["aes_created"] += 1

    db.session.flush()

    # Seed page-status rows after AES exist (same path as the assignment editor).
    seen_form_ids: Set[int] = set()
    for af in forms_needing_page_seed:
        if int(af.id) in seen_form_ids:
            continue
        seen_form_ids.add(int(af.id))
        apply_page_submission_mode_change(af, True, None)
    if plan["aes_to_create"]:
        for period_name in [str(int(y)) for y in year_list]:
            af = form_by_period.get(period_name)
            if af is None or int(af.id) in seen_form_ids:
                continue
            if af.enable_page_submission:
                apply_page_submission_mode_change(af, True, None)
                seen_form_ids.add(int(af.id))

    db.session.commit()
    logger.info(
        "FDRS assignment ensure complete: periods_created=%s aes_created=%s page_modes_enabled=%s years=%s",
        stats["periods_created"],
        stats["aes_created"],
        stats["page_modes_enabled"],
        year_list,
    )
    return stats
