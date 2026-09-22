"""Locust load test for the Humanitarian Databank Backoffice (staging).

Designed to be the single test plan executed by Azure Load Testing
(see ``azure/loadtest/loadtest.config.yaml``) and runnable locally from
``Backoffice/`` with::

    locust -f azure/loadtest/locustfile.py -u 10 -r 2 --run-time 1m

Defaults to the staging host. The script will refuse to run against the
production host (``databank.ifrc.org``) unless ``LOADTEST_ALLOW_PROD=true`` is set.

Authentication
--------------
Staging is fronted by Azure AD B2C SSO (``auth.azure_login`` -> OIDC + PKCE
against ``<tenant>.b2clogin.com``). The interactive B2C flow cannot be
scripted from Locust, and B2C-provisioned users have no usable local
password, so the legacy Flask-WTF ``POST /login`` form flow is NOT used
here.

Instead we exercise:

1. Unauthenticated health endpoints (always run):
     - GET /health
     - GET /api/ai/v2/health   (200 or 503 both accepted - 503 just means
                                 OPENAI/AI is not configured in the env)

2. Bearer-authenticated /api/v1 reads (only when ``LOADTEST_API_KEY``
   is set in the environment). Mint a dedicated read-only key in the
   staging Backoffice admin UI and pass it as
   ``Authorization: Bearer <key>``. Targets mirror the k6 suite at
   ``k6-load-tests/scenarios/api-v1-reads.js`` so results are comparable:
     - GET /api/v1/countrymap
     - GET /api/v1/templates

If you also need to exercise authenticated session-only routes, capture a
post-B2C ``session=...`` cookie from a real browser and inject it via the
``LOADTEST_SESSION_COOKIE`` env var.

When ``LOADTEST_SESSION_COOKIE`` is provided, lightweight navigation traffic
is enabled:
    - GET /                         (dashboard)
    - GET /documents                (documents/resources landing page)
    - GET /help/docs[/<doc_path>]   (help/documentation pages)

Environment variables (all namespaced with ``LOADTEST_`` so they do not
collide with existing ``HOST``/``API_KEY`` values in ``Backoffice/.env``):
    LOADTEST_HOST                  full URL of target host (default staging)
    LOADTEST_API_KEY               Backoffice Bearer API key (optional)
    LOADTEST_SESSION_COOKIE        captured post-B2C session cookie (optional)
    LOADTEST_HELP_DOC_PATH         optional extensionless help-doc path under
                                   /help/docs (e.g. "user-guides/common/navigation")
    LOADTEST_ASSIGNMENT_AES_IDS    comma-separated AES IDs kept permanently
                                   "In Progress" for save/document
                                   traffic (e.g. "123,456").  These must NOT
                                   be submitted during the run.
    LOADTEST_DOCUMENT_IDS          comma-separated submitted_document_id values
                                   to exercise GET /forms/download_document/<id>
    LOADTEST_DI_SECTION_ID         a single section_id whose section_type is
                                   'dynamic_indicators' (enables render-pending)
    LOADTEST_DI_INDICATOR_BANK_ID  a single indicator_bank_id valid for the
                                   above section (enables render-pending)
    LOADTEST_AUTO_SETUP            set to ``true`` to automatically create dedicated
                                   [LOADTEST] assignments before the run and delete
                                   them (+ all accumulated FormData) after.  Requires
                                   LOADTEST_SESSION_COOKIE only — template/country IDs
                                   are auto-discovered when not set.  When enabled,
                                   LOADTEST_ASSIGNMENT_AES_IDS is set automatically
                                   and must NOT be set manually.
                                   Assignments created with a ``[LOADTEST]`` period
                                   name prefix are silenced server-side: no
                                   notifications or emails are dispatched for them.
    LOADTEST_SETUP_TEMPLATE_ID     FormTemplate ID to use when auto-creating assignments
                                   (optional — auto-discovered from /api/v1/templates).
    LOADTEST_SETUP_COUNTRY_IDS     Comma-separated country IDs added per assignment
                                   during auto-setup (default: 193 Testland).
    LOADTEST_DEFAULT_COUNTRY_ID    Preferred country when auto-discovering (default 193).
    LOADTEST_SETUP_COUNT           Number of AssignedForms to create (default 3).
    LOADTEST_COUNTRY_ID            Optional override for dashboard data-quality tasks
                                   (default: Testland 193 from auto-setup).
    LOADTEST_DQ_TEMPLATE_ID        Optional override for dashboard/matrix template id.
    LOADTEST_DQ_PERIOD             Optional override for dashboard/matrix period name.
    LOADTEST_MATRIX_FORM_ITEM_IDS  Optional override for matrix auto-load batch items.
    LOADTEST_MATRIX_SOURCE_TEMPLATE_ID  Source template for auto-load batch (default: discovered).
    LOADTEST_MATRIX_SOURCE_PERIOD       Source period name for auto-load batch (default: discovered).
    LOADTEST_ROW_ENTITY_IDS        Optional override for variables/resolve batch rows.
    LOADTEST_PROFILE_USER_IDS      Optional override for profile-summary hover cards.
    LOADTEST_LOOKUP_LIST_ID        Lookup list for matrix search/options (default country_map).
    LOADTEST_ALLOW_PROD            set to ``true`` to allow targeting production
    ENABLE_LOGGING                 ``true``/``false`` to toggle DEBUG logging
    LOADTEST_FAILURE_BODY_MAX      max response body chars captured per failure (default 500)
    LOADTEST_FAILURE_SAMPLES_PER_ENDPOINT  retained samples per endpoint name (default 5)
    LOADTEST_FAILURE_SUMMARY_PATH  write JSON summary here at test end (default failure_summary.json)

Notification / email suppression
---------------------------------
All assignments created with a ``[LOADTEST]`` period-name prefix are silenced
server-side: ``notify_assignment_created`` and ``notify_assignment_submitted``
return early without dispatching any in-app notifications or emails.  This
means setup, teardown, and every focal-point action exercised during the run
will never trigger messages to real users.

Full form submission (``action=submit``) is intentionally excluded from the
load test because it is an infrequent workflow-completion action and the
primary source of admin email notifications.  The test targets only the
high-frequency focal-point interactions: page loads and AJAX data saves.

When both ``LOADTEST_SESSION_COOKIE`` and ``LOADTEST_ASSIGNMENT_AES_IDS`` are
provided, the script exercises the focal-point entry-form surface:
    - GET  /forms/assignment/<aes_id>                           (page load)
    - GET  /forms/assignment/<aes_id>?ajax=1                    (document-upload state refresh)
    - POST /forms/assignment/<aes_id>?ajax=1  (action=save)     (AJAX auto-save)

When ``LOADTEST_DOCUMENT_IDS`` is provided:
    - GET  /forms/download_document/<doc_id>    (document file download)

When ``LOADTEST_DI_SECTION_ID`` + ``LOADTEST_DI_INDICATOR_BANK_ID`` are provided:
    - POST /api/forms/dynamic-indicators/render-pending   (dynamic indicator render)

With ``LOADTEST_SESSION_COOKIE`` (and auto-setup or pre-set AES IDs), additional
dashboard and entry-form secondary APIs are exercised automatically after
parameter discovery at test start:
    - GET  /notifications/api/count, /preferences, /notifications/api, /stream/status
    - GET  /api/v1/csrf-token
    - GET  /api/forms/assignment/<aes_id>/entry-bootstrap
    - POST /api/forms/presence/assignment/<aes_id>/sync
    - GET  /api/forms/assignment/<aes_id>/completion-rate
    - GET  /api/v1/dashboard/data-quality
    - POST /load_more_activities
    - GET  /api/users/profile-summary
    - POST /api/v1/variables/resolve
    - POST /api/v1/matrix/auto-load-entities/batch
    - GET  /api/forms/lookup-lists/<id>/options
    - POST /forms/matrix/search-rows
    - GET  /admin/plugins/emergency_operations/api/operations, /operations/live, /list-data
    - GET  /sw.js
"""

import json
import logging
import os
import re
import threading
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

import requests as _req
from locust import HttpUser, between, events, task

# Mutable state populated by _on_test_start; read by _on_test_stop.
_auto_setup_state: dict = {}

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optional in the load test image
    def load_dotenv(*_args, **_kwargs):
        return None


load_dotenv()


DEFAULT_HOST = "https://databank-stage.ifrc.org"
PROD_HOST_FRAGMENTS = ("databank.ifrc.org",)
CSRF_TOKEN_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
_METADATA_CONTEXT_RE = re.compile(
    r'id="metadata-context-data"[^>]*>\s*(\{.*?\})\s*</script>',
    re.DOTALL,
)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_list_env(name: str) -> list[int]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return []
    values: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            value = int(token)
            if value > 0:
                values.append(value)
        except ValueError:
            continue
    return values


def _int_or_none(name: str) -> "int | None":
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
        return value if value > 0 else None
    except ValueError:
        return None


