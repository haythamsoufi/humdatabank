"""One-off prod probe: list email delivery failures needing attention."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Support upload to /tmp on Azure (bootstrap resolves from /app when __file__ is /tmp/...).
for candidate in (Path("/app"), Path(__file__).resolve().parent.parent):
    if (candidate / "app").is_dir() and (candidate / "run.py").is_file():
        root = str(candidate)
        if root not in sys.path:
            sys.path.insert(0, root)
        scripts = str(candidate / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        break
else:
    from _bootstrap import setup_cli_paths

    setup_cli_paths(__file__)

from app import create_app  # noqa: E402
from app.services.email.delivery import get_email_delivery_logs_needing_attention  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today-only", action="store_true")
    parser.add_argument("--detail", action="store_true", help="Include notification + security event context")
    args = parser.parse_args()

    app = create_app("production")
    with app.app_context():
        from app.models import Notification, SecurityEvent, User  # noqa: WPS433

        logs = get_email_delivery_logs_needing_attention()
        today = datetime.now(timezone.utc).date()

        if args.today_only:
            logs = [
                log
                for log in logs
                if (log.failed_at or log.created_at)
                and (log.failed_at or log.created_at).date() == today
            ]

        print(f"count={len(logs)}")
        for log in logs:
            ts = log.failed_at or log.created_at
            err = (log.error_message or "").replace("\n", " ")[:300]
            subj = (log.subject or "")[:120]
            print(
                f"id={log.id}\tstatus={log.status}\tuser_id={log.user_id}\t"
                f"notification_id={log.notification_id}\temail={log.email_address}\t"
                f"ts={ts}\tsubject={subj}\terror={err}"
            )
            if args.detail and log.notification_id:
                n = Notification.query.get(log.notification_id)
                if n:
                    print(
                        f"  notification: type={n.notification_type} created_at={n.created_at} "
                        f"title={n.title!r} message={ (n.message or '')[:120]!r} "
                        f"message_params={n.message_params}"
                    )

        if args.detail:
            user_ids = sorted({log.user_id for log in logs})
            for uid in user_ids:
                u = User.query.get(uid)
                print(f"user {uid}: {u.email if u else '?'} active={getattr(u, 'is_active', '?')}")

            since = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
            events = (
                SecurityEvent.query.filter(
                    SecurityEvent.event_type == "email_delivery_failure",
                    SecurityEvent.timestamp >= since,
                )
                .order_by(SecurityEvent.timestamp.desc())
                .all()
            )
            print(f"security_events_today={len(events)}")
            for ev in events:
                print(
                    f"  id={ev.id} ts={ev.timestamp} severity={ev.severity} "
                    f"desc={ev.description[:200]!r} context={ev.context_data}"
                )

            print(
                "email_api_config:",
                f"EMAIL_API_URL={'set' if app.config.get('EMAIL_API_URL') else 'MISSING'}",
                f"EMAIL_API_KEY={'set' if app.config.get('EMAIL_API_KEY') else 'MISSING'}",
                f"MAIL_DEFAULT_SENDER={app.config.get('MAIL_DEFAULT_SENDER')}",
            )

            from collections import Counter  # noqa: WPS433
            from app.models import EmailDeliveryLog  # noqa: WPS433

            today_rows = (
                EmailDeliveryLog.query.filter(EmailDeliveryLog.created_at >= since)
                .order_by(EmailDeliveryLog.created_at.asc())
                .all()
            )
            print(
                "today_delivery_log_summary:",
                len(today_rows),
                dict(Counter(str(r.status) for r in today_rows)),
            )
            for r in today_rows:
                if r.id not in {log.id for log in logs}:
                    print(
                        f"  other id={r.id} status={r.status} email={r.email_address} "
                        f"subject={(r.subject or '')[:60]} ts={r.created_at}"
                    )

            from app.models import AdminActionLog  # noqa: WPS433

            admin_rows = (
                AdminActionLog.query.filter(
                    AdminActionLog.timestamp >= since,
                    AdminActionLog.action_description.ilike("%rachael.ndune%"),
                )
                .order_by(AdminActionLog.timestamp.asc())
                .limit(30)
                .all()
            )
            print(f"admin_actions_rachael_today={len(admin_rows)}")
            for row in admin_rows:
                print(
                    f"  ts={row.timestamp} action={row.action_type} "
                    f"desc={row.action_description[:160]}"
                )


if __name__ == "__main__":
    main()
