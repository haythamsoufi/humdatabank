"""Country access request helpers."""

from __future__ import annotations

from sqlalchemy import and_, exists
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import CountryAccessRequest, UserEntityPermission
from app.models.enums import CountryAccessRequestStatusValue, EntityType
from app.services.user_analytics_service import log_admin_action
from app.utils.datetime_helpers import utcnow

AUTO_RESOLVED_ADMIN_NOTE = (
    "Access already granted outside the request workflow."
)


def _existing_country_permission_exists():
    """Correlated EXISTS: user already has country entity permission."""
    return exists().where(
        and_(
            UserEntityPermission.user_id == CountryAccessRequest.user_id,
            UserEntityPermission.entity_type == EntityType.country.value,
            UserEntityPermission.entity_id == CountryAccessRequest.country_id,
        )
    )


def pending_country_access_requests_query():
    """Pending requests where the user still lacks direct country access."""
    return (
        CountryAccessRequest.query.filter(
            CountryAccessRequest.status == CountryAccessRequestStatusValue.pending.value
        ).filter(~_existing_country_permission_exists())
    )


def count_pending_country_access_requests_needing_action() -> int:
    return int(pending_country_access_requests_query().count() or 0)


def is_auto_resolved_country_access_request(req: CountryAccessRequest) -> bool:
    return (req.admin_notes or "").strip() == AUTO_RESOLVED_ADMIN_NOTE


def processed_country_access_requests_query():
    """Approved/rejected requests for the admin processed list."""
    return CountryAccessRequest.query.filter(
        CountryAccessRequest.status.in_(
            [
                CountryAccessRequestStatusValue.approved.value,
                CountryAccessRequestStatusValue.rejected.value,
            ]
        )
    )


def reconcile_fulfilled_pending_country_access_requests(
    *,
    user_id: int | None = None,
    processed_by_user_id: int | None = None,
    country_ids: list[int] | None = None,
    log_actions: bool = False,
) -> int:
    """
    Mark pending requests as approved when the user already has country access.

    Returns the number of requests auto-resolved.
    """
    pending_q = CountryAccessRequest.query.filter(
        CountryAccessRequest.status == CountryAccessRequestStatusValue.pending.value
    ).filter(_existing_country_permission_exists())

    if user_id is not None:
        pending_q = pending_q.filter(CountryAccessRequest.user_id == user_id)
    if country_ids:
        pending_q = pending_q.filter(CountryAccessRequest.country_id.in_(country_ids))

    requests_to_close = pending_q.all()
    if not requests_to_close:
        return 0

    now = utcnow()
    for req in requests_to_close:
        req.status = CountryAccessRequestStatusValue.approved.value
        req.processed_at = now
        if processed_by_user_id is not None:
            req.processed_by_user_id = processed_by_user_id
        req.admin_notes = AUTO_RESOLVED_ADMIN_NOTE

        if log_actions:
            user = req.user
            country = req.country
            try:
                log_admin_action(
                    action_type="access_request_auto_resolve",
                    description=(
                        f"Auto-closed pending country access request for "
                        f"{user.email if user else 'unknown'} to "
                        f"{country.name if country else 'unknown'} "
                        f"(access already granted directly)"
                    ),
                    target_type="country_access_request",
                    target_id=req.id,
                    target_description=(
                        f"User: {user.email if user else 'unknown'}, "
                        f"Country: {country.name if country else 'unknown'}"
                    ),
                    new_values={
                        "user_id": req.user_id,
                        "user_email": user.email if user else None,
                        "country_id": req.country_id,
                        "country_name": country.name if country else None,
                        "status": CountryAccessRequestStatusValue.approved.value,
                        "auto_resolved": True,
                    },
                    risk_level="low",
                )
            except Exception:
                pass

    db.session.flush()
    return len(requests_to_close)


def pending_country_access_requests_by_fds_member() -> dict[int, list[CountryAccessRequest]]:
    """
    Group pending access requests by the country's assigned FDS member.

    Requests for countries without an FDS member are omitted.
    """
    pending = (
        pending_country_access_requests_query()
        .options(
            joinedload(CountryAccessRequest.user),
            joinedload(CountryAccessRequest.country),
        )
        .order_by(CountryAccessRequest.created_at.asc())
        .all()
    )
    grouped: dict[int, list[CountryAccessRequest]] = {}
    for req in pending:
        country = req.country
        fds_user_id = country.fds_member_user_id if country else None
        if not fds_user_id:
            continue
        grouped.setdefault(int(fds_user_id), []).append(req)
    return grouped


FDS_ACCESS_REQUEST_DIGEST_SUBJECT_PREFIX = "Country Access Requests - "