def _resolved_host() -> str:
    # NOTE: deliberately namespaced with LOADTEST_ to avoid clashing with the
    # generic ``HOST`` variable that the Backoffice .env already uses for
    # other purposes (e.g. DB host).
    host = (os.getenv("LOADTEST_HOST") or DEFAULT_HOST).strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        raise RuntimeError(
            f"LOADTEST_HOST must include scheme (http:// or https://). Got: {host!r}"
        )
    parsed = urlsplit(host)
    netloc = (parsed.netloc or "").lower()
    is_prod = any(frag in netloc for frag in PROD_HOST_FRAGMENTS) and "stage" not in netloc
    if is_prod and not _bool_env("LOADTEST_ALLOW_PROD"):
        raise RuntimeError(
            f"Refusing to load-test production host {netloc!r}. "
            "Set LOADTEST_ALLOW_PROD=true to override (requires ops sign-off)."
        )
    return host


# Prod App Gateway WAF blocks the default ``python-requests/x.x.x`` User-Agent.
# Locust and auto-setup must send a browser-like UA or requests get 403 before Flask.
_LOADTEST_USER_AGENT = (
    (os.getenv("LOADTEST_USER_AGENT") or "").strip()
    or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
)

_FAILURE_HEADER_KEYS = (
    "Server",
    "Date",
    "Content-Type",
    "Retry-After",
    "X-Request-Id",
    "X-Correlation-Id",
    "Request-Id",
    "X-App-Origin",
    "Via",
    "X-Azure-Ref",
    "X-MS-Ref",
)
_FAILURE_BODY_MAX = max(100, _int_or_none("LOADTEST_FAILURE_BODY_MAX") or 500)
_FAILURE_SAMPLES_CAP = max(1, _int_or_none("LOADTEST_FAILURE_SAMPLES_PER_ENDPOINT") or 5)
_FAILURE_SUMMARY_PATH = (
    (os.getenv("LOADTEST_FAILURE_SUMMARY_PATH") or "failure_summary.json").strip()
    or "failure_summary.json"
)
_failure_lock = threading.Lock()
_failure_counts: dict[str, int] = defaultdict(int)
_failure_samples: dict[str, list[dict]] = {}


def _response_elapsed_ms(response) -> float | None:
    meta = getattr(response, "request_meta", None) or {}
    if meta.get("response_time") is not None:
        try:
            return float(meta["response_time"])
        except (TypeError, ValueError):
            pass
    elapsed = getattr(response, "elapsed", None)
    if elapsed is not None:
        try:
            return elapsed.total_seconds() * 1000.0
        except Exception:
            pass
    return None


def _extract_response_headers(response) -> dict[str, str]:
    raw = getattr(response, "headers", None) or {}
    out: dict[str, str] = {}
    for key in _FAILURE_HEADER_KEYS:
        value = raw.get(key) or raw.get(key.lower())
        if value:
            out[key] = str(value)[:200]
    return out


def _extract_body_snippet(response, max_len: int) -> str:
    text = (getattr(response, "text", None) or "")[: max_len * 2]
    if not text:
        return ""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            slim = {
                k: data[k]
                for k in ("success", "error", "message", "detail", "description")
                if k in data and data[k] not in (None, "")
            }
            if slim:
                return json.dumps(slim, ensure_ascii=False)[:max_len]
            return json.dumps(data, ensure_ascii=False)[:max_len]
    except Exception:
        pass
    title = re.search(r"<title>([^<]{1,160})</title>", text, re.IGNORECASE)
    if title:
        return f"html_title={title.group(1).strip()[:120]}"
    return " ".join(text.split())[:max_len]


def _infer_failure_kind(status: int, elapsed_ms: float | None) -> str:
    if status == 0:
        return "connection_or_timeout"
    if status in (502, 503, 504):
        return "gateway_or_platform"
    if status >= 500:
        if elapsed_ms is not None and elapsed_ms >= 25000:
            return "server_error_very_slow"
        if elapsed_ms is not None and elapsed_ms >= 8000:
            return "server_error_slow"
        return "server_error"
    if status == 429:
        return "rate_limited"
    if status >= 400:
        return "client_error"
    return "unexpected_status"


def _saturation_hint(status: int, elapsed_ms: float | None, kind: str) -> str | None:
    hints: list[str] = []
    if kind == "connection_or_timeout":
        hints.append("client_timeout_or_connection_reset")
    if elapsed_ms is not None:
        if elapsed_ms >= 85000:
            hints.append("near_locust_client_timeout")
        elif elapsed_ms >= 25000:
            hints.append("very_slow_likely_gateway_or_stuck_worker")
        elif elapsed_ms >= 8000:
            hints.append("slow_likely_thread_queue_wait")
    if status in (500, 502, 503, 504) and elapsed_ms is not None and elapsed_ms >= 5000:
        hints.append("platform_error_after_long_wait")
    if status == 500 and not hints:
        hints.append("opaque_500_see_server_stuck_request_logs")
    return "; ".join(hints) if hints else None


def _request_url(response) -> str | None:
    req = getattr(response, "request", None)
    if req is None:
        return None
    url = getattr(req, "url", None) or getattr(req, "path_url", None)
    return str(url)[-240:] if url else None


def _record_exception_failure(name: str, *, exception: BaseException, response_time: float | None) -> None:
    sample = {
        "at": datetime.now(timezone.utc).isoformat(),
        "endpoint": name,
        "kind": "connection_or_timeout",
        "status": 0,
        "elapsed_ms": round(response_time, 1) if response_time is not None else None,
        "connection_error": str(exception)[:400],
        "saturation_hint": _saturation_hint(0, response_time, "connection_or_timeout"),
    }
    with _failure_lock:
        _failure_counts[name] += 1
        bucket = _failure_samples.setdefault(name, [])
        if len(bucket) < _FAILURE_SAMPLES_CAP:
            bucket.append(sample)
    logging.getLogger("locust").error(
        "[loadtest-failure] %s exception: %s elapsed_ms=%s",
        name,
        exception,
        sample["elapsed_ms"],
    )


def report_http_failure(
    response,
    name: str,
    *,
    detail: str = "",
) -> str:
    """Record rich failure context and return a Locust failure message."""
    status = int(getattr(response, "status_code", 0) or 0)
    elapsed_ms = _response_elapsed_ms(response)
    headers = _extract_response_headers(response)
    body = _extract_body_snippet(response, _FAILURE_BODY_MAX)
    kind = _infer_failure_kind(status, elapsed_ms)
    conn_err = getattr(response, "error", None)
    req = getattr(response, "request", None)
    method = getattr(req, "method", None) if req is not None else None

    sample = {
        "at": datetime.now(timezone.utc).isoformat(),
        "endpoint": name,
        "method": method,
        "kind": kind,
        "status": status,
        "elapsed_ms": round(elapsed_ms, 1) if elapsed_ms is not None else None,
        "url": _request_url(response),
        "detail": detail or None,
        "headers": headers or None,
        "body": body or None,
        "connection_error": str(conn_err)[:400] if conn_err else None,
        "saturation_hint": _saturation_hint(status, elapsed_ms, kind),
    }

    with _failure_lock:
        _failure_counts[name] += 1
        bucket = _failure_samples.setdefault(name, [])
        if len(bucket) < _FAILURE_SAMPLES_CAP:
            bucket.append(sample)

    parts = [
        f"{name} failed",
        f"kind={kind}",
        f"status={status}",
    ]
    if elapsed_ms is not None:
        parts.append(f"elapsed_ms={round(elapsed_ms, 1)}")
    if sample["saturation_hint"]:
        parts.append(f"hint={sample['saturation_hint']}")
    if detail:
        parts.append(f"detail={detail}")
    if body:
        parts.append(f"body={body!r}")
    elif status:
        parts.append("body=''")
    if headers:
        parts.append(f"headers={headers}")
    if conn_err:
        parts.append(f"conn_err={conn_err}")

    msg = " ".join(parts)
    if _bool_env("ENABLE_LOGGING", default=True):
        logging.getLogger("locust").error("[loadtest-failure] %s", msg)
    return msg


def write_failure_summary() -> None:
    log = logging.getLogger("locust")
    with _failure_lock:
        if not _failure_counts:
            log.info("[loadtest-failures] No recorded failures.")
            return
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_failures": int(sum(_failure_counts.values())),
            "by_endpoint": {k: int(v) for k, v in sorted(_failure_counts.items())},
            "samples": _failure_samples,
            "notes": (
                "elapsed_ms is client-side round-trip (queue wait + server time). "
                "Worker thread / DB pool state requires App Service console logs "
                "([STUCK_REQUEST], WORKER TIMEOUT) — not available in Locust alone."
            ),
        }

    log.error(
        "[loadtest-failures] SUMMARY total=%d distinct_endpoints=%d",
        summary["total_failures"],
        len(summary["by_endpoint"]),
    )
    for endpoint, samples in sorted(summary["samples"].items()):
        for idx, sample in enumerate(samples, start=1):
            log.error(
                "[loadtest-failures] SAMPLE %s #%d %s",
                endpoint,
                idx,
                json.dumps(sample, ensure_ascii=False, sort_keys=True),
            )

    try:
        with open(_FAILURE_SUMMARY_PATH, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False)
        log.error("[loadtest-failures] Wrote %s", _FAILURE_SUMMARY_PATH)
    except OSError as exc:
        log.warning("[loadtest-failures] Could not write %s: %s", _FAILURE_SUMMARY_PATH, exc)


