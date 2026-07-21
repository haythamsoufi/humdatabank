# Handover: Cross-tab dedupe for notification badge HTTP polling

**Date:** 2026-07-21  
**Goal:** One browser (all tabs) should fetch notification badge count **once**, not once per tab.  
**Status:** Proposal — not implemented.  
**Depends on:** Notifications on HTTP polling (notification WebSocket permanently off; AI WS uses `WEBSOCKET_ENABLED` only). See `docs/handovers/2026-07-21-notifications-off-websocket.md`.

---

## Why

With notification WebSockets disabled, each authenticated page runs `fallbackToPolling()` in `Backoffice/app/static/js/core/components.js`:

1. Immediate `GET /notifications/api/count`
2. Then `setInterval(..., 120000)` (every 2 minutes)

**Problem:** every open tab does this independently.

| Tabs open | Approx. count requests every 2 min |
|-----------|-------------------------------------|
| 1 | 1 |
| 5 | 5 |
| 10 | 10 |

That multiplies cheap HTTP traffic under real multi-tab use (dashboard + forms + admin). Each request is short (milliseconds when workers are free) but still competes for `gthread` slots and adds noise during load incidents.

**Product need:** badge freshness within ~2 minutes is fine. Instant push is not required.

---

## Current behaviour

| Item | Today |
|------|--------|
| Badge poll | Per tab, no coordination |
| Prefs (`/notifications/api/preferences`) | Already cross-tab friendly via `localStorage` TTL (24h) |
| CSRF refresh | Cross-tab gate via `localStorage.csrf_last_refresh_at` |
| Presence sync | **Leader tab + `BroadcastChannel`** in `Backoffice/app/static/js/forms/modules/presence.js` |

Badge polling should follow the **presence** pattern, not invent a new one.

---

## Proposed behaviour

1. Elect **one leader tab** per browser origin (or per logged-in session key).
2. **Only the leader** calls `GET /notifications/api/count` (initial + interval).
3. Leader writes result to a shared channel / `localStorage` and broadcasts to siblings.
4. Follower tabs **only update the badge UI** from the shared count — no network.
5. When the leader tab closes / goes hidden for too long, another visible tab takes over.
6. Optional: skip polling entirely while `document.hidden` on the leader (or hand off to a visible tab).

Target: **≈ 1 count request per user browser**, regardless of tab count.

---

## Recommended design

### Primary: BroadcastChannel + leader election (mirror presence)

Reuse ideas from `presence.js`:

- `BroadcastChannel('ifrc-notifications-badge')` (fixed name; not assignment-scoped)
- Messages: `HELLO`, `LEADER`, `COUNT`, `BYE` / `ABDICATE`
- Leader posts `COUNT { count, ts }` after each successful fetch
- Followers render `updateNotificationsBadge(count)` from `COUNT`
- Lease / heartbeat so a dead leader is replaced (e.g. if no `LEADER`/`COUNT` for `POLL_MS + skew`)

Also persist last count for fast paint:

```text
localStorage.notif_badge_count = <int>
localStorage.notif_badge_count_at = <epoch_ms>
```

On load, any tab may paint from cache immediately; only the leader refreshes from network when stale (e.g. age ≥ 120s, or always on first leadership).

### Fallback if BroadcastChannel missing

Use `localStorage` + `storage` event only:

- Before fetch: if `notif_badge_count_at` younger than poll interval, skip fetch and use cached count
- After fetch: write count + timestamp
- Other tabs hear `storage` and update badge

Slight race possible (two tabs fetching once); acceptable as degraded mode.

---

## Implementation checklist

### Client (`components.js` — notification block)

- [ ] Extract badge polling into helpers: `becomeLeader()`, `resignLeader()`, `fetchBadgeCount()`, `applyBadgeCount(count)`, `broadcastCount(count)`.
- [ ] Replace naive `setInterval(updateBadgeCountFromAPI, 120000)` with leader-only interval.
- [ ] On `fallbackToPolling()` / notify-WS-disabled path: join channel, try leadership, do **not** N-tab stampede on first paint (stagger with short random delay or “wait for LEADER 300ms”).
- [ ] On `beforeunload` / `pagehide`: leader broadcasts `BYE` so a follower can take over quickly.
- [ ] On `visibilitychange`: prefer a visible tab as leader; hidden leader may abdicate.
- [ ] Keep bell-open → `GET /notifications/api` (full list) **per tab that opens the bell** (user-driven; do not over-optimize unless easy).
- [ ] Leave prefs caching as-is (already cross-tab).
- [ ] Do not reintroduce notification WebSocket for this.

### Tests / manual verify

- [ ] Open 3–5 tabs as same user → Network: only **one** tab shows periodic `/notifications/api/count`.
- [ ] Close the polling tab → another tab starts polling within one interval (or sooner after `BYE`).
- [ ] Badge updates on follower tabs when leader fetches a new count.
- [ ] Hard-refresh all tabs: no sustained N× poll storm (at most a brief race, then one leader).
- [ ] Browser without `BroadcastChannel`: localStorage fallback still updates badges; at most rare duplicate fetches.

### Out of scope

- Server-side Redis for badge fan-out (wrong layer for same-browser tabs)
- Changing poll interval (120s stays unless product asks)
- AI chat WebSocket behaviour
- Presence logic changes (already deduped)

---

## Success criteria

- Multi-tab session ≈ **1** `/notifications/api/count` per poll period per browser
- Badge still correct on all tabs within one poll cycle
- No notification WS regressions
- Small, reviewable JS change concentrated in `components.js` (optionally a tiny shared `cross-tab-leader.js` if reuse with presence is clean)

---

## Rollback

Revert the client change; each tab polls independently again (previous behaviour). No server/migration dependency.

---

## References

- Badge polling today: `Backoffice/app/static/js/core/components.js` (`fallbackToPolling`, `updateBadgeCountFromAPI`)
- Presence leader pattern: `Backoffice/app/static/js/forms/modules/presence.js`
- CSRF cross-tab gate: `Backoffice/app/static/js/core/csrf.js` (`csrf_last_refresh_at`)
- Notify WS off: `docs/handovers/2026-07-21-notifications-off-websocket.md`
- Gateway context: `Backoffice/docs/runbooks/incidents/gateway-504-worker-saturation.md`
