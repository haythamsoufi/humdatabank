// Minimal public drafts (IndexedDB) for offline-friendly public forms (text/select/checkbox only)

const DB_NAME = 'ifrc_public_forms';
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
let STORE_NAME = 'drafts_v1'; // Default fallback

// Check if IndexedDB is available
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
  STORE_NAME = `drafts_${version}`;
  return STORE_NAME;
}

function openDb() {
  // Check if IndexedDB is available
  if (!isIndexedDBAvailable()) {
    return Promise.reject(new Error('IndexedDB is not available in this environment'));
  }

  return new Promise(async (resolve, reject) => {
    try {
      // Initialize store name with current version
      await initializeStoreName();

      // Check last used version in localStorage to detect version changes
      const lastVersionKey = 'ifrc_public_drafts_version';
      const lastVersion = localStorage.getItem(lastVersionKey);
      const currentVersion = getDraftVersion();
      const needsUpgrade = lastVersion && lastVersion !== currentVersion;

      // Use version 2 as base (version 1 was original)
      // Increment to 3 if version changed to trigger upgrade
      const dbVersion = needsUpgrade ? 3 : 2;

      const req = indexedDB.open(DB_NAME, dbVersion);

      req.onerror = function() {
        // Log error but don't expose sensitive details
        console.warn('IndexedDB open error (non-critical, drafts disabled):', req.error?.name || 'Unknown error');
        reject(new Error('IndexedDB init error'));
      };

      req.onsuccess = function() {
        // Update stored version
        if (currentVersion) {
          localStorage.setItem(lastVersionKey, currentVersion);
        }
        resolve(req.result);
      };

      req.onupgradeneeded = async function(event) {
        try {
          const db = event.target.result;
          // Ensure store name is initialized
          await initializeStoreName();

          // Delete old stores during upgrade
          const allStoreNames = Array.from(db.objectStoreNames);
          const currentStoreName = STORE_NAME;
          const oldStores = allStoreNames.filter(name =>
            name.startsWith('drafts_') && name !== currentStoreName
          );

          oldStores.forEach(storeName => {
            try {
              if (db.objectStoreNames.contains(storeName)) {
                db.deleteObjectStore(storeName);
                console.log(`[public-drafts] Deleted old draft store: ${storeName}`);
              }
            } catch (e) {
              console.warn(`[public-drafts] Failed to delete old store ${storeName}:`, e);
            }
          });

          // Create current store if it doesn't exist
          if (!db.objectStoreNames.contains(STORE_NAME)) {
            db.createObjectStore(STORE_NAME, { keyPath: 'key' });
          }
        } catch (e) {
          console.warn('IndexedDB upgrade error (non-critical):', e);
          reject(e);
        }
      };

      req.onblocked = function() {
        console.warn('IndexedDB blocked - another tab may be using it');
        // Don't reject here, let it wait
      };
    } catch (e) {
      console.warn('IndexedDB initialization error (non-critical, drafts disabled):', e);
      reject(e);
    }
  });
}

async function saveDraft(key, data) {
  if (!isIndexedDBAvailable()) {
    return; // Silently fail if IndexedDB is not available
  }

  try {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      try {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.oncomplete = () => resolve();
        tx.onerror = () => {
          console.warn('IndexedDB transaction error (non-critical):', tx.error?.name || 'Unknown error');
          reject(tx.error);
        };
        tx.objectStore(STORE_NAME).put({ key, data, updatedAt: Date.now() });
      } catch (e) {
        console.warn('IndexedDB transaction setup error (non-critical):', e);
        reject(e);
      }
    });
  } catch (e) {
    // Silently fail - drafts are a convenience feature, not critical
    // Only log if it's not a known unavailable error
    if (e.message !== 'IndexedDB is not available in this environment' &&
        e.message !== 'IndexedDB init error') {
      console.warn('Failed to save draft (non-critical):', e?.name || 'Unknown error');
    }
  }
}

