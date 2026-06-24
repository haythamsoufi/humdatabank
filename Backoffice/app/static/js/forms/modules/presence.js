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
  let lastRenderedIds = '';
  // Counts consecutive sync failures; resets on success or tab focus.
  let syncErrorCount = 0;

  const AUTO_COLLAPSE_MS = 30000;
  let autoCollapseTimer = null;

  // Must match PRESENCE_TTL_SECONDS in presence_store.py (120 s).
  const PRESENCE_TTL_MS    = 120 * 1000;
  const SYNC_BASE_MS       = 30000;
  const MAX_BACKOFF_MS     = 5 * 60 * 1000;
  // Sync backoff cap: base + backoff + max-jitter (2 s) must stay under TTL.
  const SYNC_BACKOFF_CAP_MS = PRESENCE_TTL_MS - SYNC_BASE_MS - 5000;
  const MAX_SYNC_ERRORS_BEFORE_HIDE = 3;

  let syncTimer = null;
  let stopped = false;
  let syncBackoffMs = 0;

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

  function buildCollapsedAvatar(u, index) {
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
    return wrap;
  }

  function buildExpandedRow(u) {
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

    return row;
  }

  function renderUsers(users) {
    const list = users || [];
    const currentUserIds = list.map(u => String(u.id)).sort().join(',');
    const usersChanged = currentUserIds !== lastUserIds;

    // Skip DOM rebuild when the visible user set is unchanged.
    if (currentUserIds === lastRenderedIds) {
      const hasOtherUsers = list.length > 0;
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
      showOrHideBar(list.length > 0);
      showOrHideWarning(list.length > 0);
      return;
    }

    if (usersContainer) {
      usersContainer.replaceChildren();
      list.forEach((u, index) => {
        usersContainer.appendChild(buildCollapsedAvatar(u, index));
      });
    }

    if (usersListEl) {
      usersListEl.replaceChildren();
      list.forEach(u => {
        usersListEl.appendChild(buildExpandedRow(u));
      });
    }

    const hasOtherUsers = list.length > 0;

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
    lastRenderedIds = currentUserIds;

    showOrHideBar(hasOtherUsers);
    showOrHideWarning(hasOtherUsers);
  }

  function clearTimers() {
    if (syncTimer) {
      clearTimeout(syncTimer);
      syncTimer = null;
    }
    clearAutoCollapseTimer();
  }

  function scheduleNext(fn, baseMs, backoffMs) {
    const jitter = Math.floor(Math.random() * 2000);
    const delay = Math.min(baseMs + (backoffMs || 0), MAX_BACKOFF_MS) + jitter;
    syncTimer = setTimeout(fn, delay);
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

  async function sync() {
    if (stopped || document.visibilityState !== 'visible') return;
    try {
      const fetchFn = (window.getFetch && window.getFetch()) || fetch;
      const csrfToken = (window.getCSRFToken && window.getCSRFToken()) || CSRF_TOKEN;
      const res = await fetchFn(`/api/forms/presence/assignment/${aesId}/sync`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: '{}'
      });
      if (res && res.status === 429) {
        const ra = await getRetryAfterSeconds(res);
        const base = Math.max(ra * 1000, SYNC_BASE_MS);
        syncBackoffMs = Math.min(syncBackoffMs ? syncBackoffMs * 2 : base, SYNC_BACKOFF_CAP_MS);
        scheduleNext(sync, SYNC_BASE_MS, syncBackoffMs);
        return;
      }
      if (res && res.status === 400) {
        try {
          const body = await res.clone().text();
          if (body.includes('CSRF') && typeof window.refreshCSRFToken === 'function') {
            window.refreshCSRFToken().catch(() => null);
          }
        } catch (_) { /* ignore body read errors */ }
        syncBackoffMs = 0;
        scheduleNext(sync, SYNC_BASE_MS, syncBackoffMs);
        return;
      }
      if (!res.ok) {
        syncErrorCount++;
        if (syncErrorCount >= MAX_SYNC_ERRORS_BEFORE_HIDE) {
          showOrHideBar(false);
          showOrHideWarning(false);
        }
        scheduleNext(sync, SYNC_BASE_MS, 0);
        return;
      }
      const data = await res.json();
      const users = Array.isArray(data.users) ? data.users : [];
      syncErrorCount = 0;
      syncBackoffMs = 0;
      renderUsers(users);
    } catch (e) {
      syncErrorCount++;
      if (syncErrorCount >= MAX_SYNC_ERRORS_BEFORE_HIDE) {
        showOrHideBar(false);
        showOrHideWarning(false);
      }
    }
    scheduleNext(sync, SYNC_BASE_MS, syncBackoffMs);
  }

  function sendLeaveBeacon() {
    if (stopped) return;
    try {
      navigator.sendBeacon(
        `/api/forms/presence/assignment/${aesId}/leave`,
        new Blob(['{}'], { type: 'application/json' })
      );
    } catch (_) {}
  }

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

  if (concurrentDismissBtn) {
    concurrentDismissBtn.addEventListener('click', function() {
      isWarningDismissed = true;
      showOrHideWarning(false);
    });
  }

  function start() {
    stopped = false;
    syncErrorCount = 0;
    clearTimers();
    if (document.visibilityState === 'visible') {
      sync();
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

  window.addEventListener('pagehide', sendLeaveBeacon);

  start();
})();
