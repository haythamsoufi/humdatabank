// Local drafts (IndexedDB) for authenticated (non-public) entry forms.
// Goal: allow users to keep filling the form offline and "save" locally, then submit when online.

const DB_NAME = 'ifrc_forms';
// Get version from ASSET_VERSION or CACHE_VERSION, fallback to 'v1' for backward compatibility
function getDraftVersion() {
  try {
    // Try to get from window.ASSET_VERSION (set in layout.html)
    if (window.ASSET_VERSION) {
      return window.ASSET_VERSION;
    }
  } catch (e) {
    // no-op
  }
  // Default to 'v1' if version not available (will be cleaned up on next version change)
  return 'v1';
}

// Get version from cache name asynchronously (fallback)
async function getDraftVersionFromCache() {
  try {
    if (typeof caches !== 'undefined') {
      const keys = await caches.keys();
      const cacheKey = keys.find(k => k.startsWith('ifrc-forms-'));
      if (cacheKey) {
        const match = cacheKey.match(/ifrc-forms-(.+)/);
        return match ? match[1] : 'v1';
      }
    }
  } catch (e) {
    // no-op
  }
  return 'v1';
}

// Store name is versioned to allow cleanup when version changes
let STORE_NAME = 'auth_drafts_v1'; // Default fallback

function isIndexedDBAvailable() {
  try {
    return typeof indexedDB !== 'undefined' && indexedDB !== null;
  } catch (e) {
    return false;
  }
}

// Initialize store name with version
async function initializeStoreName() {
  let version = getDraftVersion();
  // If no static version, try to get from cache
  if (version === 'v1' && typeof caches !== 'undefined') {
    version = await getDraftVersionFromCache();
  }
  STORE_NAME = `auth_drafts_${version}`;
  return STORE_NAME;
}

function openDb() {
  if (!isIndexedDBAvailable()) return Promise.reject(new Error('IndexedDB unavailable'));
  return new Promise(async (resolve, reject) => {
    // Initialize store name with current version
    await initializeStoreName();

    // Check last used version in localStorage to detect version changes
    const lastVersionKey = 'ifrc_auth_drafts_version';
    const lastVersion = localStorage.getItem(lastVersionKey);
    const currentVersion = getDraftVersion();
    const needsUpgrade = lastVersion && lastVersion !== currentVersion;

    // Use version 2 as base (version 1 was original)
    // Increment to 3 if version changed to trigger upgrade
    const dbVersion = needsUpgrade ? 3 : 2;

    const req = indexedDB.open(DB_NAME, dbVersion);
    req.onerror = () => reject(req.error || new Error('IndexedDB open error'));
    req.onsuccess = () => {
      // Update stored version
      if (currentVersion) {
        localStorage.setItem(lastVersionKey, currentVersion);
      }
      resolve(req.result);
    };
    req.onupgradeneeded = async (event) => {
      const db = event.target.result;
      // Ensure store name is initialized
      await initializeStoreName();

      // Delete old stores during upgrade
      const allStoreNames = Array.from(db.objectStoreNames);
      const currentStoreName = STORE_NAME;
      const oldStores = allStoreNames.filter(name =>
        name.startsWith('auth_drafts_') && name !== currentStoreName
      );

      oldStores.forEach(storeName => {
        try {
          if (db.objectStoreNames.contains(storeName)) {
            db.deleteObjectStore(storeName);
            console.log(`[auth-drafts] Deleted old draft store: ${storeName}`);
          }
        } catch (e) {
          console.warn(`[auth-drafts] Failed to delete old store ${storeName}:`, e);
        }
      });

      // Create current store if it doesn't exist
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'key' });
      }
    };
  });
}

async function saveDraft(key, data) {
  if (!isIndexedDBAvailable()) return;
  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error || new Error('tx error'));
      tx.objectStore(STORE_NAME).put({ key, data, updatedAt: Date.now() });
    });
  } catch (e) {
    // drafts are non-critical
    // eslint-disable-next-line no-console
    console.warn('[auth-drafts] save failed (non-critical):', e?.name || e);
  }
}

