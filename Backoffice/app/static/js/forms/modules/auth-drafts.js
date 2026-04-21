// Local drafts (IndexedDB) for authenticated (non-public) entry forms.
// Goal: allow users to keep filling the form offline and "save" locally, then submit when online.

const DB_NAME = 'ifrc_forms';
const LAST_SUFFIX_KEY = 'ifrc_auth_drafts_version';
const IDB_SCHEMA_KEY = 'ifrc_auth_drafts_idb_schema_v2';

/** @param {string} phase */
function authDraftLog(phase, detail) {
  const d = detail && typeof detail === 'object' ? detail : {};
  const payload = Object.assign({
    phase,
    t: Date.now(),
    idb: isIndexedDBAvailable(),
    idbStore: typeof STORE_NAME !== 'undefined' ? STORE_NAME : '',
    draftKey: typeof window.__ifrcAuthDraftsActiveKey === 'string' ? window.__ifrcAuthDraftsActiveKey : '',
    protocol: typeof location !== 'undefined' ? location.protocol : '',
    hrefSample: typeof location !== 'undefined' ? String(location.href).substring(0, 120) : '',
  }, d);
  try {
    if (typeof window.__ifrcAuthDraftsDartLog === 'function') {
      window.__ifrcAuthDraftsDartLog(JSON.stringify(payload));
    }
  } catch (e) { /* no-op */ }
}

// Get version from ASSET_VERSION or CACHE_VERSION, fallback to 'v1' for backward compatibility
function getDraftVersion() {
  try {
    if (window.ASSET_VERSION) {
      return window.ASSET_VERSION;
    }
  } catch (e) {
    // no-op
  }
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
let STORE_NAME = 'auth_drafts_v1';

let _authDraftsStorePrepared = false;

function storeSuffixFromName(name) {
  if (!name || typeof name !== 'string') return 'v1';
  return name.startsWith('auth_drafts_') ? name.slice('auth_drafts_'.length) : name;
}

function isIndexedDBAvailable() {
  try {
    return typeof indexedDB !== 'undefined' && indexedDB !== null;
  } catch (e) {
    return false;
  }
}

/** True when Flutter WebView JS bridge can persist drafts across origins (file vs https). */
function isMobileAppBridgeAvailable() {
  try {
    return !!(window.flutter_inappwebview && typeof window.flutter_inappwebview.callHandler === 'function');
  } catch (e) {
    return false;
  }
}

/**
 * `flutter_inappwebview` is injected after document start; host pull must not run until it exists
 * or https "Enter Data" loads with empty IDB and misses the cross-origin draft copy.
 */
async function waitForMobileBridge(maxMs) {
  if (isMobileAppBridgeAvailable()) return;
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    await new Promise((r) => setTimeout(r, 40));
    if (isMobileAppBridgeAvailable()) return;
  }
}

async function ensureFlutterBridgeForDraftsIfMobile() {
  try {
    const mobile = !!(window.isMobileApp || window.IFRCMobileApp || window.humdatabankMobileApp);
    if (!mobile) return;
    await waitForMobileBridge(5000);
  } catch (_) { /* no-op */ }
}

/**
 * Copy of draft to app documents so Enter Data (https) sees the same draft as offline bundle (file).
 * @param {string} key
 * @param {object} data
 * @param {number} updatedAt
 */
async function pushDraftToHost(key, data, updatedAt) {
  if (!isMobileAppBridgeAvailable()) return false;
  try {
    const payload = JSON.stringify({ key, data, updatedAt });
    await window.flutter_inappwebview.callHandler('authDraftPushToHost', payload);
    authDraftLog('host_push', { ok: true, fieldCount: data && typeof data === 'object' ? Object.keys(data).length : 0 });
    return true;
  } catch (e) {
    authDraftLog('host_push', { ok: false, err: (e && e.message) || String(e) });
    return false;
  }
}

/**
 * @param {string} key
 * @returns {Promise<{key:string,data:object,updatedAt:number}|null>}
 */
async function pullDraftFromHost(key) {
  if (!isMobileAppBridgeAvailable()) return null;
  try {
    const raw = await window.flutter_inappwebview.callHandler('authDraftPullFromHost', key);
    const s = raw == null ? '' : String(raw);
    if (!s || s === '{}' || s === 'null') return null;
    const rec = JSON.parse(s);
    if (rec && rec.key === key && rec.data && typeof rec.data === 'object') return rec;
    return null;
  } catch (e) {
    authDraftLog('host_pull', { ok: false, err: (e && e.message) || String(e) });
    return null;
  }
}

