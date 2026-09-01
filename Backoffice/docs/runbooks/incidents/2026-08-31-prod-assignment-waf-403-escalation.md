# 2026-08 Assignment Entry-Form `platform_403_forbidden` — App-Side Fixes + WAF/SecOps Escalation

## Summary

Two `platform_403_forbidden` events were reported by the client-side platform
error reporter (`app/static/js/lib/platform-error-reporter.js`) for AJAX
autosave requests to the assignment entry form:

| Timestamp (client) | User | URL |
|---|---|---|
| 2026-08-26 13:10 (report time) | Eszter Mados | `/assignment/4100?ajax=1` |
| 2026-08-31 13:00:43.645Z | (unspecified) | `/assignment/1610?ajax=1` |

Both are edge-layer (Azure Application Gateway WAF) blocks, not Flask
application errors — confirmed via the absence of the `X-App-Origin: 1`
header that `app/middleware/security_headers.py` sets on every Flask
response (see `looksLikeWafResponse()` in the client reporter). This matches
the incident pattern in
[`waf-403-form-payload-refactor-guide.md`](./waf-403-form-payload-refactor-guide.md).

**No production WAF log access or database access was available during this
investigation** (no Azure CLI/credentials, no `DATABASE_URL` for prod in this
environment) — the two hypotheses below could not be confirmed against the
actual `ruleId`/`matchVariableName` for either event. The client-side error
report schema at the time only carried `url`/`referrer`/`user_agent`/
`timestamp` — no request-body/size/field information — so there was no local
evidence to fall back on either. That observability gap is now closed (see
"Also shipped" below), so if this recurs, the next report will actually carry
evidence.

## App-side fixes shipped (this change)

1. **`interactive_map` plugin field JSON was not base64-wrapped** before
   being written to its hidden `field_value[id]` input, unlike matrix fields.
   Fixed in `plugins/interactive_map/static/js/map_field.js`
   (`updateHiddenInput()`) to use the same `b64:` convention as
   `__serializeMatrixData()`. This is a genuine latent bug matching an
   already-proven pattern, but **is not what caused either incident above**
   — the affected form(s) had no map fields (per user report on assignment
   4100). Kept anyway since it closes a real, previously-unprotected gap.

