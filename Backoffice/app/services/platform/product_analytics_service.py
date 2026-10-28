"""
Product usage analytics for the admin dashboard (and ops reports).

First-party only: sessions, logins, activity log, assignment submissions.
No third-party product analytics (Amplitude/GA).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import distinct, func

from app import db
from app.models import (
    AssignmentEntityStatus,
    SubmittedDocument,
    User,
    UserActivityLog,
    UserEntityPermission,
    UserLoginLog,
    UserSessionLog,
)
from app.models.rbac import RbacRole, RbacUserRole
from app.utils.datetime_helpers import utcnow


SECRETARIAT_ENTITY_TYPES = frozenset({
    "division",
    "department",
    "regional_office",
    "cluster_office",
})
NS_ENTITY_TYPES = frozenset({
    "country",
    "ns_branch",
    "ns_subbranch",
    "ns_localunit",
})
SECRETARIAT_EMAIL_MARKERS = (
    "@ifrc.org",
    "@redcross.",
    "@croix-rouge.",
)
KEY_ACTIVITY_TYPES = frozenset({
    "form_submitted",
    "form_saved",
    "form_sent_for_review",
    "form_returned_for_revision",
    "form_approved",
    "form_reopened",
    "form_validated",
    "file_uploaded",
    "data_export",
    "data_modified",
    "data_deleted",
})
# Friendly labels for dashboard charts (stable keys → display)
KEY_ACTIVITY_LABELS = {
    "form_saved": "Forms saved",
    "form_submitted": "Forms submitted",
    "form_approved": "Forms approved",
    "form_reopened": "Forms reopened",
    "form_sent_for_review": "Sent for review",
    "form_returned_for_revision": "Returned for revision",
    "form_validated": "Forms validated",
    "file_uploaded": "Files uploaded",
    "data_export": "Data exports",
    "data_modified": "Data modified",
    "data_deleted": "Data deleted",
}
NS_SCOPED_COUNTRY_LIMIT = 5


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_workday(dt: datetime) -> bool:
    """Mon–Fri only (no org holiday calendar)."""
    return _as_utc(dt).weekday() < 5


def _workday_key(dt: datetime) -> Optional[str]:
    """YYYY-MM-DD for Mon–Fri timestamps; None on weekends."""
    dt = _as_utc(dt)
    if not _is_workday(dt):
        return None
    return dt.strftime("%Y-%m-%d")


def _count_workdays(start: datetime, end: datetime) -> int:
    """Count Mon–Fri calendar dates that overlap ``[start, end)``."""
    start = _as_utc(start)
    end = _as_utc(end)
    if end <= start:
        return 0
    count = 0
    cur: date = start.date()
    last: date = end.date()
    while cur <= last:
        day_start = datetime.combine(cur, time.min, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        if day_start < end and day_end > start and cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count


def _record_active_workday(
    active_days_by_user: Dict[int, Set[str]],
    uid: int,
    ts: Optional[datetime],
) -> None:
    if not ts:
        return
    key = _workday_key(ts)
    if key:
        active_days_by_user[uid].add(key)


def classify_user_type(
    email: Optional[str],
    entity_types: Set[str],
    role_codes: Set[str],
) -> str:
    """Heuristic primary user type from org entities + email + roles."""
    email_l = (email or "").lower()
    has_sec_entity = bool(entity_types & SECRETARIAT_ENTITY_TYPES)
    has_ns_entity = bool(entity_types & NS_ENTITY_TYPES)
    looks_secretariat_email = any(m in email_l for m in SECRETARIAT_EMAIL_MARKERS)
    looks_ifrc_email = "@ifrc.org" in email_l
    adminish = any(
        c.startswith("admin_") or c == "system_manager"
        for c in role_codes
    )
    assignment_only = bool(role_codes & {
        "assignment_viewer",
        "assignment_editor_submitter",
        "assignment_documents_uploader",
        "assignment_approver",
    }) and not adminish

    if has_sec_entity and not has_ns_entity:
        return "Secretariat staff"
    if has_ns_entity and not has_sec_entity:
        # IFRC/secretariat staff often have country scope only — don't call them NS.
        if looks_ifrc_email or looks_secretariat_email or adminish:
            return "Secretariat staff (mixed access)"
        return "National Society"
    if has_sec_entity and has_ns_entity:
        if looks_ifrc_email or looks_secretariat_email or adminish:
            return "Secretariat staff (mixed access)"
        return "National Society (mixed access)"
    if looks_ifrc_email or looks_secretariat_email or adminish:
        return "Secretariat staff"
    if assignment_only:
        return "National Society"
    return "Unclassified"


# Dashboard primary buckets: IFRC vs NS (Unclassified only when neither fits).
PRIMARY_USER_TYPE_ORDER = ("IFRC", "NS", "Unclassified")


def classify_ifrc_vs_ns(
    email: Optional[str],
    entity_types: Set[str],
    role_codes: Set[str],
) -> str:
    """
    Bucket MAU as IFRC vs National Society.

    IFRC wins when any strong Secretariat signal is present (even if the user
    also has country/NS entity permissions — common for IFRC country focal work):
    ``@ifrc.org``, secretariat org entities, or admin / system_manager roles.

    ``@redcross.`` / ``@croix-rouge.`` alone are *not* treated as IFRC here
    (those domains are often National Societies).
    """
    email_l = (email or "").lower()
    has_sec_entity = bool(entity_types & SECRETARIAT_ENTITY_TYPES)
    has_ns_entity = bool(entity_types & NS_ENTITY_TYPES)
    looks_ifrc_email = "@ifrc.org" in email_l
    adminish = any(
        c.startswith("admin_") or c == "system_manager"
        for c in role_codes
    )
    assignment_only = bool(role_codes & {
        "assignment_viewer",
        "assignment_editor_submitter",
        "assignment_documents_uploader",
        "assignment_approver",
    }) and not adminish

    if looks_ifrc_email or has_sec_entity or adminish:
        return "IFRC"
    if has_ns_entity or assignment_only:
        return "NS"
    return "Unclassified"


def to_ifrc_vs_ns(detail_type: str) -> str:
    """Map detailed classify_user_type() labels to IFRC / NS / Unclassified."""
    if detail_type in {
        "Secretariat staff",
        "Secretariat staff (mixed access)",
    }:
        return "IFRC"
    if detail_type in {
        "National Society",
        "National Society (mixed access)",
    }:
        return "NS"
    return "Unclassified"


def _frequency_thresholds(
    days: int,
    workdays: Optional[int] = None,
) -> Tuple[int, int, Tuple[str, str, str]]:
    """
    Return (daily_min, weekly_min, labels) scaled to workdays in the window.

    Active-day counts exclude weekends. "Daily" means active on most workdays
    (~3+ per week on average ≈ 15 of 22), not near-perfect attendance — so a
    normal leave day or travel week does not push a regular user into Weekly.
    """
    days = max(1, int(days or 30))
    if workdays is None:
        workdays = max(1, int(round(days * 5 / 7)))
    workdays = max(1, int(workdays))

    if days <= 7:
        # Near-daily: miss at most one workday in the short window
        daily = max(1, workdays - 1) if workdays > 1 else 1
        weekly = 2 if workdays >= 3 else 1
        if weekly >= daily:
            weekly = max(1, daily - 1) if daily > 1 else 1
        mid_hi = daily - 1
        mid_label = (
            f"Several days ({weekly}–{mid_hi})"
            if mid_hi > weekly
            else f"Several days ({weekly})"
        )
        low_label = (
            "Once (1 day)"
            if weekly <= 2
            else f"Occasional (1–{weekly - 1} workdays)"
        )
        return (
            daily,
            weekly,
            (f"Near-daily ({daily}+ workdays)", mid_label, low_label),
        )

    # ~22 workdays → daily=15 (~3 days/week), weekly=4
    daily = max(1, min(workdays, int(round(workdays * 15 / 22))))
    weekly = max(1, int(round(workdays * 4 / 22)))
    if weekly >= daily:
        weekly = max(1, daily - 1) if daily > 1 else 1

    low_hi = weekly - 1
    if days <= 30:
        low_label = (
            f"Monthly (1–{low_hi} workdays)"
            if low_hi >= 1
            else "Monthly (1 workday)"
        )
        return (
            daily,
            weekly,
            (
                f"Daily ({daily}+ workdays)",
                f"Weekly ({weekly}–{daily - 1} workdays)",
                low_label,
            ),
        )

    low_label = (
        f"Occasional (1–{low_hi} workdays)"
        if low_hi >= 1
        else "Occasional (1 workday)"
    )
    return (
        daily,
        weekly,
        (
            f"Frequent ({daily}+ workdays)",
            f"Regular ({weekly}–{daily - 1} workdays)",
            low_label,
        ),
    )


def _history_months_for_days(days: int) -> int:
    """How many calendar months of trend to show for the selected window."""
    days = max(1, int(days or 30))
    if days <= 30:
        return 6
    if days <= 90:
        return 6
    return 12


def _year_month_expr(column):
    """Dialect-safe YYYY-MM expression for grouping."""
    dialect = db.engine.dialect.name
    if dialect == "postgresql":
        return func.to_char(column, "YYYY-MM")
    if dialect == "sqlite":
        return func.strftime("%Y-%m", column)
    # MySQL / MariaDB
    return func.date_format(column, "%Y-%m")


def _active_user_id_sets_since(since: datetime) -> Tuple[Set[int], Set[int], Set[int]]:
    """Session / login / activity user-id sets with activity since ``since``."""
    session_ids = {
        r[0]
        for r in db.session.query(UserSessionLog.user_id)
        .filter(UserSessionLog.last_activity >= since)
        .distinct()
        .all()
    }
    login_ids = {
        r[0]
        for r in db.session.query(UserLoginLog.user_id)
        .filter(
            UserLoginLog.timestamp >= since,
            UserLoginLog.event_type == "login_success",
            UserLoginLog.user_id.isnot(None),
        )
        .distinct()
        .all()
    }
    activity_ids = {
        r[0]
        for r in db.session.query(UserActivityLog.user_id)
        .filter(UserActivityLog.timestamp >= since)
        .distinct()
        .all()
    }
    return session_ids, login_ids, activity_ids


def _active_user_ids_since(since: datetime) -> Set[int]:
    """Unique users with a session, successful login, or activity log since ``since``."""
    session_ids, login_ids, activity_ids = _active_user_id_sets_since(since)
    return session_ids | login_ids | activity_ids


def get_product_analytics(days: int = 30) -> Dict[str, Any]:
    """
    Aggregate product-usage metrics for the admin analytics dashboard.

    ``days`` is the MAU / activity window (same control as the rest of the
    dashboard). Monthly trend length is derived from that window.
    """
    days = max(1, min(int(days or 30), 730))
    months = _history_months_for_days(days)
    now = _as_utc(utcnow())
    mau_since = now - timedelta(days=days)
    history_since = (now - timedelta(days=max(months, 1) * 31)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    # Classic active-user windows (fixed lookbacks; independent of the filter)
    dau_ids = _active_user_ids_since(now - timedelta(days=1))
    wau_ids = _active_user_ids_since(now - timedelta(days=7))
    mau_30d_ids = _active_user_ids_since(now - timedelta(days=30))

    session_active_ids, login_active_ids, activity_active_ids = _active_user_id_sets_since(
        mau_since
    )
    mau_ids = session_active_ids | login_active_ids | activity_active_ids

    active_users = (
        User.query.filter(User.id.in_(mau_ids)).all() if mau_ids else []
    )

    entity_rows = (
        db.session.query(
            UserEntityPermission.user_id,
            UserEntityPermission.entity_type,
            UserEntityPermission.entity_id,
        )
        .filter(UserEntityPermission.user_id.in_(mau_ids))
        .all()
        if mau_ids
        else []
    )
    entities_by_user: Dict[int, Set[str]] = defaultdict(set)
    country_ids_by_user: Dict[int, Set[int]] = defaultdict(set)
    for uid, etype, eid in entity_rows:
        entities_by_user[uid].add(etype)
        if etype == "country":
            country_ids_by_user[uid].add(eid)

    has_role_kind = hasattr(RbacRole, "kind")
    roles_by_user: Dict[int, Set[str]] = defaultdict(set)
    groups_by_user: Dict[int, Set[str]] = defaultdict(set)
    if mau_ids:
        if has_role_kind:
            role_rows = (
                db.session.query(
                    RbacUserRole.user_id,
                    RbacRole.code,
                    RbacRole.name,
                    RbacRole.kind,
                )
                .join(RbacRole, RbacRole.id == RbacUserRole.role_id)
                .filter(RbacUserRole.user_id.in_(mau_ids))
                .all()
            )
            for uid, code, name, kind in role_rows:
                if kind == "group":
                    groups_by_user[uid].add(name or code)
                else:
                    roles_by_user[uid].add(code)
        else:
            role_rows = (
                db.session.query(RbacUserRole.user_id, RbacRole.code)
                .join(RbacRole, RbacRole.id == RbacUserRole.role_id)
                .filter(RbacUserRole.user_id.in_(mau_ids))
                .all()
            )
            for uid, code in role_rows:
                roles_by_user[uid].add(code)

    user_type_detail_counts: Counter = Counter()
    user_type_counts: Counter = Counter({k: 0 for k in PRIMARY_USER_TYPE_ORDER})
    segment_counts: Counter = Counter()
    email_ifrc = 0
    email_other = 0
    domain_counts: Counter = Counter()
    ns_scoped_countries: Set[int] = set()
    ns_scoped_users = 0
    broad_users = 0

    for u in active_users:
        ents = entities_by_user.get(u.id, set())
        roles = roles_by_user.get(u.id, set())
        detail = classify_user_type(u.email, ents, roles)
        user_type_detail_counts[detail] += 1
        user_type_counts[classify_ifrc_vs_ns(u.email, ents, roles)] += 1
        segs = groups_by_user.get(u.id) or set()
        if segs:
            for s in segs:
                segment_counts[s] += 1
        elif has_role_kind:
            segment_counts["(no Access Group)"] += 1

        email_l = (u.email or "").lower()
        dom = email_l.split("@")[-1] if "@" in email_l else "?"
        domain_counts[dom] += 1
        if dom == "ifrc.org":
            email_ifrc += 1
        else:
            email_other += 1

        ets = entities_by_user.get(u.id, set())
        cids = country_ids_by_user.get(u.id, set())
        if ets & SECRETARIAT_ENTITY_TYPES:
            continue
        if not cids:
            continue
        if len(cids) <= NS_SCOPED_COUNTRY_LIMIT:
            ns_scoped_users += 1
            ns_scoped_countries |= cids
        else:
            broad_users += 1

    # Frequency buckets (Mon–Fri active days only)
    workdays_in_window = _count_workdays(mau_since, now)
    daily_min, weekly_min, freq_labels = _frequency_thresholds(
        days, workdays=workdays_in_window
    )
    active_days_by_user: Dict[int, Set[str]] = defaultdict(set)
    if mau_ids:
        for uid, ts in (
            db.session.query(UserSessionLog.user_id, UserSessionLog.last_activity)
            .filter(
                UserSessionLog.user_id.in_(mau_ids),
                UserSessionLog.last_activity >= mau_since,
            )
            .all()
        ):
            _record_active_workday(active_days_by_user, uid, ts)
        for uid, ts in (
            db.session.query(UserLoginLog.user_id, UserLoginLog.timestamp)
            .filter(
                UserLoginLog.user_id.in_(mau_ids),
                UserLoginLog.timestamp >= mau_since,
                UserLoginLog.event_type == "login_success",
            )
            .all()
        ):
            _record_active_workday(active_days_by_user, uid, ts)
        for uid, ts in (
            db.session.query(UserActivityLog.user_id, UserActivityLog.timestamp)
            .filter(
                UserActivityLog.user_id.in_(mau_ids),
                UserActivityLog.timestamp >= mau_since,
            )
            .all()
        ):
            _record_active_workday(active_days_by_user, uid, ts)

    freq_buckets = [
        {"label": freq_labels[0], "count": 0, "key": "frequent"},
        {"label": freq_labels[1], "count": 0, "key": "regular"},
        {"label": freq_labels[2], "count": 0, "key": "occasional"},
    ]
    for uid in mau_ids:
        n = len(active_days_by_user.get(uid, set()))
        if n >= daily_min:
            freq_buckets[0]["count"] += 1
        elif n >= weekly_min:
            freq_buckets[1]["count"] += 1
        else:
            freq_buckets[2]["count"] += 1

    session_stats = (
        db.session.query(
            func.count(UserSessionLog.id),
            func.coalesce(func.sum(UserSessionLog.page_views), 0),
            func.coalesce(func.sum(UserSessionLog.actions_performed), 0),
            func.coalesce(func.sum(UserSessionLog.forms_submitted), 0),
            func.coalesce(func.sum(UserSessionLog.files_uploaded), 0),
            func.avg(UserSessionLog.duration_minutes),
        )
        .filter(UserSessionLog.session_start >= mau_since)
        .one()
    )

    key_activity_rows = (
        db.session.query(
            UserActivityLog.activity_type,
            func.count(UserActivityLog.id),
        )
        .filter(
            UserActivityLog.timestamp >= mau_since,
            UserActivityLog.activity_type.in_(list(KEY_ACTIVITY_TYPES)),
        )
        .group_by(UserActivityLog.activity_type)
        .all()
    )
    key_activities = sorted(
        [
            {
                "type": t,
                "label": KEY_ACTIVITY_LABELS.get(t, t.replace("_", " ").title()),
                "count": int(c),
            }
            for t, c in key_activity_rows
        ],
        key=lambda x: -x["count"],
    )

    device_rows = (
        db.session.query(
            UserSessionLog.device_type,
            func.count(UserSessionLog.id),
        )
        .filter(UserSessionLog.session_start >= mau_since)
        .group_by(UserSessionLog.device_type)
        .all()
    )
    device_breakdown = sorted(
        [{"device": (d or "Unknown"), "count": int(c)} for d, c in device_rows],
        key=lambda x: -x["count"],
    )

    reports_submitted = (
        db.session.query(func.count(AssignmentEntityStatus.id))
        .filter(
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.submitted_at.isnot(None),
            AssignmentEntityStatus.submitted_at >= mau_since,
        )
        .scalar()
        or 0
    )
    countries_submitted = (
        db.session.query(func.count(distinct(AssignmentEntityStatus.entity_id)))
        .filter(
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.submitted_at.isnot(None),
            AssignmentEntityStatus.submitted_at >= mau_since,
        )
        .scalar()
        or 0
    )
    documents_uploaded = (
        db.session.query(func.count(SubmittedDocument.id))
        .filter(SubmittedDocument.uploaded_at >= mau_since)
        .scalar()
        or 0
    )

    # Monthly trend
    monthly: Dict[str, Dict[str, Any]] = {}
    sess_ym = _year_month_expr(UserSessionLog.last_activity)
    for ym, cnt in (
        db.session.query(
            sess_ym.label("ym"),
            func.count(distinct(UserSessionLog.user_id)),
        )
        .filter(UserSessionLog.last_activity >= history_since)
        .group_by("ym")
        .order_by("ym")
        .all()
    ):
        monthly.setdefault(ym, {})["mau"] = int(cnt)

    login_ym = _year_month_expr(UserLoginLog.timestamp)
    for ym, cnt in (
        db.session.query(
            login_ym.label("ym"),
            func.count(distinct(UserLoginLog.user_id)),
        )
        .filter(
            UserLoginLog.timestamp >= history_since,
            UserLoginLog.event_type == "login_success",
            UserLoginLog.user_id.isnot(None),
        )
        .group_by("ym")
        .order_by("ym")
        .all()
    ):
        bucket = monthly.setdefault(ym, {})
        # Prefer the larger of session/login unique users as MAU proxy
        bucket["mau"] = max(int(bucket.get("mau") or 0), int(cnt))

    start_ym = _year_month_expr(UserSessionLog.session_start)
    for ym, sess, pages, actions in (
        db.session.query(
            start_ym.label("ym"),
            func.count(UserSessionLog.id),
            func.coalesce(func.sum(UserSessionLog.page_views), 0),
            func.coalesce(func.sum(UserSessionLog.actions_performed), 0),
        )
        .filter(UserSessionLog.session_start >= history_since)
        .group_by("ym")
        .order_by("ym")
        .all()
    ):
        bucket = monthly.setdefault(ym, {})
        bucket["sessions"] = int(sess)
        bucket["page_views"] = int(pages)
        bucket["actions"] = int(actions)

    aes_ym = _year_month_expr(AssignmentEntityStatus.submitted_at)
    for ym, cnt, entities in (
        db.session.query(
            aes_ym.label("ym"),
            func.count(AssignmentEntityStatus.id),
            func.count(distinct(AssignmentEntityStatus.entity_id)),
        )
        .filter(
            AssignmentEntityStatus.submitted_at.isnot(None),
            AssignmentEntityStatus.submitted_at >= history_since,
            AssignmentEntityStatus.entity_type == "country",
        )
        .group_by("ym")
        .order_by("ym")
        .all()
    ):
        bucket = monthly.setdefault(ym, {})
        bucket["reports_submitted"] = int(cnt)
        bucket["countries_submitted"] = int(entities)

    doc_ym = _year_month_expr(SubmittedDocument.uploaded_at)
    for ym, cnt in (
        db.session.query(
            doc_ym.label("ym"),
            func.count(SubmittedDocument.id),
        )
        .filter(SubmittedDocument.uploaded_at >= history_since)
        .group_by("ym")
        .order_by("ym")
        .all()
    ):
        monthly.setdefault(ym, {})["documents_uploaded"] = int(cnt)

    monthly_series = []
    for ym in sorted(monthly.keys()):
        b = monthly[ym]
        monthly_series.append({
            "month": ym,
            "mau": int(b.get("mau") or 0),
            "sessions": int(b.get("sessions") or 0),
            "page_views": int(b.get("page_views") or 0),
            "actions": int(b.get("actions") or 0),
            "reports_submitted": int(b.get("reports_submitted") or 0),
            "countries_submitted": int(b.get("countries_submitted") or 0),
            "documents_uploaded": int(b.get("documents_uploaded") or 0),
        })

    role_mau_counts: Counter = Counter()
    for uid in mau_ids:
        for code in roles_by_user.get(uid, set()):
            role_mau_counts[code] += 1

    total_users = db.session.query(func.count(User.id)).scalar() or 0
    active_accounts = (
        db.session.query(func.count(User.id)).filter(User.active.is_(True)).scalar() or 0
    )

    # Primary chart: IFRC vs NS (stable order); detail kept for ops/debug
    user_types = [
        {"type": label, "count": int(user_type_counts.get(label, 0))}
        for label in PRIMARY_USER_TYPE_ORDER
        if user_type_counts.get(label, 0) or label in ("IFRC", "NS")
    ]
    user_type_details = sorted(
        [{"type": k, "count": v} for k, v in user_type_detail_counts.items()],
        key=lambda x: -x["count"],
    )
    segments = [
        {"name": k, "count": v}
        for k, v in segment_counts.most_common(20)
    ]
    top_domains = [
        {"domain": d, "count": c}
        for d, c in domain_counts.most_common(10)
    ]
    top_roles = [
        {"code": code, "count": n}
        for code, n in role_mau_counts.most_common(10)
    ]

    return {
        "window_days": days,
        "history_months": months,
        "mau_since": mau_since.isoformat(),
        "generated_at": now.isoformat(),
        "accounts": {
            "total_registered": int(total_users),
            "active_flag_true": int(active_accounts),
        },
        "mau": {
            "unique_users": len(mau_ids),
            "from_sessions": len(session_active_ids),
            "from_logins": len(login_active_ids),
            "from_activity_log": len(activity_active_ids),
        },
        "active_users": {
            "dau": len(dau_ids),
            "wau": len(wau_ids),
            "mau_30d": len(mau_30d_ids),
            "labels": ["DAU (1 day)", "WAU (7 days)", "MAU (30 days)"],
            "counts": [len(dau_ids), len(wau_ids), len(mau_30d_ids)],
            "stickiness_dau_mau": (
                round(len(dau_ids) / len(mau_30d_ids), 3) if mau_30d_ids else None
            ),
            "stickiness_wau_mau": (
                round(len(wau_ids) / len(mau_30d_ids), 3) if mau_30d_ids else None
            ),
        },
        "frequency": {
            "buckets": freq_buckets,
            "labels": [b["label"] for b in freq_buckets],
            "counts": [b["count"] for b in freq_buckets],
            "workdays_in_window": workdays_in_window,
            "excludes_weekends": True,
        },
        "user_types": {
            "rows": user_types,
            "labels": [r["type"] for r in user_types],
            "counts": [r["count"] for r in user_types],
            "detail_rows": user_type_details,
            "email_ifrc_org": email_ifrc,
            "email_other": email_other,
            "top_domains": top_domains,
            "top_roles": top_roles,
        },
        "segmentation": {
            "available": has_role_kind,
            "rows": segments,
            "labels": [r["name"] for r in segments],
            "counts": [r["count"] for r in segments],
        },
        "geographic": {
            "countries_ns_scoped": len(ns_scoped_countries),
            "ns_scoped_users": ns_scoped_users,
            "broad_access_users": broad_users,
            "countries_submitted": int(countries_submitted),
            "reports_submitted": int(reports_submitted),
            "documents_uploaded": int(documents_uploaded),
        },
        "sessions": {
            "count": int(session_stats[0] or 0),
            "page_views": int(session_stats[1] or 0),
            "actions_performed": int(session_stats[2] or 0),
            "forms_submitted_counter": int(session_stats[3] or 0),
            "files_uploaded_counter": int(session_stats[4] or 0),
            "avg_duration_minutes": (
                round(float(session_stats[5]), 1)
                if session_stats[5] is not None
                else None
            ),
            "devices": device_breakdown,
        },
        "key_activities": {
            "rows": key_activities,
            "labels": [r["label"] for r in key_activities],
            "counts": [r["count"] for r in key_activities],
        },
        "monthly": {
            "series": monthly_series,
            "labels": [m["month"] for m in monthly_series],
            "mau": [m["mau"] for m in monthly_series],
            "reports_submitted": [m["reports_submitted"] for m in monthly_series],
            "sessions": [m["sessions"] for m in monthly_series],
            "documents_uploaded": [m["documents_uploaded"] for m in monthly_series],
        },
    }
