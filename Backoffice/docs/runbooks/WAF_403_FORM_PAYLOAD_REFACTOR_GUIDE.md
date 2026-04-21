# WAF 403 Form Payload Refactor Guide

## Purpose

Use this guide when production returns `403 Forbidden` with `Server: Microsoft-Azure-Application-Gateway/v2` for form submissions that work locally/staging.

This is an edge-layer block (Application Gateway WAF), not a Flask handler error.

---

## Incident Pattern (Observed)

- Endpoint examples:
  - `POST /admin/settings`
  - `POST /forms/assignment/<id>?ajax=1`
- Response:
  - `HTTP/1.1 403 Forbidden`
  - `Server: Microsoft-Azure-Application-Gateway/v2`
- Behavior:
  - Same image works in staging/local
  - Fails only in production

Interpretation: payload shape/content is triggering WAF managed-rule false positives.

---

## Why Hidden Blobs Exist

Several pages use rich client-side editors (chips, translation matrices, multilingual template editors). Browsers only submit input fields, so JavaScript mirrors in-memory state into hidden inputs before submit.

Examples in `admin/settings`:

- `name="document_types_translations"` JSON hidden field
- `name="age_groups_translations"` JSON hidden field
- `name="sex_categories_translations"` JSON hidden field
- `name="<email_template_key>_translations"` JSON hidden field per template
- `name="template_metadata_json"` JSON hidden field

This makes one submit convenient, but creates large encoded payloads with HTML, JSON, and template syntax mixed together.

---

## How Saving Currently Works (`/admin/settings`)

1. GET route loads all settings from DB (`app.utils.app_settings`) and renders one large form.
2. Client-side JS edits local state for chip lists/translations/email templates.
3. On submit, JS serializes state into hidden JSON inputs.
4. POST route parses all sections and persists many settings at once:
   - languages, flags, lists, translations, branding, email templates, metadata
5. Route redirects back with flash message.

Key backend entry point:
- `Backoffice/app/routes/admin/settings.py` -> `manage_settings()`

Key template:
- `Backoffice/app/templates/admin/settings/manage_settings.html`

---

## Why WAF Flags This Pattern

Common triggers in managed rules:

- Large body size (high field count + large text fields)
- Encoded JSON in form-urlencoded bodies
- HTML/Jinja-like text in posted fields (`<`, `>`, `{{ ... }}`, URLs, punctuation-heavy strings)
- Mixed content types in one request (config + templates + translations)

Even valid admin content can match signatures intended to catch XSS/SQLi.

---

## Azure App Gateway WAF Rules the App Should Respect

The production edge uses Azure Application Gateway WAF with OWASP-managed rules. Exact `ruleId` values can vary by CRS version/policy, but these rule families are commonly involved with rich admin forms:

- `REQUEST-941-*` (XSS detections)
  - Triggered by HTML/script-like patterns in submitted values.
- `REQUEST-942-*` (SQL injection detections)
  - Triggered by punctuation-heavy or SQL-like token patterns in text blobs.
- `REQUEST-920-*` (protocol/enforcement anomalies)
  - Triggered by unusual encoding, malformed inputs, or argument characteristics.
- Size-enforcement / body-inspection limits
  - Large request bodies or many arguments can increase block probability.

Important: do not hardcode behavior around specific IDs only. Build payloads to be rule-friendly by default.

### App-side constraints to follow

Treat these as engineering guardrails for all admin/form submissions:

1. Keep each request body as small as practical (target small JSON payloads over giant form bodies).
2. Avoid re-posting unchanged hidden JSON snapshots.
3. Avoid sending inactive-tab/editor state in the same submit.
4. Prefer structured JSON keys over opaque escaped string blobs.
5. Submit long rich text in dedicated requests (or chunked writes) rather than mixed with unrelated settings.
6. Keep field names stable and explicit (helps targeted WAF exclusions by argument when needed).
7. Validate and normalize on client/server before submit (trim, remove empty keys, remove duplicate arrays).

### Developer do/don't matrix

