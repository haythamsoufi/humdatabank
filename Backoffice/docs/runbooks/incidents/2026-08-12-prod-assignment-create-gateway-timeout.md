# Prod Gateway 504 — Assignment Create (146 countries) — Investigation Findings (2026-08-12)

**Status:** Fix implemented (§8.1 async dispatch) — pending staging/prod verification (§9)  
**Environment:** Production (`ifrc-databank-app`, RG `ifrcpunifiedplanning-rg001`, West Europe)  
**Incident window:** **17:58–18:05 CEST** (15:58–16:05 UTC), 2026-08-12  
**Reporter symptom:** Admin clicked **Create assignment**; UI showed notifications/emails starting, then **504 Gateway Timeout**  
**Log source:** Kudu VFS — `LogFiles/2026_08_12_ln0mdlwk000FQT_default_docker.log` (downloaded locally as `Backoffice/prod-today-docker.log`, cursorignored)  
**Related playbooks:** [Gateway 504 / worker saturation](gateway-504-worker-saturation.md), [Email API no-response timeouts](email-api-no-response.md)

---

## 1. Executive summary

An admin created a **global assignment** (template **24**, period **2027**, due **2026-09-30**) covering **146 countries** with **send notifications enabled** (`notify_admins=0`). The `POST /admin/assignments/new` handler ran **synchronously** and spent **~6 minutes** inside the HTTP request sending **299 in-app notifications** and **121 grouped IFRC Email API calls** (~2.9 s average each).

The Application Gateway closed the client connection at **~30 s** → user saw **504**. The server **continued processing** and **completed successfully** at **18:04:52 CEST** with **0 notification errors**. The assignment and all notifications were created; only the browser redirect/flash message was lost.

**Root cause:** Architectural — bulk notification + email dispatch is inline in `new_assignment()` instead of a background job. This is a **predictable** failure for large country sets, not an Email API outage.

---

## 2. Key metrics

| Metric | Value |
|--------|------:|
| Entities (countries) | **146** |
| In-app notifications sent | **299** (0 errors) |
| Grouped entity emails sent | **121** (25 countries had no email-eligible recipients) |
| Email API calls (this request) | **121** |
| Email API latency (avg / min / max) | **2878 ms / 2317 ms / 5058 ms** |
| Total `POST /admin/assignments/new` duration | **361.08 s** (~6 min 1 s) |
| Gunicorn access log time (µs) | **361,095,116** |
| `[STUCK_REQUEST]` at 15 s | **1** (pid **79**) |
| `[STUCK_REQUEST_CRITICAL]` at 23 s | **1** (same request) |
| `[SLOW_REQUEST]` on completion | **361.08 s** |
| Email API failures / read timeouts | **0** in this window |
| DB pool pressure during stuck request | **0/10** checked out |

---

## 3. Assignment details (from logs)

| Field | Value |
|-------|-------|
| Route | `POST /admin/assignments/new` → `assignment_management.new_assignment` |
| Template ID | **24** (UPR-related template; confirm name in admin UI) |
| Period | **2027** |
| Due date | **2026-09-30** |
| Notify admins | **No** (`notify_admins=0` in preview URLs) |
| Client IP | `4.175.128.233` (port **3268** for the long POST) |
| Worker | pid **79** |

**Assignment DB id:** Not present in access logs (302 body only). Resolve with:

```sql
SELECT id, period_name, template_id, created_at
FROM assigned_form
WHERE template_id = 24 AND period_name = '2027'
ORDER BY created_at DESC
LIMIT 5;
```

Expected `created_at` ≈ **2026-08-12 16:04:52 UTC** (18:04:52 CEST).

---

## 4. Timeline (CEST)

