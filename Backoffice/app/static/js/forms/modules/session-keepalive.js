// Session keepalive for authenticated entry forms.
//
// Problem: users filling out the form in the browser make no server requests
// while typing, so session['last_activity'] is never refreshed.  After the
// configured SESSION_INACTIVITY_TIMEOUT (default 2 hours) the middleware
// in app/middleware/session_timeout.py invalidates the session and the next
// save attempt returns 401, losing unsaved data.
//
// Fix: this module detects genuine user interaction (keystrokes, clicks, input
// events) and sends a lightweight POST to /api/forms/session/keepalive every
// KEEPALIVE_INTERVAL_MS — but ONLY when the user was recently active.  Idle
// sessions (user walked away) let the inactivity clock run down normally.
//
// The keepalive endpoint also returns a fresh CSRF token, which simultaneously
// prevents 403 failures caused by WTF_CSRF_TIME_LIMIT (1 hour default).
//
// Exports:
//   initSessionKeepalive()     — call once after form initialisation
//   refreshSessionNow()        — force an immediate keepalive (used by ajax-save)
//   getLastActivityTimestamp() — milliseconds since epoch of last detected interaction

import { debugLog } from './debug.js';

const MODULE_NAME = 'session-keepalive';
const _t = (k) => (typeof window.t === 'function' ? window.t(k) : k);

// Keepalive fires every 60 min while the user is active.
// This is intentionally shorter than the 2-hour inactivity window and also
// refreshes CSRF before the 1-hour WTF_CSRF_TIME_LIMIT.
const KEEPALIVE_INTERVAL_MS = 60 * 60 * 1000;

// User must have interacted within the last KEEPALIVE_INTERVAL_MS for the
// ping to be sent; otherwise it is skipped (idle session should expire).
const ACTIVITY_WINDOW_MS = KEEPALIVE_INTERVAL_MS;

// Warn user at 115 min idle (5 min before the 2-hour timeout).
const WARN_IDLE_MS = 115 * 60 * 1000;

const KEEPALIVE_URL = '/api/forms/session/keepalive';

let _form = null;
let lastActivityAt = Date.now(); // treat page-load as implicit activity
let lastKeepaliveAt = 0;
let keepaliveTimer = null;
let warnTimer = null;
let _initialized = false;

export function getLastActivityTimestamp() {
    return lastActivityAt;
}

function recordActivity() {
    lastActivityAt = Date.now();
    // If a warning was already shown, dismiss it once the user is active again.
    if (warnTimer) {
        clearTimeout(warnTimer);
        warnTimer = null;
    }
    scheduleIdleWarning();
}

function updateCsrfToken(newToken) {
    if (!newToken) return;
    // Update the hidden CSRF input inside the entry form.
    if (_form) {
        const csrfInput = _form.querySelector('input[name="csrf_token"]');
        if (csrfInput) csrfInput.value = newToken;
    }
    // Update any csrf-token meta tags (used by presence.js, etc.).
    document.querySelectorAll('meta[name="csrf-token"]').forEach((m) => {
        m.setAttribute('content', newToken);
    });
    // Update the global CSRF accessor if the app exposes one.
    if (typeof window.setCSRFToken === 'function') {
        window.setCSRFToken(newToken);
    }
}

async function sendKeepalive() {
    const sinceActivity = Date.now() - lastActivityAt;
    const wasRecentlyActive = sinceActivity < ACTIVITY_WINDOW_MS;

    if (!wasRecentlyActive) {
        debugLog(MODULE_NAME, '⏭ Skipping keepalive — no recent interaction (idle for',
            Math.round(sinceActivity / 60000), 'min)');
        scheduleNext();
        return;
    }

    try {
        debugLog(MODULE_NAME, '💓 Sending session keepalive...');

        // Read CSRF token from form (may have been updated by a prior keepalive).
        const csrfInput = _form && _form.querySelector('input[name="csrf_token"]');
        const csrfValue = csrfInput ? csrfInput.value : (
            (document.querySelector('meta[name="csrf-token"]') || {}).content || ''
        );

        const headers = { 'X-Requested-With': 'XMLHttpRequest' };
        if (csrfValue) headers['X-CSRFToken'] = csrfValue;

        const fetchFn = (window.getFetch && window.getFetch()) || fetch;
        const res = await fetchFn(KEEPALIVE_URL, {
            method: 'POST',
            credentials: 'same-origin',
            headers,
        });

        if (res.ok) {
            lastKeepaliveAt = Date.now();
            const data = await res.json().catch(() => ({}));
            if (data && data.csrf_token) {
                updateCsrfToken(data.csrf_token);
                debugLog(MODULE_NAME, '✅ Keepalive ok — CSRF token refreshed');
            } else {
                debugLog(MODULE_NAME, '✅ Keepalive ok');
            }
        } else if (res.status === 401) {
            // Session already expired; nothing to refresh — the next save will handle it.
            debugLog(MODULE_NAME, '⚠️ Keepalive 401 — session has already expired');
        } else if (res.status === 429) {
            debugLog(MODULE_NAME, '⚠️ Keepalive rate-limited, will retry next interval');
        } else {
            debugLog(MODULE_NAME, '⚠️ Keepalive returned', res.status);
        }
    } catch (e) {
        // Network offline or server unreachable — not an error worth surfacing.
        debugLog(MODULE_NAME, '⚠️ Keepalive request failed:', e && e.message);
    }

    scheduleNext();
}

function scheduleNext() {
    if (keepaliveTimer) clearTimeout(keepaliveTimer);
    keepaliveTimer = setTimeout(sendKeepalive, KEEPALIVE_INTERVAL_MS);
}

function scheduleIdleWarning() {
    if (warnTimer) clearTimeout(warnTimer);
    warnTimer = setTimeout(() => {
        warnTimer = null;
        // Only warn if no keepalive has refreshed the session recently.
        const sinceKeepalive = lastKeepaliveAt > 0 ? (Date.now() - lastKeepaliveAt) : Infinity;
        const sinceActivity  = Date.now() - lastActivityAt;
        if (sinceActivity >= WARN_IDLE_MS && sinceKeepalive >= WARN_IDLE_MS) {
            if (typeof window.showFlashMessage === 'function') {
                window.showFlashMessage(
                    _t('Your session may expire soon due to inactivity. Save your work to stay signed in.'),
                    'warning',
                );
            }
        }
    }, WARN_IDLE_MS);
}

export function initSessionKeepalive() {
    if (_initialized) return;
    _form = document.getElementById('focalDataEntryForm');
    if (!_form) return;

    _initialized = true;

    // Listen for genuine user interaction events.
    const TRACKED_EVENTS = ['keydown', 'mousedown', 'touchstart', 'input'];
    TRACKED_EVENTS.forEach((evt) => {
        document.addEventListener(evt, recordActivity, { passive: true });
    });

    // Returning to the tab counts as activity.
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') recordActivity();
    });

    // Schedule first timed keepalive and the initial idle-warning countdown.
    scheduleNext();
    scheduleIdleWarning();

    debugLog(MODULE_NAME,
        `✅ Session keepalive initialised — interval: ${KEEPALIVE_INTERVAL_MS / 60000} min, ` +
        `idle-warn: ${WARN_IDLE_MS / 60000} min`);
}

/**
 * Force an immediate keepalive, bypassing the normal schedule.
 * Called by ajax-save before submitting so the session is guaranteed fresh.
 */
export async function refreshSessionNow() {
    if (keepaliveTimer) {
        clearTimeout(keepaliveTimer);
        keepaliveTimer = null;
    }
    recordActivity();
    await sendKeepalive();
}
