# Agent prompt: Consolidation audit — redundant HTTP calls & DB queries

Use this prompt to run a read-only review across the repo. **Do not implement fixes** unless a finding is trivial; the deliverable is the audit report.

---

## Objective

Review the **Humanitarian Databank** repo (focus **Backoffice** first, then **Website** / **MobileApp** if the same pattern appears) for places where **multiple client-side fetches** or **multiple server-side DB queries** load related data that could be **one page response + one combined query**.

Produce a **prioritized findings report** with concrete file references and recommended fixes.

---

## Reference case study (already fixed — use as the template)

**Problem:** `Backoffice/app/templates/admin/assignments/manage_assignment.html` + `manage-assignment.js`

- Countries were server-rendered in HTML (`countries_by_region`).
- **Part of** filters were loaded client-side via **two sequential API calls** after page load (`/api/part-of-programs`, then `/organization?tab=nss`), causing empty UI then delayed checkboxes.
- The route ran **two separate DB queries** (`get_countries_by_region()` + `get_part_of_category_data()`).

**Fix pattern:**

1. **Client:** Embed static/read-only data in `window.*Config` from the same page render; render UI synchronously on `DOMContentLoaded`. Keep fetch only as fallback for user actions or truly dynamic data.
2. **Server:** One helper — `get_countries_by_region_with_part_of()` — one `Country` query with `joinedload(Country.national_societies)` + `joinedload(Country.secretariat_regional_office)`, build both structures in one Python pass.
3. **Route:** One context helper — `_manage_assignment_country_context()` — instead of separate template kwargs.

Read the current implementation before searching elsewhere:

- `Backoffice/app/utils/country_utils.py` — `get_countries_by_region_with_part_of()`
- `Backoffice/app/routes/admin/assignment_management.py` — `_manage_assignment_country_context()`
- `Backoffice/app/static/js/admin/manage-assignment.js` — `bootstrapPartOfCategoriesFromConfig()`
- `Backoffice/app/templates/admin/organization/index.html` — good precedent: `part_of_programs` embedded server-side to avoid `/api/part-of-programs` on load

---

## Scope

| Area | Priority | Notes |
|------|----------|-------|
| `Backoffice/app/routes/` | P0 | Route handlers that call the same model/util multiple times per request |
| `Backoffice/app/static/js/` | P0 | Chained `fetch()` on page load; data already available server-side |
| `Backoffice/app/templates/` | P0 | `window.*Config` blocks vs lazy JS loaders |
| `Backoffice/app/services/` | P1 | Service methods called in loops (N+1) or duplicate queries in one workflow |
| `Website/` | P2 | Parallel fetches on mount for SSR-hydratable data |
| `MobileApp/` | P2 | Multiple API calls on screen open that could be one endpoint |

Read **`docs/DEVELOPER-HANDBOOK.md`** for architecture conventions before proposing changes.

---

## Patterns to hunt

### A. Client: “waterfall fetches” on page load

Look for:

- `fetch()` / `$.ajax()` / `axios` in `DOMContentLoaded`, `$(document).ready`, or tab-show handlers that load **read-only config** already known when the page was rendered.
- **Chained fetches:** second call uses data from first (e.g. categories → NS mapping).
- **Duplicate endpoints:** same URL fetched from multiple components on one page.
- **Tab-gated lazy load** that re-fetches data already needed on first paint.

Search hints:

```bash
rg "fetch\(" Backoffice/app/static/js
rg "window\.\w+Config" Backoffice/app/templates
rg "\.then\(.*fetch|await fetch.*await fetch" Backoffice/app/static/js
```

Compare each hit to whether the route already queries that data.

### B. Server: duplicate queries per request

Look for:

- Same util called twice in one route (e.g. `get_countries_by_region()` + related lookup).
- Separate queries for parent + child rows that share a FK (`Country` + `NationalSociety`, template + published version, assignment + entity statuses).
- **N+1** in loops: `for x in items: Model.query.get(x.id)`.
- JSON API endpoints called by their own page’s JS when the HTML route could embed the payload.

Search hints:

```bash
rg "\.query\.|db\.session" Backoffice/app/routes --glob "*.py"
rg "get_.*_by_region|joinedload|selectinload" Backoffice/app
```

### C. Missed “embed on render” opportunities

Good signal: server renders partial HTML but JS immediately refetches the same dataset to populate filters/grids/dropdowns.

Check pages with:

- `window.*Config` **and** on-load fetch for overlapping data.
- AG Grid / Select2 / hierarchical selectors that fetch hierarchy on first tab click when the route already loaded parent context.

Start with templates that define `window.*Config`:

- `manage_assignment.html`
- `user_form.html`
- `organization/index.html`
- `manage_settings.html`
- `communication/center.html`
- `manage_translations.html`
- `users.html`
- `assignments.html`

