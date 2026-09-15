#!/usr/bin/env python3
"""Read-only SecurityEvent inspector for local DB or Azure SSH.

Works when uploaded to /tmp by azure_webapp_tools (cwd=/app) and when run
from Backoffice/scripts/ops/.

Examples::

  azure_webapp_tools.bat prod security-event 894
  azure_webapp_tools.bat prod security-event --list --unresolved --severity high
  azure_webapp_tools.bat staging security-event 12 --json

  cd /app && python /tmp/inspect_security_event.py 894
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable, Optional


def _ensure_app_importable() -> None:
    """Make ``from app import …`` work from /tmp upload or scripts/ops/."""
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

AES_PATH_RE = re.compile(r"/(?:forms/)?assignment/(\d+)\b", re.IGNORECASE)


def extract_assignment_ids(*texts: Optional[str]) -> list[int]:
    """Collect unique ``/assignment/<id>`` or ``/forms/assignment/<id>`` ids."""
    found: list[int] = []
    seen: set[int] = set()
    for text in texts:
        if not text:
            continue
        for match in AES_PATH_RE.finditer(str(text)):
            aes_id = int(match.group(1))
            if aes_id not in seen:
                seen.add(aes_id)
                found.append(aes_id)
    return found


def enum_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    raw = getattr(value, "value", None)
    return str(raw) if raw is not None else str(value)


def iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def user_label(user: Any) -> Optional[dict[str, Any]]:
    if user is None:
        return None
    return {
        "id": getattr(user, "id", None),
        "email": getattr(user, "email", None),
        "name": getattr(user, "name", None),
        "is_active": getattr(user, "is_active", None),
    }


def format_user(user: Optional[dict[str, Any]]) -> str:
    if not user:
        return "anonymous"
    name = user.get("name") or "—"
    email = user.get("email") or "—"
    return f"{name} <{email}> (id={user.get('id')})"


def context_excerpt(context: Optional[dict[str, Any]]) -> dict[str, Any]:
    data = context or {}
    keys = (
        "url",
        "referrer",
        "failed_url",
        "source",
        "platform",
        "client_timestamp",
        "diagnostics_summary",
        "likely_causes",
        "request_field_count",
        "request_approx_bytes",
    )
    excerpt = {key: data.get(key) for key in keys if data.get(key) not in (None, "", [])}
    worker = data.get("worker_metrics") or {}
    if worker:
        excerpt["worker_pid"] = worker.get("worker_pid")
        excerpt["in_flight_count"] = worker.get("in_flight_count")
        excerpt["stale_in_flight_count"] = worker.get("stale_in_flight_count")
        excerpt["traffic_last_60s"] = worker.get("traffic_last_60s")
        excerpt["traffic_last_5m"] = worker.get("traffic_last_5m")
        excerpt["redis_cross_worker"] = worker.get("redis_cross_worker")
        pool = worker.get("db_pool") or {}
        if pool:
            excerpt["db_pool"] = (
                f"{pool.get('checked_out')}/{pool.get('size')} "
                f"checked out (overflow {pool.get('overflow')})"
            )
    return excerpt


def event_summary(event: Any, *, include_context: bool = True) -> dict[str, Any]:
    context = getattr(event, "context_data", None) or {}
    payload = {
        "id": event.id,
        "event_type": event.event_type,
        "severity": event.severity,
        "description": event.description,
        "timestamp": iso(event.timestamp),
        "ip_address": event.ip_address,
        "user_agent": event.user_agent,
        "user": user_label(getattr(event, "user", None)),
        "is_resolved": bool(event.is_resolved),
        "resolved_at": iso(getattr(event, "resolved_at", None)),
        "resolved_by": user_label(getattr(event, "resolved_by", None)),
        "resolution_notes": getattr(event, "resolution_notes", None),
    }
    if include_context:
        payload["context_excerpt"] = context_excerpt(context)
        payload["context_data"] = context
    return payload


def lookup_assignment(aes_id: int) -> Optional[dict[str, Any]]:
    from app.models import AssignmentEntityStatus

    aes = AssignmentEntityStatus.query.get(aes_id)
    if aes is None:
        return {"aes_id": aes_id, "error": "AssignmentEntityStatus not found"}

    assigned = aes.assigned_form
    template = getattr(assigned, "template", None) if assigned else None
    entity: dict[str, Any] = {"type": aes.entity_type, "id": aes.entity_id}
    try:
        entity_obj = aes.entity
        entity["name"] = getattr(entity_obj, "name", None) or str(entity_obj)
    except Exception as exc:
        entity["lookup_error"] = str(exc)

    template_name = getattr(template, "name", None) if template else None
    period_name = getattr(assigned, "period_name", None) if assigned else None
    custom_name = getattr(assigned, "custom_name", None) if assigned else None
    display = custom_name or (
        f"{template_name} – {period_name}" if template_name or period_name else None
    )

    return {
        "aes_id": aes.id,
        "status": enum_value(aes.status),
        "completion_rate": str(aes.completion_rate) if aes.completion_rate is not None else None,
        "status_timestamp": iso(aes.status_timestamp),
        "submitted_at": iso(aes.submitted_at),
        "entity": entity,
        "assigned_form": {
            "id": assigned.id if assigned else None,
            "period_name": period_name,
            "custom_name": custom_name,
            "display_name": display,
            "is_effectively_closed": bool(assigned and assigned.is_effectively_closed),
        }
        if assigned
        else None,
        "template": {"id": template.id, "name": template_name} if template else None,
    }


def assignments_from_event(event: Any) -> list[dict[str, Any]]:
    context = getattr(event, "context_data", None) or {}
    ids = extract_assignment_ids(
        getattr(event, "description", None),
        context.get("url"),
        context.get("referrer"),
        context.get("failed_url"),
    )
    return [lookup_assignment(aes_id) for aes_id in ids]


def inspect_event(event_id: int, *, nearby_hours: int = 2) -> dict[str, Any]:
    from app.models import SecurityEvent

    event = SecurityEvent.query.get(event_id)
    if event is None:
        return {"error": f"SecurityEvent {event_id} not found"}

    related = (
        SecurityEvent.query.filter(
            SecurityEvent.id != event_id,
            SecurityEvent.ip_address == event.ip_address,
            SecurityEvent.timestamp >= event.timestamp - timedelta(days=7),
        )
        .order_by(SecurityEvent.timestamp.desc())
        .limit(10)
        .all()
    )
    same_type_window = (
        SecurityEvent.query.filter(
            SecurityEvent.event_type == event.event_type,
            SecurityEvent.timestamp >= event.timestamp - timedelta(hours=24),
            SecurityEvent.timestamp <= event.timestamp + timedelta(hours=24),
        )
        .order_by(SecurityEvent.timestamp.desc())
        .limit(20)
        .all()
    )
    recent_same_type = (
        SecurityEvent.query.filter(SecurityEvent.event_type == event.event_type)
        .order_by(SecurityEvent.timestamp.desc())
        .limit(12)
        .all()
    )
    nearby = (
        SecurityEvent.query.filter(
            SecurityEvent.timestamp >= event.timestamp - timedelta(hours=nearby_hours),
            SecurityEvent.timestamp <= event.timestamp + timedelta(hours=nearby_hours),
        )
        .order_by(SecurityEvent.timestamp.desc())
        .limit(25)
        .all()
    )
    user_recent = []
    if event.user_id:
        user_recent = (
            SecurityEvent.query.filter(
                SecurityEvent.user_id == event.user_id,
                SecurityEvent.timestamp >= event.timestamp - timedelta(days=14),
            )
            .order_by(SecurityEvent.timestamp.desc())
            .limit(15)
            .all()
        )

    return {
        "event": event_summary(event),
        "assignments": assignments_from_event(event),
        "related_same_ip_7d": [event_summary(item, include_context=False) for item in related],
        "same_type_plus_minus_24h": [
            {
                "id": item.id,
                "timestamp": iso(item.timestamp),
                "severity": item.severity,
                "ip_address": item.ip_address,
                "description": (item.description or "")[:180],
                "is_resolved": bool(item.is_resolved),
            }
            for item in same_type_window
        ],
        "same_type_total": SecurityEvent.query.filter(
            SecurityEvent.event_type == event.event_type
        ).count(),
        "recent_same_type": [
            {
                "id": item.id,
                "timestamp": iso(item.timestamp),
                "severity": item.severity,
                "url": (item.context_data or {}).get("url"),
                "referrer": (item.context_data or {}).get("referrer"),
                "user_id": item.user_id,
                "likely_causes": (item.context_data or {}).get("likely_causes"),
                "is_resolved": bool(item.is_resolved),
            }
            for item in recent_same_type
        ],
        "nearby_any_type": [
            {
                "id": item.id,
                "timestamp": iso(item.timestamp),
                "event_type": item.event_type,
                "severity": item.severity,
                "user_id": item.user_id,
                "description": (item.description or "")[:180],
            }
            for item in nearby
        ],
        "user_events_14d": [
            {
                "id": item.id,
                "timestamp": iso(item.timestamp),
                "event_type": item.event_type,
                "severity": item.severity,
                "description": (item.description or "")[:180],
            }
            for item in user_recent
        ],
    }


def list_events(
    *,
    unresolved: bool = False,
    severity: Optional[str] = None,
    event_type: Optional[str] = None,
    user_id: Optional[int] = None,
    limit: int = 20,
) -> dict[str, Any]:
    from app.models import SecurityEvent

    query = SecurityEvent.query
    if unresolved:
        query = query.filter(SecurityEvent.is_resolved.is_(False))
    if severity:
        query = query.filter(SecurityEvent.severity == severity)
    if event_type:
        query = query.filter(SecurityEvent.event_type == event_type)
    if user_id is not None:
        query = query.filter(SecurityEvent.user_id == user_id)

    rows = query.order_by(SecurityEvent.timestamp.desc()).limit(limit).all()
    return {
        "filters": {
            "unresolved": unresolved,
            "severity": severity,
            "event_type": event_type,
            "user_id": user_id,
            "limit": limit,
        },
        "count": len(rows),
        "events": [
            {
                "id": item.id,
                "timestamp": iso(item.timestamp),
                "event_type": item.event_type,
                "severity": item.severity,
                "is_resolved": bool(item.is_resolved),
                "user_id": item.user_id,
                "ip_address": item.ip_address,
                "url": (item.context_data or {}).get("url"),
                "description": (item.description or "")[:140],
            }
            for item in rows
        ],
    }


def _print_kv(label: str, value: Any) -> None:
    text = "—" if value in (None, "") else str(value)
    print(f"{label:<18}{text}")


def print_list_report(payload: dict[str, Any]) -> None:
    filters = payload["filters"]
    active = ", ".join(
        f"{key}={value}"
        for key, value in filters.items()
        if value not in (None, False, "")
    )
    print(f"=== Security events ({payload['count']}) ===")
    if active:
        print(f"Filters: {active}")
    print()
    if not payload["events"]:
        print("No events matched.")
        return
    header = f"{'id':>6}  {'when':<26}  {'type':<32}  {'sev':<8}  {'res':<3}  user  url"
    print(header)
    print("-" * len(header))
    for item in payload["events"]:
        print(
            f"{item['id']:>6}  {(item['timestamp'] or '—'):<26}  "
            f"{(item['event_type'] or '—'):<32}  {(item['severity'] or '—'):<8}  "
            f"{'yes' if item['is_resolved'] else 'no':<3}  "
            f"{item['user_id'] or '—'}  {item.get('url') or '—'}"
        )


def _print_compact_rows(rows: Iterable[dict[str, Any]], *, keys: tuple[str, ...]) -> None:
    rows = list(rows)
    if not rows:
        print("  (none)")
        return
    for row in rows:
        bits = [f"{key}={row.get(key)}" for key in keys if row.get(key) not in (None, "")]
        print("  - " + ", ".join(bits))


def print_event_report(payload: dict[str, Any]) -> None:
    if payload.get("error"):
        print(payload["error"])
        return

    event = payload["event"]
    excerpt = event.get("context_excerpt") or {}
    print(f"=== Security event {event['id']} ===")
    _print_kv("Type", event["event_type"])
    _print_kv("Severity", event["severity"])
    _print_kv("Status", "RESOLVED" if event["is_resolved"] else "UNRESOLVED")
    _print_kv("When", event["timestamp"])
    _print_kv("User", format_user(event.get("user")))
    _print_kv("IP", event.get("ip_address"))
    _print_kv("User-Agent", event.get("user_agent"))
    print()
    print("Description")
    print(f"  {event.get('description') or '—'}")
    print()
    print("Context")
    for key in (
        "url",
        "referrer",
        "failed_url",
        "source",
        "likely_causes",
        "diagnostics_summary",
        "worker_pid",
        "in_flight_count",
        "stale_in_flight_count",
        "traffic_last_60s",
        "db_pool",
        "redis_cross_worker",
    ):
        if key in excerpt:
            _print_kv(key, excerpt[key])

    if event.get("is_resolved"):
        print()
        print("Resolution")
        _print_kv("Resolved at", event.get("resolved_at"))
        _print_kv("Resolved by", format_user(event.get("resolved_by")))
        _print_kv("Notes", event.get("resolution_notes") or "No notes")

    assignments = payload.get("assignments") or []
    if assignments:
        print()
        print("Assignments referenced in URL/referrer")
        for item in assignments:
            if item.get("error"):
                print(f"  - AES {item.get('aes_id')}: {item['error']}")
                continue
            entity = item.get("entity") or {}
            form = item.get("assigned_form") or {}
            template = item.get("template") or {}
            print(
                f"  - AES {item['aes_id']}: {form.get('display_name') or template.get('name') or '—'}"
                f" / {entity.get('name') or entity.get('type')} ({entity.get('type')} #{entity.get('id')})"
                f" status={item.get('status')} completion={item.get('completion_rate')}"
            )

    print()
    print(f"Same type total: {payload.get('same_type_total')}")
    print("Same type ±24h")
    _print_compact_rows(
        payload.get("same_type_plus_minus_24h") or [],
        keys=("id", "timestamp", "severity", "ip_address", "is_resolved"),
    )
    print("Related same IP (7d)")
    _print_compact_rows(
        payload.get("related_same_ip_7d") or [],
        keys=("id", "timestamp", "event_type", "severity", "is_resolved"),
    )
    print("Nearby any type")
    _print_compact_rows(
        payload.get("nearby_any_type") or [],
        keys=("id", "timestamp", "event_type", "severity", "user_id"),
    )
    print("This user, last 14d")
    _print_compact_rows(
        payload.get("user_events_14d") or [],
        keys=("id", "timestamp", "event_type", "severity"),
    )
    print()
    print("Full context_data / worker_metrics: re-run with --json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only dump of SecurityEvent row(s) (and related assignment / neighbours)."
    )
    parser.add_argument("event_id", nargs="?", type=int, help="SecurityEvent id (e.g. 894)")
    parser.add_argument("--list", action="store_true", help="List recent events instead of one id")
    parser.add_argument("--unresolved", action="store_true", help="With --list: only unresolved")
    parser.add_argument("--severity", help="With --list: filter severity (low/medium/high/critical)")
    parser.add_argument("--type", dest="event_type", help="With --list: filter event_type")
    parser.add_argument("--user-id", type=int, help="With --list: filter user_id")
    parser.add_argument("--limit", type=int, default=20, help="With --list: max rows (default 20)")
    parser.add_argument("--nearby-hours", type=int, default=2, help="Nearby-event window (default 2)")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a text report")
    return parser


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.event_id is None and not args.list:
        parser.error("provide an event id, or --list")
    if args.event_id is not None and args.list:
        parser.error("use either an event id or --list, not both")
    return args


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    from app import create_app

    app = create_app()
    with app.app_context():
        if args.list:
            payload = list_events(
                unresolved=args.unresolved,
                severity=args.severity,
                event_type=args.event_type,
                user_id=args.user_id,
                limit=args.limit,
            )
        else:
            payload = inspect_event(args.event_id, nearby_hours=args.nearby_hours)

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    elif args.list:
        print_list_report(payload)
    else:
        print_event_report(payload)
    return 1 if payload.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
