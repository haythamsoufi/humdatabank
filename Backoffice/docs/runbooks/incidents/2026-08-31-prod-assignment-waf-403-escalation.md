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
   - **Follow-up (2026-09-01):** the `b64:` wrap of `field_value[1414]` did
     **not** clear production 403s on `/assignment/1703` (same AppGW block
     after deploy). Remaining triggers were raw `*_emergency_metadata` JSON,
     emergency-operations `Name (CODE)` select values, repeat-group free
     text, ~300 empty sex/age arguments on the AJAX save path, **and** a
     1384-byte b64-wrapped matrix `field_value[id]` that sits in the
     `920370` "Argument value too long" range. Those are now wrapped,
     omitted, or split across `__cN` chunks — see the main guide.
   - **Further follow-up (2026-09-01):** after the fixes above shipped
     (still pre-deploy at the time), a prod report on the *previous*
     deployment identified a third, distinct trigger: the literal
     `__other__` sentinel (`question-other-option.js`'s "Other (please
     specify)..." value) on a repeat-group `single_choice` field, with no
     other unusual content in that submission. This doesn't fit the
     punctuation-signature or argument-length patterns above — see "New
     finding (2026-09-01): the `__other__` sentinel itself trips the WAF" in
     the main guide for the dunder/SSTI-pattern hypothesis. Fixed by
     extending `question-text-waf-encode.js` to also wrap
     `select[data-allow-other="true"]` and its `.other-text-input`
     "please specify" companion, decoded on read in
     `processing_service.py::FormItemProcessor._process_question_data` and
     `processors/repeat_group.py`'s `_process_question_value_by_type` /
     `_process_multiple_choice_value`.

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
**argument-count** limit (`REQUEST-920-*` family / `max_request_body_size_in_kb`
policy setting), only content-signature false positives. **Per-argument
length** (`920370`) is mitigated for oversized matrix/plugin hidden fields
and any other `b64:`-wrapped value (narrative text, emergency metadata)
via chunking (`matrix-field-chunking.js` + `read_waf_protected_form_value()`).
If a recurrence is actually a whole-body size or argument-*count* block,
only a WAF policy change (or a payload-size reduction refactor — see
"Recommended Standard" in the main guide) will fix it.

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
>    size that was blocked (if size-related, e.g. `max_request_body_size_in_kb`
>    or `REQUEST-920-*` argument-count family).
> 2. If it's a **signature false positive** (`REQUEST-941-*`/`REQUEST-942-*`):
>    a targeted exclusion scoped to `path: /assignment/*` (POST) +
>    `argument: field_value[*]` — least-privilege, does not disable the rule
>    globally or on any other route/argument.
> 3. If it's a **body-size or argument-count limit**: please share the
>    current configured limits for this Application Gateway/WAF policy so we
>    can decide whether to ask for a policy increase or invest in a payload-
>    size-reduction refactor on our side (splitting the autosave into smaller
>    requests) instead.
>
> We've already shipped app-side mitigations (base64-wrapping structured
> JSON and free-text answers to dodge signature false positives) and added
> client-side telemetry so any recurrence will carry request size/field-count
> evidence automatically. This request is to close the loop with an
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

- `npx vitest run` — full JS suite: 650 passed, 4 pre-existing unrelated
  test failures + 1 pre-existing broken test file (missing
  `chart-payload-normalize.js` source, unrelated to forms/WAF) — all
  confirmed identical on `git stash`, not introduced by this change.
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

**2026-09-01 `__other__` sentinel follow-up specifically:**
- `npx vitest run tests/js/forms/question-text-waf-encode.test.js
  tests/js/forms/matrix-field-chunking.test.js` — 24/24 passed, including 2
  new tests (`select[data-allow-other="true"]` + `.other-text-input`
  discovery, wrap/restore round-trip).
- `pytest tests/unit/test_services/test_form_data_processors.py
  tests/unit/test_services/test_form_processing_service.py
  tests/unit/test_services/test_form_data_service.py` — 329 passed
  (including 10 new tests covering the `__other__` sentinel + b64-wrapped
  `field_other_text[id]`/`..._other_text`, top-level and repeat-group, plus
  the `MatrixJsonDecodeError` safe-failure path); the same 10 pre-existing
  failures above reproduce identically on `git stash` for this narrower
  file set too.
