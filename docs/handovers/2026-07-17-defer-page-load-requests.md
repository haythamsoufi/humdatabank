# Handover: Defer Unnecessary Page-Load Requests

**Date:** 2026-07-17  
**Goal:** Cut unnecessary authenticated-page and entry-form HTTP traffic (gateway-504 / worker saturation).  
**Status:** Implemented; peer review found HIGH/MEDIUM flaws to fix before merge.

---

## Context

Production pressure (see `Backoffice/docs/runbooks/incidents/gateway-504-worker-saturation.md`) came partly from:

- Layout-wide calls: `/notifications/api/stream/status`, `/notifications/api/preferences`, CSRF refresh multiplication, chatbot title + tour preload
- Page extras: auto-translate services on load, manage-assignment hierarchies, user-form entity trees, org categories fetch, explore-data compliance off-tab
- Entry form: many matrix `variables/resolve` + auto-load + completion-rate round-trips

A plan was executed across phases. The working tree also contains **unrelated WIP** (presence, `api-fetch.js` `responseAsResult`, data API, scheduler lock, etc.). Do not conflate those with this work when reviewing.

---

## What was implemented (intended behavior)

### Phase 1 — Global (layout)

| Item | Change | Key files |
|------|--------|-----------|
| WS status | Inject `notify_websocket_enabled` → `window.NOTIFY_WS_ENABLED`; skip `GET /notifications/api/stream/status` when set | `template_context.py`, `layout.html`, `components.js` |
| Prefs TTL | 15 min → **24h** (`forceRefreshNotificationPreferencesCache` still invalidates on save) | `components.js` |
| WS limit exceeded | Close socket before `fallbackToPolling()` | `components.js` |
| CSRF interval | Skip when `document.hidden`; cross-tab gate via `localStorage.csrf_last_refresh_at` | `csrf.js` |
| Chatbot title | No fetch on every page load; fetch on FAB click | `chatbot/core.js` |

### Phase 2 — Admin pages

| Item | Change | Key files |
|------|--------|-----------|
| Auto-translate | `loadTranslationServices()` only on `#auto-translate-all-btn` (once; retry on error) | `auto-translate.js` |
| Explore data | `loadComplianceData()` only if `explore_first_tab == 'compliance'` | `explore_data.html` |
| Org index | Inject `part_of_programs` from already-loaded NSs; remove on-load fetch | `organization.py`, `organization/index.html` |
| User form | Entity hierarchies deferred until Entity Permissions tab | `user-form.js` |
| Manage assignment | Categories / secretariat / regions / NS hierarchy deferred to tab open | `manage-assignment.js` |

### Phase 3 — Tours

| Item | Change | Key files |
|------|--------|-----------|
| Preload | Chat-open preload of 3 tours is a **no-op** | `spotlight-tours.js` |
| Sticky hash | Clear `#chatbot-tour=` when register fails | `workflow-tour-parser.js` |
| Static JSON | EN fallback when translated MD has empty steps; ran `flask workflows generate-static` → **32** files under `app/static/generated/tours/` | `workflow_docs_service.py`, untracked `*.fr/es/ar.json` |

### Phase 4 — Entry form

| Item | Change | Key files |
|------|--------|-----------|
| Reverse+tick | Batch `variables/resolve` with `row_entity_ids` (N → 1) | `matrix-handler.js` |
| Bootstrap | `GET /api/forms/assignment/<aes_id>/entry-bootstrap` → `completion_rate` + `auto_load` + `resolved_variables` | `forms_api.py` |
| Client wire | Early `__entryBootstrapPromise` in `main.js`; matrix prefers bootstrap | `main.js`, `matrix-handler.js` |

---

## Files primarily owned by this work

```
Backoffice/app/template_context.py
Backoffice/app/templates/core/layout.html
Backoffice/app/static/js/core/components.js
Backoffice/app/static/js/core/csrf.js
Backoffice/app/static/js/chatbot/core.js
Backoffice/app/static/js/chatbot/spotlight-tours.js
Backoffice/app/static/js/tours/workflow-tour-parser.js
Backoffice/app/services/workflow_docs_service.py
Backoffice/app/static/js/admin/auto-translate.js
Backoffice/app/static/js/admin/user-form.js
Backoffice/app/static/js/admin/manage-assignment.js
Backoffice/app/routes/admin/organization.py
Backoffice/app/templates/admin/organization/index.html
Backoffice/app/templates/admin/data_exploration/explore_data.html
Backoffice/app/routes/forms_api.py
Backoffice/app/static/js/forms/main.js
Backoffice/app/static/js/forms/modules/matrix-handler.js
Backoffice/app/static/generated/tours/*.{fr,es,ar}.json  (untracked; commit if shipping)
```

### Unrelated WIP in the same working tree (do not “fix” as part of this unless asked)

- `presence.js`, `presence_store.py`, presence tests  
- `api-fetch.js` (`responseAsResult`) + many admin JS call-site migrations  
- `data.py` / `data_retrieval_service.py` + tests  
- `scheduler_lock.py`, `gunicorn.conf.py`, seeding, handbook, gateway runbook edits  

