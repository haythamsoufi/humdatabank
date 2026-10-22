#!/usr/bin/env python3
"""Read-only: match a security email-failure event to Communication Center rows.

Prints the security event and any email_delivery_log / notification rows whose
subject or title contains the event subject tail.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

for candidate in (Path("/app"), Path(__file__).resolve().parents[2]):
    if (candidate / "app").is_dir() and (candidate / "run.py").is_file():
        root = str(candidate)
        if root not in sys.path:
            sys.path.insert(0, root)
        scripts = str(candidate / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        break


def _status(value) -> str:
    raw = getattr(value, "value", None)
    return str(raw if raw is not None else value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_id", type=int)
    args = parser.parse_args()

    from app import create_app

    app = create_app()
    with app.app_context():
        from sqlalchemy import or_

        from app.models import EmailDeliveryLog, Notification, SecurityEvent, User
        from app.services.email.delivery import email_delivery_log_needs_attention

        event = SecurityEvent.query.get(args.event_id)
        if event is None:
            print(f"event {args.event_id} not found")
            return 1

        description = event.description or ""
        print(f"event_id={event.id}")
        print(f"timestamp={event.timestamp}")
        print(f"event_type={event.event_type}")
        print(f"description={description}")
        print(f"context={event.context_data}")

        marker = "Subject: "
        subject = description.split(marker, 1)[1].strip() if marker in description else description
        # Drop the "New Notification: " prefix so we also match the in-app title.
        title_hint = subject
        prefix = "New Notification: "
        if title_hint.startswith(prefix):
            title_hint = title_hint[len(prefix) :]
        needle = title_hint[:80]
        print(f"needle={needle!r}")

        logs = (
            EmailDeliveryLog.query.filter(EmailDeliveryLog.subject.ilike(f"%{needle}%"))
            .order_by(EmailDeliveryLog.created_at.desc())
            .limit(30)
            .all()
        )
        print(f"matching_logs={len(logs)}")
        for log in logs:
            user = User.query.get(log.user_id) if log.user_id else None
            notif = Notification.query.get(log.notification_id) if log.notification_id else None
            needs = email_delivery_log_needs_attention(log)
            print(
                f"log id={log.id} status={_status(log.status)} needs_attention={needs} "
                f"notification_id={log.notification_id} user_id={log.user_id} "
                f"email={getattr(user, 'email', None)} "
                f"created_at={log.created_at} failed_at={log.failed_at} sent_at={log.sent_at} "
                f"retry_count={log.retry_count}"
            )
            print(f"  subject={log.subject}")
            err = (log.error_message or "").replace("\n", " ")[:240]
            print(f"  error={err}")
            if notif is not None:
                print(
                    f"  notification type={_status(notif.notification_type)} "
                    f"archived={notif.is_archived} created_at={notif.created_at} "
                    f"title={notif.title!r}"
                )

        notifs = (
            Notification.query.filter(
                or_(
                    Notification.title.ilike(f"%{needle}%"),
                    Notification.message.ilike(f"%{needle}%"),
                )
            )
            .order_by(Notification.created_at.desc())
            .limit(20)
            .all()
        )
        from app.services.communication.center_service import fetch_communications_center_page
        from app.services.email.delivery import get_email_delivery_logs_needing_attention

        attention = get_email_delivery_logs_needing_attention()
        print(f"attention_count={len(attention)}")
        for log in attention:
            print(
                f"  attention log id={log.id} status={_status(log.status)} "
                f"notification_id={log.notification_id} subject={(log.subject or '')[:100]}"
            )

        page = fetch_communications_center_page(page=1, per_page=50)
        print(f"page1_rows={len(page['rows'])} failed_email_delivery_count={page['failed_email_delivery_count']}")
        for row in page["rows"]:
            if row.get("notification_id") in {3854, 3855} or row.get("email_log_id") == 3538:
                print(
                    "page1_match "
                    f"notification_id={row.get('notification_id')} "
                    f"email_log_id={row.get('email_log_id')} "
                    f"email_status={row.get('email_status')} "
                    f"user_email={row.get('user_email')} "
                    f"title={row.get('title')!r} "
                    f"message={row.get('message')!r} "
                    f"included_for_email_failure={row.get('included_for_email_failure')}"
                )

        print(f"matching_notifications={len(notifs)}")
        for notif in notifs:
            user = User.query.get(notif.user_id)
            print(
                f"notification id={notif.id} user={getattr(user, 'email', None)} "
                f"archived={notif.is_archived} created_at={notif.created_at} "
                f"type={_status(notif.notification_type)} title={notif.title!r}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
