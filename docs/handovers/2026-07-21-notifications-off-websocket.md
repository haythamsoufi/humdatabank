# Handover: Move notifications off WebSocket (HTTP-only)

**Date:** 2026-07-21  
**Goal:** Stop using long-lived WebSockets for notifications; use short HTTP requests only.  
**Product decision:** No need for instant notification push.  
**Status:** Not implemented — ready for another agent to execute.

---

## Why

Production gateway 502/504 / worker saturation is worsened by notification WebSockets on Gunicorn **`gthread`**:

- **1 WebSocket connection = 1 worker thread** for the entire time the page/tab stays open.
- Each user can open **multiple tabs** → multiple notification WS → multiple pinned threads.
- Prod capacity is small (e.g. `GUNICORN_WORKERS=3` × `GUNICORN_THREADS=8` = **24 slots**). WS budget reserves HTTP threads (`threads − 2` per worker), but open notification sockets still consume a large share of concurrency.
- Infra correlated ~9–10 long-lived `/api/notifications/ws` connections with unresponsive windows. Lightweight HTTP (presence, prefs, csrf) then **queues** and hits App Gateway ~30s → client 504.

Notifications do **not** need realtime push. Needed behaviour:

1. Load unread badge / list when useful (page load and/or bell open)
2. Occasional refresh is fine (seconds–minutes latency OK)

Short HTTP holds a thread for **milliseconds**, then frees it. WS holds it for **hours**.

Related context:

- `Backoffice/docs/runbooks/incidents/gateway-504-worker-saturation.md`
- `Backoffice/docs/runbooks/incidents/gateway-loadtest-reproduction-plan.md`
- Prior deferrals: `docs/handovers/2026-07-17-defer-page-load-requests.md`

**Out of scope:** AI chat / AI docs WebSockets — those are real streaming use cases. Do **not** disable global `WEBSOCKET_ENABLED` if that also kills AI WS unless you split the flags.

---

## Current behaviour (what exists today)

| Piece | Location | Behaviour |
|-------|----------|-----------|
| Client notification WS | `Backoffice/app/static/js/core/components.js` | Connects to `/api/notifications/ws`; reconnect; on failure/`limit_exceeded` → `fallbackToPolling()` |
| Polling fallback | same file | `updateBadgeCountFromAPI()` then `setInterval(..., 120000)` (2 min) |
| WS status gate | `layout.html` / `template_context.py` / `components.js` | `window.NOTIFY_WS_ENABLED` / `notify_websocket_enabled`; may skip `/notifications/api/stream/status` |
| Server WS endpoint | `Backoffice/app/routes/notifications_ws.py` | Registers `/api/notifications/ws`, heartbeats ~15s, uses `ws_manager` channel `notifications` |
| Broadcast on create | `Backoffice/app/services/notification/core.py` | Calls `broadcast_notification` / `broadcast_unread_count` via `ws_manager` |
| Shared WS pool | `Backoffice/app/utils/ws_manager.py` | Per-worker total + per-user caps; notifications share budget with AI channels |
| Config | `WEBSOCKET_ENABLED`, stream status in `Backoffice/app/routes/notifications.py` | Global-ish enablement — be careful not to break AI |

---

## Target behaviour

1. **Never open** `/api/notifications/ws` from the layout/notification UI.
2. Badge/count via **HTTP only**:
   - Initial: existing `updateBadgeCountFromAPI()` (or equivalent) on load / when visible
   - Refresh: keep a **slow poll** (current 120s is fine) **or** refresh mainly when the bell opens + optional slow poll
   - List: keep loading `/notifications/api` when the dropdown opens (already mostly on-demand)
3. Server may keep the notifications WS route for a deprecation period, but nothing in UI should connect.
4. `broadcast_notification` / `broadcast_unread_count` become no-ops for notifications UX (safe to leave calls; they simply find no sockets). Optional cleanup later.
5. **AI WebSockets stay enabled** unless explicitly redesigned.

Suggested config approach (prefer explicit over abusing global flag):

- Add something like `NOTIFY_WEBSOCKET_ENABLED=false` (default false going forward), wired into `notify_websocket_enabled` / `NOTIFY_WS_ENABLED`
- Do **not** set `WEBSOCKET_ENABLED=false` globally if AI chat still needs WS

---

## Implementation checklist

### Client (primary)

- [ ] In `components.js`, force notification path to **polling/HTTP only** (skip `connectWebSocket` / `createWebSocketConnection` for notifications).
- [ ] Ensure badge still updates on first load when WS is skipped (today `fallbackToPolling()` already calls `updateBadgeCountFromAPI()` — preserve that; fix any path that assumed WS would push the first unread count).
- [ ] Stop reconnect / ping intervals for notification WS.
- [ ] Keep bell-open → `GET /notifications/api` behaviour.
- [ ] Prefer injected `NOTIFY_WS_ENABLED === false` so no `/notifications/api/stream/status` call is needed.
- [ ] Clean up dead notification-WS code paths only if safe; otherwise leave unused behind a flag for easy rollback.

### Server / config

- [ ] Add dedicated **notifications** WS kill-switch (config + env), default off in prod intent.
- [ ] Wire `template_context.py` / layout inject so client sees disabled without probing.
- [ ] Optionally stop registering notifications WS route when flag is off (`notifications_ws.py` `register_notifications_ws`).
- [ ] Leave AI WS registration alone (`ai_ws.py`).
- [ ] Optional: no-op or gate `broadcast_*` for notifications when flag off (reduces useless work).

### Tests

- [ ] Update/add JS or route tests so notification UI works with WS disabled.
- [ ] Confirm AI WS tests still pass.
- [ ] Confirm `ws_manager` notification channel budget is irrelevant when no clients connect (no change required if client never connects).

### Verify manually

- [ ] Login → badge loads without WS in Network tab (no `ws` / `wss` to `/api/notifications/ws`).
- [ ] Open bell → list loads over HTTP.
- [ ] Create a notification as another admin → badge updates within poll interval (or on next bell open / navigation) — **not** instantly; that is accepted.
- [ ] Multiple tabs do **not** each hold a WS thread.
- [ ] SSH pressure script / logs: fewer long-lived notification WS; `[WS_POOL]` notification counts drop.

### Deploy / rollback

- [ ] Ship behind config flag first (`NOTIFY_WEBSOCKET_ENABLED=false` in App Settings).
- [ ] Rollback = set flag true (or revert client) if product complains about delayed badge updates.

---

## Non-goals

- Instant push / Redis pubsub for notifications
- Moving AI chat off WebSocket
- Increasing `GUNICORN_THREADS` as a substitute for this change
- Full deletion of `notifications_ws.py` in the first PR (flag-off is enough)

---

## Success criteria

- Zero notification WS connections from normal browsing
- Notification badge/list still work via HTTP
- Measurable drop in pinned `gthread` usage under multi-tab load
- AI WebSocket behaviour unchanged