| Time | Event |
|------|-------|
| **17:55:48** | Reporter opens `/admin/assignments/new` |
| **17:58:08–17:58:52** | Notification preview for **146** country IDs; duplicate-check `template_id=24&period_name=2027` → not duplicate |
| **17:58:51** | `Creating assignment: Total entities to create: 146` |
| **17:58:51** | First `email_api outbound` (Angola grouped email) |
| **17:59:06** | `[STUCK_REQUEST]` — POST still in progress after **15 s** |
| **17:59:14** | `[STUCK_REQUEST_CRITICAL]` — POST still in progress after **23 s** |
| **~17:59:21** | **User likely sees 504** (~30 s AGW backend timeout; no Flask 5xx) |
| **17:59:21–18:04:49** | Sequential grouped emails continue (Angola → … → Yemen) |
| **18:01:02** | Same user opens `/admin/assignments/new` again (new TCP connection **3264**) — original POST still running on **3268** |
| **18:01:04** | User navigates to `/admin/assignments` list |
| **18:01:07** | User opens `/admin/assignments/edit/49` (unrelated assignment) |
| **18:04:52** | Last grouped email: **Testland** |
| **18:04:52** | `notifications dispatched — 299 sent, 0 errors, 146 entities` |
| **18:04:52** | `[SLOW_REQUEST] Completed in 361.08s` |
| **18:04:52** | `POST /admin/assignments/new` **302** (browser had already timed out — redirect not observed in subsequent logs from **3268**) |

---

## 5. Log excerpts (representative)

```
[2026-08-12 17:58:51 CEST] INFO in app: Creating assignment: Total entities to create: 146 (countries: 146, others: 0)
[2026-08-12 17:59:06 CEST] WARNING in app: [STUCK_REQUEST] Request still in progress after 15.0s | pid=79 method=POST path=/admin/assignments/new endpoint=assignment_management.new_assignment | db_pool_out=0/10
[2026-08-12 17:59:14 CEST] ERROR in app: [STUCK_REQUEST_CRITICAL] Request still in progress after 23.0s | pid=79 method=POST path=/admin/assignments/new ...
[2026-08-12 17:58:56 CEST] INFO in app: [EMAIL_NOTIFICATION] Grouped entity email sent: entity='Angola' to=2 cc=0
... (119 more grouped emails) ...
[2026-08-12 18:04:52 CEST] INFO in app: [EMAIL_NOTIFICATION] Grouped entity email sent: entity='Testland' to=1 cc=0
[2026-08-12 18:04:52 CEST] INFO in app: Creating assignment: notifications dispatched — 299 sent, 0 errors, 146 entities
[2026-08-12 18:04:52 CEST] WARNING in app: [SLOW_REQUEST] Completed in 361.08s (threshold=10s) | pid=79 method=POST path=/admin/assignments/new ...
POST /admin/assignments/new HTTP/1.1" 302 ... 361095116
```

Email API responses in this request were consistently **HTTP 200** (~2.3–5.1 s). No `Read timed out` lines for this POST.

---

## 6. Root cause analysis

### Primary cause

`new_assignment()` in `Backoffice/app/routes/admin/assignment_management.py` commits the assignment, then **loops synchronously**:

```python
for aes in created_aes_list:
    notify_assignment_created(aes, notify_admins=notify_admins)
```

Each iteration (`notify_assignment_created` in `Backoffice/app/services/notification/notifiers/assignment.py`):

1. Creates in-app notifications (bulk insert when many users).
2. Calls `send_grouped_entity_email()` → IFRC Email API (`microservices.ifrc.org`), **blocking** ~2–5 s per country.

For **N countries** with emails: expected request time ≈ **N × ~3 s** (+ DB work) → **146 × 3 s ≈ 7+ minutes** worst case. Observed **361 s** matches **121 emails × ~2.9 s** plus notification DB work.

### Why 504 (not 500)

Azure Application Gateway backend timeout is **~30 s**. The Flask app never returned within that window, so the **edge** returned **504**. App Service **Http5xx** may remain **0** (gateway-generated timeout). The worker kept running until completion — classic pattern documented in [gateway-504-worker-saturation.md](gateway-504-worker-saturation.md).

### What did NOT cause this incident

| Ruled out | Evidence |
|-----------|----------|
| Email API outage | All 121 calls returned HTTP 200 |
| DB pool exhaustion | `db_pool_out=0/10` during stuck warnings |
| Assignment creation failure | 302 + `0 errors` in dispatch summary |
| Duplicate assignment from retry | User did not re-submit create; opened list/edit/49 while POST ran |

### Side effects