### D. Duplicate helpers

Look for parallel implementations of the same query:

- `get_countries_by_region()` vs `_get_countries_by_region()` in `user_management/helpers.py`
- Inline query logic in routes vs utils/services

Flag consolidation candidates (one canonical helper, others thin wrappers).

---

## Anti-patterns (do not recommend)

- Merging unrelated domains into one mega-endpoint “for performance.”
- One raw SQL join when SQLAlchemy `joinedload` / `selectinload` + one Python pass is enough.
- Removing lazy load for **user-triggered** or **large/rare** data (NS hierarchy, secretariat tree, search autocomplete).
- Caching layers unless there is measured pain — prefer fixing the source query/fetch first.

---

## Good patterns to preserve / replicate

1. **Server embed for first paint:** `organization/index.html` → `part_of_programs` in template.
2. **Config bootstrap:** `window.manageAssignmentConfig`, `window.userFormConfig`, etc.
3. **Combined context helpers:** `_manage_assignment_country_context()` pattern.
4. **Eager loading:** `EntityService.batch_entity_names()` instead of per-row lookups.
5. **Deferred fetch only for heavy/conditional UI:** NS structure, secretariat hierarchy in `manage-assignment.js` (loads on tab first show — OK if data is large and not needed initially).

---

## Methodology

1. **Inventory** — List pages with on-load JS fetches and their route handlers.
2. **Trace** — For each fetch, find the Flask route/service and what DB queries it runs.
3. **Compare** — Does the GET that rendered the page already query overlapping tables?
4. **Classify** each finding:

   | Type | Description |
   |------|-------------|
   | **Quick win** | Embed in existing render; delete redundant fetch |
   | **Server merge** | Combine 2+ queries into one helper with eager loads |
   | **API merge** | Single JSON endpoint replacing 2+ client calls (when page is API-driven) |
   | **N+1 fix** | Batch query / `joinedload` |
   | **Leave alone** | Justify (dynamic, large, user-triggered, cross-page reuse) |

5. **Estimate impact:** latency (extra round-trips), query count, UX (empty → pop-in), maintenance.
6. **Propose minimal fix** per finding — smallest diff that matches existing conventions.

---

## Output format

Write findings to **`Backoffice/docs/audits/consolidation-http-db-review.md`** using this structure:

```markdown
# Consolidation audit: HTTP & DB redundancy

## Executive summary
- N findings: X quick wins, Y server merges, Z leave alone
- Top 3 recommended next PRs

## Findings

### [P0|P1|P2] Short title
- **Location:** file:line, related files
- **Current behavior:** what happens today (N fetches / M queries)
- **Why redundant:** what overlaps
- **Recommended fix:** 2–4 sentences, name proposed helper/approach
- **Effort:** S/M/L
- **Risk:** low/medium — note caching, payload size, stale data
- **Reference pattern:** link to manage_assignment or organization/index fix

## Appendix
- Search commands run
- Pages reviewed checklist
- Explicit “no change” decisions with rationale
```

Also return a **short summary in chat**: top 5 quick wins sorted by impact/effort.

---

## Constraints

- **Read before judging** — confirm data is static on first paint vs intentionally lazy.
- **Minimize scope in recommendations** — no drive-by refactors.
- **Match repo conventions** — utils in `app/utils/`, services in `app/services/`, config via `window.*Config`.
- **No commits** unless explicitly asked.
- **Tests:** note if a combined helper needs a unit test (see `tests/unit/test_utils/test_country_utils.py`).
- **Do not live-fetch** production databank.ifrc.org.

---

## Priority rubric

Score each finding: `(user-visible delay) + (query/fetch count) − (implementation effort)`

Prioritize:

1. Admin pages used frequently (assignments, users, organization, form builder, submissions).
2. Waterfall fetches on initial load (not tab-click lazy load).
3. Same-table duplicate queries in one request.

---

## Suggested starting points

- `Backoffice/app/static/js/admin/` — all admin JS modules
- `Backoffice/app/routes/admin/organization/` — compare with `countries.py` embed pattern
- `Backoffice/app/routes/admin/user_management/` — duplicate `_get_countries_by_region`
- `Backoffice/app/templates/admin/user_management/user_form.html` + JS
- Form builder templates/JS — often multiple indicator/template fetches
- Any route rendering a grid where JSON endpoint duplicates the grid query

---

## Success criteria

The audit is done when:

- [ ] At least **15 admin pages/flows** explicitly checked (pass or fail)
- [ ] Every on-load `fetch` in `Backoffice/app/static/js/admin/` classified
- [ ] At least **5 concrete quick wins** with file paths
- [ ] No recommendation that merges unrelated concerns
- [ ] Report written to `Backoffice/docs/audits/consolidation-http-db-review.md`
