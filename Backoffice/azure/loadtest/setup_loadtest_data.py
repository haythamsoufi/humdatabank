"""Setup and teardown script for dedicated load-test assignments on Backoffice staging.

Creates isolated "[LOADTEST]" assignments that the locustfile can write to freely
without polluting real staging data.  Deleting the assignments on teardown also
cascades to FormData, notifications, and entity statuses (all handled by the
existing /admin/assignments/delete/<id> route).

HTTP flow
---------
setup:
  1. GET  /admin/                                            -- extract CSRF token
  2. POST /admin/assignments/new                             -- creates AssignedForm
  3. POST /admin/assignments/<id>/entities/add  (JSON)       -- creates AES per country
  4. PUT  /admin/assignments/<id>/entities/<aes_id>  (JSON)  -- moves Pending -> In Progress

teardown:
  POST /admin/assignments/delete/<id>   -- cascades FormData + AES rows

State is persisted to .loadtest-state.json next to this script so teardown
knows exactly which assignments to remove even if the process is interrupted.

Usage (CLI)
-----------
  # Create 3 assignments using template 1, country 5:
  python setup_loadtest_data.py setup --template-id 1 --country-ids 5 --count 3

  # Create 2 assignments, 2 countries each (gives 4 AES IDs per assignment):
  python setup_loadtest_data.py setup --template-id 1 --country-ids 5,12 --count 2

  # Tear down everything created by the last setup:
  python setup_loadtest_data.py teardown

Environment variables (override CLI args)
-----------------------------------------
  LOADTEST_HOST                  default https://databank-stage.ifrc.org
  LOADTEST_SESSION_COOKIE        required — captured post-B2C session cookie
  LOADTEST_SETUP_TEMPLATE_ID     template_id to use for new assignments
  LOADTEST_SETUP_COUNTRY_IDS     comma-separated country IDs to add per assignment
  LOADTEST_SETUP_COUNT           number of assignments to create (default 3)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("[error] 'requests' is not installed.  Run: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATE_FILE = Path(__file__).parent / ".loadtest-state.json"
DEFAULT_HOST = "https://databank-stage.ifrc.org"

# Matches both hidden-input and meta-tag CSRF patterns used in Backoffice admin.
_CSRF_RE = re.compile(
    r'(?:name="csrf_token"[^>]*value="([^"]+)"'
    r'|<meta\s+name="csrf-token"\s+content="([^"]+)")',
    re.IGNORECASE,
)
# Matches /admin/assignments/edit/<id> in Location header after assignment creation.
_EDIT_URL_RE = re.compile(r"/assignments/edit/(\d+)")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _make_session(session_cookie: str) -> requests.Session:
    s = requests.Session()
    blob = session_cookie.split(";", 1)[0].strip()
    if "=" in blob:
        name, _, value = blob.partition("=")
    else:
        name, value = "session", blob
    s.cookies.set(name.strip(), value.strip())
    return s


def _get_csrf(session: requests.Session, host: str) -> str:
    """Fetch a fresh CSRF token from the admin dashboard."""
    resp = session.get(f"{host}/admin/", timeout=30)
    resp.raise_for_status()
    m = _CSRF_RE.search(resp.text)
    if not m:
        raise RuntimeError(
            "Could not find CSRF token on admin page — is the session cookie valid?"
        )
    return m.group(1) or m.group(2)


def _create_assignment(
    session: requests.Session,
    host: str,
    template_id: int,
    period_name: str,
) -> int:
    """GET /admin/assignments/new to obtain the form CSRF, then POST to create.

    Fetching the token from the exact form page avoids mismatches that occur
    when the token is pulled from a different admin page.
    """
    get_resp = session.get(f"{host}/admin/assignments/new", timeout=30)
    get_resp.raise_for_status()
    m_csrf = _CSRF_RE.search(get_resp.text)
    if not m_csrf:
        raise RuntimeError(
            "CSRF token not found on /admin/assignments/new -- "
            "is the session cookie valid and does the account have admin access?"
        )
    csrf_token = m_csrf.group(1) or m_csrf.group(2)

    resp = session.post(
        f"{host}/admin/assignments/new",
        data={
            "csrf_token": csrf_token,
            "template_id": str(template_id),
            "period_name": period_name,
            "confirm_duplicate": "1",
        },
        allow_redirects=False,
        timeout=30,
    )
    if resp.status_code not in (301, 302):
        raise RuntimeError(
            f"Assignment creation failed: HTTP {resp.status_code}\n"
            f"Body (first 500 chars): {resp.text[:500]}"
        )
    location = resp.headers.get("Location", "")
    m = _EDIT_URL_RE.search(location)
    if not m:
        raise RuntimeError(
            f"Could not parse assignment ID from redirect URL: {location!r}"
        )
    return int(m.group(1))


def _add_entity(
    session: requests.Session,
    host: str,
    csrf_token: str,
    assignment_id: int,
    entity_type: str,
    entity_id: int,
) -> int:
    """POST /admin/assignments/<id>/entities/add → return new AES ID (status_id)."""
    resp = session.post(
        f"{host}/admin/assignments/{assignment_id}/entities/add",
        json={"entity_type": entity_type, "entity_id": entity_id},
        headers={
            "X-CSRFToken": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30,
    )
    if resp.status_code == 409:
        raise RuntimeError(
            f"Entity country={entity_id} is already assigned to assignment {assignment_id}."
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"add_entity failed: HTTP {resp.status_code} — {resp.text[:300]}"
        )
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"add_entity returned non-success: {data}")
    return int(data["status_id"])


def _activate_aes(
    session: requests.Session,
    host: str,
    csrf_token: str,
    assignment_id: int,
    aes_id: int,
) -> None:
    """PUT /admin/assignments/<id>/entities/<aes_id> → set status to In Progress."""
    resp = session.put(
        f"{host}/admin/assignments/{assignment_id}/entities/{aes_id}",
        json={"status": "In Progress"},
        headers={
            "X-CSRFToken": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"activate_aes failed for AES {aes_id}: HTTP {resp.status_code} — {resp.text[:200]}"
        )


def _delete_assignment(
    session: requests.Session,
    host: str,
    csrf_token: str,
    assignment_id: int,
) -> bool:
    """POST /admin/assignments/delete/<id> → cascades FormData + AES rows."""
    resp = session.post(
        f"{host}/admin/assignments/delete/{assignment_id}",
        data={"csrf_token": csrf_token},
        allow_redirects=False,
        timeout=30,
    )
    return resp.status_code in (200, 302)


def _discover_template_id(session: requests.Session, host: str) -> int:
    """Return the first published template ID from GET /api/v1/templates."""
    resp = session.get(
        f"{host}/api/v1/templates",
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    templates = data.get("templates", data) if isinstance(data, dict) else data
    valid = [t for t in (templates or []) if t.get("id")]
    if not valid:
        raise RuntimeError(
            "No templates returned by /api/v1/templates -- "
            "does the session account have access to at least one published template?"
        )
    return int(valid[0]["id"])


def _discover_country_id(session: requests.Session, host: str) -> int:
    """Return the first country ID from GET /api/v1/countrymap."""
    resp = session.get(
        f"{host}/api/v1/countrymap",
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    countries = data.get("countries", data) if isinstance(data, dict) else data
    valid = [c for c in (countries or []) if c.get("id")]
    if not valid:
        raise RuntimeError("No countries returned by /api/v1/countrymap")
    return int(valid[0]["id"])


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_setup(args: argparse.Namespace) -> None:
    host = (os.getenv("LOADTEST_HOST") or DEFAULT_HOST).rstrip("/")
    session_cookie = (os.getenv("LOADTEST_SESSION_COOKIE") or "").strip()
    template_id = args.template_id or int(os.getenv("LOADTEST_SETUP_TEMPLATE_ID") or 0)
    raw_ids = os.getenv("LOADTEST_SETUP_COUNTRY_IDS") or ""
    country_ids: list[int] = args.country_ids or [
        int(x) for x in raw_ids.split(",") if x.strip()
    ]
    count: int = args.count or int(os.getenv("LOADTEST_SETUP_COUNT") or 3)

    if not session_cookie:
        print("[error] LOADTEST_SESSION_COOKIE env var is required")
        sys.exit(1)

    session = _make_session(session_cookie)

    # Auto-discover template and country when not provided.
    if not template_id:
        print("[setup] LOADTEST_SETUP_TEMPLATE_ID not set -- auto-discovering via /api/v1/templates ...")
        try:
            template_id = _discover_template_id(session, host)
            print(f"[setup] Auto-discovered template_id={template_id}")
        except Exception as exc:
            print(f"[error] Could not auto-discover template: {exc}")
            sys.exit(1)

    if not country_ids:
        print("[setup] LOADTEST_SETUP_COUNTRY_IDS not set -- auto-discovering via /api/v1/countrymap ...")
        try:
            country_ids = [_discover_country_id(session, host)]
            print(f"[setup] Auto-discovered country_ids={country_ids}")
        except Exception as exc:
            print(f"[error] Could not auto-discover country: {exc}")
            sys.exit(1)
    run_label = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    print(f"\n[setup] Host:       {host}")
    print(f"[setup] Template:   {template_id}")
    print(f"[setup] Countries:  {country_ids}")
    print(f"[setup] Count:      {count}")
    print(f"[setup] Run label:  {run_label}\n")

    created: list[dict] = []

    for i in range(count):
        period_name = f"[LOADTEST] {run_label} #{i + 1}"
        print(f"  Creating assignment {i + 1}/{count}: {period_name!r} ...", end=" ", flush=True)

        # _create_assignment self-fetches CSRF from the form page.
        assignment_id = _create_assignment(session, host, template_id, period_name)
        print(f"AssignedForm ID={assignment_id}")

        # One fresh CSRF fetch covers all entity add/activate calls for this assignment.
        csrf = _get_csrf(session, host)
        aes_ids: list[int] = []
        for country_id in country_ids:
            print(f"    Adding country {country_id} ...", end=" ", flush=True)
            aes_id = _add_entity(session, host, csrf, assignment_id, "country", country_id)
            print(f"AES ID={aes_id}", end=" -> ", flush=True)
            _activate_aes(session, host, csrf, assignment_id, aes_id)
            print("In Progress")

            aes_ids.append(aes_id)

        created.append({"assignment_id": assignment_id, "aes_ids": aes_ids})

    all_aes_ids = [aes_id for item in created for aes_id in item["aes_ids"]]
    all_assignment_ids = [item["assignment_id"] for item in created]

    state = {
        "host": host,
        "run_label": run_label,
        "template_id": template_id,
        "country_ids": country_ids,
        "assignments": created,
        "all_aes_ids": all_aes_ids,
        "all_assignment_ids": all_assignment_ids,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))

    aes_str = ",".join(str(x) for x in all_aes_ids)
    asgn_str = ",".join(str(x) for x in all_assignment_ids)

    print(f"\n[setup] Done — {len(created)} assignment(s), {len(all_aes_ids)} AES ID(s).")
    print(f"[setup] State saved to: {STATE_FILE}\n")
    print("-" * 60)
    print("  Set these env vars before running the load test:\n")
    print(f"  LOADTEST_ASSIGNMENT_AES_IDS={aes_str}")
    print(f"  LOADTEST_SUBMIT_AES_IDS=    (optional - use a subset of the above")
    print(f"                               if you want submit/reopen testing;")
    print(f"                               keep those IDs OUT of ASSIGNMENT_AES_IDS)")
    print()
    print("  PowerShell:")
    print(f'  $env:LOADTEST_ASSIGNMENT_AES_IDS = "{aes_str}"')
    print()
    print("  Bash:")
    print(f'  export LOADTEST_ASSIGNMENT_AES_IDS="{aes_str}"')
    print("-" * 60)
    print(f"\n  Assignment IDs (for admin UI / teardown): {asgn_str}")
    print()


def cmd_teardown(args: argparse.Namespace) -> None:  # noqa: ARG001
    if not STATE_FILE.exists():
        print(f"[teardown] No state file found at {STATE_FILE}. Nothing to do.")
        return

    state: dict = json.loads(STATE_FILE.read_text())
    host: str = state["host"]
    assignments: list[dict] = state.get("assignments", [])
    run_label: str = state.get("run_label", "?")

    session_cookie = (os.getenv("LOADTEST_SESSION_COOKIE") or "").strip()
    if not session_cookie:
        print("[error] LOADTEST_SESSION_COOKIE env var is required for teardown")
        sys.exit(1)

    session = _make_session(session_cookie)

    print(f"\n[teardown] Host:       {host}")
    print(f"[teardown] Run label:  {run_label}")
    print(f"[teardown] Assignments: {len(assignments)}\n")

    failed: list[int] = []
    for item in assignments:
        assignment_id: int = item["assignment_id"]
        aes_ids: list[int] = item.get("aes_ids", [])
        print(f"  Deleting AssignedForm {assignment_id} (AES IDs: {aes_ids}) ...", end=" ", flush=True)
        try:
            csrf = _get_csrf(session, host)
            ok = _delete_assignment(session, host, csrf, assignment_id)
            print("OK" if ok else "FAILED (unexpected status)")
            if not ok:
                failed.append(assignment_id)
        except Exception as exc:
            print(f"ERROR — {exc}")
            failed.append(assignment_id)

    if failed:
        print(f"\n[teardown] WARNING: {len(failed)} assignment(s) could not be deleted: {failed}")
        print(f"[teardown] State file kept at {STATE_FILE} — retry teardown after fixing the issue.")
    else:
        STATE_FILE.unlink()
        print(f"\n[teardown] Done — all assignments deleted, {STATE_FILE.name} removed.")
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Create / remove dedicated [LOADTEST] assignments on Backoffice staging.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="command", required=True)

    setup_p = sub.add_parser("setup", help="Create dedicated load-test assignments")
    setup_p.add_argument("--template-id", type=int, default=0, metavar="ID",
                         help="FormTemplate ID (must have a published version)")
    setup_p.add_argument("--country-ids", type=lambda v: [int(x) for x in v.split(",") if x.strip()],
                         default=[], metavar="1,2,…",
                         help="Comma-separated country IDs to add per assignment")
    setup_p.add_argument("--count", type=int, default=3, metavar="N",
                         help="Number of AssignedForms to create (default 3)")

    sub.add_parser("teardown", help="Delete all assignments created by the last setup run")

    return p


if __name__ == "__main__":
    parser = _build_parser()
    parsed = parser.parse_args()
    if parsed.command == "setup":
        cmd_setup(parsed)
    elif parsed.command == "teardown":
        cmd_teardown(parsed)
