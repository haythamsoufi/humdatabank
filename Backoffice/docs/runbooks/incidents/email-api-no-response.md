# Email API No-Response Timeouts — Triage & Escalation

**Status:** Recurring, mitigated (not eliminated)
**Affected environment:** Production and staging — any send through the IFRC Email API (`microservices.ifrc.org/Email/api/Email`)
**Primary symptom:** Communication Center shows an email as **Failed**, but the recipient may have actually received it
**Last reviewed:** 2026-08-11

Related: [General incident triage](general-incident-triage.md) (Scenario G), [Gateway 504 / worker saturation](gateway-504-worker-saturation.md) (same "blocked thread" shape, different endpoint).

---

## 1. Executive summary

`app/services/email/client.py` calls the IFRC Email API with a **15s read timeout**
(`requests.post(..., timeout=15)`). When the API doesn't return an HTTP response
within that window — a read timeout or connection error, **not** an HTTP error status
— the app cannot tell whether the API:

- never received/processed the request, or
- received and sent it, but the response back to us was slow or lost.

Historically both outcomes were recorded identically as `EmailDeliveryLog.status =
'failed'`, which is what the Communication Center (`admin/communication/center.html`)
renders as **Failed**. An admin clicking **Retry** on a message that had actually
already gone through would then send a genuine duplicate — there is no idempotency
key in the outbound payload, and the IFRC API doesn't expose a lookup/status endpoint
to check first.

**This is primarily an upstream latency issue** (see §3 for why), but two gaps on our
side made it look worse and created real duplicate-send risk. Both are now fixed (§4):
a distinct `unknown` delivery status, and a per-attempt `client_request_id` for
escalation. What's *not* fixed — because it requires the other team — is listed in §5.

---

## 2. Recognizing this pattern in logs

```
ERROR in app: Email API request failed (no HTTP response) | client_request_id=<hex> | redacted_url=... | error=HTTPSConnectionPool(host='microservices.ifrc.org', port=443): Read timed out. (read timeout=15)
```

Often paired with, if the send happened inside the Communication Center's bulk retry
endpoint:

```
WARNING [STUCK_REQUEST] Request still in progress after 15.0s | ... path=/admin/api/communications/email-delivery/retry-failed
ERROR   [STUCK_REQUEST_CRITICAL] Request still in progress after 23.0s | ...
WARNING [SLOW_REQUEST] Completed in 23.45s (threshold=10s) | ... path=/admin/api/communications/email-delivery/retry-failed
```

**This is not a WORKER TIMEOUT / 504 incident** (contrast with [Gateway 504](gateway-504-worker-saturation.md)) — the request completes normally from Flask's point of view, just slowly. The gateway may still 504 the *client* if the batch runs long enough; see §4.3.

### Worked example (2026-08-11, production)

Four sequential sends inside one "Retry all failed emails" click:

| # | Sent (UTC) | Response | Elapsed | Result |
|---|---|---|---|---|
| 1 | 13:03:27.145 | 13:03:30.335 | 3.19s | 200 OK |
| 2 | 13:03:30.360 | 13:03:32.855 | 2.50s | 200 OK |
| 3 | 13:03:32.879 | 13:03:35.398 | 2.52s | 200 OK |
| 4 | 13:03:35.421 | *(none)* | >15.00s | Read timeout |

Same URL, same payload shape, ~5450 bytes every time. Calls 1–3 prove the network
path/auth/payload are fine seconds earlier — call 4 going completely silent for 15s+
right after is a strong signal the stall is server-side on the API, not something
about the specific request we sent.

---

## 3. Whose side is this on?

**Raise with the team managing `microservices.ifrc.org` when:**
- A request identical in shape to recently-successful ones gets **zero bytes back**
  for the full timeout window (as in the worked example above).
- "Successful" calls are themselves taking multiple seconds (2.5–3.2s in the example)
  — worth asking their expected P95/P99 for this endpoint.
- You want a **correlation ID or status-lookup endpoint** — today neither side can
  definitively confirm what happened to a specific stalled request after the fact
  (our response-header log shows `response_correlation_header=none` on every call).

**What to hand them** (see §6 for a ready-to-send ticket template):
- The `client_request_id` from our logs (see §4.2) and exact UTC timestamp.
- The redacted URL/path and approximate payload size.
- Whether it was an isolated blip or part of a cluster (check the circuit breaker log
  — see §4.4).

**On our side, check first:**
- Is this a **single isolated timeout** surrounded by fast successes (→ upstream
  blip, not ours), or are **most/all** calls failing (→ check our own egress: DNS,
  firewall/NSG rules, expired cert trust, `EMAIL_API_URL`/`EMAIL_API_KEY`
  misconfiguration)? A full outage on our side fails *every* call, not an
  occasional one sandwiched between successes.
- Is the circuit breaker open (`Email API circuit breaker open — skipping outbound
  call...`)? That's us deliberately not calling the API after 3 consecutive
  no-response failures — see §4.4. Not itself a bug, but confirms a real upstream
  problem rather than one flaky call.

---

## 4. Mitigations already in place

### 4.1 Distinct `unknown` status (not `failed`)

A no-response outcome now lands as `EmailDeliveryLog.status = 'unknown'` instead of
`'failed'` — see `mark_email_failed_or_unknown()` in `app/services/email/delivery.py`.
The Communication Center grid renders it as an amber **"No Response"** badge (vs. red
**"Failed"**), with a tooltip explaining the message may already have been sent. It's
still retryable/dismissable like a failure — an admin should verify with the recipient
before retrying if a duplicate would matter (e.g. approval emails, external comms).