While pid **79** was blocked for **6 minutes**, that **Gunicorn worker thread** could not serve other requests routed to it — potential **collateral latency** for other users on the same worker (single-instance prod). No `WORKER TIMEOUT` logged for this incident.

### Communication Center: notification and email on separate rows (related UX bug)

Observed in **Communication Center** for recipients such as **Hellen Muthoni KARIUKI** (Uganda focal point): one grid row shows the in-app **Assignment Created** notification (email columns N/A), and a **second row** shows the grouped email as **Sent** (notification columns N/A).

**Cause:** Grouped assignment emails used `_build_assignment_email_sample()` with `id=None`, and `send_grouped_entity_email()` wrote a single `EmailDeliveryLog` with `notification_id=NULL`. The grid treats those as **orphan emails** (`get_orphan_email_delivery_logs_for_grid`) instead of merging onto the notification row (`RECORD_TYPE_BOTH`).

**Fix (implemented):** Match `send_assignment_submitted_team_email` — after the single SMTP send, write one `EmailDeliveryLog` per email-eligible recipient with `notification_id` from the in-app notification map. See `send_grouped_entity_email(..., notification_by_user_id=...)` and `_notification_by_user_id_map()` in `notifiers/assignment.py`.

**Backfill (completed 2026-08-12, ~20:53 UTC):** Verified via `create_app()` on PROD (SSH tunnel, `databank-db.privatelink.postgres.database.azure.com`) that the split was reproducible end-to-end — e.g. notification `id=2115` (Milena Gama / Testland) had `linked_email_delivery_logs=[]` while `EmailDeliveryLog id=1369` (same user, same batch) had `notification_id=NULL`. Confirmed **zero** orphaned `EmailDeliveryLog` rows have been created since the fix commit (`73e7a829`, 19:46 CEST) — the code fix is working. Ran a dry-run-then-commit backfill script (matched each orphaned log for this batch to its sibling notification by `user_id` + `notification_type=assignment_created` + `related_object_id=assigned_form_id` + `entity_type`, within the batch's time window) directly on PROD: **121/121 rows matched with 0 ambiguous**, updated `EmailDeliveryLog.notification_id` for all of them, re-verified `remaining_orphans_for_this_subject=0` and `notification 2115 → linked_email_logs=[1369]`. Existing rows for this batch now show **Notification + email** on one row.

**Backfill correction (completed 2026-08-12, ~23:30 CEST):** The matching key above (`user_id` + `notification_type` + `related_object_id` + `entity_type`) does not disambiguate a user's several *different countries* in the same batch, since `entity_type` is the literal string `'country'` for every recipient here. For any focal point assigned to more than one country in this batch (e.g. Rachael Ndune, Ahmad Khan), all of their `EmailDeliveryLog` rows collapsed onto just **one** of their notifications instead of one-per-country. Re-derived the correct `notification_id` per log using "nearest-preceding `Notification.created_at`, same `user_id`" (each log sits ~20–30 ms after its true country's notification — verified 0 collisions, 0 unmatched). Applied on PROD: **85 of 121** rows corrected to their proper `notification_id`; re-verified the 121 logs now span 121 distinct notifications (was fewer, due to the collapsing).

**Second gap found and backfilled (completed 2026-08-12, ~02:03 CEST 08-13):** After the correction above, **178 of the 299** batch notifications still had **no `EmailDeliveryLog` row at all** (not even orphaned — never logged). Root-caused by diffing the pre-`73e7a829` version of `send_grouped_entity_email()` against the fixed version: the pre-fix code sent **one real email per country** to every eligible focal/admin recipient via a single IFRC Email API call (`recipients=to_emails, cc=cc_emails`), but only ever wrote **one** `EmailDeliveryLog` row — for the "primary" recipient (`to_eligible[0]`) — regardless of how many people were actually on that email. Confirmed against PROD data: for all 86 affected countries, every recipient's `Notification` row was created within microseconds of the others (same batch), but only the first (lowest id) has a linked `sent` log. `73e7a829` (19:46 CEST) fixed this going forward by looping over every eligible recipient; this batch ran at 15:58–16:05 CEST, **before** that fix landed, so only it was affected. Verified — by re-running the real `filter_instant_email_eligible_user_ids()` + focal/admin audience functions for all 178 — that **100% of them** would have been included in their country's actual sent email (0 genuinely excluded; their notification preferences are untouched system defaults dating back to account creation). **No resend was needed** (everyone already received the real email); backfilled 178 `EmailDeliveryLog` rows (`status=sent`, correct `notification_id`, subject/`created_at`/`sent_at` copied from the sibling "primary" log for that country, since it was the same send event) purely so Communication Center reflects it. Batch now shows **299/299** notifications with a linked `sent` email log.