async function loadDraft(key) {
  if (!isIndexedDBAvailable()) {
    return null; // Silently return null if IndexedDB is not available
  }

  try {
    const db = await openDb();
    return await new Promise((resolve, reject) => {
      try {
        const tx = db.transaction(STORE_NAME, 'readonly');
        tx.onerror = () => {
          console.warn('IndexedDB transaction error (non-critical):', tx.error?.name || 'Unknown error');
          reject(tx.error);
        };
        const req = tx.objectStore(STORE_NAME).get(key);
        req.onsuccess = () => resolve(req.result?.data || null);
        req.onerror = () => {
          console.warn('IndexedDB read error (non-critical):', req.error?.name || 'Unknown error');
          reject(req.error);
        };
      } catch (e) {
        console.warn('IndexedDB transaction setup error (non-critical):', e);
        reject(e);
      }
    });
  } catch (e) {
    // Silently return null - drafts are a convenience feature, not critical
    // Only log if it's not a known unavailable error
    if (e.message !== 'IndexedDB is not available in this environment' &&
        e.message !== 'IndexedDB init error') {
      console.warn('Failed to load draft (non-critical):', e?.name || 'Unknown error');
    }
    return null;
  }
}

export function initPublicDrafts({ publicToken }) {
  const form = document.getElementById('focalDataEntryForm');
  if (!form) return;
  const key = `public_${publicToken}`;

  // Offline banner
  function getOfflineBanner() {
    let el = document.getElementById('offline-status-banner');
    if (!el) {
      el = document.createElement('div');
      el.id = 'offline-status-banner';
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
      el.textContent = 'You are offline. Working in offline mode; drafts are saved locally.';
      document.body.appendChild(el);
    }
    return el;
  }

  function showOfflineBanner(show) {
    const el = getOfflineBanner();
    el.style.display = show ? 'block' : 'none';
  }

  // Initial state
  showOfflineBanner(!navigator.onLine);
  window.addEventListener('offline', () => showOfflineBanner(true));
  window.addEventListener('online', () => showOfflineBanner(false));

  // restore draft - only if IndexedDB is available
  if (isIndexedDBAvailable()) {
    loadDraft(key).then((data) => {
      if (!data) return;
      Object.entries(data).forEach(([name, value]) => {
        const el = form.elements.namedItem(name);
        if (!el) return;
        if (el instanceof RadioNodeList) {
          // radios/checkbox groups
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
      if (typeof window.showFlashMessage === 'function') window.showFlashMessage('Draft restored', 'info');
    }).catch((e) => {
      // Silently ignore - drafts are optional
    });
  }

  // collect simple fields
  function collectData() {
    const data = {};
    Array.from(form.elements).forEach((el) => {
      if (!el.name) return;
      if (el.disabled) return;
      if (el.type === 'file') return; // skip files in MVP
      if (el.type === 'checkbox') {
        // checkboxes with same name -> array
        const same = form.querySelectorAll(`[name="${CSS.escape(el.name)}"]`);
        if (same.length > 1) {
          data[el.name] = Array.from(same)
            .filter((n) => n.checked)
            .map((n) => n.value);
        } else {
          data[el.name] = el.checked;
        }
      } else if (el instanceof RadioNodeList || el.type === 'radio') {
        const group = form.elements[el.name];
        const selected = Array.from(group).find((n) => n.checked);
        data[el.name] = selected ? selected.value : '';
      } else {
        data[el.name] = el.value;
      }
    });
    return data;
  }

  // Manual save only - no auto-save on input
  const btn = document.getElementById('public-save-draft-btn');
  if (btn) {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      saveDraft(key, collectData()).then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage('Draft saved', 'success'); });
    });
  }

  // Guard submit when offline
  form.addEventListener('submit', (e) => {
    if (!navigator.onLine) {
      e.preventDefault();
      saveDraft(key, collectData()).then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage('You are offline. Draft saved; submit when online.', 'warning'); });
    }
  });
}