2. **Question `text`/`textarea` answers were never protected from WAF
   signature false positives.** Unlike matrix/plugin JSON, plain
   `field_value[id]` text answers were read directly off `request.form` with
   no `b64:` wrapping at all — narrative text (quotes, semicolons, angle
   brackets, pasted rich text) is exactly the class of content
   `REQUEST-941-*`/`REQUEST-942-*` signature rules false-positive on (see
   "Why WAF Flags This Pattern" in the main guide). Fixed by extending the
   existing `b64:` convention to this field type:
   - `app/static/js/forms/modules/question-text-waf-encode.js` (new) —
     wraps free-text question inputs before AJAX autosave
     (`ajax-save.js::saveFormOnce`) and before the native "Submit" form post
     (via a `document`-level `submit` listener, mirroring
     `matrix-handler.js`'s own hook).
   - `app/services/forms/processing_service.py::FormItemProcessor._process_question_data`
     — decodes via the existing generic `decode_b64_matrix_json()`.
   - `app/services/forms/data_service.py::FormDataService._process_question_data`
     — catches `MatrixJsonDecodeError` and reports a validation error
     *before* touching stored data (same safe-failure contract as
     matrix/plugin fields).
   - `app/templates/forms/entry_form/entry_form.html` — added
     `data-question-type` to `.form-item-block` so the client can target
     only `text`/`textarea` question inputs.
   - **Trade-off, accepted deliberately:** this hides question free text
     from WAF signature inspection, same as matrix/plugin JSON already does.
     See the "Trade-off note" added to the main guide.
   - **Known gap, not covered:** repeat-group instances (their
     `field_value[id]` inputs get renamed to
     `repeat_<sectionId>_<instance>_field_<fieldIndex>_<inputIndex>` on JS
     clone before this selector can see them — see the comment at the top of
     `question-text-waf-encode.js`).

3. **Also shipped: request-body telemetry on platform-error reports.** The
   client reporter's payload previously carried no information about *what*
   was being submitted. `platform-error-reporter.js` now attaches a
   best-effort `request_field_count` / `request_approx_bytes` summary of the
   `FormData`/string body that failed (computed client-side, since the WAF
   blocks the request before Flask — or any server-side logging — ever sees
   it). Surfaced in `POST /api/v1/platform-error` → `context_data` and in the
   security-event `description` (`app/routes/api/error_log.py`). If a similar
   403 recurs, the resulting `SecurityEvent`/admin-alert email will show
   approximately how large/how many fields the failing request had, without
   needing WAF log access.

## What is *not* fixed by app changes (belt-and-suspenders WAF exclusion)

Base64-wrapping is a tactical, app-side mitigation (see "Why not the same one
everywhere" in the main guide) — it cannot fix a WAF **body-size** or
**argument-length/count** limit (`REQUEST-920-*` family /
`max_request_body_size_in_kb` policy setting), only content-signature false
positives. If either occurrence above was actually a size/argument-count
block rather than a signature false positive, only a WAF policy change (or a
payload-size reduction refactor — see "Recommended Standard" in the main
guide, not attempted in this change given its scope/risk) will fix it.

### 2026-09-01 update: concrete evidence for a size-based (not signature) block

A real production save payload was inspected and found to contain a matrix
`field_value[id]` argument (48-key indicator/support-planning matrix) whose
`b64:`-wrapped value was **1384 bytes** — 34% larger than its raw JSON form
(1033 bytes), due to base64's ~33% size overhead. This lands squarely in the
range of OWASP CRS's `920370` "Argument value too long" rule family (example
default `tx.arg_length=400`; Azure does not disclose its actual configured
value, but even the *raw, un-encoded* 1033-byte JSON would already exceed
that documented example default). See the updated "Azure App Gateway WAF
Rules the App Should Respect" section in
[`waf-403-form-payload-refactor-guide.md`](./waf-403-form-payload-refactor-guide.md)
for the full rule-family breakdown (`920360`/`920370`/`920380`/`920390`).

**Important implication:** base64-wrapping large matrix/plugin fields (the
tactical fix already shipped) helps against signature rules (`941`/`942`)
but *increases* the byte length of exactly the fields most likely to trip an
argument-length rule. If WAF logs for a future incident point at the
`920360`–`920390` family specifically, the correct fix is a **scoped WAF
exclusion** (`argument: field_value[*]` on this path), not more base64
coverage — this is now reflected in items 1–2 of the escalation request
below.

**App-side mitigation shipped same day:** matrix fields are now chunked into
multiple sub-350-byte arguments before submission (`matrix-field-chunking.js`
+ `get_possibly_chunked_form_value()`) — see "Azure App Gateway WAF Rules the
App Should Respect" in
[`waf-403-form-payload-refactor-guide.md`](./waf-403-form-payload-refactor-guide.md)
for the full mechanism. This directly neutralizes a per-argument length rule
for matrix fields without waiting on infra, but doesn't cover plugin fields
yet and doesn't help if the real threshold is size-based at the *total body*
level instead — the escalation below is still worth sending to confirm which
rule actually fired and close any remaining gap.

### Escalation request — send to IT/SecOps (Azure Application Gateway WAF policy owner)

> **Subject:** WAF false-positive / body-limit review — assignment entry-form autosave (`/assignment/<id>?ajax=1`)
>
> We've had two `403 Forbidden` platform-level blocks (Application Gateway
> WAF, not the Flask app — confirmed no `X-App-Origin` response header) on
> the Backoffice assignment entry-form autosave endpoint:
>
> - `POST /assignment/4100?ajax=1` — 2026-08-26 ~13:10 UTC
> - `POST /assignment/1610?ajax=1` — 2026-08-31 13:00:43 UTC
>
> Both are authenticated, session-based POSTs from the Backoffice admin app
> (not public-facing), carrying legitimate country-report form data
> (indicator values, question answers, matrix tables). We don't have Log
> Analytics/WAF log access from the engineering side to pull the exact
> `ruleId`/`matchVariableName` ourselves.
>
> **Requested:**
> 1. Pull the WAF diagnostic log entries for the two timestamps/paths above
>    and share `ruleId`, `matchVariableName`, `action`, and the request body
>    size that was blocked. **Please specifically check whether the rule is
>    in the `920360`/`920370`/`920380`/`920390` family** ("argument name/value
>    too long", "too many arguments", "total argument size exceeded") —
>    we've since found a real save payload with a single form-field argument
>    around 1.4 KB (a 48-key matrix table), which is a strong candidate for
>    tripping a per-argument length limit rather than the whole-body size
>    limit or a content-signature rule.
> 2. If it's a **per-argument length rule** (`920360`–`920390`) or a
>    **content-signature false positive** (`REQUEST-941-*`/`REQUEST-942-*`):
>    a targeted exclusion scoped to `path: /assignment/*` (POST) +
>    `argument: field_value[*]` — least-privilege, does not disable the rule
>    globally or on any other route/argument.
> 3. If it's the **whole-body size or overall-argument-count limit**: please
>    share the current configured limits for this Application Gateway/WAF
>    policy so we can decide whether to ask for a policy increase or invest
>    in a payload-size-reduction refactor on our side (splitting the autosave
>    into smaller requests) instead.
>
> We've already shipped app-side mitigations (base64-wrapping structured
> JSON and free-text answers to dodge signature false positives) and added
> client-side telemetry so any recurrence will carry request size/field-count
> evidence automatically. **Note for your side:** that base64 encoding
> increases the affected fields' byte length by ~33%, so it does not help —
> and can slightly worsen — a per-argument-length block; only items 2/3 above
> actually fix that class of block. This request is to close the loop with an
> infra-side fix per your own least-privilege exclusion policy, rather than
> relying solely on the app-side workaround long-term.
>
> **Business justification:** This is a core, frequently-used data-entry
> workflow (assignment/country-report autosave); false 403s here risk silent
> data loss for focal points if a save is rejected and the user doesn't
> notice the toast.
> **Proposed scope:** `path + argument exclusion only` (per your least-
> privilege exclusion policy), not global rule disablement.

## Verification

- `npx vitest run` — full JS suite: 633 passed, 4 pre-existing unrelated
  failures (confirmed identical on `git stash`, not introduced by this
  change).
- `pytest tests/unit/test_services/test_form_data_service.py
  tests/unit/test_services/test_form_processing_service.py
  tests/unit/test_routes/test_api_error_log.py` — all new/updated tests
  pass; 10 pre-existing unrelated failures confirmed identical on `git
  stash` (environment/fixture issues in `TestHasMeaningfulData`/
  `TestValidateRepeatSection`/etc., unrelated to this change's files).
- No production/staging manual test was possible (no WAF, no prod DB access
  from this environment) — recommend a staging validation pass with a
  production-like WAF policy before relying on this for the next incident
  (see "Verification Plan" in the main guide).