---

## Peer-review findings (fix before merge)

Four review passes (notifications/CSRF, tours/chatbot, admin deferrals, entry bootstrap). Prioritized fix list:

### HIGH — fix first

1. **Entry bootstrap empty auto_load still re-fetches** (`matrix-handler.js`)  
   If bootstrap returns `auto_load[fieldId] = { entities: [] }`, client still enters reverse/forward paths because it only checks `entities.length === 0`.  
   **Fix:** If bootstrap *has an entry* for `fieldId`, skip legacy auto-load APIs even when `entities` is empty.

2. **Manage-assignment secretariat deferral broken** (`manage-assignment.js`)  
   Startup `activateSecretariatSubtab(...)` always calls `loadSecretariatHierarchyOnce` / regions loader even when Add Entities → Secretariat is hidden.  
   **Fix:** Only load when `#add-entities-panel` and `#add-entities-secretariat-panel` are visible; keep UI-only tab switching on init without network side effects.

3. **Bootstrap can do more work than before** (`forms_api.py`)  
   Per-matrix `resolve_variables`, duplicate batch resolve for tick + `resolved_variables`, always scans all matrices.  
   **Fix:** Hoist assignment-level resolve once; one batch for tick+rows; skip auto-load work when no matrix has `auto_load_entities`.

### MEDIUM

4. **Notifications:** On “limit exceeded”, also clear `reconnectTimeout` / stop reconnect; call `updateBadgeCountFromAPI()` immediately when entering polling (first load with WS disabled can leave badge blank ~120s). (`components.js`)

5. **Chatbot title:** Fetch on `toggleChat(true)`, not only FAB click (form-builder opens chat without FAB). (`core.js` / `widget-ui.js`)

6. **Manage-assignment categories:** Call `loadCategoriesOnce()` from `activateEntityTab` / `activateAddEntitiesSubTab` when Manage or Countries becomes active (localStorage restore race).

7. **Tours:** Many generated `*.fr/es/ar.json` are English content with non-EN `language` tag — functional for CDN miss avoidance, wrong UX. Prefer `contentLanguage` / mark fallback; longer-term fix localized MD field parser.

8. **No tests** for `/entry-bootstrap`.

### LOW

- CSRF wake path ignores cross-tab `csrf_last_refresh_at`  
- Unguarded `localStorage` in WS inject path  
- Stale comments that still say tours preload on chat open  
- `entry-bootstrap` not in API usage logging skip list (completion-rate is skipped)

---

## Suggested fix order for next agent

1. Matrix-handler bootstrap empty-entry guard (HIGH #1)  
2. Manage-assignment secretariat init visibility gate (HIGH #2)  
3. Deduplicate / gate bootstrap server work (HIGH #3)  
4. Notification limit-exceeded + immediate badge (MEDIUM #4)  
5. Title refresh in `toggleChat(true)` (MEDIUM #5)  
6. Categories on tab activate (MEDIUM #6)  
7. Add unit/route tests for entry-bootstrap  
8. Commit generated tour JSON if shipping CDN/static path  

---

## How to verify

### Quick network checks (DevTools)

1. Any authenticated page: **no** `GET /notifications/api/stream/status` when `window.NOTIFY_WS_ENABLED` is defined; prefs at most once/24h (localStorage).  
2. Open chatbot FAB once: **no** speculative `/workflows/.../tour` for add-user/submit-data/view-assignments.  
3. Organization page: **no** `GET .../part-of-programs` on load; NS grid still has category columns.  
4. Manage assignment: with Manage Entities default, **no** secretariat hierarchy until Secretariat sub-tab shown (after HIGH #2 fix).  
5. Entry form (matrix + auto-load): one `entry-bootstrap`; **no** duplicate auto-load/resolve when bootstrap returned empty entities (after HIGH #1 fix).  
6. Explore Data (non-compliance first tab): **no** compliance fetch until Compliance tab click.

### Commands

```bash
cd Backoffice
python -m flask workflows generate-static   # regenerate tour JSON if needed
# Add tests under tests/unit for forms_api entry-bootstrap when implemented
```

---

## Design notes / contracts

- **`window.NOTIFY_WS_ENABLED`:** set in `layout.html` only when `current_user.is_authenticated`, immediately before `components.js`.  
- **`window.__entryBootstrapPromise` / `__entryBootstrap`:** set by `forms/main.js` when `#completion-rate-display[data-aes-id]` exists.  
- **Auto-load keys:** string FormItem ids matching `data-field-id` / matrix-handler `fieldId`.  
- **Prefs:** do **not** defer prefs fetch to bell click — breaks notification sound if user never opens bell. TTL raise was the chosen approach.  
- **SSR:** do **not** fold completion/auto-load into streamed entry HTML — TTFB was intentionally protected; bootstrap is the consolidation point.

---

## Plan reference

Cursor plan (local): `.cursor/plans/defer_unnecessary_page-load_requests_*.plan.md` (do not edit unless updating the plan).  
Conversation reviews were done via subagents on 2026-07-17 against the live `git diff HEAD`.
