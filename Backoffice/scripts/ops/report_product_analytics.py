#!/usr/bin/env python3
"""Read-only product analytics report for local DB or Azure SSH.

Metrics align with IFRC product-analytics asks:
  MAU, frequency of use, primary user types, segmentation,
  geographic reach, key activities/transactions per month.

Examples::

  cd Backoffice && python scripts/ops/report_product_analytics.py
  azure_webapp_tools.bat prod script ops/report_product_analytics.py
  ... -RemoteArgs "--months 6 --json"
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def _ensure_app_importable() -> None:
    app_root = Path("/app")
    if (app_root / "run.py").is_file() and (app_root / "app").is_dir():
        if str(app_root) not in sys.path:
            sys.path.insert(0, str(app_root))
        return
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from _bootstrap import setup_cli_paths

    setup_cli_paths(__file__)


_ensure_app_importable()


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

# Meaningful transaction activity types for "key activities"
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


def iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


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
        return "National Society"
    if has_sec_entity and has_ns_entity:
        # Mixed access — prefer secretariat if email/admin suggests HQ
        if looks_secretariat_email or adminish:
            return "Secretariat staff (mixed access)"
        return "National Society (mixed access)"
    if looks_secretariat_email or adminish:
        return "Secretariat staff"
    if assignment_only:
        return "National Society"
    return "Unclassified"


def build_report(months: int, days_mau: int = 30) -> Dict[str, Any]:
    from sqlalchemy import func, distinct
    from app import db
    from app.models import (
        User,
        UserActivityLog,
        UserSessionLog,
        UserLoginLog,
        UserEntityPermission,
        Country,
        NationalSociety,
        AssignmentEntityStatus,
        SubmittedDocument,
    )
    from app.models.rbac import RbacRole, RbacUserRole
    from app.utils.datetime_helpers import utcnow

    # Prod images may predate ROLE_KIND_GROUP; kind column is still 'group'|'permission'.
    role_kind_group = "group"

    now = utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    mau_since = now - timedelta(days=days_mau)
    history_since = now - timedelta(days=max(months, 1) * 31)
    # Align history window to start of month for cleaner month buckets
    history_since = history_since.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # --- Active user sets from sessions / logins / activity ---
    session_active_ids = {
        r[0]
        for r in db.session.query(UserSessionLog.user_id)
        .filter(UserSessionLog.last_activity >= mau_since)
        .distinct()
        .all()
    }
    login_active_ids = {
        r[0]
        for r in db.session.query(UserLoginLog.user_id)
        .filter(
            UserLoginLog.timestamp >= mau_since,
            UserLoginLog.event_type == "login_success",
            UserLoginLog.user_id.isnot(None),
        )
        .distinct()
        .all()
    }
    activity_active_ids = {
        r[0]
        for r in db.session.query(UserActivityLog.user_id)
        .filter(UserActivityLog.timestamp >= mau_since)
        .distinct()
        .all()
    }
    mau_ids = session_active_ids | login_active_ids | activity_active_ids

    # Exclude obvious non-human / system emails if present
    active_users = (
        User.query.filter(User.id.in_(mau_ids)).all()
        if mau_ids
        else []
    )

    # Entity permissions for active users
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

    # Roles (permission + group) for active users.
    # Prod may predate RbacRole.kind (Access Groups); detect via mapper.
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
                if kind == role_kind_group:
                    groups_by_user[uid].add(name or code)
                else:
                    roles_by_user[uid].add(code)
        else:
            role_rows = (
                db.session.query(
                    RbacUserRole.user_id,
                    RbacRole.code,
                    RbacRole.name,
                )
                .join(RbacRole, RbacRole.id == RbacUserRole.role_id)
                .filter(RbacUserRole.user_id.in_(mau_ids))
                .all()
            )
            for uid, code, _name in role_rows:
                roles_by_user[uid].add(code)

    from app.services.platform.product_analytics_service import (
        PRIMARY_USER_TYPE_ORDER,
        _count_workdays,
        _frequency_thresholds,
        _record_active_workday,
        classify_ifrc_vs_ns,
    )

    user_type_detail_counts: Counter = Counter()
    user_type_counts: Counter = Counter({k: 0 for k in PRIMARY_USER_TYPE_ORDER})
    user_type_examples: Dict[str, List[str]] = defaultdict(list)
    segment_counts: Counter = Counter()
    mau_country_ids: Set[int] = set()

    for u in active_users:
        ents = entities_by_user.get(u.id, set())
        roles = roles_by_user.get(u.id, set())
        detail = classify_user_type(u.email, ents, roles)
        primary = classify_ifrc_vs_ns(u.email, ents, roles)
        user_type_detail_counts[detail] += 1
        user_type_counts[primary] += 1
        if len(user_type_examples[primary]) < 5:
            user_type_examples[primary].append(u.email)
        segs = groups_by_user.get(u.id) or set()
        if segs:
            for s in segs:
                segment_counts[s] += 1
        else:
            segment_counts["(no Access Group)"] += 1
        mau_country_ids.update(country_ids_by_user.get(u.id, set()))

    # Geographic reach: countries linked to MAU users + NS names
    countries = (
        Country.query.filter(Country.id.in_(mau_country_ids)).all()
        if mau_country_ids
        else []
    )
    ns_by_country = {}
    if mau_country_ids:
        for ns in NationalSociety.query.filter(
            NationalSociety.country_id.in_(mau_country_ids)
        ).all():
            ns_by_country[ns.country_id] = ns.name

    # Frequency: Mon–Fri active days only (aligned with product_analytics_service)
    workdays_in_window = _count_workdays(mau_since, now)
    daily_min, weekly_min, freq_labels = _frequency_thresholds(
        days_mau, workdays=workdays_in_window
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

    freq_buckets = Counter({label: 0 for label in freq_labels})
    for uid in mau_ids:
        n = len(active_days_by_user.get(uid, set()))
        if n >= daily_min:
            freq_buckets[freq_labels[0]] += 1
        elif n >= weekly_min:
            freq_buckets[freq_labels[1]] += 1
        else:
            freq_buckets[freq_labels[2]] += 1

    # Sessions in MAU window
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

    # Key activities from activity log (last 30d + by month)
    activity_type_rows = (
        db.session.query(
            UserActivityLog.activity_type,
            func.count(UserActivityLog.id),
        )
        .filter(UserActivityLog.timestamp >= mau_since)
        .group_by(UserActivityLog.activity_type)
        .all()
    )
    activity_breakdown = {t: int(c) for t, c in activity_type_rows}
    key_activities_30d = {
        t: c for t, c in activity_breakdown.items() if t in KEY_ACTIVITY_TYPES
    }

    # Monthly series: MAU, sessions, submissions, docs
    monthly: Dict[str, Dict[str, Any]] = {}

    # Distinct active users per calendar month (from sessions)
    month_user_rows = (
        db.session.query(
            func.to_char(UserSessionLog.last_activity, "YYYY-MM").label("ym"),
            func.count(distinct(UserSessionLog.user_id)),
        )
        .filter(UserSessionLog.last_activity >= history_since)
        .group_by("ym")
        .order_by("ym")
        .all()
    )
    for ym, cnt in month_user_rows:
        monthly.setdefault(ym, {})["mau_from_sessions"] = int(cnt)

    # Also count from successful logins (captures users with sparse session rows)
    month_login_rows = (
        db.session.query(
            func.to_char(UserLoginLog.timestamp, "YYYY-MM").label("ym"),
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
    )
    for ym, cnt in month_login_rows:
        monthly.setdefault(ym, {})["unique_logins"] = int(cnt)

    month_sess_rows = (
        db.session.query(
            func.to_char(UserSessionLog.session_start, "YYYY-MM").label("ym"),
            func.count(UserSessionLog.id),
            func.coalesce(func.sum(UserSessionLog.forms_submitted), 0),
            func.coalesce(func.sum(UserSessionLog.files_uploaded), 0),
            func.coalesce(func.sum(UserSessionLog.page_views), 0),
            func.coalesce(func.sum(UserSessionLog.actions_performed), 0),
        )
        .filter(UserSessionLog.session_start >= history_since)
        .group_by("ym")
        .order_by("ym")
        .all()
    )
    for ym, sess, forms, files, pages, actions in month_sess_rows:
        bucket = monthly.setdefault(ym, {})
        bucket["sessions"] = int(sess)
        bucket["forms_submitted_session_counter"] = int(forms)
        bucket["files_uploaded_session_counter"] = int(files)
        bucket["page_views"] = int(pages)
        bucket["actions_performed"] = int(actions)

    # Assignment entity submissions (reports submitted) by month — use submitted_at
    aes_rows = (
        db.session.query(
            func.to_char(AssignmentEntityStatus.submitted_at, "YYYY-MM").label("ym"),
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
    )
    for ym, cnt, entities in aes_rows:
        bucket = monthly.setdefault(ym, {})
        bucket["reports_submitted"] = int(cnt)
        bucket["countries_that_submitted"] = int(entities)

    # Submitted documents
    doc_rows = (
        db.session.query(
            func.to_char(SubmittedDocument.uploaded_at, "YYYY-MM").label("ym"),
            func.count(SubmittedDocument.id),
        )
        .filter(SubmittedDocument.uploaded_at >= history_since)
        .group_by("ym")
        .order_by("ym")
        .all()
    )
    for ym, cnt in doc_rows:
        monthly.setdefault(ym, {})["documents_uploaded"] = int(cnt)

    # Activity-log key events by month
    key_act_month_rows = (
        db.session.query(
            func.to_char(UserActivityLog.timestamp, "YYYY-MM").label("ym"),
            UserActivityLog.activity_type,
            func.count(UserActivityLog.id),
        )
        .filter(
            UserActivityLog.timestamp >= history_since,
            UserActivityLog.activity_type.in_(list(KEY_ACTIVITY_TYPES)),
        )
        .group_by("ym", UserActivityLog.activity_type)
        .order_by("ym")
        .all()
    )
    for ym, atype, cnt in key_act_month_rows:
        bucket = monthly.setdefault(ym, {})
        acts = bucket.setdefault("key_activities", {})
        acts[atype] = int(cnt)

    # Total registered / active accounts (context)
    total_users = db.session.query(func.count(User.id)).scalar() or 0
    active_accounts = (
        db.session.query(func.count(User.id)).filter(User.active.is_(True)).scalar() or 0
    )

    # Device mix from recent sessions
    device_rows = (
        db.session.query(
            UserSessionLog.device_type,
            func.count(UserSessionLog.id),
        )
        .filter(UserSessionLog.session_start >= mau_since)
        .group_by(UserSessionLog.device_type)
        .all()
    )
    device_breakdown = {
        (d or "Unknown"): int(c) for d, c in device_rows
    }

    # Top roles among MAU (permission roles)
    role_mau_counts: Counter = Counter()
    for uid in mau_ids:
        for code in roles_by_user.get(uid, set()):
            role_mau_counts[code] += 1

    report = {
        "generated_at": iso(now),
        "window": {
            "mau_days": days_mau,
            "mau_since": iso(mau_since),
            "history_months": months,
            "history_since": iso(history_since),
            "source": "first-party DB (user_session_log, user_login_log, user_activity_log, assignment_entity_status)",
            "note": (
                "MAU = unique authenticated users with a successful login, "
                "session activity, or activity-log event in the window. "
                "No third-party product analytics (Amplitude/GA) — "
                "tracking-tool unique-user IDs are not available in this DB."
            ),
        },
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
        "frequency_of_use": {
            "definition": (
                "Among MAU, bucketed by distinct active workdays (Mon–Fri) "
                f"in the last {days_mau} days "
                f"({workdays_in_window} workdays in window; weekends excluded)"
            ),
            "workdays_in_window": workdays_in_window,
            "buckets": dict(freq_buckets),
        },
        "primary_user_types": {
            "definition": (
                "Among MAU: IFRC (@ifrc.org, secretariat entities, or admin) "
                "vs NS (country/NS entities or assignment-only; @ifrc.org wins "
                "even with country scope). Volunteers are not a distinct "
                "account type in this platform."
            ),
            "counts": {k: int(user_type_counts.get(k, 0)) for k in PRIMARY_USER_TYPE_ORDER},
            "detail_counts": dict(user_type_detail_counts),
            "examples": {k: v for k, v in user_type_examples.items()},
            "top_permission_roles_among_mau": dict(role_mau_counts.most_common(15)),
        },
        "user_segmentation": {
            "definition": (
                "Access Groups (RBAC kind=group) among MAU users"
                if has_role_kind
                else "Access Groups unavailable on this deploy (RbacRole.kind missing)"
            ),
            "available": has_role_kind,
            "counts": dict(segment_counts.most_common()),
        },
        "geographic_reach": {
            "countries_with_mau_users": len(mau_country_ids),
            "countries": sorted(
                [
                    {
                        "id": c.id,
                        "name": c.name,
                        "iso3": getattr(c, "iso3", None),
                        "national_society": ns_by_country.get(c.id),
                    }
                    for c in countries
                ],
                key=lambda x: (x["name"] or ""),
            ),
        },
        "key_activities_last_30d": {
            "sessions": {
                "count": int(session_stats[0] or 0),
                "page_views": int(session_stats[1] or 0),
                "actions_performed": int(session_stats[2] or 0),
                "forms_submitted_counter": int(session_stats[3] or 0),
                "files_uploaded_counter": int(session_stats[4] or 0),
                "avg_duration_minutes": (
                    round(float(session_stats[5]), 2) if session_stats[5] is not None else None
                ),
            },
            "activity_log_key_types": key_activities_30d,
            "activity_log_all_types": activity_breakdown,
            "device_breakdown": device_breakdown,
        },
        "monthly": dict(sorted(monthly.items())),
    }
    return report


def print_human(report: Dict[str, Any]) -> None:
    w = report["window"]
    print("=" * 72)
    print("IFRC Databank — Product Analytics (first-party)")
    print(f"Generated: {report['generated_at']}")
    print(f"MAU window: last {w['mau_days']} days (since {w['mau_since']})")
    print(f"History: {w['history_months']} months (since {w['history_since']})")
    print("=" * 72)
    print()
    print("NOTE:", w["note"])
    print()

    print("--- Accounts ---")
    print(f"  Registered users:     {report['accounts']['total_registered']}")
    print(f"  Active (flag=true):   {report['accounts']['active_flag_true']}")
    print()

    mau = report["mau"]
    print("--- Monthly Active Users (MAU) ---")
    print(f"  Unique users:         {mau['unique_users']}")
    print(f"    via sessions:       {mau['from_sessions']}")
    print(f"    via logins:         {mau['from_logins']}")
    print(f"    via activity log:   {mau['from_activity_log']}")
    print()

    print("--- Frequency of Use (among MAU) ---")
    print(f"  {report['frequency_of_use']['definition']}")
    for k, v in report["frequency_of_use"]["buckets"].items():
        print(f"  {k:24s} {v}")
    print()

    print("--- Primary User Type(s) ---")
    print(f"  {report['primary_user_types']['definition']}")
    for k, v in sorted(
        report["primary_user_types"]["counts"].items(),
        key=lambda x: -x[1],
    ):
        print(f"  {k:40s} {v}")
    print("  Top roles among MAU:")
    for code, n in list(
        report["primary_user_types"]["top_permission_roles_among_mau"].items()
    )[:10]:
        print(f"    {code:40s} {n}")
    print()

    print("--- User Segmentation (Access Groups) ---")
    segs = report["user_segmentation"]["counts"]
    if not segs:
        print("  (none)")
    else:
        for k, v in list(segs.items())[:25]:
            print(f"  {k:40s} {v}")
    print()

    geo = report["geographic_reach"]
    print("--- Geographic Reach ---")
    print(f"  Countries / NS with MAU users: {geo['countries_with_mau_users']}")
    for c in geo["countries"][:40]:
        ns = c.get("national_society") or "—"
        iso3 = c.get("iso3") or "?"
        print(f"    {iso3:4s}  {c['name']}  ({ns})")
    if len(geo["countries"]) > 40:
        print(f"    … +{len(geo['countries']) - 40} more")
    print()

    ka = report["key_activities_last_30d"]
    print("--- Key Activities (last 30 days) ---")
    s = ka["sessions"]
    print(f"  Sessions:             {s['count']}")
    print(f"  Page views:           {s['page_views']}")
    print(f"  Actions performed:    {s['actions_performed']}")
    print(f"  Forms submitted (sess counter): {s['forms_submitted_counter']}")
    print(f"  Files uploaded (sess counter):  {s['files_uploaded_counter']}")
    print(f"  Avg session minutes:  {s['avg_duration_minutes']}")
    print("  Activity-log key types:")
    for t, n in sorted(ka["activity_log_key_types"].items(), key=lambda x: -x[1]):
        print(f"    {t:35s} {n}")
    print("  Devices:")
    for d, n in sorted(ka["device_breakdown"].items(), key=lambda x: -x[1]):
        print(f"    {d:20s} {n}")
    print()

    print("--- Monthly trend ---")
    print(
        f"  {'Month':8s} {'MAU':>6s} {'LoginsU':>8s} {'Sess':>7s} "
        f"{'Reports':>8s} {'Docs':>6s} {'Pages':>8s}"
    )
    for ym, b in report["monthly"].items():
        print(
            f"  {ym:8s} {b.get('mau_from_sessions', 0):6d} "
            f"{b.get('unique_logins', 0):8d} {b.get('sessions', 0):7d} "
            f"{b.get('reports_submitted', 0):8d} "
            f"{b.get('documents_uploaded', 0):6d} "
            f"{b.get('page_views', 0):8d}"
        )
    print()
    print("Done.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Product analytics report (read-only)")
    parser.add_argument("--months", type=int, default=6, help="History months (default 6)")
    parser.add_argument("--mau-days", type=int, default=30, help="MAU window days (default 30)")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    from app import create_app

    app = create_app()
    with app.app_context():
        report = build_report(months=args.months, days_mau=args.mau_days)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_human(report)
        # Also write a compact JSON trailer for machine parse of the log
        print("---JSON---")
        print(json.dumps(report, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