@events.request.add_listener
def _on_locust_request(
    request_type,
    name,
    response_time,
    response_length,
    response,
    context,
    exception,
    **kwargs,
) -> None:
    """Capture transport-level failures that never enter catch_response handlers."""
    if exception is None:
        return
    # With catch_response=True (all task helpers), the handler records via _fail_http.
    if response is not None:
        return
    _record_exception_failure(name, exception=exception, response_time=response_time)


# ---------------------------------------------------------------------------
# Admin HTTP helpers used by auto-setup / auto-teardown
# ---------------------------------------------------------------------------

_CSRF_RE = re.compile(
    r'(?:name="csrf_token"[^>]*value="([^"]+)"'
    r'|<meta\s+name="csrf-token"\s+content="([^"]+)")',
    re.IGNORECASE,
)
_EDIT_URL_RE = re.compile(r"/assignments/edit/(\d+)")


def _admin_session(host: str, session_cookie: str) -> "_req.Session":
    s = _req.Session()
    blob = session_cookie.split(";", 1)[0].strip()
    if "=" in blob:
        name, _, value = blob.partition("=")
    else:
        name, value = "session", blob
    parsed = urlsplit(host)
    domain = parsed.hostname or parsed.netloc.split(":")[0]
    s.cookies.set(name.strip() or "session", (value or blob).strip(), domain=domain, path="/")
    s.headers.update({"User-Agent": _LOADTEST_USER_AGENT})
    return s


