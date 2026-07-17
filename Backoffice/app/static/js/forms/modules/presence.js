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
  let lastRenderedIds = '';
  // Counts consecutive sync failures; resets on success or tab focus.
  let syncErrorCount = 0;

  const AUTO_COLLAPSE_MS = 30000;
  let autoCollapseTimer = null;

  // Must match PRESENCE_TTL_SECONDS in presence_store.py (120 s).
  const PRESENCE_TTL_MS    = 120 * 1000;
  const SYNC_BASE_MS       = 30000;
  // Slower cadence while nobody else is editing (the common case). A joining
  // co-editor is still discovered within one idle tick, well inside the TTL.
  const SYNC_IDLE_MS       = 60000;
  const MAX_BACKOFF_MS     = 5 * 60 * 1000;
  // Sync backoff cap: base + backoff + max-jitter (2 s) must stay under TTL.
  const SYNC_BACKOFF_CAP_MS = PRESENCE_TTL_MS - SYNC_BASE_MS - 5000;
  const MAX_SYNC_ERRORS_BEFORE_HIDE = 3;

  // Cross-tab dedupe: one "leader" tab per assignment does the network syncs
  // and shares results over a BroadcastChannel; sibling tabs just render them.
  // The lease must exceed the slowest cadence (SYNC_IDLE_MS + jitter) so a
  // live leader is never usurped between two broadcasts.
  const LEASE_MS = SYNC_IDLE_MS + 10000;
  const SIBLING_FRESH_MS = LEASE_MS + 5000;
  // A user re-appearing within this window (e.g. a brief server-side presence
  // flicker) does not re-trigger the warning or the auto-expand.
  const NEW_USER_MEMORY_MS = 10 * 60 * 1000;
  const TAB_ID = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);

  let syncTimer = null;
  let stopped = false;
  let syncBackoffMs = 0;
  let lastHadUsers = false;
  let leaderId = null;                 // tabId currently doing network syncs (may be self)
  let leaderSeenAt = 0;                // last time a foreign leader broadcast USERS
  const siblings = new Map();          // tabId -> last message timestamp
  const recentlySeenUsers = new Map(); // userId -> last rendered timestamp

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
    const hasOtherUsers = list.length > 0;

    // "New" = not rendered within NEW_USER_MEMORY_MS. A user briefly dropping
    // out of one poll and returning on the next (server-side flicker) must not
    // re-trigger the dismissed warning or the auto-expand.
    const now = Date.now();
    let hasNewUser = false;
    list.forEach(u => {
      const seenAt = recentlySeenUsers.get(u.id);
      if (seenAt === undefined || (now - seenAt) > NEW_USER_MEMORY_MS) {
        hasNewUser = true;
      }
      recentlySeenUsers.set(u.id, now);
    });
    recentlySeenUsers.forEach((seenAt, id) => {
      if (now - seenAt > NEW_USER_MEMORY_MS * 2) recentlySeenUsers.delete(id);
    });
    lastHadUsers = hasOtherUsers;

    // Skip DOM rebuild when the visible user set is unchanged.
    if (currentUserIds !== lastRenderedIds) {
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

      lastRenderedIds = currentUserIds;
    }

    if (hasNewUser) {
      isWarningDismissed = false;
      expandByDefault();
    }

    if (!hasOtherUsers) {
      clearAutoCollapseTimer();
      if (isExpanded) {
        setExpanded(false);
      }
    }

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

  function nextBaseMs() {
    return lastHadUsers ? SYNC_BASE_MS : SYNC_IDLE_MS;
  }

  // ── Cross-tab coordination ────────────────────────────────────────────────
  let bc = null;
  try {
    bc = (typeof BroadcastChannel !== 'undefined')
      ? new BroadcastChannel('ifrc-presence-' + aesId)
      : null;
  } catch (_) { bc = null; }

  function bcPost(msg) {
    if (!bc) return;
    try { bc.postMessage(Object.assign({ tabId: TAB_ID }, msg)); } catch (_) {}
  }

  function hasFreshForeignLease() {
    return !!(bc && leaderId && leaderId !== TAB_ID && (Date.now() - leaderSeenAt) < LEASE_MS);
  }

  function scheduleTakeover() {
    // Small random delay so multiple follower tabs don't all poll at once.
    if (syncTimer) clearTimeout(syncTimer);
    syncTimer = setTimeout(sync, 500 + Math.floor(Math.random() * 2500));
  }

  if (bc) {
    bc.onmessage = (ev) => {
      const msg = ev && ev.data;
      if (!msg || !msg.tabId || msg.tabId === TAB_ID) return;
      siblings.set(msg.tabId, Date.now());
      if (msg.type === 'USERS') {
        // Foreign leader claim. If both tabs believe they lead (e.g. they
        // started simultaneously), the lower tabId wins and the other yields.
        if (leaderId !== TAB_ID || msg.tabId < TAB_ID) {
          leaderId = msg.tabId;
          leaderSeenAt = Date.now();
          renderUsers(Array.isArray(msg.users) ? msg.users : []);
          bcPost({ type: 'FOLLOW' });
        }
      } else if (msg.type === 'BYE' || msg.type === 'ABDICATE') {
        if (msg.type === 'BYE') siblings.delete(msg.tabId);
        if (leaderId === msg.tabId) {
          leaderId = null;
          leaderSeenAt = 0;
          if (!stopped && document.visibilityState === 'visible') scheduleTakeover();
        }
      }
      // HELLO / FOLLOW need no handling beyond the sibling refresh above.
    };
    bcPost({ type: 'HELLO' });
  }

  async function sync() {
    if (stopped || document.visibilityState !== 'visible') return;
    if (hasFreshForeignLease()) {
      // Another tab of this browser is polling for this assignment; its
      // results arrive over the BroadcastChannel.
      scheduleNext(sync, nextBaseMs(), 0);
      return;
    }
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
      leaderId = TAB_ID;
      bcPost({ type: 'USERS', users: users });
    } catch (e) {
      syncErrorCount++;
      if (syncErrorCount >= MAX_SYNC_ERRORS_BEFORE_HIDE) {
        showOrHideBar(false);
        showOrHideWarning(false);
      }
    }
    scheduleNext(sync, nextBaseMs(), syncBackoffMs);
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
      // A hidden tab stops polling, so hand leadership over right away —
      // otherwise a visible sibling would wait out the full lease first.
      if (leaderId === TAB_ID) {
        leaderId = null;
        bcPost({ type: 'ABDICATE' });
      }
      stop();
    }
  });

  window.addEventListener('pagehide', () => {
    bcPost({ type: 'BYE' });
    // Skip the leave beacon when another tab of this browser still has the
    // same assignment open — it keeps the user's presence alive, and removing
    // it here would make the user flicker for other editors.
    const now = Date.now();
    let hasFreshSibling = false;
    siblings.forEach((ts) => {
      if (now - ts < SIBLING_FRESH_MS) hasFreshSibling = true;
    });
    if (!hasFreshSibling) sendLeaveBeacon();
  });

  start();
})();