async function loadDraft(key) {
  if (!isIndexedDBAvailable()) return null;
  try {
    const db = await openDb();
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly');
      tx.onerror = () => reject(tx.error || new Error('tx error'));
      const req = tx.objectStore(STORE_NAME).get(key);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error || new Error('read error'));
    });
  } catch (e) {
    return null;
  }
}

/**
 * Show a custom confirmation dialog (uses centralized confirm-dialogs.js)
 * @param {string} message - The confirmation message to display
 * @returns {Promise<boolean>} - Promise that resolves to true if confirmed, false if cancelled
 */
function showCustomConfirm(message) {
  return new Promise((resolve) => {
    if (typeof window.showConfirmation === 'function') {
      window.showConfirmation(message, () => resolve(true), () => resolve(false), 'Restore', 'Cancel', 'Restore Draft?');
    } else {
      console.warn('Confirmation dialog not available');
      resolve(false);
    }
  });
}

function collectFormData(form) {
  const data = {};
  Array.from(form.elements).forEach((el) => {
    if (!el || !el.name) return;
    if (el.disabled) return;
    if (el.type === 'file') return; // can't persist uploads in MVP

    // Radios/checkbox groups
    try {
      if (el instanceof RadioNodeList) {
        // handled by namedItem access below; skip
        return;
      }
    } catch (_) { /* no-op */ }

    if (el.type === 'checkbox') {
      const same = form.querySelectorAll(`[name="${CSS.escape(el.name)}"]`);
      if (same.length > 1) {
        data[el.name] = Array.from(same).filter(n => n.checked).map(n => n.value);
      } else {
        data[el.name] = !!el.checked;
      }
      return;
    }

    if (el.type === 'radio') {
      const group = form.elements[el.name];
      const selected = Array.from(group).find((n) => n.checked);
      data[el.name] = selected ? selected.value : '';
      return;
    }

    data[el.name] = el.value;
  });
  return data;
}

function restoreFormData(form, data) {
  if (!data) return;
  Object.entries(data).forEach(([name, value]) => {
    const el = form.elements.namedItem(name);
    if (!el) return;
    if (el instanceof RadioNodeList) {
      Array.from(el).forEach((n) => {
        if (n.type === 'checkbox') {
          n.checked = Array.isArray(value) && value.includes(n.value);
        } else if (n.type === 'radio') {
          n.checked = value === n.value;
        }
      });
    } else if (el.type === 'checkbox') {
      el.checked = !!value;
    } else {
      el.value = value;
    }
  });
}

function getAesId() {
  const el = document.getElementById('presence-bar') || document.querySelector('[data-aes-id]');
  const id = el?.getAttribute('data-aes-id') || el?.dataset?.aesId;
  return id ? String(id) : null;
}

function getCurrentUserId() {
  const el = document.getElementById('presence-bar');
  const id = el?.getAttribute('data-current-user-id') || el?.dataset?.currentUserId;
  return id ? String(id) : '0';
}