- Do: one user click can orchestrate multiple smaller API calls.
- Do: send deltas (`changed_only`) for translation/template maps.
- Do: isolate heavy text fields to dedicated endpoint(s).
- Do: instrument request size and blocked endpoint metrics.
- Don't: include all hidden `*_translations` and metadata fields every submit.
- Don't: serialize full editor state into one `application/x-www-form-urlencoded` request.
- Don't: couple unrelated settings into all-or-nothing posts.

### IT/SecOps exclusion strategy (least privilege)

When a false positive still occurs:

1. Capture `ruleId`, `matchVariableName`, URI, and timestamp from WAF logs.
2. Exclude only:
   - the affected endpoint path, and
   - the affected argument name(s).
3. Keep exclusions scoped to known-safe admin/authenticated routes.
4. Prefer argument/path exclusions over global rule disablement.

Use this request template with IT:

- Endpoint: `<path>`
- Method: `<POST/PUT>`
- Blocked rule: `<ruleId>`
- Matched argument: `<matchVariableName>`
- Business justification: `<why content is expected>`
- Proposed scope: `path + argument exclusion only`

---

## Recommended Standard (Keep Single "Save Settings" UX)

Do not require per-tab manual saving. Keep one Save button, but change transport strategy.

### 1) Keep one user action, split network writes behind the scenes

On click of one Save button:

- Submit small/simple settings normally (languages, toggles, short text fields).
- Send heavy sections via targeted JSON endpoints (email templates, large translation maps), either:
  - sequentially in JS, or
  - batched by section with smaller payloads.

User still sees one save action and one success/failure status.

### 2) Send only changed fields (delta), not full snapshots

- Track dirty state client-side.
- Exclude unchanged hidden fields from submission.
- For list translations/templates, send only changed keys/languages.

### 3) Prefer JSON APIs for rich text payloads

- Use `application/json` with explicit schema and size-aware chunks.
- Avoid giant `application/x-www-form-urlencoded` blobs for large nested data.

### 4) Keep backend idempotent and partial-update safe

- Accept missing sections as "no change."
- Validate each section independently.
- Return per-section result map so UI can show precise failures.

### 5) Coordinate with WAF policy (required in production)

App refactor reduces risk, but production should still add targeted WAF exclusions for known safe admin fields/endpoints.

---

## Lean Refactor Plan for `/admin/settings` (Recommended First)

Goal: keep one Save button and avoid an overcomplicated redesign, while preventing large unchanged blobs from being posted.

### Why this endpoint is the first target

Observed payload confirms `manage_settings` currently submits:

- all list translation blobs (`*_translations`)
- all organization translation blobs
- all email templates (large HTML content per language)
- template metadata JSON

even when one simple field changed. This is the exact pattern that increases WAF false positives.

### Minimal architecture change (reusable pattern)

Use a "single UX action, sectioned transport" pattern:

1. Keep one visible Save click.
2. Split data into sections internally:
   - light settings (languages, toggles, small text, branding primitives)
   - list translations
   - email templates + metadata (heavy)
3. Send only dirty sections.
4. Keep backend partial-update safe (missing section = no change).

This pattern can be reused for other admin pages with hidden JSON state.

### Phase plan (low risk, incremental)

#### Phase 1 (fast win, smallest diff)

- Add client-side dirty tracking in `manage_settings.html`.
- Do not submit `email_templates_present=1` unless email/template metadata changed.
- Do not include unchanged hidden `*_translations` fields in request.
- Keep existing `POST /admin/settings` route behavior unchanged for posted fields.

Expected impact: large reduction in payload size for common edits, with minimal backend change.

#### Phase 2 (safe hardening)

- Add dedicated JSON endpoint for heavy template writes:
  - example: `POST /admin/api/settings/email-templates`
  - accept `{ changed_templates: {...}, changed_metadata: {...} }`
- Keep one Save UX:
  - submit light settings form
  - then call heavy endpoint only if dirty
  - show one combined success/failure status

Expected impact: removes the largest WAF trigger from form-urlencoded submissions.

#### Phase 3 (generalize for reuse)

