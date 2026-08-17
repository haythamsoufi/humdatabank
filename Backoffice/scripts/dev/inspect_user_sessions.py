#!/usr/bin/env python3
"""One-off prod diagnostic: dump UserSessionLog + UserLoginLog rows for one user.

Prints full detail for currently-active sessions and the most recent N inactive
ones (for context), plus a summary of the full history and matching login log
rows so duplicate-session timestamps can be correlated with login events.

Usage:
    python scripts/inspect_user_sessions.py --email someone@ifrc.org [--recent 8]
"""
from __future__ import annotations

import argparse
import sys
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


def _fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC") if dt else "-"


def _print_session(s, now, ensure_utc, prev_end=None):
    gap_str = ""
    start_aware = ensure_utc(s.session_start)
    if prev_end is not None:
        gap_min = (start_aware - prev_end).total_seconds() / 60
        gap_str = f"  [gap_since_prev_end={gap_min:.1f}min]"
    last_activity_aware = ensure_utc(s.last_activity)
    idle_min = (now - last_activity_aware).total_seconds() / 60
    print(
        f"\n- session_pk={s.id} session_id={s.session_id}\n"
        f"  is_active={s.is_active}  ended_by={s.ended_by}\n"
        f"  session_start={_fmt_dt(s.session_start)}\n"
        f"  session_end  ={_fmt_dt(s.session_end)}\n"
        f"  last_activity={_fmt_dt(s.last_activity)}  (idle_now={idle_min:.1f}min)\n"
        f"  duration_minutes={s.duration_minutes}\n"
        f"  ip={s.ip_address}  browser={s.browser}  os={s.operating_system}  device={s.device_type}\n"
        f"  page_views={s.page_views}  actions={s.actions_performed}  forms={s.forms_submitted}\n"
        f"  user_agent={s.user_agent}"
        f"{gap_str}"
    )
    return ensure_utc(s.session_end) or last_activity_aware


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--recent", type=int, default=8, help="How many most-recent inactive sessions to show in full")
    args = parser.parse_args()

    app = create_app("production")
    with app.app_context():
        from app.models import User, UserSessionLog, UserLoginLog
        from app.utils.datetime_helpers import utcnow, ensure_utc

        email = args.email.strip().lower()
        user = User.query.filter(User.email.ilike(email)).first()
        if not user:
            print(f"No user found for email={email}")
            return

        print(f"user_id={user.id} email={user.email} is_active={user.is_active}")

        all_sessions = (
            UserSessionLog.query.filter_by(user_id=user.id)
            .order_by(UserSessionLog.session_start.asc())
            .all()
        )
        now = utcnow()
        active_sessions = [s for s in all_sessions if s.is_active]

        print(f"\n=== Summary: {len(all_sessions)} total session rows, {len(active_sessions)} currently ACTIVE ===")
        if all_sessions:
            print(f"Oldest session_start: {_fmt_dt(all_sessions[0].session_start)}")
            print(f"Newest session_start: {_fmt_dt(all_sessions[-1].session_start)}")

        print(f"\n=== ACTIVE sessions (is_active=True): {len(active_sessions)} ===")
        prev_end = None
        for s in active_sessions:
            prev_end = _print_session(s, now, ensure_utc, prev_end)

        recent_inactive = [s for s in all_sessions if not s.is_active][-args.recent:]
        print(f"\n=== Most recent {len(recent_inactive)} INACTIVE sessions (for context) ===")
        prev_end = None
        for s in recent_inactive:
            prev_end = _print_session(s, now, ensure_utc, prev_end)

        logs = (
            UserLoginLog.query.filter_by(user_id=user.id)
            .order_by(UserLoginLog.timestamp.desc())
            .limit(30)
            .all()
        )
        print(f"\n=== Most recent UserLoginLog rows (up to 30, newest first): {len(logs)} ===")
        for lg in logs:
            print(
                f"- ts={_fmt_dt(lg.timestamp)}  event={lg.event_type}  "
                f"session_id={lg.session_id}  ip={lg.ip_address}  browser={lg.browser}  "
                f"os={lg.operating_system}  device={lg.device_type}  "
                f"suspicious={lg.is_suspicious}  bot={lg.is_bot_detected}  "
                f"failure_reason={lg.failure_reason}  referrer={lg.referrer_url}"
            )


if __name__ == "__main__":
    main()
