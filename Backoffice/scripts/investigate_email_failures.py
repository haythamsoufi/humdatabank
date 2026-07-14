"""One-off: inspect failed email deliveries and related application logs on prod."""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone

# Flask app context
sys.path.insert(0, "/app")
os.environ.setdefault("FLASK_CONFIG", "production")

from app import create_app, db
from app.models import EmailDeliveryLog

# Windows reported times are likely Europe/Zurich (UTC+2 in summer).
# Search both local (CEST) and UTC windows with padding.
WINDOWS = [
    ("Jul 12 13:49 local (CEST)", datetime(2026, 7, 12, 11, 44, 0, tzinfo=timezone.utc), datetime(2026, 7, 12, 11, 54, 0, tzinfo=timezone.utc)),
    ("Jul 13 01:43 local (CEST)", datetime(2026, 7, 12, 23, 38, 0, tzinfo=timezone.utc), datetime(2026, 7, 12, 23, 48, 0, tzinfo=timezone.utc)),
    ("Jul 12 13:49 UTC", datetime(2026, 7, 12, 13, 44, 0, tzinfo=timezone.utc), datetime(2026, 7, 12, 13, 54, 0, tzinfo=timezone.utc)),
    ("Jul 13 01:43 UTC", datetime(2026, 7, 13, 1, 38, 0, tzinfo=timezone.utc), datetime(2026, 7, 13, 1, 48, 0, tzinfo=timezone.utc)),
]

LOG_PATH = "/app/instance/logs/application.log"
OUT_PATH = "/tmp/email_failure_investigation.txt"
EMAIL_PATTERNS = re.compile(
    r"email_api|send_email|Failed to send|Email send returned False|EMAIL_API|mark_email_failed",
    re.IGNORECASE,
)


def _naive_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


def main() -> int:
    lines: list[str] = []
    app = create_app("production")
    with app.app_context():
        lines.append("=== Failed email_delivery_log rows (Jul 12-13 2026) ===")
        start = datetime(2026, 7, 12, 0, 0, 0)
        end = datetime(2026, 7, 13, 23, 59, 59)
        failed = (
            EmailDeliveryLog.query.filter(
                EmailDeliveryLog.status.in_(("failed", "retrying")),
                EmailDeliveryLog.created_at >= start,
                EmailDeliveryLog.created_at <= end,
            )
            .order_by(EmailDeliveryLog.created_at.asc())
            .all()
        )
        if not failed:
            lines.append("(no failed/retrying rows in date range)")
        for row in failed:
            lines.append(
                f"id={row.id} created={row.created_at} failed_at={row.failed_at} "
                f"status={row.status} user_id={row.user_id} "
                f"email={row.email_address} subject={row.subject!r} "
                f"notification_id={row.notification_id} retry_count={row.retry_count} "
                f"error={row.error_message!r}"
            )

        lines.append("")
        lines.append("=== Failed rows in incident windows ===")
        for label, wstart, wend in WINDOWS:
            lines.append(f"-- {label} ({wstart.isoformat()} .. {wend.isoformat()}) --")
            matches = [
                row
                for row in failed
                if row.created_at
                and _naive_utc(wstart) <= row.created_at <= _naive_utc(wend)
            ]
            if not matches:
                # also match on failed_at
                matches = [
                    row
                    for row in failed
                    if row.failed_at
                    and _naive_utc(wstart) <= row.failed_at <= _naive_utc(wend)
                ]
            if not matches:
                lines.append("  (none)")
            for row in matches:
                lines.append(
                    f"  id={row.id} created={row.created_at} failed_at={row.failed_at} "
                    f"email={row.email_address} subject={row.subject!r} error={row.error_message!r}"
                )

    lines.append("")
    lines.append(f"=== application.log snippets ({LOG_PATH}) ===")
    if os.path.isfile(LOG_PATH):
        try:
            with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
                all_lines = fh.readlines()
            lines.append(f"total_lines={len(all_lines)}")
            for label, wstart, wend in WINDOWS:
                lines.append(f"-- log grep {label} --")
                # log timestamps are typically naive UTC in app logs
                date_tokens = {
                    wstart.strftime("%Y-%m-%d %H:%M"),
                    wend.strftime("%Y-%m-%d %H:%M"),
                    (wstart - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
                    (wend + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
                }
                hits = []
                for ln in all_lines:
                    if not any(tok in ln for tok in date_tokens):
                        continue
                    if EMAIL_PATTERNS.search(ln):
                        hits.append(ln.rstrip())
                if not hits:
                    # broader: any line in the minute window
                    for ln in all_lines:
                        if any(tok in ln for tok in date_tokens):
                            hits.append(ln.rstrip())
                lines.extend(hits[:80] if hits else ["  (no lines in window)"])
        except Exception as exc:
            lines.append(f"error reading log: {exc}")
    else:
        lines.append("application.log not found")

    output = "\n".join(lines)
    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write(output)
    print(output)
    print(f"\nWrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
