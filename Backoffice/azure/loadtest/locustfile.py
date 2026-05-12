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
    LOADTEST_SUBMIT_AES_IDS        comma-separated AES IDs used exclusively
                                   for submit traffic. Keep these
                                   separate from LOADTEST_ASSIGNMENT_AES_IDS
                                   so save tasks never hit a locked form.
                                   The session holder must have permission to
                                   submit for these assignments.
    LOADTEST_DOCUMENT_IDS          comma-separated submitted_document_id values
                                   to exercise GET /forms/download_document/<id>
    LOADTEST_DI_SECTION_ID         a single section_id whose section_type is
                                   'dynamic_indicators' (enables render-pending)
    LOADTEST_DI_INDICATOR_BANK_ID  a single indicator_bank_id valid for the
                                   above section (enables render-pending)
    LOADTEST_AUTO_SETUP            set to ``true`` to automatically create dedicated
                                   [LOADTEST] assignments before the run and delete
                                   them (+ all accumulated FormData) after.  Requires
                                   LOADTEST_SESSION_COOKIE, LOADTEST_SETUP_TEMPLATE_ID,
                                   and LOADTEST_SETUP_COUNTRY_IDS.  When enabled,
                                   LOADTEST_ASSIGNMENT_AES_IDS is set automatically
                                   and must NOT be set manually.
    LOADTEST_SETUP_TEMPLATE_ID     FormTemplate ID to use when auto-creating assignments
                                   (must have a published version).
    LOADTEST_SETUP_COUNTRY_IDS     Comma-separated country IDs added per assignment
                                   during auto-setup (e.g. "5,12").
    LOADTEST_SETUP_COUNT           Number of AssignedForms to create (default 3).
    LOADTEST_ALLOW_PROD            set to ``true`` to allow targeting production
    ENABLE_LOGGING                 ``true``/``false`` to toggle DEBUG logging

When both ``LOADTEST_SESSION_COOKIE`` and ``LOADTEST_ASSIGNMENT_AES_IDS`` are
provided, the script exercises the full focal-point entry-form surface:
    - GET  /forms/assignment/<aes_id>                           (page load)
    - GET  /forms/assignment/<aes_id>?ajax=1                    (document-upload state refresh)
    - POST /forms/assignment/<aes_id>?ajax=1  (action=save)     (AJAX auto-save)

When ``LOADTEST_SUBMIT_AES_IDS`` is also provided:
    - POST /forms/assignment/<aes_id>           (action=submit, full submission)

When ``LOADTEST_DOCUMENT_IDS`` is provided:
    - GET  /forms/download_document/<doc_id>    (document file download)

When ``LOADTEST_DI_SECTION_ID`` + ``LOADTEST_DI_INDICATOR_BANK_ID`` are provided:
    - POST /api/forms/dynamic-indicators/render-pending   (dynamic indicator render)
"""

import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

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
    return s


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


def _discover_template_id(s: "_req.Session", host: str) -> int:
    """Return the first available published template ID via GET /api/v1/templates."""
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
    return int(valid[0]["id"])


def _discover_country_id(s: "_req.Session", host: str) -> int:
    """Return the first available country ID via GET /api/v1/countrymap."""
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
    return int(valid[0]["id"])


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
    """
    if not _bool_env("LOADTEST_AUTO_SETUP"):
        return

    log = logging.getLogger("locust")
    host = _resolved_host()
    session_cookie = (os.getenv("LOADTEST_SESSION_COOKIE") or "").strip()
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
            log.info("[auto-setup] LOADTEST_SETUP_TEMPLATE_ID not set — auto-discovering via /api/v1/templates ...")
            template_id = _discover_template_id(s, host)
            log.info("[auto-setup] Auto-discovered template_id=%d", template_id)

        if not country_ids:
            log.info("[auto-setup] LOADTEST_SETUP_COUNTRY_IDS not set — auto-discovering via /api/v1/countrymap ...")
            country_ids = [_discover_country_id(s, host)]
            log.info("[auto-setup] Auto-discovered country_ids=%s", country_ids)

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

            created.append({"assignment_id": assignment_id, "aes_ids": aes_ids})

        all_aes_ids = [aes_id for item in created for aes_id in item["aes_ids"]]
        _auto_setup_state.update({
            "host": host,
            "session_cookie": session_cookie,
            "assignments": created,
            "all_aes_ids": all_aes_ids,
        })

        # Inject into os.environ so VU on_start reads them (single-engine).
        os.environ["LOADTEST_ASSIGNMENT_AES_IDS"] = ",".join(str(x) for x in all_aes_ids)
        log.info(
            "[auto-setup] Done. LOADTEST_ASSIGNMENT_AES_IDS=%s",
            os.environ["LOADTEST_ASSIGNMENT_AES_IDS"],
        )

    except Exception as exc:
        log.error("[auto-setup] FAILED: %s", exc, exc_info=True)
        raise SystemExit(f"[auto-setup] Cannot continue without test data: {exc}") from exc


