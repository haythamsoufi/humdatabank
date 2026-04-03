// Live presence for assignment entry form
(function initPresence() {
  const presenceBar = document.getElementById('presence-bar');
  if (!presenceBar) return;

  const aesId = presenceBar.getAttribute('data-aes-id');
  if (!aesId) return;

  // Prevent duplicate polling loops (e.g., if the module is loaded twice)
  window.__ifrcPresenceInit = window.__ifrcPresenceInit || {};
  if (window.__ifrcPresenceInit[aesId]) return;
  window.__ifrcPresenceInit[aesId] = true;

  const currentUserId = Number(presenceBar.getAttribute('data-current-user-id') || 0);
  const usersContainer = document.getElementById('presence-users');
  const concurrentWarning = document.getElementById('concurrent-users-warning');
  const concurrentDismissBtn = document.getElementById('concurrent-users-dismiss');
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const CSRF_TOKEN = csrfMeta ? csrfMeta.getAttribute('content') : '';

  let isWarningDismissed = false;
  let lastUserIds = '';

  const HEARTBEAT_BASE_MS = 30000;
  const REFRESH_BASE_MS = 30000;
  const MAX_BACKOFF_MS = 5 * 60 * 1000;
  let heartbeatTimer = null;
  let activeTimer = null;
  let stopped = false;
  let hbBackoffMs = 0;
  let auBackoffMs = 0;

  function getInitials(name) {
    if (!name) return '?';
    const parts = name.trim().split(/\s+/).slice(0, 2);
    return parts.map(p => (p && p[0] ? p[0].toUpperCase() : '')).join('') || '?';
  }

  function showOrHideBar(hasUsers) {
    if (!presenceBar) return;
    presenceBar.style.display = hasUsers ? '' : 'none';
  }

  function showOrHideWarning(hasOtherUsers) {
    if (!concurrentWarning) return;
    if (hasOtherUsers && !isWarningDismissed) {
      concurrentWarning.classList.remove('hidden');
    } else {
      concurrentWarning.classList.add('hidden');
    }
  }

  function renderUsers(users) {
    if (!usersContainer) return;
    usersContainer.replaceChildren();
    (users || []).forEach(u => {
      const el = document.createElement('div');
      el.className = 'w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold border-2 border-white';
      el.title = u.name || 'User';
      el.style.backgroundColor = u.profile_color || '#3B82F6';
      el.textContent = getInitials(u.name);
      usersContainer.appendChild(el);
    });
    const hasOtherUsers = (users || []).length > 0;

    // Reset dismissed state if the list of users has changed
    const currentUserIds = (users || []).map(u => String(u.id)).sort().join(',');
    if (currentUserIds !== lastUserIds && lastUserIds !== '') {
      isWarningDismissed = false;
    }
    lastUserIds = currentUserIds;

    showOrHideBar(hasOtherUsers);
    showOrHideWarning(hasOtherUsers);
  }

  function clearTimers() {
    if (heartbeatTimer) {
      clearTimeout(heartbeatTimer);
      heartbeatTimer = null;
    }
    if (activeTimer) {
      clearTimeout(activeTimer);
      activeTimer = null;
    }
  }

  function scheduleNext(fn, baseMs, backoffMs, setTimer) {
    // Small jitter avoids synchronized bursts across many users/tabs.
    const jitter = Math.floor(Math.random() * 2000); // 0-2s
    const delay = Math.min(baseMs + (backoffMs || 0), MAX_BACKOFF_MS) + jitter;
    setTimer(setTimeout(fn, delay));
  }

  async function getRetryAfterSeconds(res) {
    try {
      const h = res.headers && res.headers.get && res.headers.get('Retry-After');
      if (h && /^\d+$/.test(String(h))) return Number(h);
    } catch (e) {
      // ignore
    }
    try {
      const data = await res.clone().json();
      const ra = data && (data.retry_after || data.retryAfter);
      if (ra && !Number.isNaN(Number(ra))) return Number(ra);
    } catch (e) {
      // ignore
    }
    return 60;
  }

  async function heartbeat() {
    if (stopped || document.visibilityState !== 'visible') return;
    try {
      const fetchFn = (window.getFetch && window.getFetch()) || fetch;
      const csrfToken = (window.getCSRFToken && window.getCSRFToken()) || CSRF_TOKEN;
      const res = await fetchFn(`/api/forms/presence/assignment/${aesId}/heartbeat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: '{}'
      });
      if (res && res.status === 429) {
        const ra = await getRetryAfterSeconds(res);
        const base = Math.max(ra * 1000, HEARTBEAT_BASE_MS);
        hbBackoffMs = Math.min(hbBackoffMs ? hbBackoffMs * 2 : base, MAX_BACKOFF_MS);
      } else {
        hbBackoffMs = 0;
      }
    } catch (e) {
      // Silent fail
    }
    scheduleNext(heartbeat, HEARTBEAT_BASE_MS, hbBackoffMs, t => (heartbeatTimer = t));
  }

  async function fetchActive() {
    if (stopped || document.visibilityState !== 'visible') return;
    try {
      const fetchFn = (window.getFetch && window.getFetch()) || fetch;
      const res = await fetchFn(`/api/forms/presence/assignment/${aesId}/active-users`, {
        headers: { 'Accept': 'application/json' }
      });
      if (res && res.status === 429) {
        const ra = await getRetryAfterSeconds(res);
        const base = Math.max(ra * 1000, REFRESH_BASE_MS);
        auBackoffMs = Math.min(auBackoffMs ? auBackoffMs * 2 : base, MAX_BACKOFF_MS);
        scheduleNext(fetchActive, REFRESH_BASE_MS, auBackoffMs, t => (activeTimer = t));
        return;
      }
      if (!res.ok) {
        // For non-rate-limit errors, hide UI.
        showOrHideBar(false);
        showOrHideWarning(false);
        scheduleNext(fetchActive, REFRESH_BASE_MS, 0, t => (activeTimer = t));
        return;
      }
      const data = await res.json();
      const users = Array.isArray(data.users) ? data.users : [];
      const others = users.filter(u => Number(u.id) !== currentUserId);
      renderUsers(others);
      auBackoffMs = 0;
    } catch (e) {
      showOrHideBar(false);
      showOrHideWarning(false);
    }
    scheduleNext(fetchActive, REFRESH_BASE_MS, auBackoffMs, t => (activeTimer = t));
  }

  // Handle dismiss button for concurrent users warning
  if (concurrentDismissBtn) {
    concurrentDismissBtn.addEventListener('click', function() {
      isWarningDismissed = true;
      showOrHideWarning(false);
    });
  }

  function start() {
    stopped = false;
    clearTimers();
    if (document.visibilityState === 'visible') {
      heartbeat();
      fetchActive();
    }
  }

  function stop() {
    stopped = true;
    clearTimers();
  }

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      start();
    } else {
      stop();
    }
  });

  // Kick off immediately and then self-schedule (with backoff/jitter)
  start();
})();