This only changes the *outcome that was already ambiguous* — an explicit HTTP error
status from the API (400/401/403/5xx, code `email_api_http_error`) still means
`'failed'`, because the API responding at all confirms it saw and rejected the
request.

### 4.2 Per-attempt `client_request_id`

`_send_via_ifrc()` (`app/services/email/client.py`) generates a `uuid4` per send
attempt, sends it as an `X-Client-Request-Id` header (never as a JSON body field —
the IFRC contract isn't documented to tolerate unknown keys), and logs it on the
outbound, response, and error log lines. The API doesn't currently echo it back, so
today this is mainly for **our own logs** — grep for it to find the exact outbound
attempt when escalating a specific stuck send (see §6). If the API team ever adds
request-id echoing or a lookup endpoint, this is what we'd match against.

### 4.3 Bounded, parallel batch retries

`admin_retry_failed_email_delivery_logs()` used to retry every failed log serially,
inside the single HTTP request from the admin's "Retry all failed emails" click — one
slow call blocked everything queued behind it (the worked example's 23.45s for just 4
emails). It now:
- Processes retries concurrently on a small bounded thread pool
  (`EMAIL_RETRY_BATCH_MAX_WORKERS`, default 5, env-configurable).
- Caps each call to `EMAIL_RETRY_BATCH_MAX_PER_CALL` items (default 20,
  env-configurable) and returns `remaining_count`; the Communication Center JS
  (`_runBulkEmailAction` in `communication.js`) automatically re-calls the endpoint
  while `remaining_count > 0`, capped at 10 rounds client-side as a safety net.

This bounds worst-case wall-clock time per HTTP round-trip so a large backlog after
an outage can't hold a web worker (and a DB connection) open for minutes, and can't
put the admin's own request at risk of a gateway timeout.

### 4.4 Circuit breaker (pre-existing, from the 2026-07-22 incident)

`_EmailApiCircuitBreaker` in `client.py` opens after 3 *consecutive* no-response
failures (timeouts/connection errors — not ordinary HTTP error responses) and
short-circuits new attempts for 60s so callers fail in microseconds instead of each
paying the full 15s timeout. One "trial" call is let through after the open window;
success closes the breaker. Process-local by design (no Redis) — each Gunicorn worker
protects its own threads independently. Env-configurable:
`EMAIL_API_BREAKER_FAILURE_THRESHOLD` (default 3), `EMAIL_API_BREAKER_OPEN_SECONDS`
(default 60).

---

## 5. What's still open (needs the API team, not just us)

- **No idempotency key support.** We can't tell the API "this is attempt #2 of the
  same logical email, don't double-send if attempt #1 actually landed." Retrying an
  `unknown` log is still a real duplicate-send risk if the original attempt actually
  succeeded — the `unknown` status makes this *visible* to the admin instead of
  hiding it as a generic failure, but doesn't prevent it.
- **No correlation ID echoed in responses**, and no status-lookup endpoint by request
  ID — see §4.2. Without one of these, no stalled send can ever be definitively
  confirmed after the fact from our side.
- **Baseline latency.** Even successful calls in the worked example took 2.5–3.2s.
  Worth establishing an agreed SLA so we know what "normal" looks like vs. a real
  degradation.

---

## 6. Escalation ticket template

```
Subject: microservices.ifrc.org/Email/api/Email — no HTTP response within 15s

Environment: production (Humanitarian Databank Backoffice)
Endpoint: POST https://microservices.ifrc.org/Email/api/Email
Time (UTC): <exact timestamp from "email_api outbound" log line>
client_request_id: <from our logs — see §4.2>

What happened: our request received zero bytes back for >15s (our client timeout),
immediately after N consecutive successful calls to the same endpoint (each
~X.Xs) with the same payload shape/size — see attached log excerpt.

Ask:
1. Can you confirm from your side whether a request arrived around this timestamp,
   and if so what happened to it (processed/sent, or never received)?
2. Can responses include a correlation/request ID (we'll happily echo one we send,
   e.g. our X-Client-Request-Id header) so both sides can match a specific request
   across logs, including when our side never got a response?
3. Is there a status-lookup endpoint (by request ID or similar) we could poll after
   a timeout, instead of blindly retrying and risking a duplicate send?
4. What's the expected P95/P99 response time for this endpoint? We're seeing
   2.5–3.2s on successful calls in the attached window.
```

Attach the relevant log lines (outbound + response/error, with `client_request_id`)
for the stalled call and the calls immediately before/after it.

---

## 7. Related code

| What | Where |
|---|---|
| HTTP call + timeout + circuit breaker | `app/services/email/client.py` (`_send_via_ifrc`) |
| Status classification (`failed` vs `unknown`) | `app/services/email/delivery.py` (`mark_email_failed_or_unknown`, `ACTIONABLE_EMAIL_STATUSES`) |
| Send call sites (create the `EmailDeliveryLog` row) | `app/services/notification/emails.py`, `app/services/email/service.py`, `app/services/email/fds_access_request_digest.py`, `app/services/email/campaign_broadcast.py` |
| Bulk retry endpoint | `app/routes/admin/communication.py` (`api_retry_failed_email_deliveries`) → `admin_retry_failed_email_delivery_logs` |
| Communication Center grid/badge | `app/static/js/admin/communication-grids.js` (`renderEmailStatus`), `app/static/js/admin/communication.js` (`_runBulkEmailAction`) |
| Migration adding the `unknown` enum value | `migrations/versions/add_email_delivery_unknown_status.py` |