/** Updated on save/load for mobile WebView sync probes (no async IndexedDB in evaluateJavascript). */
function updateDraftDiagSnapshot(data) {
  try {
    window.__ifrcAuthDraftsDiagSnapshot = {
      fieldCount: data && typeof data === 'object' ? Object.keys(data).length : 0,
      hasRecord: true,
      updatedAt: Date.now(),
    };
  } catch (e) { /* no-op */ }
}

// Initialize store name with version
async function initializeStoreName() {
  let version = getDraftVersion();
  if (version === 'v1' && typeof caches !== 'undefined') {
    version = await getDraftVersionFromCache();
  }
  STORE_NAME = `auth_drafts_${version}`;
  return STORE_NAME;
}

/**
 * Resolve IndexedDB object store name (async). Call from main before initAuthDrafts, or openDb will await this.
 */
export async function prepareAuthDraftsStore() {
  if (_authDraftsStorePrepared) return STORE_NAME;
  const t0 = Date.now();
  try {
    await initializeStoreName();
    const suffix = storeSuffixFromName(STORE_NAME);
    // Do not write LAST_SUFFIX_KEY here — openDb needs the previous session value to
    // detect store migrations (suffix change). LAST_SUFFIX is updated on open success.
    _authDraftsStorePrepared = true;
    authDraftLog('prepare', { ok: true, idbStore: STORE_NAME, suffix, ms: Date.now() - t0 });
    return STORE_NAME;
  } catch (e) {
    authDraftLog('prepare', { ok: false, err: (e && e.message) || String(e), name: e && e.name, ms: Date.now() - t0 });
    throw e;
  }
}

function openDb() {
  if (!isIndexedDBAvailable()) return Promise.reject(new Error('IndexedDB unavailable'));
  return new Promise((resolve, reject) => {
    (async () => {
      if (!_authDraftsStorePrepared) await prepareAuthDraftsStore();

      const currentSuffix = storeSuffixFromName(STORE_NAME);
      let lastSuffix = null;
      try {
        lastSuffix = localStorage.getItem(LAST_SUFFIX_KEY);
      } catch (e) { /* no-op */ }

      const needsStructuralChange = !!(lastSuffix && lastSuffix !== currentSuffix);

      let lastOpenedSchema = 2;
      try {
        lastOpenedSchema = parseInt(localStorage.getItem(IDB_SCHEMA_KEY) || '2', 10);
      } catch (e) {
        lastOpenedSchema = 2;
      }
      if (Number.isNaN(lastOpenedSchema) || lastOpenedSchema < 2) lastOpenedSchema = 2;

      const openVersion = needsStructuralChange ? lastOpenedSchema + 1 : lastOpenedSchema;

      const req = indexedDB.open(DB_NAME, openVersion);
      req.onerror = () => {
        const err = req.error || new Error('IndexedDB open error');
        authDraftLog('openDb', { ok: false, err: err.message, name: err.name, openVersion });
        reject(err);
      };
      req.onsuccess = () => {
        const db = req.result;
        try {
          localStorage.setItem(IDB_SCHEMA_KEY, String(db.version));
          localStorage.setItem(LAST_SUFFIX_KEY, currentSuffix);
        } catch (e) { /* no-op */ }
        authDraftLog('openDb', { ok: true, idbStore: STORE_NAME, suffix: currentSuffix, dbVersion: db.version });
        resolve(db);
      };
      req.onupgradeneeded = (event) => {
        const db = event.target.result;
        const currentStoreName = STORE_NAME;
        const oldStores = Array.from(db.objectStoreNames).filter(name =>
          name.startsWith('auth_drafts_') && name !== currentStoreName
        );
        oldStores.forEach((storeName) => {
          try {
            if (db.objectStoreNames.contains(storeName)) {
              db.deleteObjectStore(storeName);
              authDraftLog('upgrade_delete', { ok: true, deleted: storeName });
            }
          } catch (e) {
            authDraftLog('upgrade_delete', { ok: false, store: storeName, err: (e && e.message) || String(e) });
          }
        });
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'key' });
          authDraftLog('upgrade_create', { ok: true, idbStore: STORE_NAME });
        }
      };
    })().catch(reject);
  });
}

async function saveDraft(key, data) {
  const updatedAt = Date.now();
  const t0 = Date.now();
  const fieldCount = data && typeof data === 'object' ? Object.keys(data).length : 0;
  let idbSaved = false;
  if (isIndexedDBAvailable()) {
    try {
      const db = await openDb();
      await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error || new Error('tx error'));
        tx.objectStore(STORE_NAME).put({ key, data, updatedAt });
      });
      updateDraftDiagSnapshot(data);
      idbSaved = true;
      authDraftLog('save', { ok: true, fieldCount, ms: Date.now() - t0 });
    } catch (e) {
      authDraftLog('save', {
        ok: false,
        fieldCount,
        err: (e && e.message) || String(e),
        name: e && e.name,
        ms: Date.now() - t0,
      });
    }
  }
  const pushed = await pushDraftToHost(key, data, updatedAt);
  if (!idbSaved && pushed) {
    updateDraftDiagSnapshot(data);
    authDraftLog('save', { ok: true, fieldCount, source: 'host_only', ms: Date.now() - t0 });
  }
}