def _fetch_session_csrf(s: "_req.Session", host: str) -> str | None:
    """Fetch a CSRF token for session-authenticated JSON POSTs (e.g. presence sync)."""
    try:
        resp = s.get(
            f"{host}/api/v1/csrf-token",
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("csrf_token")
    except Exception:
        pass
    return None


def _admin_csrf(s: "_req.Session", host: str) -> str:
    resp = s.get(f"{host}/admin/", timeout=30)
    resp.raise_for_status()
    m = _CSRF_RE.search(resp.text)
    if not m:
        raise RuntimeError(
            "CSRF token not found on /admin/ — is LOADTEST_SESSION_COOKIE valid "
            "and does the account have admin access?"
        )
    return m.group(1) or m.group(2)


def _admin_create_assignment(
    s: "_req.Session", host: str, template_id: int, period_name: str
) -> int:
    """GET /admin/assignments/new to obtain the form CSRF, then POST to create.

    Fetching the token from the exact form page being submitted avoids the
    mismatch that occurs when the token is pulled from a different admin page.
    """
    get_resp = s.get(f"{host}/admin/assignments/new", timeout=30)
    get_resp.raise_for_status()
    m_csrf = _CSRF_RE.search(get_resp.text)
    if not m_csrf:
        raise RuntimeError(
            "CSRF token not found on /admin/assignments/new -- "
            "is the session cookie valid and does the account have admin access?"
        )
    csrf = m_csrf.group(1) or m_csrf.group(2)

    form_url = f"{host}/admin/assignments/new"
    resp = s.post(
        form_url,
        data={
            "csrf_token": csrf,
            "template_id": str(template_id),
            "period_name": period_name,
            "confirm_duplicate": "1",
        },
        headers={"Referer": form_url},
        allow_redirects=False,
        timeout=30,
    )
    if resp.status_code not in (301, 302):
        raise RuntimeError(
            f"create_assignment HTTP {resp.status_code}: {resp.text[:300]}"
        )
    location = resp.headers.get("Location", "")
    m = _EDIT_URL_RE.search(location)
    if m:
        return int(m.group(1))
    # Fallback: server redirected to the listing page (pre-deploy behaviour).
    # Recover the new assignment ID via the duplicate-check endpoint, which
    # returns the ID for an existing template+period combination.
    chk = s.get(
        f"{host}/admin/assignments/check_duplicate",
        params={"template_id": template_id, "period_name": period_name},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if chk.status_code == 200:
        data = chk.json()
        if data.get("exists") and data.get("assignment", {}).get("id"):
            return int(data["assignment"]["id"])
    raise RuntimeError(
        f"Could not parse assignment ID from redirect: {location!r}; "
        f"fallback check_duplicate also failed (HTTP {chk.status_code})"
    )


def _admin_add_entity(
    s: "_req.Session",
    host: str,
    csrf: str,
    assignment_id: int,
    entity_type: str,
    entity_id: int,
) -> int:
    edit_url = f"{host}/admin/assignments/edit/{assignment_id}"
    resp = s.post(
        f"{host}/admin/assignments/{assignment_id}/entities/add",
        json={"entity_type": entity_type, "entity_id": entity_id},
        headers={
            "X-CSRFToken": csrf,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": edit_url,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"add_entity HTTP {resp.status_code}: {resp.text[:200]}"
        )
    return int(resp.json()["status_id"])


def _admin_activate_aes(
    s: "_req.Session", host: str, csrf: str, assignment_id: int, aes_id: int
) -> None:
    edit_url = f"{host}/admin/assignments/edit/{assignment_id}"
    resp = s.put(
        f"{host}/admin/assignments/{assignment_id}/entities/{aes_id}",
        json={"status": "In Progress"},
        headers={
            "X-CSRFToken": csrf,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": edit_url,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"activate_aes HTTP {resp.status_code}: {resp.text[:200]}")


def _admin_delete_assignment(
    s: "_req.Session", host: str, csrf: str, assignment_id: int
) -> None:
    delete_url = f"{host}/admin/assignments/delete/{assignment_id}"
    s.post(
        delete_url,
        data={"csrf_token": csrf},
        headers={"Referer": delete_url},
        allow_redirects=False,
        timeout=30,
    )


_AUTO_LOAD_TEMPLATE_HINTS = (
    "fdrs",
    "upr",
    "emergency",
    "appeal",
    "matrix",
    "reporting",
)
# Dedicated test country on staging and prod — avoid real countries (e.g. Afghanistan id 1).
_DEFAULT_LOADTEST_COUNTRY_ID = 193
_LOADTEST_COUNTRY_NAME_HINTS = ("testland",)


def _preferred_loadtest_country_id() -> int:
    return _int_or_none("LOADTEST_DEFAULT_COUNTRY_ID") or _DEFAULT_LOADTEST_COUNTRY_ID


def _discover_template_id(s: "_req.Session", host: str) -> int:
    """Pick a published template, preferring names likely to contain auto-load matrices."""
    resp = s.get(
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
            "No templates returned by /api/v1/templates — does the session account "
            "have access to at least one published template?"
        )

    def _score(t: dict) -> tuple[int, int]:
        name = (t.get("name") or "").lower()
        hint = any(h in name for h in _AUTO_LOAD_TEMPLATE_HINTS)
        items = int(t.get("items_count") or 0)
        return (1 if hint else 0, items)

    best = max(valid, key=_score)
    return int(best["id"])


def _discover_current_user_id(s: "_req.Session", host: str) -> int | None:
    """Return the logged-in user id via GET /api/v1/user/profile."""
    try:
        resp = s.get(
            f"{host}/api/v1/user/profile",
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code == 200:
            uid = resp.json().get("id")
            if uid is not None:
                return int(uid)
    except Exception:
        pass
    return None


def _apply_entry_bootstrap_payload(payload: dict) -> tuple[list[int], list[int]]:
    """Extract matrix form_item_ids and row_entity_ids from an entry-bootstrap body."""
    auto_load = payload.get("auto_load") or {}
    form_item_ids = [int(k) for k in auto_load.keys() if str(k).isdigit()]
    row_entity_ids: list[int] = []
    for block in auto_load.values():
        if not isinstance(block, dict):
            continue
        for ent in block.get("entities") or []:
            if isinstance(ent, dict) and ent.get("entity_id") is not None:
                try:
                    row_entity_ids.append(int(ent["entity_id"]))
                except (TypeError, ValueError):
                    pass
    resolved = payload.get("resolved_variables") or {}
    for key in resolved.keys():
        if str(key).isdigit():
            row_entity_ids.append(int(key))
    return form_item_ids, list(dict.fromkeys(row_entity_ids))[:20]


def _discover_matrix_from_peer_assignments(
    s: "_req.Session",
    host: str,
    *,
    country_id: int | None,
) -> dict | None:
    """Find matrix auto-load params from an existing non-[LOADTEST] assignment (admin JSON APIs)."""
    try:
        resp = s.get(
            f"{host}/admin/assignments",
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        assignments = resp.json().get("assignments") or []
    except Exception:
        return None

    for asn in assignments:
        period_name = (asn.get("period_name") or "").strip()
        if period_name.startswith("[LOADTEST]"):
            continue
        assignment_id = asn.get("id")
        template_id = asn.get("template_id")
        if not assignment_id or not template_id:
            continue
        try:
            ent_resp = s.get(
                f"{host}/admin/assignments/{assignment_id}/entities",
                headers={"Accept": "application/json"},
                timeout=30,
            )
            if ent_resp.status_code != 200:
                continue
            entities = ent_resp.json().get("entities") or []
        except Exception:
            continue

        for ent in entities:
            if country_id is not None:
                if ent.get("entity_type") != "country" or int(ent.get("entity_id") or 0) != country_id:
                    continue
            aes_id = ent.get("status_id")
            if not aes_id:
                continue
            try:
                boot = s.get(
                    f"{host}/api/forms/assignment/{aes_id}/entry-bootstrap",
                    headers={"Accept": "application/json"},
                    timeout=30,
                )
                if boot.status_code != 200:
                    continue
                form_item_ids, row_entity_ids = _apply_entry_bootstrap_payload(boot.json())
                if not form_item_ids:
                    continue
                return {
                    "template_id": int(template_id),
                    "period": period_name,
                    "matrix_form_item_ids": form_item_ids,
                    "row_entity_ids": row_entity_ids,
                    "matrix_source_template_id": int(template_id),
                    "matrix_source_period": period_name,
                    "peer_aes_id": int(aes_id),
                }
            except Exception:
                continue
    return None


def _discover_country_id(s: "_req.Session", host: str) -> int:
    """Return Testland (id 193) when present, else first country from /api/v1/countrymap."""
    resp = s.get(
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

    preferred_id = _preferred_loadtest_country_id()
    for c in valid:
        if int(c["id"]) == preferred_id:
            return preferred_id

    for c in valid:
        name = (c.get("name") or "").lower()
        if any(h in name for h in _LOADTEST_COUNTRY_NAME_HINTS):
            return int(c["id"])

    return int(valid[0]["id"])


def _discover_entry_metadata(s: "_req.Session", host: str, aes_id: int) -> dict:
    """Load entry form HTML and parse ``metadata-context-data`` JSON."""
    resp = s.get(
        f"{host}/forms/assignment/{aes_id}",
        headers={"Accept": "text/html"},
        timeout=30,
    )
    if resp.status_code != 200:
        return {}
    match = _METADATA_CONTEXT_RE.search(resp.text or "")
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
        return payload if isinstance(payload, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _post_setup_discover(
    s: "_req.Session",
    host: str,
    aes_id: int,
    template_id: int | None,
    period: str | None,
    country_id: int | None,
) -> None:
    """One discovery round-trip after assignments are known.

    Stores into ``_auto_setup_state``:
      template_id, period, country_id  — dashboard / matrix context
      matrix_form_item_ids             — matrix auto-load batch sub-requests
      row_entity_ids                   — variables/resolve batch mode
      profile_user_ids                 — profile-summary hover cards
    """
    log = logging.getLogger("locust")

    meta = _discover_entry_metadata(s, host, aes_id)
    if meta:
        if not template_id and meta.get("template_id") is not None:
            try:
                template_id = int(meta["template_id"])
            except (TypeError, ValueError):
                pass
        if not period:
            period = (meta.get("assignment_period") or "").strip() or None
        if not country_id and meta.get("entity_type") == "country" and meta.get("entity_id") not in (None, ""):
            try:
                country_id = int(meta["entity_id"])
            except (TypeError, ValueError):
                pass

    row_entity_ids: list[int] = []
    try:
        resp = s.get(
            f"{host}/api/forms/assignment/{aes_id}/entry-bootstrap",
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code == 200:
            payload = resp.json()
            form_item_ids, row_entity_ids = _apply_entry_bootstrap_payload(payload)
            if form_item_ids:
                _auto_setup_state["matrix_form_item_ids"] = form_item_ids
                if template_id and period:
                    _auto_setup_state.setdefault("matrix_source_template_id", template_id)
                    _auto_setup_state.setdefault("matrix_source_period", period)
            if row_entity_ids:
                _auto_setup_state["row_entity_ids"] = row_entity_ids
            log.info(
                "[discovery] entry-bootstrap: matrix_form_item_ids=%s row_entity_ids=%s",
                form_item_ids,
                _auto_setup_state.get("row_entity_ids", []),
            )
        else:
            log.warning("[discovery] entry-bootstrap returned HTTP %d", resp.status_code)
    except Exception as exc:
        log.warning("[discovery] entry-bootstrap failed: %s", exc)

    if not _auto_setup_state.get("matrix_form_item_ids"):
        peer = _discover_matrix_from_peer_assignments(
            s, host, country_id=country_id
        )
        if peer:
            _auto_setup_state["matrix_form_item_ids"] = peer["matrix_form_item_ids"]
            if peer.get("row_entity_ids"):
                _auto_setup_state["row_entity_ids"] = peer["row_entity_ids"]
            if peer.get("matrix_source_template_id"):
                _auto_setup_state["matrix_source_template_id"] = peer["matrix_source_template_id"]
            if peer.get("matrix_source_period"):
                _auto_setup_state["matrix_source_period"] = peer["matrix_source_period"]
            if not template_id and peer.get("template_id"):
                template_id = peer["template_id"]
            if not period and peer.get("period"):
                period = peer["period"]
            log.info(
                "[discovery] peer-assignment fallback: template_id=%s period=%r "
                "matrix_form_item_ids=%s (peer_aes_id=%s)",
                peer.get("template_id"),
                peer.get("period"),
                peer.get("matrix_form_item_ids"),
                peer.get("peer_aes_id"),
            )

    current_user_id = _discover_current_user_id(s, host)
    if current_user_id is not None:
        _auto_setup_state.setdefault("current_user_id", current_user_id)

    try:
        csrf = _fetch_session_csrf(s, host)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        if csrf:
            headers["X-CSRFToken"] = csrf
        resp = s.post(
            f"{host}/api/forms/presence/assignment/{aes_id}/sync",
            json={},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            users = resp.json().get("users") or []
            user_ids = [int(u["id"]) for u in users if u.get("id")]
            if user_ids:
                _auto_setup_state["profile_user_ids"] = user_ids[:3]
            log.info("[discovery] presence sync: profile_user_ids=%s", user_ids[:3])
    except Exception as exc:
        log.warning("[discovery] presence sync failed: %s", exc)

    if not _auto_setup_state.get("profile_user_ids") and current_user_id is not None:
        _auto_setup_state["profile_user_ids"] = [current_user_id]
        log.info("[discovery] profile_user_ids fallback to current user: %s", current_user_id)

    if template_id:
        _auto_setup_state.setdefault("template_id", template_id)
    if period:
        _auto_setup_state.setdefault("period", period)
    if country_id:
        _auto_setup_state.setdefault("country_id", country_id)


def _run_parameter_discovery(
    host: str,
    session_cookie: str,
    aes_ids: list[int],
    *,
    template_id: int | None = None,
    period: str | None = None,
    country_id: int | None = None,
) -> None:
    """Discover dashboard/matrix params for the first AES id (non-fatal on failure)."""
    if not aes_ids or not session_cookie:
        return
    log = logging.getLogger("locust")
    try:
        session = _admin_session(host, session_cookie)
        _post_setup_discover(
            session,
            host,
            aes_ids[0],
            template_id or _int_or_none("LOADTEST_DQ_TEMPLATE_ID"),
            period or (os.getenv("LOADTEST_DQ_PERIOD") or "").strip() or None,
            country_id or _int_or_none("LOADTEST_COUNTRY_ID"),
        )
    except Exception as exc:
        log.warning("[discovery] Parameter discovery failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Auto-setup: create [LOADTEST] assignments before VUs spawn
# ---------------------------------------------------------------------------

@events.test_start.add_listener
def _on_test_start(environment, **_kwargs) -> None:  # noqa: ANN001
    """Create dedicated [LOADTEST] assignments when LOADTEST_AUTO_SETUP=true.

    Runs once on the master / single-engine process before any VU starts.
    Sets os.environ["LOADTEST_ASSIGNMENT_AES_IDS"] so each VU's on_start
    picks up the IDs automatically (single-engine only; distributed runs
    require a shared config store).

    When auto-setup is disabled, still discovers dashboard/matrix params
    from existing LOADTEST_ASSIGNMENT_AES_IDS when a session cookie is set.
    """
    log = logging.getLogger("locust")
    host = _resolved_host()
    session_cookie = (os.getenv("LOADTEST_SESSION_COOKIE") or "").strip()
    all_aes_ids: list[int] = []
    setup_template_id: int | None = None
    setup_country_id: int | None = None

    if _bool_env("LOADTEST_AUTO_SETUP"):
        template_id = _int_or_none("LOADTEST_SETUP_TEMPLATE_ID")
        country_ids = _int_list_env("LOADTEST_SETUP_COUNTRY_IDS")
        count = max(1, int(os.getenv("LOADTEST_SETUP_COUNT") or "3"))

        if not session_cookie:
            log.warning(
                "[auto-setup] LOADTEST_AUTO_SETUP=true but LOADTEST_SESSION_COOKIE is not set. "
                "Entry-form tasks will be disabled."
            )
            return

        try:
            s = _admin_session(host, session_cookie)

            # Auto-discover template and country when not explicitly configured.
            if not template_id:
                log.info(
                    "[auto-setup] LOADTEST_SETUP_TEMPLATE_ID not set — auto-discovering via /api/v1/templates ..."
                )
                template_id = _discover_template_id(s, host)
                log.info("[auto-setup] Auto-discovered template_id=%d", template_id)

            if not country_ids:
                log.info(
                    "[auto-setup] LOADTEST_SETUP_COUNTRY_IDS not set — auto-discovering via /api/v1/countrymap ..."
                )
                country_ids = [_discover_country_id(s, host)]
                log.info("[auto-setup] Auto-discovered country_ids=%s", country_ids)

            setup_template_id = template_id
            setup_country_id = country_ids[0] if country_ids else None

            log.info(
                "[auto-setup] Creating %d assignment(s) — template=%s countries=%s",
                count, template_id, country_ids,
            )

            run_label = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            created: list[dict] = []

            for i in range(count):
                period_name = f"[LOADTEST] {run_label} #{i + 1}"
                # _admin_create_assignment self-fetches CSRF from the form page.
                assignment_id = _admin_create_assignment(s, host, template_id, period_name)
                log.info("[auto-setup]  AssignedForm ID=%d  %r", assignment_id, period_name)

                # One fresh CSRF fetch covers all entity add/activate calls for this assignment.
                csrf = _admin_csrf(s, host)
                aes_ids: list[int] = []
                for country_id in country_ids:
                    aes_id = _admin_add_entity(s, host, csrf, assignment_id, "country", country_id)
                    _admin_activate_aes(s, host, csrf, assignment_id, aes_id)
                    log.info(
                        "[auto-setup]    country=%d -> AES ID=%d (In Progress)",
                        country_id, aes_id,
                    )
                    aes_ids.append(aes_id)

                created.append({
                    "assignment_id": assignment_id,
                    "aes_ids": aes_ids,
                    "period_name": period_name,
                })

            all_aes_ids = [aes_id for item in created for aes_id in item["aes_ids"]]
            first_period = created[0]["period_name"] if created else None
            _auto_setup_state.update({
                "host": host,
                "session_cookie": session_cookie,
                "assignments": created,
                "all_aes_ids": all_aes_ids,
                "template_id": setup_template_id,
                "country_id": setup_country_id,
                "period": first_period,
            })

            # Inject into os.environ so VU on_start reads them (single-engine).
            os.environ["LOADTEST_ASSIGNMENT_AES_IDS"] = ",".join(str(x) for x in all_aes_ids)
            log.info(
                "[auto-setup] Done. LOADTEST_ASSIGNMENT_AES_IDS=%s",
                os.environ["LOADTEST_ASSIGNMENT_AES_IDS"],
            )

            _run_parameter_discovery(
                host,
                session_cookie,
                all_aes_ids,
                template_id=setup_template_id,
                period=first_period,
                country_id=setup_country_id,
            )

        except Exception as exc:
            log.error("[auto-setup] FAILED: %s", exc, exc_info=True)
            raise SystemExit(f"[auto-setup] Cannot continue without test data: {exc}") from exc
        return

    all_aes_ids = _int_list_env("LOADTEST_ASSIGNMENT_AES_IDS")
    if all_aes_ids and session_cookie:
        _run_parameter_discovery(
            host,
            session_cookie,
            all_aes_ids,
            template_id=_int_or_none("LOADTEST_DQ_TEMPLATE_ID"),
            period=(os.getenv("LOADTEST_DQ_PERIOD") or "").strip() or None,
            country_id=_int_or_none("LOADTEST_COUNTRY_ID"),
        )


# ---------------------------------------------------------------------------
# Auto-teardown: delete [LOADTEST] assignments after the run
# ---------------------------------------------------------------------------

@events.test_stop.add_listener
def _on_test_stop(environment, **_kwargs) -> None:  # noqa: ANN001
    """Delete all assignments created by _on_test_start."""
    write_failure_summary()

    if not _auto_setup_state:
        return

    log = logging.getLogger("locust")
    host = _auto_setup_state["host"]
    session_cookie = _auto_setup_state["session_cookie"]
    assignments: list[dict] = _auto_setup_state.get("assignments", [])

    log.info("[auto-teardown] Deleting %d assignment(s)...", len(assignments))
    try:
        s = _admin_session(host, session_cookie)
        for item in assignments:
            assignment_id: int = item["assignment_id"]
            try:
                csrf = _admin_csrf(s, host)
                _admin_delete_assignment(s, host, csrf, assignment_id)
                log.info("[auto-teardown] Deleted assignment %d", assignment_id)
            except Exception as exc:
                log.error(
                    "[auto-teardown] Failed to delete assignment %d: %s",
                    assignment_id, exc,
                )
    except Exception as exc:
        log.error("[auto-teardown] Session error: %s", exc)

    _auto_setup_state.clear()
    log.info("[auto-teardown] Done.")


@events.init.add_listener
def _on_locust_init(environment, **_kwargs):
    """Validate config once at startup, before any user spawns."""
    try:
        host = _resolved_host()
    except RuntimeError as exc:
        environment.runner.quit() if environment.runner else None
        raise SystemExit(f"[locust] config error: {exc}") from exc

    api_key = (os.getenv("LOADTEST_API_KEY") or "").strip()
    logging.getLogger("locust").info(
        "[locust] host=%s api_key_present=%s", host, bool(api_key)
    )


class BackofficeUser(HttpUser):
    """Read-only smoke user for the Backoffice."""

    wait_time = between(1, 3)
    host = _resolved_host()
    timeout_duration = 90  # seconds

    def on_start(self) -> None:
        self.enable_logging = _bool_env("ENABLE_LOGGING", default=True)
        logging.basicConfig(
            level=logging.DEBUG if self.enable_logging else logging.WARNING,
            format="%(asctime)s %(levelname)s %(message)s",
        )

        self.api_key = (os.getenv("LOADTEST_API_KEY") or "").strip()
        self.session_cookie = (os.getenv("LOADTEST_SESSION_COOKIE") or "").strip()
        self.help_doc_path = (os.getenv("LOADTEST_HELP_DOC_PATH") or "").strip().strip("/")

        # --- Save pool (kept In Progress throughout the run) ---
        self.assignment_aes_ids = _int_list_env("LOADTEST_ASSIGNMENT_AES_IDS")
        self._assignment_rr_idx = -1
        self._entry_csrf_tokens: dict[int, str] = {}

        # --- Document download pool ---
        self.document_ids = _int_list_env("LOADTEST_DOCUMENT_IDS")
        self._document_rr_idx = -1

        # --- Dynamic indicator render params ---
        self._di_section_id: int | None = _int_or_none("LOADTEST_DI_SECTION_ID")
        self._di_indicator_bank_id: int | None = _int_or_none("LOADTEST_DI_INDICATOR_BANK_ID")

        # --- Auto-discovered dashboard / matrix params (env-var override supported) ---
        self._country_id: int | None = (
            _auto_setup_state.get("country_id") or _int_or_none("LOADTEST_COUNTRY_ID")
        )
        self._dq_template_id: int | None = (
            _auto_setup_state.get("template_id") or _int_or_none("LOADTEST_DQ_TEMPLATE_ID")
        )
        self._dq_period: str = (
            _auto_setup_state.get("period") or os.getenv("LOADTEST_DQ_PERIOD") or ""
        )
        self._matrix_form_item_ids: list[int] = (
            _auto_setup_state.get("matrix_form_item_ids")
            or _int_list_env("LOADTEST_MATRIX_FORM_ITEM_IDS")
        )
        self._row_entity_ids: list[int] = (
            _auto_setup_state.get("row_entity_ids")
            or _int_list_env("LOADTEST_ROW_ENTITY_IDS")
        )
        self._profile_user_ids: list[int] = (
            _auto_setup_state.get("profile_user_ids")
            or _int_list_env("LOADTEST_PROFILE_USER_IDS")
        )
        self._matrix_source_template_id: int | None = (
            _auto_setup_state.get("matrix_source_template_id")
            or _int_or_none("LOADTEST_MATRIX_SOURCE_TEMPLATE_ID")
            or self._dq_template_id
        )
        self._matrix_source_period: str = (
            _auto_setup_state.get("matrix_source_period")
            or (os.getenv("LOADTEST_MATRIX_SOURCE_PERIOD") or "").strip()
            or self._dq_period
        )
        self._lookup_list_id: str = (
            (os.getenv("LOADTEST_LOOKUP_LIST_ID") or "").strip() or "country_map"
        )
        self._matrix_batch_params: dict[int, list[int]] = {}
        self._dashboard_csrf_token: str = ""
        self._api_csrf_token: str = ""

        # ETag cache: maps endpoint path -> last ETag value received.
        # Sent as If-None-Match on subsequent requests so the server can return
        # 304 Not Modified (zero body transfer) when the data hasn't changed.
        self._etag_cache: dict[str, str] = {}

        # Session + entry-form traffic flags
        self.navigation_focus_enabled = bool(self.session_cookie)
        self.entry_focus_enabled = bool(self.assignment_aes_ids and self.session_cookie)
        self.document_focus_enabled = bool(self.document_ids and self.session_cookie)
        self.di_focus_enabled = bool(
            self._di_section_id and self._di_indicator_bank_id and self.session_cookie
        )
        self.notification_focus_enabled = bool(self.session_cookie)
        self.emops_focus_enabled = bool(self.session_cookie)
        self.dashboard_focus_enabled = bool(
            self.session_cookie
            and self._country_id
            and self._dq_template_id
            and self._dq_period
        )
        self.matrix_focus_enabled = bool(self.entry_focus_enabled)
        self.matrix_batch_enabled = bool(
            self.entry_focus_enabled
            and self._matrix_form_item_ids
            and self._matrix_source_template_id
            and self._matrix_source_period
        )
        self.profile_focus_enabled = bool(
            self.session_cookie and self._profile_user_ids
        )

        if self.session_cookie:
            # Validate the cookie is latin-1 safe before injecting it.
            # HTTP header values (including Cookie:) must be latin-1 encodable;
            # non-ASCII characters cause a UnicodeEncodeError on every request.
            # This can happen when a cookie is copy-pasted with invisible Unicode
            # chars, or when Azure Load Testing env-var injection corrupts the value.
            try:
                self.session_cookie.encode("latin-1")
            except UnicodeEncodeError as exc:
                bad_char = self.session_cookie[exc.start]
                logging.getLogger("locust").error(
                    "[locust] LOADTEST_SESSION_COOKIE contains a non-ASCII character "
                    "(U+%04X %r) at position %d — the cookie is invalid and will be "
                    "ignored.  Re-capture a fresh session cookie and retry.",
                    ord(bad_char), bad_char, exc.start,
                )
                self.session_cookie = ""
                self.navigation_focus_enabled = False
                self.entry_focus_enabled = False
                self.document_focus_enabled = False
                self.di_focus_enabled = False
                self.notification_focus_enabled = False
                self.emops_focus_enabled = False
                self.dashboard_focus_enabled = False
                self.matrix_focus_enabled = False
                self.matrix_batch_enabled = False
                self.profile_focus_enabled = False

        if self.session_cookie:
            # Inject a previously captured post-B2C Flask session cookie
            # into the per-VU cookie jar so authenticated session routes work.
            # Accept either:
            # - "session=<value>"
            # - raw cookie value (assumes cookie name "session")
            cookie_blob = self.session_cookie.split(";", 1)[0].strip()
            if "=" in cookie_blob:
                cookie_name, _, cookie_value = cookie_blob.partition("=")
            else:
                cookie_name, cookie_value = "session", cookie_blob
            if cookie_name and cookie_value:
                self.client.cookies.set(cookie_name.strip(), cookie_value.strip())

        # WTF_CSRF_SSL_STRICT=True on staging requires a same-origin Referer on
        # every HTTPS mutation (POST/PUT/PATCH/DELETE).  Setting it once as a
        # persistent session header covers all self.client calls without having
        # to add it individually to each task.
        self.client.headers.update({
            "Referer": self.host,
            "User-Agent": _LOADTEST_USER_AGENT,
        })

        if self.assignment_aes_ids and not self.session_cookie:
            logging.getLogger("locust").warning(
                "[locust] LOADTEST_ASSIGNMENT_AES_IDS provided but LOADTEST_SESSION_COOKIE is missing; "
                "entry-form focal-point tasks are disabled."
            )
        if self.document_ids and not self.session_cookie:
            logging.getLogger("locust").warning(
                "[locust] LOADTEST_DOCUMENT_IDS provided but LOADTEST_SESSION_COOKIE is missing; "
                "document download tasks are disabled."
            )

    def _headers(self, *, with_auth: bool = False, accept: str = "application/json", extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": accept}
        if with_auth and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update(extra)
        return headers

    def _fail_http(self, response, name: str, *, detail: str = "") -> None:
        response.failure(report_http_failure(response, name, detail=detail))

    def _get(self, path: str, *, name: str, with_auth: bool, accept: tuple[int, ...] = (200,), accept_header: str = "application/json", extra_headers: dict[str, str] | None = None) -> None:
        with self.client.get(
            path,
            headers=self._headers(with_auth=with_auth, accept=accept_header, extra=extra_headers),
            name=name,
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code in accept:
                response.success()
                return
            self._fail_http(response, name)

    def _get_with_etag(self, path: str, *, name: str, with_auth: bool) -> None:
        """GET with ETag-based conditional caching.

        Sends ``If-None-Match`` when a previous ETag was stored for this path.
        Stores the new ``ETag`` from the response so the next call can use it.
        Accepts both 200 (fresh data) and 304 (not modified) as success.
        """
        extra: dict[str, str] = {}
        cached_etag = self._etag_cache.get(path)
        if cached_etag:
            extra['If-None-Match'] = f'"{cached_etag}"'

        with self.client.get(
            path,
            headers=self._headers(with_auth=with_auth, accept="application/json", extra=extra),
            name=name,
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code == 304:
                # Not Modified — data unchanged, served from cache on the server side.
                response.success()
                return
            if response.status_code == 200:
                etag = response.headers.get('ETag', '').strip().strip('"')
                if etag:
                    self._etag_cache[path] = etag
                response.success()
                return
            self._fail_http(response, name)

    def _next_aes_id(self) -> int | None:
        if not self.assignment_aes_ids:
            return None
        self._assignment_rr_idx = (self._assignment_rr_idx + 1) % len(self.assignment_aes_ids)
        return self.assignment_aes_ids[self._assignment_rr_idx]

    def _next_assignment_aes_id(self) -> int | None:
        return self._next_aes_id()

    def _entry_csrf(self, aes_id: int) -> str | None:
        csrf_token = self._entry_csrf_tokens.get(aes_id)
        if csrf_token:
            return csrf_token
        if not self._refresh_entry_context(aes_id):
            return None
        return self._entry_csrf_tokens.get(aes_id)

    def _session_csrf_for_post(self, aes_id: int | None = None) -> str | None:
        """CSRF for session JSON POSTs; prefers entry-form token, falls back to /api/v1/csrf-token."""
        if aes_id is not None:
            cached = self._entry_csrf_tokens.get(aes_id)
            if cached:
                return cached
        if self._api_csrf_token:
            return self._api_csrf_token
        if self._dashboard_csrf_token:
            return self._dashboard_csrf_token
        with self.client.get(
            "/api/v1/csrf-token",
            headers=self._headers(with_auth=False, accept="application/json"),
            name="GET /api/v1/csrf-token",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code != 200:
                self._fail_http(response, "GET /api/v1/csrf-token")
                return None
            try:
                token = response.json().get("csrf_token")
            except Exception:
                self._fail_http(response, "GET /api/v1/csrf-token", detail="response not JSON")
                return None
            if not token:
                self._fail_http(response, "GET /api/v1/csrf-token", detail="csrf_token missing")
                return None
            self._api_csrf_token = token
            response.success()
            return token

    def _cache_bootstrap_params(self, aes_id: int, payload: dict) -> None:
        """Cache form_item_ids from entry-bootstrap auto_load (VU-level warm-up)."""
        auto_load = payload.get("auto_load") or {}
        ids = [int(k) for k in auto_load.keys() if str(k).isdigit()]
        if ids:
            self._matrix_batch_params[aes_id] = ids

        row_ids: list[int] = []
        for block in auto_load.values():
            if not isinstance(block, dict):
                continue
            for ent in block.get("entities") or []:
                if isinstance(ent, dict) and ent.get("entity_id") is not None:
                    try:
                        row_ids.append(int(ent["entity_id"]))
                    except (TypeError, ValueError):
                        pass
        resolved = payload.get("resolved_variables") or {}
        for key in resolved.keys():
            if str(key).isdigit():
                row_ids.append(int(key))
        if row_ids and not self._row_entity_ids:
            self._row_entity_ids = list(dict.fromkeys(row_ids))[:20]

    def _build_auto_load_batch_requests(self, aes_id: int) -> list[dict]:
        """Build sub-requests for /api/v1/matrix/auto-load-entities/batch."""
        form_item_ids = (
            self._matrix_batch_params.get(aes_id)
            or self._matrix_form_item_ids
        )
        if not form_item_ids or not self._matrix_source_template_id or not self._matrix_source_period:
            return []
        return [
            {
                "source_template_id": self._matrix_source_template_id,
                "source_assignment_period": self._matrix_source_period,
                "source_form_item_id": fid,
                "assignment_entity_status_id": aes_id,
            }
            for fid in form_item_ids[:5]
        ]

    def _next_document_id(self) -> int | None:
        if not self.document_ids:
            return None
        self._document_rr_idx = (self._document_rr_idx + 1) % len(self.document_ids)
        return self.document_ids[self._document_rr_idx]

    def _refresh_dashboard_csrf(self) -> bool:
        with self.client.get(
            "/",
            headers=self._headers(with_auth=False, accept="text/html"),
            name="GET / (dashboard)",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code != 200:
                self._fail_http(response, "GET / (dashboard)")
                return False
            match = CSRF_TOKEN_RE.search(response.text or "")
            if match:
                self._dashboard_csrf_token = match.group(1)
            response.success()
            return bool(self._dashboard_csrf_token)

    def _refresh_entry_context(self, aes_id: int) -> bool:
        path = f"/forms/assignment/{aes_id}"
        with self.client.get(
            path,
            headers=self._headers(with_auth=False, accept="text/html"),
            name="GET /forms/assignment/[aes_id]",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code != 200:
                self._fail_http(
                    response,
                    "GET /forms/assignment/[aes_id]",
                    detail=f"aes_id={aes_id}",
                )
                return False

            match = CSRF_TOKEN_RE.search(response.text or "")
            if not match:
                self._fail_http(
                    response,
                    "GET /forms/assignment/[aes_id]",
                    detail=f"csrf_token missing aes_id={aes_id}",
                )
                return False

            self._entry_csrf_tokens[aes_id] = match.group(1)
            response.success()
            return True

    @task(3)
    def health(self) -> None:
        """Lightweight public health endpoint (always available)."""
        self._get("/health", name="GET /health", with_auth=False)

    @task(1)
    def ai_health(self) -> None:
        """AI subsystem health. 503 is acceptable when AI is not configured."""
        self._get(
            "/api/ai/v2/health",
            name="GET /api/ai/v2/health",
            with_auth=False,
            accept=(200, 503),
        )

    @task(2)
    def api_v1_countrymap(self) -> None:
        """Bearer-authenticated country map read (skipped when no API key).

        Uses ETag / If-None-Match so repeated calls within the 5-minute server
        cache window receive 304 Not Modified instead of the full 117 KB body.
        """
        if not self.api_key:
            return
        self._get_with_etag(
            "/api/v1/countrymap",
            name="GET /api/v1/countrymap",
            with_auth=True,
        )

    @task(2)
    def api_v1_templates(self) -> None:
        """Bearer-authenticated templates read (skipped when no API key)."""
        if not self.api_key:
            return
        self._get(
            "/api/v1/templates",
            name="GET /api/v1/templates",
            with_auth=True,
        )

    # ----------------------- Navigation flow -----------------------
    # Enabled when:
    #   LOADTEST_SESSION_COOKIE=session=<captured_cookie_value>
    #
    # Simulates page-to-page movement between dashboard, documents, and help.

    @task(4)
    def nav_dashboard(self) -> None:
        if not self.navigation_focus_enabled:
            return
        self._refresh_dashboard_csrf()

    @task(2)
    def nav_documents(self) -> None:
        if not self.navigation_focus_enabled:
            return
        self._get(
            "/documents",
            name="GET /documents",
            with_auth=False,
            accept=(200,),
            accept_header="text/html",
        )

    @task(2)
    def nav_help_docs(self) -> None:
        if not self.navigation_focus_enabled:
            return
        path = "/help/docs"
        if self.help_doc_path:
            path = f"/help/docs/{self.help_doc_path}"
        self._get(
            path,
            name="GET /help/docs[/<doc_path>]",
            with_auth=False,
            accept=(200, 404),  # 404 if a custom doc path is misconfigured
            accept_header="text/html",
        )

    # ----------------------- Focal-point entry form flow -----------------------
    # Enabled only when:
    #   LOADTEST_ASSIGNMENT_AES_IDS=1,2,3
    #   LOADTEST_SESSION_COOKIE=session=<captured_cookie_value>

    @task(8)
    def assignment_entry_form_page(self) -> None:
        if not self.entry_focus_enabled:
            return
        aes_id = self._next_assignment_aes_id()
        if aes_id is None:
            return
        self._refresh_entry_context(aes_id)

    @task(5)
    def assignment_entry_form_ajax_save(self) -> None:
        if not self.entry_focus_enabled:
            return
        aes_id = self._next_assignment_aes_id()
        if aes_id is None:
            return

        csrf_token = self._entry_csrf_tokens.get(aes_id)
        if not csrf_token and not self._refresh_entry_context(aes_id):
            return
        csrf_token = self._entry_csrf_tokens.get(aes_id)
        if not csrf_token:
            return

        payload = {"action": "save", "csrf_token": csrf_token}
        with self.client.post(
            f"/forms/assignment/{aes_id}?ajax=1",
            data=payload,
            headers=self._headers(
                with_auth=False,
                accept="application/json",
                extra={"X-Requested-With": "XMLHttpRequest"},
            ),
            name="POST /forms/assignment/[aes_id]?ajax=1 (save)",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code != 200:
                # CSRF token may have rotated; refresh context and let next iteration retry.
                self._entry_csrf_tokens.pop(aes_id, None)
                self._fail_http(
                    response,
                    "POST /forms/assignment/[aes_id]?ajax=1 (save)",
                    detail=f"aes_id={aes_id}",
                )
                return

            try:
                data = response.json()
            except Exception:
                data = None

            if isinstance(data, dict) and data.get("success") is True:
                response.success()
            else:
                self._fail_http(
                    response,
                    "POST /forms/assignment/[aes_id]?ajax=1 (save)",
                    detail=f"aes_id={aes_id} payload={str(data)[:200]}",
                )

    # -------- Document-upload AJAX state refresh (GET ?ajax=1) ---------
    # document-upload.js fires this GET automatically on page load when the
    # form contains document fields, to sync server-side upload state with
    # the client before enabling the upload UI.

    @task(3)
    def assignment_entry_form_ajax_get(self) -> None:
        if not self.entry_focus_enabled:
            return
        aes_id = self._next_assignment_aes_id()
        if aes_id is None:
            return

        self._get(
            f"/forms/assignment/{aes_id}?ajax=1",
            name="GET /forms/assignment/[aes_id]?ajax=1",
            with_auth=False,
            accept=(200,),
            accept_header="text/html,application/json",
        )

    # -------------------- Document file download ------------------------
    # document-upload.js and the form itself expose download links for
    # submitted documents.  Requires LOADTEST_DOCUMENT_IDS.

    @task(3)
    def assignment_document_download(self) -> None:
        if not self.document_focus_enabled:
            return
        doc_id = self._next_document_id()
        if doc_id is None:
            return

        self._get(
            f"/forms/download_document/{doc_id}",
            name="GET /forms/download_document/[doc_id]",
            with_auth=False,
            accept=(200, 302, 404),  # 302 if stored on Azure Blob; 404 if file missing
            accept_header="application/octet-stream,*/*",
        )

    # --------------- Dynamic indicator render-pending -------------------
    # dynamic-indicators.js posts to this endpoint to preview an indicator
    # before persisting it.  Requires LOADTEST_DI_SECTION_ID and
    # LOADTEST_DI_INDICATOR_BANK_ID to be set to a valid section/indicator
    # pair in the target environment.

    @task(2)
    def assignment_dynamic_indicators_render(self) -> None:
        if not self.di_focus_enabled:
            return
        aes_id = self._next_assignment_aes_id()
        if aes_id is None:
            return

        csrf_token = self._entry_csrf_tokens.get(aes_id)
        if not csrf_token and not self._refresh_entry_context(aes_id):
            return
        csrf_token = self._entry_csrf_tokens.get(aes_id)
        if not csrf_token:
            return

        with self.client.post(
            "/api/forms/dynamic-indicators/render-pending",
            data={
                "section_id": str(self._di_section_id),
                "indicator_bank_id": str(self._di_indicator_bank_id),
            },
            headers=self._headers(
                with_auth=False,
                accept="application/json",
                extra={
                    "X-CSRFToken": csrf_token,
                    "X-Requested-With": "XMLHttpRequest",
                },
            ),
            name="POST /api/forms/dynamic-indicators/render-pending",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code in (200, 400, 404):
                # 400 = bad section/indicator combo; 404 = section not found.
                # Both still exercise routing, auth, and DB query layers.
                response.success()
            else:
                self._fail_http(
                    response,
                    "POST /api/forms/dynamic-indicators/render-pending",
                )

    # -----------------------------------------------------------------------
    # Notification endpoints (badge, list, preferences, CSRF)
    # -----------------------------------------------------------------------

    @task(6)
    def notification_badge_count(self) -> None:
        if not self.notification_focus_enabled:
            return
        self._get(
            "/notifications/api/count",
            name="GET /notifications/api/count",
            with_auth=False,
            accept_header="application/json",
        )

    @task(2)
    def notification_preferences(self) -> None:
        if not self.notification_focus_enabled:
            return
        self._get(
            "/notifications/api/preferences",
            name="GET /notifications/api/preferences",
            with_auth=False,
            accept_header="application/json",
        )

    @task(3)
    def notification_list(self) -> None:
        if not self.notification_focus_enabled:
            return
        self._get(
            "/notifications/api?limit=10&offset=0",
            name="GET /notifications/api",
            with_auth=False,
            accept_header="application/json",
        )

    @task(2)
    def csrf_refresh(self) -> None:
        if not self.notification_focus_enabled:
            return
        self._get(
            "/api/v1/csrf-token",
            name="GET /api/v1/csrf-token",
            with_auth=False,
            accept_header="application/json",
        )

    # -----------------------------------------------------------------------
    # Entry-form secondary APIs (bootstrap, presence, completion-rate)
    # -----------------------------------------------------------------------

    @task(8)
    def entry_bootstrap(self) -> None:
        if not self.entry_focus_enabled:
            return
        aes_id = self._next_aes_id()
        if aes_id is None:
            return
        with self.client.get(
            f"/api/forms/assignment/{aes_id}/entry-bootstrap",
            headers=self._headers(with_auth=False, accept="application/json"),
            name="GET /api/forms/assignment/<aes_id>/entry-bootstrap",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code == 200:
                try:
                    self._cache_bootstrap_params(aes_id, response.json())
                except Exception:
                    pass
                response.success()
            else:
                self._fail_http(
                    response,
                    "GET /api/forms/assignment/<aes_id>/entry-bootstrap",
                    detail=f"aes_id={aes_id}",
                )

    @task(2)
    def presence_sync(self) -> None:
        if not self.entry_focus_enabled:
            return
        aes_id = self._next_aes_id()
        if aes_id is None:
            return
        csrf_token = self._session_csrf_for_post(aes_id)
        if not csrf_token:
            return
        with self.client.post(
            f"/api/forms/presence/assignment/{aes_id}/sync",
            json={},
            headers=self._headers(
                with_auth=False,
                accept="application/json",
                extra={
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrf_token,
                    "X-Requested-With": "XMLHttpRequest",
                },
            ),
            name="POST /api/forms/presence/assignment/<aes_id>/sync",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                # Browser backs off on rate limit; treat as expected under load.
                response.success()
            else:
                self._fail_http(
                    response,
                    "POST /api/forms/presence/assignment/<aes_id>/sync",
                    detail=f"aes_id={aes_id}",
                )

    @task(2)
    def completion_rate(self) -> None:
        if not self.entry_focus_enabled:
            return
        aes_id = self._next_aes_id()
        if aes_id is None:
            return
        self._get(
            f"/api/forms/assignment/{aes_id}/completion-rate",
            name="GET /api/forms/assignment/<aes_id>/completion-rate",
            with_auth=False,
            accept_header="application/json",
        )

    # -----------------------------------------------------------------------
    # Dashboard secondary APIs (data-quality, activities, profile hover)
    # -----------------------------------------------------------------------

    @task(3)
    def data_quality_score(self) -> None:
        if not self.dashboard_focus_enabled:
            return
        params = urlencode({
            "entity_type": "country",
            "entity_id": self._country_id,
            "template_id": self._dq_template_id,
            "period": self._dq_period,
        })
        self._get(
            f"/api/v1/dashboard/data-quality?{params}",
            name="GET /api/v1/dashboard/data-quality",
            with_auth=False,
            accept=(200, 403, 404),
            accept_header="application/json",
        )

    @task(3)
    def load_more_activities(self) -> None:
        if not self.dashboard_focus_enabled:
            return
        if not self._dashboard_csrf_token:
            self._refresh_dashboard_csrf()
        if not self._dashboard_csrf_token:
            return
        with self.client.post(
            "/load_more_activities",
            data={
                "offset": "0",
                "limit": "10",
                "country_id": str(self._country_id),
                "csrf_token": self._dashboard_csrf_token,
            },
            headers=self._headers(
                with_auth=False,
                accept="application/json",
                extra={"X-Requested-With": "XMLHttpRequest"},
            ),
            name="POST /load_more_activities",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                self._fail_http(response, "POST /load_more_activities")

    @task(2)
    def profile_summary(self) -> None:
        if not self.profile_focus_enabled:
            return
        query = urlencode(
            [("user_ids", str(uid)) for uid in self._profile_user_ids[:3]],
            doseq=True,
        )
        self._get(
            f"/api/users/profile-summary?{query}",
            name="GET /api/users/profile-summary",
            with_auth=False,
            accept_header="application/json",
        )

    # -----------------------------------------------------------------------
    # Matrix / lookup / plugin APIs
    # -----------------------------------------------------------------------

    @task(4)
    def variables_resolve(self) -> None:
        if not self.matrix_focus_enabled or not self._dq_template_id:
            return
        aes_id = self._next_aes_id()
        if aes_id is None:
            return
        csrf_token = self._entry_csrf(aes_id)
        if not csrf_token:
            return
        body: dict = {
            "assignment_entity_status_id": aes_id,
            "template_id": self._dq_template_id,
        }
        if self._row_entity_ids:
            body["row_entity_ids"] = self._row_entity_ids[:10]
        with self.client.post(
            "/api/v1/variables/resolve",
            json=body,
            headers=self._headers(
                with_auth=False,
                accept="application/json",
                extra={
                    "X-CSRFToken": csrf_token,
                    "X-Requested-With": "XMLHttpRequest",
                },
            ),
            name="POST /api/v1/variables/resolve",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code in (200, 400, 404):
                response.success()
            else:
                self._fail_http(
                    response,
                    "POST /api/v1/variables/resolve",
                    detail=f"aes_id={aes_id}",
                )

    @task(4)
    def matrix_auto_load_batch(self) -> None:
        if not self.matrix_batch_enabled:
            return
        aes_id = self._next_aes_id()
        if aes_id is None:
            return
        csrf_token = self._entry_csrf(aes_id)
        if not csrf_token:
            return
        sub_requests = self._build_auto_load_batch_requests(aes_id)
        if not sub_requests:
            return
        with self.client.post(
            "/api/v1/matrix/auto-load-entities/batch",
            json={"requests": sub_requests},
            headers=self._headers(
                with_auth=False,
                accept="application/json",
                extra={
                    "X-CSRFToken": csrf_token,
                    "X-Requested-With": "XMLHttpRequest",
                },
            ),
            name="POST /api/v1/matrix/auto-load-entities/batch",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code in (200, 400, 404):
                response.success()
            else:
                self._fail_http(
                    response,
                    "POST /api/v1/matrix/auto-load-entities/batch",
                    detail=f"aes_id={aes_id}",
                )

    @task(4)
    def lookup_list_options(self) -> None:
        if not self.matrix_focus_enabled:
            return
        self._get(
            f"/api/forms/lookup-lists/{self._lookup_list_id}/options",
            name="GET /api/forms/lookup-lists/<id>/options",
            with_auth=False,
            accept_header="application/json",
        )

    @task(2)
    def matrix_search_rows(self) -> None:
        if not self.matrix_focus_enabled:
            return
        aes_id = self._next_aes_id()
        if aes_id is None:
            return
        csrf_token = self._entry_csrf(aes_id)
        if not csrf_token:
            return
        with self.client.post(
            "/forms/matrix/search-rows",
            json={
                "lookup_list_id": self._lookup_list_id,
                "display_column": "name",
                "filters": [],
                "search_term": "",
                "existing_rows": [],
                "limit": 50,
            },
            headers=self._headers(
                with_auth=False,
                accept="application/json",
                extra={
                    "X-CSRFToken": csrf_token,
                    "X-Requested-With": "XMLHttpRequest",
                },
            ),
            name="POST /forms/matrix/search-rows",
            catch_response=True,
            timeout=self.timeout_duration,
        ) as response:
            if response.status_code in (200, 400, 404):
                response.success()
            else:
                self._fail_http(
                    response,
                    "POST /forms/matrix/search-rows",
                )

    @task(1)
    def notification_stream_status(self) -> None:
        if not self.notification_focus_enabled:
            return
        self._get(
            "/notifications/api/stream/status",
            name="GET /notifications/api/stream/status",
            with_auth=False,
            accept_header="application/json",
        )

    @task(2)
    def emops_operations(self) -> None:
        if not self.emops_focus_enabled:
            return
        self._get(
            "/admin/plugins/emergency_operations/api/operations",
            name="GET /admin/plugins/emergency_operations/api/operations",
            with_auth=False,
            accept=(200, 403, 404, 503),
            accept_header="application/json",
        )

    @task(1)
    def emops_operations_live(self) -> None:
        if not self.emops_focus_enabled:
            return
        self._get(
            "/admin/plugins/emergency_operations/api/operations/live",
            name="GET /admin/plugins/emergency_operations/api/operations/live",
            with_auth=False,
            accept=(200, 403, 404, 503),
            accept_header="application/json",
        )

    @task(1)
    def emops_list_data(self) -> None:
        if not self.emops_focus_enabled:
            return
        self._get(
            "/admin/plugins/emergency_operations/api/list-data",
            name="GET /admin/plugins/emergency_operations/api/list-data",
            with_auth=False,
            accept=(200, 403, 404, 503),
            accept_header="application/json",
        )

    @task(1)
    def service_worker(self) -> None:
        self._get(
            "/sw.js",
            name="GET /sw.js",
            with_auth=False,
            accept=(200, 304),
            accept_header="*/*",
        )

    def on_stop(self) -> None:
        return None


# To run locally from Backoffice/ (PowerShell):
#   $env:LOADTEST_HOST = "https://databank-stage.ifrc.org"
#   $env:LOADTEST_API_KEY = "..."
#   locust -f azure/loadtest/locustfile.py -u 10 -r 2 --run-time 1m --headless
#
# To run locally from Backoffice/ (bash):
#   LOADTEST_HOST=https://databank-stage.ifrc.org \
#   LOADTEST_API_KEY=... \
#   locust -f azure/loadtest/locustfile.py -u 10 -r 2 --run-time 1m --headless