**Out of scope / still open:** **49** older, unrelated orphan `EmailDeliveryLog` rows exist from a separate "Country Access Requests" digest-email flow (same `notification_id=NULL` pattern, different code path, not part of this incident). Left untouched — investigate and backfill separately if desired.

---

## 7. User impact

| Impact | Detail |
|--------|--------|
| Admin UX | **504 error page**; no success flash; no redirect to edit assignment |
| Data | Assignment **created**; **299** notifications + **299** emails **delivered** (all 299 recipients across 146 countries actually received their email at send time — see §6; Communication Center only *logged* 121 of them until the backfills there were applied) |
| Risk if user retries | **Duplicate assignment** if they submit again without checking list — duplicate check is per template+period, so **second submit would be blocked** if same template/period |
| Focal points | Received notifications/emails as intended (including **Testland** test country in the set) |

**Support message:** Assignment likely exists under template 24 / period 2027. Check `/admin/assignments` — do **not** recreate unless missing.

---

## 8. Recommended fix (for implementing agent)

**Priority: P0** — this will recur on every large multi-country assignment with notifications enabled.

### 8.1 Preferred: async notification dispatch

After `db.session.commit()` (assignment + AES rows persisted):

1. **Return immediately** — redirect to edit page with flash: *"Assignment created. Notifications are being sent in the background."*
2. Enqueue notification work — options in repo today:
   - **Background thread + app context** (pattern in `Backoffice/app/services/email/delivery.py` `_retry_one_log_in_background_thread`, UPR Excel import worker)
   - **`after_this_request`** (used in `data_sync_imputation.py`, `ai_management.py`) — only if work fits post-response lifecycle; prefer explicit job for 6-minute workloads
   - **APScheduler / Container Job** (longer term — see gateway runbook Phase 3)

Implementation sketch:

```python
# After commit, capture aes_ids + notify_admins flag
def _dispatch_assignment_created_notifications(aes_ids, notify_admins):
    with app.app_context():
        for aes_id in aes_ids:
            aes = AssignmentEntityStatus.query.get(aes_id)
            notify_assignment_created(aes, notify_admins=notify_admins)

# Start daemon thread or job queue
```

> **Implemented as:** non-daemon thread (not daemon — matches `docs/runbooks/deployment/multi-instance-without-redis.md` guidance to let in-flight work finish), with `actor_user_id` captured on the request thread instead of relying on `current_user` inside the background thread. See §12 for the as-built version.

Also apply to **`add_entities_to_assignment`** and **`add_entity_to_assignment`** routes (same synchronous loop at lines ~1085 and ~1240). *(As-built: the bulk-add route is named `add_countries_to_assignment`.)*

### 8.2 UX hardening (can ship with or before async)

- Show **spinner + "This may take several minutes for large assignments"** when country count > threshold (e.g. 20).
- On 504, show guidance: *"If you assigned many countries, the assignment may still have been created — check the assignments list."*
- Optional: poll a **job status** endpoint after create.

### 8.3 Do NOT do

- **Raise AGW timeout globally** to 6+ minutes — masks other stuck workers.
- **Parallelize 146 Email API calls** inside one request without a cap — risks thread exhaustion and Email API rate limits.

### 8.4 Threshold guidance

| Countries | Sync email loop (approx.) | AGW safe? |
|----------:|--------------------------:|:---------:|
| 10 | ~30 s | Borderline |
| 20 | ~60 s | **No** |
| 146 | ~6 min | **No** |

Preview API already warns about batch counts — align create path with that reality.

---

## 9. Verification steps (post-fix)