async function loadDraft(key) {
  const t0 = Date.now();
  let idbRec = null;
  if (isIndexedDBAvailable()) {
    try {
      const db = await openDb();
      idbRec = await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        tx.onerror = () => reject(tx.error || new Error('tx error'));
        const req = tx.objectStore(STORE_NAME).get(key);
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error || new Error('read error'));
      });
    } catch (e) {
      authDraftLog('load', {
        ok: false,
        err: (e && e.message) || String(e),
        name: e && e.name,
        source: 'idb',
        ms: Date.now() - t0,
      });
    }
  }
  let hostRec = null;
  if (isMobileAppBridgeAvailable()) {
    hostRec = await pullDraftFromHost(key);
  }
  let rec = null;
  let source = 'none';
  if (idbRec && idbRec.data && hostRec && hostRec.data) {
    const idbT = idbRec.updatedAt || 0;
    const hostT = hostRec.updatedAt || 0;
    rec = idbT >= hostT ? idbRec : hostRec;
    source = idbT >= hostT ? 'idb' : 'host';
  } else if (idbRec && idbRec.data) {
    rec = idbRec;
    source = 'idb';
  } else if (hostRec && hostRec.data) {
    rec = hostRec;
    source = 'host';
  }
  if (rec && rec.data && source === 'host' && isIndexedDBAvailable()) {
    try {
      const db = await openDb();
      await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error || new Error('tx error'));
        tx.objectStore(STORE_NAME).put({
          key,
          data: rec.data,
          updatedAt: rec.updatedAt || Date.now(),
        });
      });
      updateDraftDiagSnapshot(rec.data);
    } catch (_) { /* no-op */ }
  }
  const fc = rec && rec.data && typeof rec.data === 'object' ? Object.keys(rec.data).length : 0;
  authDraftLog('load', {
    ok: true,
    hasRecord: !!(rec && rec.data),
    fieldCount: fc,
    ms: Date.now() - t0,
    source,
  });
  return rec || null;
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
      authDraftLog('confirm', { ok: false, err: 'showConfirmation not available' });
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

    try {
      if (el instanceof RadioNodeList) {
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

function waitForFormInitialized(maxMs = 90000) {
  return new Promise((resolve) => {
    const done = () => resolve();
    try {
      if (document.body && document.body.dataset && document.body.dataset.formInitialized === 'true') {
        done();
        return;
      }
    } catch (_) { /* no-op */ }
    const start = Date.now();
    const t = setInterval(() => {
      try {
        if (document.body && document.body.dataset && document.body.dataset.formInitialized === 'true') {
          clearInterval(t);
          done();
          return;
        }
      } catch (_) { /* no-op */ }
      if (Date.now() - start > maxMs) {
        clearInterval(t);
        done();
      }
    }, 50);
  });
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

  const pubRoot = document.querySelector('[data-is-public-submission]');
  if (pubRoot && pubRoot.dataset.isPublicSubmission === 'true') return;

  const aesId = getAesId();
  if (!aesId) return;

  const userId = getCurrentUserId();
  const key = `auth:${userId}:${aesId}`;
  try {
    window.__ifrcAuthDraftsActiveKey = key;
  } catch (e) { /* no-op */ }

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

  let isOffline = !navigator.onLine;
  function setOffline(next) {
    isOffline = !!next;
    try {
      const el = getOfflineBanner();
      el.style.display = isOffline ? 'block' : 'none';

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

  void (async () => {
    try {
      await ensureFlutterBridgeForDraftsIfMobile();
      const record = await loadDraft(key);
      try {
        if (record && record.data) {
          window.__ifrcAuthDraftsDiagSnapshot = {
            fieldCount: Object.keys(record.data).length,
            hasRecord: true,
            updatedAt: Date.now(),
          };
        }
      } catch (_) { /* no-op */ }
      if (!record || !record.data) {
        authDraftLog('restore_skip', { ok: true, reason: 'no_record' });
        return;
      }
      await waitForFormInitialized();
      const shouldRestore = isOffline || await showCustomConfirm('A local draft is available for this form. Restore it?');
      if (!shouldRestore) {
        authDraftLog('restore_skip', { ok: true, reason: 'user_declined' });
        return;
      }
      authDraftLog('restore_start', { ok: true, fieldCount: Object.keys(record.data).length });
      restoreFormData(form, record.data);
      try {
        if (window.matrixHandler && typeof window.matrixHandler.syncFromDraftRestore === 'function') {
          await window.matrixHandler.syncFromDraftRestore();
        }
      } catch (e) {
        authDraftLog('restore_matrix', { ok: false, err: (e && e.message) || String(e), name: e && e.name });
      }
      try {
        Array.from(form.querySelectorAll('input, select, textarea')).forEach((el) => {
          if (!el.name) return;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        });
      } catch (_) { /* no-op */ }
      authDraftLog('restore_done', { ok: true });
      if (typeof window.showFlashMessage === 'function') window.showFlashMessage('Draft restored', 'info');
    } catch (e) {
      authDraftLog('restore_chain', { ok: false, err: (e && e.message) || String(e), name: e && e.name });
    }
  })();

  const draftBtn = document.getElementById('auth-save-draft-btn');
  const saveBtn = document.querySelector('button[name="action"][value="save"]');
  const updateDraftButtonVisibility = () => {
    if (isOffline) {
      if (draftBtn) {
        draftBtn.classList.remove('hidden');
      }
      if (saveBtn) {
        saveBtn.classList.add('hidden');
      }
    } else {
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
  setOffline(!navigator.onLine);

  if (draftBtn) {
    draftBtn.addEventListener('click', (e) => {
      e.preventDefault();
      if (window.matrixHandler && typeof window.matrixHandler.collectMatrixData === 'function') {
        window.matrixHandler.collectMatrixData();
      }
      saveDraft(key, collectFormData(form)).then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage('Draft saved', 'success'); });
    });
  }

  try {
    window.__ifrcAuthDrafts = {
      saveNow: () => {
        if (window.matrixHandler && typeof window.matrixHandler.collectMatrixData === 'function') {
          window.matrixHandler.collectMatrixData();
        }
        return saveDraft(key, collectFormData(form));
      },
      setOffline
    };
  } catch (e) { /* no-op */ }

  try {
    window.__ifrcAuthDraftsPeekSync = function () {
      return {
        draftKey: key,
        indexedDB: isIndexedDBAvailable(),
        idbStore: STORE_NAME,
        protocol: (typeof location !== 'undefined' ? location.protocol : ''),
        origin: (typeof location !== 'undefined' ? location.origin : ''),
        hrefSample: (typeof location !== 'undefined' ? String(location.href).substring(0, 96) : ''),
        snapshot: window.__ifrcAuthDraftsDiagSnapshot || null,
      };
    };
    window.__ifrcAuthDraftsGetDiag = async () => {
      const out = {
        draftKey: key,
        indexedDB: isIndexedDBAvailable(),
        protocol: (typeof location !== 'undefined' ? location.protocol : ''),
        origin: (typeof location !== 'undefined' ? location.origin : ''),
        hrefSample: (typeof location !== 'undefined' ? String(location.href).substring(0, 96) : ''),
      };
      try {
        await prepareAuthDraftsStore();
        out.idbStore = STORE_NAME;
      } catch (e) {
        out.idbStoreError = String(e);
      }
      try {
        const rec = await loadDraft(key);
        out.hasRecord = !!(rec && rec.data);
        out.savedFieldCount = rec && rec.data ? Object.keys(rec.data).length : 0;
        if (rec && rec.data) {
          out.sampleFieldKeys = Object.keys(rec.data).slice(0, 12);
        }
      } catch (e) {
        out.loadError = String(e);
      }
      return out;
    };
  } catch (e) { /* no-op */ }

  const interceptIfOffline = (e) => {
    if (!isOffline) return;
    e.preventDefault();
    e.stopPropagation();
    if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
    if (window.matrixHandler && typeof window.matrixHandler.collectMatrixData === 'function') {
      window.matrixHandler.collectMatrixData();
    }
    authDraftLog('intercept_save', { ok: true, source: 'button_or_submit' });
    saveDraft(key, collectFormData(form)).then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage('You are offline. Draft saved locally.', 'warning'); });
  };

  const submitBtn = document.querySelector('button[name="action"][value="submit"]');
  if (saveBtn) saveBtn.addEventListener('click', interceptIfOffline, true);
  if (submitBtn) submitBtn.addEventListener('click', interceptIfOffline, true);

  form.addEventListener('submit', (e) => {
    if (!isOffline) return;
    e.preventDefault();
    if (window.matrixHandler && typeof window.matrixHandler.collectMatrixData === 'function') {
      window.matrixHandler.collectMatrixData();
    }
    authDraftLog('intercept_save', { ok: true, source: 'form_submit' });
    saveDraft(key, collectFormData(form)).then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage('You are offline. Draft saved locally.', 'warning'); });
  }, true);
}