export function initAuthDrafts() {
  const form = document.getElementById('focalDataEntryForm');
  if (!form) return;

  // Only for non-public pages
  const pubRoot = document.querySelector('[data-is-public-submission]');
  if (pubRoot && pubRoot.dataset.isPublicSubmission === 'true') return;

  const aesId = getAesId();
  if (!aesId) return;

  const userId = getCurrentUserId();
  const key = `auth:${userId}:${aesId}`;

  // Offline banner (authenticated forms)
  function getOfflineBanner() {
    let el = document.getElementById('auth-offline-status-banner');
    if (!el) {
      el = document.createElement('div');
      el.id = 'auth-offline-status-banner';
      el.style.position = 'fixed';
      el.style.left = '0';
      el.style.right = '0';
      el.style.bottom = '0';
      el.style.zIndex = '2147483646';
      el.style.padding = '10px 14px';
      el.style.background = '#f59e0b';
      el.style.color = '#111827';
      el.style.fontSize = '14px';
      el.style.fontWeight = '600';
      el.style.boxShadow = '0 -2px 8px rgba(0,0,0,.15)';
      el.style.display = 'none';
      el.style.textAlign = 'center';
      el.textContent = 'You are offline. You can keep working; drafts will be saved locally.';
      document.body.appendChild(el);
    }
    return el;
  }

  // Track offline state (navigator.onLine can be unreliable with DevTools presets)
  let isOffline = !navigator.onLine;
  function setOffline(next) {
    isOffline = !!next;
    try {
      const el = getOfflineBanner();
      el.style.display = isOffline ? 'block' : 'none';

      // Adjust flash messages position when offline banner is active
      // Handle all flash message containers (they can be created dynamically)
      const flashMessagesContainers = document.querySelectorAll('.flash-messages');
      flashMessagesContainers.forEach((container) => {
        if (isOffline) {
          container.classList.add('offline-banner-active');
        } else {
          container.classList.remove('offline-banner-active');
        }
      });
    } catch (e) { /* no-op */ }
    updateDraftButtonVisibility();
  }

  // Restore if draft exists
  if (isIndexedDBAvailable()) {
    loadDraft(key).then(async (record) => {
      if (!record || !record.data) return;
      const shouldRestore = isOffline || await showCustomConfirm('A local draft is available for this form. Restore it?');
      if (!shouldRestore) return;
      restoreFormData(form, record.data);
      if (typeof window.showFlashMessage === 'function') window.showFlashMessage('Draft restored', 'info');
    }).catch(() => {});
  }

  // Manual save draft button (if present)
  const draftBtn = document.getElementById('auth-save-draft-btn');
  const saveBtn = document.querySelector('button[name="action"][value="save"]');
  const updateDraftButtonVisibility = () => {
    if (isOffline) {
      // When offline: show "Save Draft", hide "Save"
      if (draftBtn) {
        draftBtn.classList.remove('hidden');
      }
      if (saveBtn) {
        saveBtn.classList.add('hidden');
      }
    } else {
      // When online: hide "Save Draft", show "Save"
      if (draftBtn) {
        draftBtn.classList.add('hidden');
      }
      if (saveBtn) {
        saveBtn.classList.remove('hidden');
      }
    }
  };
  updateDraftButtonVisibility();
  window.addEventListener('online', () => setOffline(false));
  window.addEventListener('offline', () => setOffline(true));
  // Initial banner state
  setOffline(!navigator.onLine);

  if (draftBtn) {
    draftBtn.addEventListener('click', (e) => {
      e.preventDefault();
      saveDraft(key, collectFormData(form)).then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage('Draft saved', 'success'); });
    });
  }

  // Expose helpers for other modules (e.g., ajax-save fallback)
  try {
    window.__ifrcAuthDrafts = {
      saveNow: () => saveDraft(key, collectFormData(form)),
      setOffline
    };
  } catch (e) { /* no-op */ }

  // If offline, intercept Save/Submit clicks early and save draft instead
  const interceptIfOffline = (e) => {
    if (!isOffline) return;
    e.preventDefault();
    e.stopPropagation();
    if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
    saveDraft(key, collectFormData(form)).then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage('You are offline. Draft saved locally.', 'warning'); });
  };

  const submitBtn = document.querySelector('button[name="action"][value="submit"]');
  // Note: saveBtn is already defined above in updateDraftButtonVisibility scope
  if (saveBtn) saveBtn.addEventListener('click', interceptIfOffline, true);
  if (submitBtn) submitBtn.addEventListener('click', interceptIfOffline, true);

  // Also guard plain form submission when offline
  form.addEventListener('submit', (e) => {
    if (!isOffline) return;
    e.preventDefault();
    saveDraft(key, collectFormData(form)).then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage('You are offline. Draft saved locally.', 'warning'); });
  }, true);
}