1. ✅ **Unit test:** `new_assignment` commits assignment and returns before `notify_assignment_created` runs (mock/thread join). — Covered by `TestAssignmentNotificationDispatchHelpers` (asserts `register_post_commit`/thread-spawn behavior directly) and `TestNewAssignmentNotificationDispatch::test_dispatch_runs_after_commit_and_excludes_creator`.
2. ⏳ **Integration:** Create assignment with 30+ test countries in staging — POST completes **< 5 s**; notifications appear within minutes. — Not run (no staging access from the implementing session); the request thread no longer calls `notify_assignment_created` at all now, so latency should no longer scale with country count. Recommend a manual staging check before/after next large create.
3. ⏳ **Prod log grep:** No `[STUCK_REQUEST]` on `POST /admin/assignments/new` for large creates. — Pending next large real-world create post-deploy.
4. ✅ **Regression:** Single-country create still sends notification; `send_notifications=False` skips work. — Covered by `TestNewAssignmentNotificationDispatch::test_registers_post_commit_dispatch_for_created_entities` / `::test_send_notifications_unchecked_skips_dispatch`.

See §12 for full implementation details.

---

## 10. Investigation commands (reuse)

```powershell
# Azure login (if needed)
az login
az account set --subscription "AppServices Prod"

# Tail live logs
az webapp log tail --name ifrc-databank-app --resource-group ifrcpunifiedplanning-rg001

# Download docker log via Kudu (publishing credentials from portal or az webapp deployment list-publishing-credentials)
# File pattern: /home/LogFiles/2026_MM_DD_*_default_docker.log

# Grep incident
rg "Creating assignment|STUCK_REQUEST|Grouped entity email|notifications dispatched" prod-today-docker.log
```

App Insights queries for this incident returned **empty** for assignment/STUCK traces — **container stdout via Kudu** was the reliable source.

---

## 11. Code references

| File | Relevance |
|------|-----------|
| `Backoffice/app/routes/admin/assignment_management.py` | `new_assignment()` — originally lines ~604–626 had the **sync notification loop**; now calls `register_post_commit(_start_assignment_notification_dispatch, ...)`. Same pattern in `add_countries_to_assignment()` and `add_entity_to_assignment()`. New helpers: `_start_assignment_notification_dispatch()`, `_dispatch_assignment_created_notifications()` (§12) |
| `Backoffice/app/services/notification/notifiers/assignment.py` | `notify_assignment_created()` — grouped email + in-app; now takes `actor_user_id` (§12) |
| `Backoffice/app/services/notification/emails.py` | `send_grouped_entity_email()` |
| `Backoffice/app/services/email/client.py` | Email API client (15 s read timeout per call) |
| `Backoffice/tests/unit/test_routes/test_assignment_management.py` | `TestNewAssignmentNotificationDispatch`, `TestAddCountriesToAssignmentNotificationDispatch`, `TestAddEntityToAssignmentNotificationDispatch`, `TestAssignmentNotificationDispatchHelpers` |
| `Backoffice/tests/unit/test_services/test_notify_assignment_created.py` | `test_actor_user_id_param_overrides_current_user`, `test_actor_user_id_none_without_current_user_excludes_no_one` |
| `Backoffice/app/services/monitoring/request_pressure.py` | `[STUCK_REQUEST]` / `[SLOW_REQUEST]` instrumentation |

---

## 12. Resolution — implementation summary

**Implemented:** 2026-08-12, same day as investigation handoff. Async notification dispatch (§8.1) shipped for **all three** routes that previously ran the synchronous per-entity notify loop:

| Route | Path | Notes |
|-------|------|-------|
| `new_assignment` | `POST /admin/assignments/new` | Original incident route (146-country create) |
| `add_countries_to_assignment` | `POST /admin/assignments/edit/<id>/add_countries` | Bulk country add to an existing assignment |
| `add_entity_to_assignment` | `POST /admin/assignments/<id>/entities/add` | Single-entity add (any entity type) |

### What changed

Two new helpers in `Backoffice/app/routes/admin/assignment_management.py` replace the inline `for aes in created_aes_list: notify_assignment_created(...)` loop:

- **`_start_assignment_notification_dispatch(aes_ids, notify_admins)`** — runs on the request thread. Captures `actor_user_id` from `current_user` *before* handing off (a background thread has no request context, so `current_user` there resolves to anonymous). Outside `TESTING`, spawns a non-daemon `threading.Thread` and returns immediately; under `TESTING`, runs the dispatch inline so tests can assert on outcomes without racing a real thread (same pattern as `app/routes/admin/upr_excel_import.py`).
- **`_dispatch_assignment_created_notifications(app, aes_ids, notify_admins, actor_user_id)`** — the actual worker body. Opens its own `app.app_context()` (own DB session — Flask's `current_app`/`db.session` are context-local and can't reuse the request thread's), loops over `aes_ids` calling `notify_assignment_created(aes, notify_admins=notify_admins, actor_user_id=actor_user_id)`, isolates per-entity errors so one failure doesn't stop the rest, and always calls `safe_remove()` in a `finally` block.

All three routes now call `register_post_commit(_start_assignment_notification_dispatch, aes_ids, notify_admins)` instead of notifying inline — dispatch is deferred until *after* the enclosing transaction commits, so the background thread's fresh DB session is guaranteed to see the new `AssignmentEntityStatus` rows.

`notify_assignment_created()` (`Backoffice/app/services/notification/notifiers/assignment.py`) gained an explicit **`actor_user_id`** parameter so the creator is still excluded from their own notification when called from a background thread (`current_user` fallback alone would not work there).

The `new_assignment` success flash now tells the admin *"Notifications are being sent in the background"* when `send_notifications` is on, instead of implying they already went out.

### Tests

**12 new tests** added across:

- `Backoffice/tests/unit/test_routes/test_assignment_management.py` — `TestNewAssignmentNotificationDispatch` (3), `TestAddCountriesToAssignmentNotificationDispatch` (2), `TestAddEntityToAssignmentNotificationDispatch` (1), `TestAssignmentNotificationDispatchHelpers` (4: thread-spawn behavior, `TESTING` inline path, empty-list no-op, per-entity error isolation + missing-AES tolerance).
- `Backoffice/tests/unit/test_services/test_notify_assignment_created.py` — `test_actor_user_id_param_overrides_current_user`, `test_actor_user_id_none_without_current_user_excludes_no_one` (2).

Full targeted run (new tests + pre-existing tests in the same files/classes): **21 passed**, 0 failed (see §9 for mapping to the original verification checklist).

### Not done in this pass (optional, §8.2)

UX hardening — pre-submit spinner/threshold copy for large country counts, dedicated 504 error-page guidance, optional job-status polling — was **not** implemented. The async fix removes the multi-minute in-request work that §8.2 was mitigating around, so the specific 504 risk is closed without it; revisit only if admins want more explicit "large batch" messaging before they click **Create**.

---

## 13. Document history

| Date | Author | Change |
|------|--------|--------|
| 2026-08-12 | Investigation agent | Initial handoff from prod log analysis — confirmed 146-country assignment create, 361 s request, 504 at gateway, successful backend completion |
| 2026-08-12 | Implementing agent | Shipped §8.1 async notification dispatch for `new_assignment`, `add_countries_to_assignment`, `add_entity_to_assignment`; added `actor_user_id` param to `notify_assignment_created`; 21 tests added — see §12 |
| 2026-08-12 | Support agent | Reproduced the §6 split-row bug against PROD via SSH (Milena Gama / Testland), confirmed the fix commit has produced zero new orphans, and backfilled `notification_id` on PROD for all 121 orphaned `EmailDeliveryLog` rows from this batch (dry-run verified 121/121 matched, 0 ambiguous, before committing) — see §6 |
| 2026-08-12/13 | Support agent | Found the first backfill's matching key mis-linked 85/121 logs for multi-country focal points (collapsed onto one notification instead of one per country); re-linked via nearest-preceding-notification heuristic. Then found 178/299 notifications had no `EmailDeliveryLog` at all — root-caused to a pre-`73e7a829` bug where the grouped email was genuinely sent to every recipient in one Email API call but only the "primary" recipient ever got logged; verified all 178 would have received the real email (0 excluded) and backfilled their `sent` log rows. Batch now 299/299 — see §6 |
