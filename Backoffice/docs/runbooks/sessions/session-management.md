# Session Management and Presence

Operational notes for Flask-Login sessions, cleanup commands, cookie security, multi-worker affinity, and real-time presence (forms).

---

## 1. Session CLI Helpers

From `Backoffice/` with the virtual environment activated and `.env` loaded:

```bash
# Remove expired/orphaned sessions
python -m flask cleanup-sessions

# List all active sessions (inspect user, IP, last activity)
python -m flask show-all-sessions
```

**When to run `cleanup-sessions`:**
- Scheduled weekly maintenance (add to cron or Azure scheduled task).
- After a large batch of users have been deactivated.
- When the session table has grown unusually large (symptoms: slow login pages, high DB query times).

**Expected output:** A count of sessions removed. If 0 are removed repeatedly during normal operation, sessions may already be expiring naturally — that is fine.

**Session timeout:** Inactive sessions are automatically invalidated after 2 hours (configurable in `config.py`). Cleanup removes the DB rows for already-expired sessions.

---

## 2. Session Security

### SECRET_KEY rotation impact

`SECRET_KEY` is used to sign session cookies and Backoffice-issued Bearer JWTs. **Rotating it immediately invalidates all active sessions site-wide** — every logged-in browser session will be signed out, and existing JWTs signed with the old key cease to work.

Before rotating in production:
- Coordinate with the team — schedule during low-usage hours.
- Notify active focal points who may have unsaved form data.
- Notify operators if any API clients use JWT authentication — they must obtain fresh tokens after rotation.
- After rotation: confirm login works immediately by testing as a non-admin user.

### CSRF tokens

CSRF tokens are tied to the session. They expire when the session expires. If a user keeps a form tab open for more than 2 hours without activity:
- The session expires.
- The next form submit will fail with a CSRF error.
- User must refresh the page, log back in, and re-submit.

This is expected behaviour, not a bug. If CSRF errors happen immediately after login (within seconds), investigate whether `SECRET_KEY` is inconsistent across slots or workers.

### HTTP-only cookies

Session cookies are HTTP-only and Secure (HTTPS only). Do not modify these settings without a security review.

---

## 3. Multi-Worker and Sticky Sessions

### Azure App Service ARR Affinity

If the Backoffice runs with more than one worker instance (scale-out) and uses **server-side session storage**, users must be routed to the same worker on each request. Azure App Service uses the `ARR Affinity` cookie to achieve this.

**Check ARR Affinity is enabled** in Azure Portal → App Service → Configuration → General settings.

**Symptoms of broken affinity:**
- Users experience intermittent logouts or CSRF failures despite a short session.
- Different requests within the same user session land on different workers, each with their own session store.

### Redis-backed sessions (preferred for multi-worker)

When `REDIS_URL` is configured:
- Sessions are stored in Redis (shared across all workers) — affinity is no longer required.
- Cross-worker rate limiting for authenticated JSON APIs and AI routes also becomes consistent.
- **Preferred for production deployments with 2+ workers.**

Without `REDIS_URL`:
- Each worker has its own in-memory session state and rate limiter.
- ARR Affinity must be enabled.
- AI WebSocket connections (`/api/ai/v2/ws`) require ARR affinity or single-worker deployment.

---

## 4. Presence Heartbeats (Form Collaboration)

Real-time presence indicators (showing which user is currently editing a form) use **Redis or in-memory cache** — **not** the `user_activity_log` database table.

**Key rules:**
- `user_activity_log` is for meaningful audit events (login, submission, approval). Do not write heartbeat data there.
- Presence data has a short TTL (typically 60–120 seconds). Stale presence (user closed tab without logging out) clears automatically.
- If presence shows as "stuck" for a departed user: wait for TTL to expire, or flush the Redis key manually if you have Redis access.

**Endpoints:** `/api/forms/presence/...` (see source in `app/routes/forms.py` for exact paths).

---

## 5. Viewing and Terminating Sessions

### View all active sessions
```bash
python -m flask show-all-sessions
```

Output shows: session ID, user email, last activity timestamp, IP address (if recorded).

### Terminate a specific user's session

There is no single-user session termination command. Options:

1. **Deactivate the user account** (Admin → User Management → [user] → Active = No). Deactivated users cannot log in and their session is rejected on next request.
2. **Rotate `SECRET_KEY`** — terminates **all** sessions site-wide (use for security incidents only).
3. If Redis is in use and you have Redis CLI access: identify the session key and `DEL` it directly.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Users report being logged out frequently | Session timeout set too short, or affinity broken | Check `PERMANENT_SESSION_LIFETIME` in config; enable ARR Affinity |
| CSRF errors immediately after login | `SECRET_KEY` inconsistent across slots | Ensure `SECRET_KEY` is a slot-sticky setting in Azure App Service |
| CSRF errors after long idle on form | Session expired (2h timeout) | Expected — user must refresh and re-login |
| Presence indicator stuck on departed user | Redis TTL not yet expired | Wait for TTL, or manually flush the Redis key |
| `cleanup-sessions` removes 0 sessions | Sessions expiring naturally before cleanup runs | Normal — no action needed |
| API client `401` after `SECRET_KEY` rotation | JWT signed with old key is invalid | Client must obtain a new token (re-authenticate) |
| Sessions not shared across workers | Redis not configured | Set `REDIS_URL` or enable ARR Affinity in Azure |
