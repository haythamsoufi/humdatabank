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
  const teamsIconUrl = presenceBar.getAttribute('data-teams-icon-url') || '';
  const teamsChatLabel = presenceBar.getAttribute('data-teams-chat-label') || 'Chat';
  const usersContainer    = document.getElementById('presence-users');       // collapsed avatars
  const usersListEl       = document.getElementById('presence-users-list');  // expanded list
  const expandBtn         = document.getElementById('presence-expand-btn');
  const collapseBtn       = document.getElementById('presence-collapse-btn');
  const concurrentWarning = document.getElementById('concurrent-users-warning');
  const concurrentDismissBtn = document.getElementById('concurrent-users-dismiss');
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const CSRF_TOKEN = csrfMeta ? csrfMeta.getAttribute('content') : '';

  let isExpanded = false;
  let isWarningDismissed = false;
  let lastUserIds = '';
  // Counts consecutive fetchActive failures; resets on success or tab focus.
  let fetchErrorCount = 0;

  const AUTO_COLLAPSE_MS = 30000;
  let autoCollapseTimer = null;

  // Must match backend ttl_seconds (forms_api.py).
  const PRESENCE_TTL_MS    = 120 * 1000;
  const HEARTBEAT_BASE_MS  = 30000;
  const REFRESH_BASE_MS    = 30000;
  const MAX_BACKOFF_MS     = 5 * 60 * 1000;
  // Heartbeat backoff cap: base + backoff + max-jitter (2 s) must stay under TTL.
  // 120 000 - 30 000 - 2 000 - 3 000 (safety) = 85 000 ms
  const HB_BACKOFF_CAP_MS  = PRESENCE_TTL_MS - HEARTBEAT_BASE_MS - 5000;
  // Tolerate this many consecutive fetchActive errors before hiding the bar.
  const MAX_FETCH_ERRORS_BEFORE_HIDE = 3;

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

  function buildTeamsUrl(email) {
    if (!email) return null;
    return 'https://teams.microsoft.com/l/chat/0/0?users=' + encodeURIComponent(email);
  }

  function setExpanded(expanded) {
    isExpanded = expanded;
    presenceBar.classList.toggle('presence-bar--expanded', isExpanded);
    if (expandBtn)   expandBtn.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
    if (collapseBtn) collapseBtn.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
  }

  function clearAutoCollapseTimer() {
    if (autoCollapseTimer) {
      clearTimeout(autoCollapseTimer);
      autoCollapseTimer = null;
    }
  }

  function scheduleAutoCollapse() {
    clearAutoCollapseTimer();
    autoCollapseTimer = setTimeout(() => {
      autoCollapseTimer = null;
      setExpanded(false);
    }, AUTO_COLLAPSE_MS);
  }

  function expandByDefault() {
    setExpanded(true);
    scheduleAutoCollapse();
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
    // -- Collapsed: stacked avatars with active orbit animation --
    if (usersContainer) {
      usersContainer.replaceChildren();
      (users || []).forEach((u, index) => {
        const wrap = document.createElement('div');
        wrap.className = 'presence-collapsed-avatar-wrap';
        wrap.style.setProperty('--presence-avatar-color', u.profile_color || '#3B82F6');
        wrap.style.setProperty('--presence-anim-delay', `${index * 0.55}s`);
        wrap.style.setProperty('--presence-stack', String(index));

        const el = document.createElement('div');
        el.className = 'presence-collapsed-avatar';
        el.title = u.name || 'User';
        el.style.backgroundColor = u.profile_color || '#3B82F6';
        el.textContent = getInitials(u.name);

        wrap.appendChild(el);
        usersContainer.appendChild(wrap);
      });
    }

    // -- Expanded: full name + Teams link per user --
    if (usersListEl) {
      usersListEl.replaceChildren();
      (users || []).forEach(u => {
        const row = document.createElement('div');
        row.className = 'presence-user-row';

        const avatar = document.createElement('div');
        avatar.className = 'presence-user-avatar';
        avatar.style.backgroundColor = u.profile_color || '#3B82F6';
        avatar.textContent = getInitials(u.name);

        const name = document.createElement('span');
        name.className = 'presence-user-name';
        name.textContent = u.name || 'User';
        name.title = u.name || 'User';

        row.appendChild(avatar);
        row.appendChild(name);

        const teamsUrl = buildTeamsUrl(u.email);
        if (teamsUrl) {
          const teamsBtn = document.createElement('a');
          teamsBtn.href = teamsUrl;
          teamsBtn.target = '_blank';
          teamsBtn.rel = 'noopener noreferrer';
          teamsBtn.className = 'presence-teams-btn';
          teamsBtn.title = 'Chat on Microsoft Teams';
          teamsBtn.setAttribute('aria-label', 'Chat with ' + (u.name || 'user') + ' on Microsoft Teams');
          if (teamsIconUrl) {
            const icon = document.createElement('img');
            icon.src = teamsIconUrl;
            icon.alt = '';
            icon.setAttribute('aria-hidden', 'true');
            icon.className = 'presence-teams-icon';
            teamsBtn.appendChild(icon);
          }
          const label = document.createElement('span');
          label.className = 'presence-teams-label';
          label.textContent = teamsChatLabel;
          teamsBtn.appendChild(label);
          row.appendChild(teamsBtn);
        }

        usersListEl.appendChild(row);
      });
    }

    const hasOtherUsers = (users || []).length > 0;

    // Reset dismissed state if the list of users has changed
    const currentUserIds = (users || []).map(u => String(u.id)).sort().join(',');
    const usersChanged = currentUserIds !== lastUserIds;
    if (usersChanged && lastUserIds !== '') {
      isWarningDismissed = false;
    }

    if (hasOtherUsers && usersChanged) {
      expandByDefault();
    }

    if (!hasOtherUsers) {
      clearAutoCollapseTimer();
      if (isExpanded) {
        setExpanded(false);
      }
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
    clearAutoCollapseTimer();
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
      if (res && res.status === 400) {
        const refreshFn = window.refreshCSRFToken;
        if (typeof refreshFn === 'function') {
          const newToken = await refreshFn().catch(() => null);
          if (newToken) {
            const retry = await fetchFn(`/api/forms/presence/assignment/${aesId}/heartbeat`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': newToken,
                'X-Requested-With': 'XMLHttpRequest'
              },
              credentials: 'same-origin',
              body: '{}'
            });
            if (retry && retry.ok) {
              hbBackoffMs = 0;
              scheduleNext(heartbeat, HEARTBEAT_BASE_MS, hbBackoffMs, t => (heartbeatTimer = t));
              return;
            }
          }
        }
      }
      if (res && res.status === 429) {
        const ra = await getRetryAfterSeconds(res);
        const base = Math.max(ra * 1000, HEARTBEAT_BASE_MS);
        // Cap so that base + backoff + jitter never exceeds PRESENCE_TTL_MS.
        hbBackoffMs = Math.min(hbBackoffMs ? hbBackoffMs * 2 : base, HB_BACKOFF_CAP_MS);
      } else {
        hbBackoffMs = 0;
      }
    } catch (e) {
      // Silent fail — TTL (120 s) tolerates up to 3 missed 30 s beats.
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
        // Tolerate transient server errors: only hide bar after persistent failures.
        fetchErrorCount++;
        if (fetchErrorCount >= MAX_FETCH_ERRORS_BEFORE_HIDE) {
          showOrHideBar(false);
          showOrHideWarning(false);
        }
        scheduleNext(fetchActive, REFRESH_BASE_MS, 0, t => (activeTimer = t));
        return;
      }
      const data = await res.json();
      const users = Array.isArray(data.users) ? data.users : [];
      const others = users.filter(u => Number(u.id) !== currentUserId);
      fetchErrorCount = 0;
      renderUsers(others);
      auBackoffMs = 0;
    } catch (e) {
      // Tolerate transient network errors: only hide bar after persistent failures.
      fetchErrorCount++;
      if (fetchErrorCount >= MAX_FETCH_ERRORS_BEFORE_HIDE) {
        showOrHideBar(false);
        showOrHideWarning(false);
      }
    }
    scheduleNext(fetchActive, REFRESH_BASE_MS, auBackoffMs, t => (activeTimer = t));
  }

  // Expand/collapse toggle buttons
  if (expandBtn) {
    expandBtn.addEventListener('click', () => {
      clearAutoCollapseTimer();
      setExpanded(true);
    });
  }
  if (collapseBtn) {
    collapseBtn.addEventListener('click', () => {
      clearAutoCollapseTimer();
      setExpanded(false);
    });
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
    // Give fresh error tolerance whenever the polling loop (re)starts.
    fetchErrorCount = 0;
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