# ---------------------------------------------------------------------------
# Auto-teardown: delete [LOADTEST] assignments after the run
# ---------------------------------------------------------------------------

@events.test_stop.add_listener
def _on_test_stop(environment, **_kwargs) -> None:  # noqa: ANN001
    """Delete all assignments created by _on_test_start."""
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

        # --- Submit pool (separate from save pool to avoid lock collisions) ---
        self.submit_aes_ids = _int_list_env("LOADTEST_SUBMIT_AES_IDS")
        self._submit_rr_idx = -1

        # --- Document download pool ---
        self.document_ids = _int_list_env("LOADTEST_DOCUMENT_IDS")
        self._document_rr_idx = -1

        # --- Dynamic indicator render params ---
        self._di_section_id: int | None = _int_or_none("LOADTEST_DI_SECTION_ID")
        self._di_indicator_bank_id: int | None = _int_or_none("LOADTEST_DI_INDICATOR_BANK_ID")

        # ETag cache: maps endpoint path -> last ETag value received.
        # Sent as If-None-Match on subsequent requests so the server can return
        # 304 Not Modified (zero body transfer) when the data hasn't changed.
        self._etag_cache: dict[str, str] = {}

        # Session + entry-form traffic flags
        self.navigation_focus_enabled = bool(self.session_cookie)
        self.entry_focus_enabled = bool(self.assignment_aes_ids and self.session_cookie)
        self.submit_focus_enabled = bool(self.submit_aes_ids and self.session_cookie)
        self.document_focus_enabled = bool(self.document_ids and self.session_cookie)
        self.di_focus_enabled = bool(
            self._di_section_id and self._di_indicator_bank_id and self.session_cookie
        )

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
        self.client.headers.update({"Referer": self.host})

        if self.assignment_aes_ids and not self.session_cookie:
            logging.getLogger("locust").warning(
                "[locust] LOADTEST_ASSIGNMENT_AES_IDS provided but LOADTEST_SESSION_COOKIE is missing; "
                "entry-form focal-point tasks are disabled."
            )
        if self.submit_aes_ids and not self.session_cookie:
            logging.getLogger("locust").warning(
                "[locust] LOADTEST_SUBMIT_AES_IDS provided but LOADTEST_SESSION_COOKIE is missing; "
                "submit task is disabled."
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
            msg = f"{name} failed: status={response.status_code} body={response.text[:200]!r}"
            response.failure(msg)
            if self.enable_logging:
                logging.error(msg)

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
            msg = f"{name} failed: status={response.status_code} body={response.text[:200]!r}"
            response.failure(msg)
            if self.enable_logging:
                logging.error(msg)

    def _next_assignment_aes_id(self) -> int | None:
        if not self.assignment_aes_ids:
            return None
        self._assignment_rr_idx = (self._assignment_rr_idx + 1) % len(self.assignment_aes_ids)
        return self.assignment_aes_ids[self._assignment_rr_idx]

    def _next_submit_aes_id(self) -> int | None:
        if not self.submit_aes_ids:
            return None
        self._submit_rr_idx = (self._submit_rr_idx + 1) % len(self.submit_aes_ids)
        return self.submit_aes_ids[self._submit_rr_idx]

    def _next_document_id(self) -> int | None:
        if not self.document_ids:
            return None
        self._document_rr_idx = (self._document_rr_idx + 1) % len(self.document_ids)
        return self.document_ids[self._document_rr_idx]

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
                response.failure(
                    f"Entry form load failed for aes_id={aes_id}: status={response.status_code}"
                )
                return False

            match = CSRF_TOKEN_RE.search(response.text or "")
            if not match:
                response.failure(
                    f"Entry form loaded but csrf_token missing for aes_id={aes_id}"
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
        self._get(
            "/",
            name="GET / (dashboard)",
            with_auth=False,
            accept=(200,),
            accept_header="text/html",
        )

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
                response.failure(
                    f"AJAX save failed for aes_id={aes_id}: status={response.status_code}"
                )
                return

            try:
                data = response.json()
            except Exception:
                data = None

            if isinstance(data, dict) and data.get("success") is True:
                response.success()
            else:
                response.failure(
                    f"AJAX save returned non-success payload for aes_id={aes_id}: {str(data)[:200]}"
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

    # ------------------- Full form submission (action=submit) -------------------
    # This is the heaviest single action a focal-point performs: validates all
    # fields, writes final status, and triggers downstream notifications.
    # Uses LOADTEST_SUBMIT_AES_IDS (separate pool from save pool) to avoid
    # locking assignments used by the AJAX save tasks.
    # Accepts 200 (validation errors kept on page) and 302 (successful redirect).

    @task(1)
    def assignment_entry_form_submit(self) -> None:
        if not self.submit_focus_enabled:
            return
        aes_id = self._next_submit_aes_id()
        if aes_id is None:
            return

        # Ensure we have a CSRF token for this assignment.
        csrf_token = self._entry_csrf_tokens.get(aes_id)
        if not csrf_token:
            # Fetch the page to get a token; use a dedicated slot in the cache
            # so we do not pollute the save-pool cache.
            path = f"/forms/assignment/{aes_id}"
            with self.client.get(
                path,
                headers=self._headers(with_auth=False, accept="text/html"),
                name="GET /forms/assignment/[submit_aes_id] (csrf-fetch)",
                catch_response=True,
                timeout=self.timeout_duration,
            ) as response:
                if response.status_code != 200:
                    response.failure(
                        f"CSRF fetch for submit failed aes_id={aes_id}: "
                        f"status={response.status_code}"
                    )
                    return
                match = CSRF_TOKEN_RE.search(response.text or "")
                if not match:
                    response.failure(
                        f"CSRF token missing on submit form page aes_id={aes_id}"
                    )
                    return
                self._entry_csrf_tokens[aes_id] = match.group(1)
                response.success()

        csrf_token = self._entry_csrf_tokens.get(aes_id)
        if not csrf_token:
            return

        payload = {"action": "submit", "csrf_token": csrf_token}
        with self.client.post(
            f"/forms/assignment/{aes_id}",
            data=payload,
            headers=self._headers(
                with_auth=False,
                accept="text/html,application/json",
                extra={"X-Requested-With": "XMLHttpRequest"},
            ),
            name="POST /forms/assignment/[submit_aes_id] (submit)",
            catch_response=True,
            allow_redirects=False,
            timeout=self.timeout_duration,
        ) as response:
            # 302 = successful submission redirect; 200 = validation errors shown
            if response.status_code in (200, 302):
                # CSRF token is consumed on submit; force refresh on next call.
                self._entry_csrf_tokens.pop(aes_id, None)
                response.success()
            else:
                self._entry_csrf_tokens.pop(aes_id, None)
                response.failure(
                    f"Submit failed for aes_id={aes_id}: status={response.status_code}"
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
                response.failure(
                    f"DI render-pending failed: status={response.status_code}"
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