- Extract reusable frontend helper (shared util) for:
  - initial value snapshot
  - dirty key tracking
  - "changed_only" payload builder
- Reuse helper on other heavy admin forms.

---

## Files to Include (Scanned and Prioritized)

### Tier 1 - Required for first refactor

- `Backoffice/app/templates/admin/settings/manage_settings.html`
  - Current single mega form, multiple submit listeners, all hidden blobs synced on submit.
- `Backoffice/app/routes/admin/settings.py`
  - `manage_settings()` currently parses all sections from one request.
  - Best place to add partial-update guards and optional new JSON endpoint.
- `Backoffice/app/utils/app_settings.py`
  - Persistence layer for list translations, branding, email templates, metadata.
  - Needed if we add patch/merge helpers for changed-only writes.

### Tier 2 - Reusable utility extraction

- `Backoffice/app/static/js/lib/form-submit-guard.js`
  - Good shared location for a new lightweight dirty/delta helper module.
- `Backoffice/app/static/js/components/translation-modal.js`
  - Related translation editing behavior; useful integration point if shared state helper is added.

### Tier 3 - Next likely WAF-risk candidates (after `/admin/settings`)

- `Backoffice/app/templates/admin/templates/new_template.html`
  - Posts `name_translations` hidden JSON.
- `Backoffice/app/routes/admin/form_builder.py`
  - Handles multiple translation JSON fields and large form-builder payloads.
- `Backoffice/app/templates/forms/form_builder/form_builder.html`
  - Multiple submit handlers and JSON serialization paths.

Use these as the second rollout wave once settings refactor is stable.

---

## Practical Scope Guardrails (keep it simple)

To avoid overengineering:

1. Do not redesign tabs or UX flow.
2. Do not replace all forms with SPA/API architecture.
3. Start with only the heaviest section (email templates).
4. Keep old route backward-compatible during migration.
5. Add instrumentation: request size + section names submitted.
6. Stop after payload and 403 rate improve; then reuse pattern elsewhere.

---

## System-Wide Refactor Checklist

Use this checklist on any page that posts large state:

1. Is there a single mega form posting many hidden JSON fields?
2. Are there `*_translations`, `*_metadata`, or rich template HTML fields?
3. Does submit include inactive-tab data?
4. Are unchanged values re-sent every time?
5. Is the route all-or-nothing for unrelated sections?

If yes to 2+ items, refactor.

---

## Quick Discovery Queries

Run these to find likely hotspots:

- Hidden JSON blobs in templates:
  - `rg "type=\"hidden\".*tojson|forceescape|_translations|_metadata|_json" Backoffice/app/templates`
- Large state serialization on submit:
  - `rg "addEventListener\\('submit'|JSON\\.stringify\\(" Backoffice/app/templates Backoffice/app/static/js`
- Monolithic POST handlers:
  - `rg "request\\.form\\.getlist|request\\.form\\.get\\(" Backoffice/app/routes`

---

## Rollout Plan

1. Start with endpoints currently blocked in production (`/admin/settings`, form assignment save).
2. Introduce partial JSON endpoints for heavy sections.
3. Keep existing route for backward compatibility during migration.
4. Add payload-size telemetry and request IDs for troubleshooting.
5. Once stable, remove legacy hidden blob fields.

---

## Verification Plan

Before production:

- Test same save flows in staging with production-like WAF policy.
- Confirm payload size decreases significantly.
- Confirm unchanged data is not submitted.
- Confirm partial failure handling is user-friendly and reversible.

In production:

- Monitor `403` rate at Application Gateway WAF logs by endpoint.
- Confirm rule-hit reduction after deploy.
- Keep narrow WAF exclusions only where needed.

---

## Operational Escalation Template

When escalating to IT/SecOps, include:

- Timestamp (UTC)
- Host and full request path
- Correlation/request ID if available
- WAF log fields:
  - `ruleId`
  - `message/details`
  - `matchVariableName`
  - `action`

Ask for targeted exclusions on specific safe fields/paths, not global rule disablement.

