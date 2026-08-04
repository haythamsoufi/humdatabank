// Local drafts (IndexedDB) for authenticated (non-public) entry forms.
// Goal: allow users to keep filling the form offline and "save" locally, then submit when online.

import { ensureRepeatEntriesFromDraftData } from './repeat-sections.js';
import {
  collectFormData,
  diffAgainstBaseline,
  DRAFT_EXCLUDED_FIELDS,
  draftHasContent,
  escapeFieldName,
  getActiveSectionContext,
  getPersistedSectionContext,
  canRestoreAuthDraft,
  mergeDraftRecords,
  parseDraftRestoreContext,
  resolveDraftPayloadForRestore,
  restoreFormData,
  storeSuffixFromName,
} from './auth-drafts-core.js';

const _t = (k) => (typeof window.t === 'function' ? window.t(k) : k);

const DB_NAME = 'ifrc_forms';
const LAST_SUFFIX_KEY = 'ifrc_auth_drafts_version';
const IDB_SCHEMA_KEY = 'ifrc_auth_drafts_idb_schema_v2';
const SPILL_PREFIX = 'ifrc_auth_draft_spill_';

/** Synchronous localStorage backup for pagehide when async IndexedDB may not finish. */
function spillDraftSync(key, data, updatedAt, diffBased) {
  if (!data || typeof data !== 'object' || Object.keys(data).length === 0) return;
  try {
    localStorage.setItem(SPILL_PREFIX + key, JSON.stringify({
      key, data, updatedAt, diffBased: !!diffBased,
    }));
  } catch (_) { /* quota / private mode */ }
}

function readSpilledDraft(key) {
  try {
    const raw = localStorage.getItem(SPILL_PREFIX + key);
    if (!raw) return null;
    const rec = JSON.parse(raw);
    if (rec && rec.key === key && rec.data && typeof rec.data === 'object') return rec;
  } catch (_) { /* no-op */ }
  return null;
}

function clearSpilledDraft(key) {
  try { localStorage.removeItem(SPILL_PREFIX + key); } catch (_) { /* no-op */ }
}

let _cachedDb = null;
let _openDbPromise = null;

function invalidateDbCache() {
  _openDbPromise = null;
  if (_cachedDb) {
    try { _cachedDb.close(); } catch (_) { /* no-op */ }
    _cachedDb = null;
  }
}

function attachDbLifecycle(db) {
  db.onversionchange = () => {
    authDraftLog('openDb', { ok: true, reason: 'versionchange' });
    invalidateDbCache();
    try { db.close(); } catch (_) { /* no-op */ }
  };
  db.onclose = () => {
    if (_cachedDb === db) {
      _cachedDb = null;
      _openDbPromise = null;
    }
  };
}

/** Migrate legacy auth_drafts_* stores sequentially within the upgrade transaction. */
function migrateOldAuthDraftStores(tx, db, currentStoreName, oldStoreNames, index = 0) {
  if (index >= oldStoreNames.length) return;
  const storeName = oldStoreNames[index];
  if (!db.objectStoreNames.contains(storeName)) {
    migrateOldAuthDraftStores(tx, db, currentStoreName, oldStoreNames, index + 1);
    return;
  }
  const oldStore = tx.objectStore(storeName);
  const newStore = tx.objectStore(currentStoreName);
  const migrateReq = oldStore.getAll();
  migrateReq.onsuccess = () => {
    (migrateReq.result || []).forEach((rec) => {
      try { newStore.put(rec); } catch (_) { /* no-op */ }
    });
    try {
      db.deleteObjectStore(storeName);
      authDraftLog('upgrade_migrate', {
        ok: true,
        from: storeName,
        to: currentStoreName,
        count: (migrateReq.result || []).length,
      });
    } catch (e) {
      authDraftLog('upgrade_migrate', { ok: false, store: storeName, err: (e && e.message) || String(e) });
    }
    migrateOldAuthDraftStores(tx, db, currentStoreName, oldStoreNames, index + 1);
  };
  migrateReq.onerror = () => {
    authDraftLog('upgrade_migrate', { ok: false, store: storeName, err: 'getAll failed' });
    migrateOldAuthDraftStores(tx, db, currentStoreName, oldStoreNames, index + 1);
  };
}

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
async function pushDraftToHost(key, data, updatedAt, diffBased) {
  if (!isMobileAppBridgeAvailable()) return false;
  try {
    const payload = JSON.stringify({ key, data, updatedAt, diffBased: !!diffBased });
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
  if (_cachedDb) return Promise.resolve(_cachedDb);
  if (_openDbPromise) return _openDbPromise;

  _openDbPromise = new Promise((resolve, reject) => {
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
        _openDbPromise = null;
        const err = req.error || new Error('IndexedDB open error');
        authDraftLog('openDb', { ok: false, err: err.message, name: err.name, openVersion });
        reject(err);
      };
      req.onsuccess = () => {
        const db = req.result;
        attachDbLifecycle(db);
        _cachedDb = db;
        try {
          localStorage.setItem(IDB_SCHEMA_KEY, String(db.version));
          localStorage.setItem(LAST_SUFFIX_KEY, currentSuffix);
        } catch (e) { /* no-op */ }
        authDraftLog('openDb', { ok: true, idbStore: STORE_NAME, suffix: currentSuffix, dbVersion: db.version });
        resolve(db);
      };
      req.onupgradeneeded = (event) => {
        const db = event.target.result;
        const tx = event.target.transaction;
        const currentStoreName = STORE_NAME;
        if (!db.objectStoreNames.contains(currentStoreName)) {
          db.createObjectStore(currentStoreName, { keyPath: 'key' });
          authDraftLog('upgrade_create', { ok: true, idbStore: STORE_NAME });
        }
        const oldStores = Array.from(db.objectStoreNames).filter((name) =>
          name.startsWith('auth_drafts_') && name !== currentStoreName
        );
        migrateOldAuthDraftStores(tx, db, currentStoreName, oldStores);
      };
    })().catch((err) => {
      _openDbPromise = null;
      reject(err);
    });
  });

  return _openDbPromise;
}

async function saveDraft(key, data, diffBased = false) {
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
        tx.objectStore(STORE_NAME).put({ key, data, updatedAt, diffBased: !!diffBased });
      });
      clearSpilledDraft(key);
      updateDraftDiagSnapshot(data);
      idbSaved = true;
      authDraftLog('save', { ok: true, fieldCount, diffBased: !!diffBased, ms: Date.now() - t0 });
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
  const pushed = await pushDraftToHost(key, data, updatedAt, diffBased);
  if (!idbSaved && pushed) {
    updateDraftDiagSnapshot(data);
    authDraftLog('save', { ok: true, fieldCount, source: 'host_only', ms: Date.now() - t0 });
  }
}

async function deleteDraft(key) {
  const t0 = Date.now();
  clearSpilledDraft(key);
  if (isIndexedDBAvailable()) {
    try {
      const db = await openDb();
      await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error || new Error('tx error'));
        tx.objectStore(STORE_NAME).delete(key);
      });
      authDraftLog('delete', { ok: true, ms: Date.now() - t0 });
    } catch (e) {
      authDraftLog('delete', {
        ok: false,
        err: (e && e.message) || String(e),
        name: e && e.name,
        ms: Date.now() - t0,
      });
    }
  }
  if (isMobileAppBridgeAvailable()) {
    try {
      await window.flutter_inappwebview.callHandler(
        'authDraftPushToHost',
        JSON.stringify({ key, data: null, updatedAt: 0, deleted: true }),
      );
    } catch (_) { /* no-op */ }
  }
  try {
    window.__ifrcAuthDraftsDiagSnapshot = { fieldCount: 0, hasRecord: false, updatedAt: Date.now() };
  } catch (_) { /* no-op */ }
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
  let { rec, source } = mergeDraftRecords(idbRec, hostRec);
  const spilled = readSpilledDraft(key);
  if (spilled && (!rec || (spilled.updatedAt || 0) > (rec.updatedAt || 0))) {
    rec = spilled;
    source = 'spill';
  }
  if (rec && rec.data && (source === 'host' || source === 'spill') && isIndexedDBAvailable()) {
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
          diffBased: !!rec.diffBased,
        });
      });
      if (source === 'spill') clearSpilledDraft(key);
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
      window.showConfirmation(message, () => resolve(true), () => resolve(false), _t('Restore'), _t('Cancel'), _t('Restore Draft?'));
    } else {
      authDraftLog('confirm', { ok: false, err: 'showConfirmation not available' });
      resolve(false);
    }
  });
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

/** Block edits while the restore prompt / async restore chain is in flight. */
function setFormRestorePending(form, pending) {
  if (!form) return;
  if (pending) {
    form.setAttribute('aria-busy', 'true');
    form.classList.add('auth-draft-restore-pending');
    form.querySelectorAll('input, select, textarea, button').forEach((el) => {
      if (el.dataset.authDraftRestoreLock === '1') return;
      el.dataset.authDraftRestoreLock = '1';
      el.dataset.authDraftRestoreWasDisabled = el.disabled ? '1' : '0';
      el.disabled = true;
    });
    return;
  }
  form.removeAttribute('aria-busy');
  form.classList.remove('auth-draft-restore-pending');
  form.querySelectorAll('[data-auth-draft-restore-lock="1"]').forEach((el) => {
    el.disabled = el.dataset.authDraftRestoreWasDisabled === '1';
    delete el.dataset.authDraftRestoreLock;
    delete el.dataset.authDraftRestoreWasDisabled;
  });
}

/** Scroll container for the entry form (main element or window). */
function getFormScrollContainer() {
  const main = document.querySelector('main[style*="overflow-y"]') || document.querySelector('main');
  if (main && main.scrollHeight > main.clientHeight) return main;
  return window;
}

/**
 * Raw scroll offsets as a fallback when no section id can be resolved.
 */
function captureViewportAnchor() {
  const hash = (window.location.hash || '').replace(/^#/, '');
  const anchorEl = hash ? document.getElementById(hash) : null;
  const container = getFormScrollContainer();
  const sidebarNav = document.getElementById('sidebar-nav-scroll');

  if (anchorEl && anchorEl.isConnected) {
    const containerRect = container === window ? { top: 0 } : container.getBoundingClientRect();
    const state = {
      mode: 'anchor',
      anchorId: hash,
      container,
      anchorTopInViewport: anchorEl.getBoundingClientRect().top - containerRect.top,
      windowY: window.scrollY,
      containerScrollTop: container === window ? null : container.scrollTop,
      sidebarNavScroll: sidebarNav ? sidebarNav.scrollTop : null,
    };
    return state;
  }

  return {
    mode: 'offset',
    container,
    windowY: window.scrollY,
    containerScrollTop: container === window ? null : container.scrollTop,
    sidebarNavScroll: sidebarNav ? sidebarNav.scrollTop : null,
  };
}

function restoreViewportAnchorSync(state) {
  if (!state) return;
  if (state.mode === 'anchor' && state.anchorId) {
    const el = document.getElementById(state.anchorId);
    const container = state.container || getFormScrollContainer();
    if (el && el.isConnected) {
      const containerRect = container === window ? { top: 0 } : container.getBoundingClientRect();
      const delta = (el.getBoundingClientRect().top - containerRect.top) - state.anchorTopInViewport;
      if (Math.abs(delta) > 1) {
        if (container === window) {
          window.scrollBy(0, delta);
        } else {
          container.scrollTop += delta;
        }
      }
    }
  } else {
    if (state.containerScrollTop != null && state.container && state.container !== window) {
      state.container.scrollTop = state.containerScrollTop;
    }
    window.scrollTo(window.scrollX, state.windowY);
  }
  if (state.sidebarNavScroll != null) {
    const nav = document.getElementById('sidebar-nav-scroll');
    if (nav) nav.scrollTop = state.sidebarNavScroll;
  }
}

function needsPaginationPageChange(pageNumber) {
  const pag = window.__ifrcPagination;
  if (!pag || pageNumber == null || typeof pag.getCurrentPageNumber !== 'function') return false;
  const target = parseInt(String(pageNumber), 10);
  if (!Number.isFinite(target)) return false;
  const current = pag.getCurrentPageNumber();
  return current != null && current !== target;
}

/** Wait for pagination / scroll-spy to highlight the stored section before the restore dialog. */
async function waitForInitialSectionScroll(expectedSectionId, maxMs = 4500) {
  if (!expectedSectionId) return { matched: false, reason: 'no_expected_section' };
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    const activeLink = document.querySelector('a.section-link.is-active');
    const activeId = activeLink?.dataset?.sectionId
      || (activeLink?.getAttribute('href') || '').replace(/^#/, '');
    const el = document.getElementById(expectedSectionId);
    const rect = el ? el.getBoundingClientRect() : null;
    const inView = rect && rect.top < window.innerHeight * 0.6 && rect.bottom > 80;
    if (activeId === expectedSectionId || inView) {
      return { matched: true, activeId, inView: !!inView, waitedMs: Date.now() - start };
    }
    await new Promise((r) => setTimeout(r, 50));
  }
  return { matched: false, reason: 'timeout', waitedMs: Date.now() - start };
}

/** Return user to their section after draft restore (paginated forms + anchor nudge). */
function restoreSectionAfterDraft(ctx, viewportFallback) {
  try {
    window.__ifrcSectionNavScrollSpy?.pause?.(4000);
  } catch (_) { /* no-op */ }

  const pag = window.__ifrcPagination;
  if (ctx?.sectionId && pag && typeof pag.navigateToSection === 'function' && needsPaginationPageChange(ctx.pageNumber)) {
    pag.navigateToSection(ctx.sectionId, ctx.pageNumber);
  }
  if (viewportFallback) restoreViewportAnchorSync(viewportFallback);
}

/** Re-apply section scroll after async layout work (relevance, matrix repaint). */
function scheduleSectionContextRestore(ctx, viewportFallback) {
  restoreSectionAfterDraft(ctx, viewportFallback);
  document.addEventListener('ifrc:relevance-settled', () => restoreSectionAfterDraft(ctx, viewportFallback), { once: true });
  [200, 800].forEach((ms) => setTimeout(() => restoreSectionAfterDraft(ctx, viewportFallback), ms));
}

/**
 * toggleDisaggregationInputs clears input values in the selected container for
 * non-total modes ("prevent value replication"); re-apply the draft values it
 * just wiped, then let the calculator recompute totals via change events.
 */
function reapplyDraftValuesToDisaggContainer(draftData, radio, fieldId, itemType, mode) {
  if (mode === 'total') return;
  const scope = radio.closest('.repeat-entry') || document;
  const container = scope.querySelector(
    `.disaggregation-inputs[data-parent-id="${escapeFieldName(String(fieldId))}"][data-item-type="${itemType}"][data-mode="${escapeFieldName(mode)}"]`,
  );
  if (!container) return;
  container.querySelectorAll('input[name]').forEach((input) => {
    if (!Object.prototype.hasOwnProperty.call(draftData, input.name)) return;
    const v = draftData[input.name];
    if (typeof v !== 'string' && typeof v !== 'number') return;
    if (input.value === String(v)) return;
    input.value = v;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

/** Re-sync disaggregation container visibility to match restored reporting-mode radios. */
function syncDisaggregationModesAfterRestore(form, draftData) {
  if (!form || !draftData || typeof window.toggleDisaggregationInputs !== 'function') return;
  const seen = new Set();
  Object.keys(draftData).forEach((name) => {
    if (!name.endsWith('_reporting_mode') || seen.has(name)) return;
    seen.add(name);
    const mode = draftData[name];
    if (!mode) return;
    const radio = form.querySelector(
      `input[type="radio"][name="${escapeFieldName(name)}"][value="${escapeFieldName(String(mode))}"]`,
    );
    if (!radio || !radio.checked) return;

    const standardMatch = name.match(/^(indicator|dynamic)_(.+)_reporting_mode$/);
    if (standardMatch) {
      const itemType = standardMatch[1];
      let fieldId = standardMatch[2];
      if (itemType === 'dynamic') {
        const fieldContainer = radio.closest('[data-assignment-id]');
        const containerFieldId = fieldContainer?.getAttribute('data-item-id');
        if (containerFieldId) fieldId = containerFieldId;
      }
      window.toggleDisaggregationInputs(fieldId, String(mode), itemType, radio);
      reapplyDraftValuesToDisaggContainer(draftData, radio, fieldId, itemType, String(mode));
      return;
    }

    const repeatMatch = name.match(/^repeat_\d+_\d+_field_\d+_reporting_mode$/);
    if (repeatMatch) {
      const block = radio.closest('.form-item-block');
      const fieldId = block?.getAttribute('data-item-id');
      const itemType = block?.getAttribute('data-item-type') === 'indicator' ? 'indicator' : 'dynamic';
      if (fieldId) {
        window.toggleDisaggregationInputs(fieldId, String(mode), itemType, radio);
        reapplyDraftValuesToDisaggContainer(draftData, radio, fieldId, itemType, String(mode));
      }
    }
  });
}

/** Fire input/change on restored fields so widgets, DNA flags, and calculators sync. */
function dispatchRestoredFieldEvents(form, draftData) {
  if (!form || !draftData) return;
  const restoredNames = new Set(Object.keys(draftData));

  // DNA / N/A first — toggles field disable state before value fields notify listeners.
  Array.from(form.querySelectorAll('input[type="checkbox"]')).forEach((el) => {
    if (!el.name || !restoredNames.has(el.name)) return;
    if (!el.name.includes('_data_not_available') && !el.name.includes('_not_applicable')) return;
    el.dispatchEvent(new Event('change', { bubbles: true }));
  });

  Array.from(form.querySelectorAll('input, select, textarea')).forEach((el) => {
    if (!el.name || !restoredNames.has(el.name)) return;
    if (DRAFT_EXCLUDED_FIELDS.has(el.name)) return;
    if (el.name.includes('_data_not_available') || el.name.includes('_not_applicable')) return;
    if (el.name.endsWith('_reporting_mode')) return;
    if (el.type === 'radio' && !el.checked) return;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  });
  syncDisaggregationModesAfterRestore(form, draftData);
}

function getAesId() {
  const el = document.getElementById('presence-bar') || document.querySelector('[data-aes-id]');
  const id = el?.getAttribute('data-aes-id') || el?.dataset?.aesId;
  return id ? String(id) : null;
}

function getCurrentUserId() {
  const el = document.getElementById('presence-bar');
  const id = el?.getAttribute('data-current-user-id') || el?.dataset?.currentUserId;
  if (!id || String(id) === '0') return null;
  return String(id);
}

export function initAuthDrafts() {
  const form = document.getElementById('focalDataEntryForm');
  if (!form) return;

  const pubRoot = document.querySelector('[data-is-public-submission]');
  if (pubRoot && pubRoot.dataset.isPublicSubmission === 'true') return;

  const aesId = getAesId();
  if (!aesId) return;

  const userId = getCurrentUserId();
  if (!userId) return;

  const key = `auth:${userId}:${aesId}`;
  try {
    window.__ifrcAuthDraftsActiveKey = key;
  } catch (e) { /* no-op */ }

  // ── Diff-based drafts ─────────────────────────────────────────────────
  // Baseline = server-rendered form state captured once the form is ready.
  // Drafts store only fields that differ from it, so a restore can never
  // touch (let alone clear) DB-saved values the user never edited.
  let baselineSnapshot = null;
  let hasSavedChangesThisSession = false;

  function runMatrixCollect() {
    try {
      if (window.matrixHandler && typeof window.matrixHandler.collectMatrixData === 'function') {
        window.matrixHandler.collectMatrixData();
      }
    } catch (_) { /* no-op */ }
  }

  function captureBaseline(reason) {
    runMatrixCollect();
    baselineSnapshot = collectFormData(form);
    authDraftLog('baseline', { ok: true, reason, fieldCount: Object.keys(baselineSnapshot).length });
  }

  const baselineReady = waitForFormInitialized().then(() => {
    if (!baselineSnapshot) captureBaseline('form_initialized');
  });

  /** Draft payload = changes vs baseline; null until the baseline exists. */
  function collectDraftData() {
    if (!baselineSnapshot) return null;
    runMatrixCollect();
    return diffAgainstBaseline(collectFormData(form), baselineSnapshot);
  }

  /**
   * Persist current changes as a diff-based draft.
   * Empty diff: skip the write — this protects a declined draft from being
   * overwritten by idle timers. If we already saved changes this session and
   * the user reverted everything back to the baseline, delete the stale draft.
   */
  async function saveDraftNow(source) {
    if (window.__ifrcConditionsIsClearing === true) {
      authDraftLog('save_skip', { ok: true, reason: 'conditions_clearing', source });
      return;
    }
    const data = collectDraftData();
    if (!data) {
      authDraftLog('save_skip', { ok: true, reason: 'baseline_not_ready', source });
      return;
    }
    const changed = Object.keys(data).length;
    if (changed === 0) {
      if (hasSavedChangesThisSession) {
        hasSavedChangesThisSession = false;
        await deleteDraft(key);
        authDraftLog('save_skip', { ok: true, reason: 'reverted_to_baseline', source });
      } else {
        authDraftLog('save_skip', { ok: true, reason: 'no_changes', source });
      }
      return;
    }
    hasSavedChangesThisSession = true;
    await saveDraft(key, data, true);
  }

  function getOfflineBanner() {
    let el = document.getElementById('auth-offline-status-banner');
    if (!el) {
      el = document.createElement('div');
      el.id = 'auth-offline-status-banner';
      el.className = 'auth-offline-status-banner';
      el.setAttribute('role', 'status');
      el.textContent = _t('You are offline. You can keep working; drafts will be saved locally.');
      document.body.appendChild(el);
    }
    return el;
  }

  let isOffline = !navigator.onLine;
  function setOffline(next) {
    isOffline = !!next;
    try {
      const el = getOfflineBanner();
      el.classList.toggle('is-visible', isOffline);

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
    let restorePending = false;
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
      if (!draftHasContent(record)) {
        authDraftLog('restore_skip', { ok: true, reason: 'no_record' });
        return;
      }
      const restoreContext = parseDraftRestoreContext(form);
      if (!canRestoreAuthDraft(restoreContext)) {
        authDraftLog('restore_skip', {
          ok: true,
          reason: 'assignment_not_restorable',
          assignmentStatus: restoreContext?.assignmentStatus || '',
          reviewEnabled: !!restoreContext?.reviewEnabled,
          isDelegationUser: !!restoreContext?.isDelegationUser,
        });
        return;
      }
      restorePending = true;
      setFormRestorePending(form, true);
      await waitForFormInitialized();
      await baselineReady;
      const { data: restorableData } = resolveDraftPayloadForRestore(record, baselineSnapshot);
      if (!draftHasContent({ data: restorableData })) {
        if (!record.diffBased) void deleteDraft(key);
        authDraftLog('restore_skip', { ok: true, reason: 'nothing_to_restore' });
        return;
      }
      const persistedContext = getPersistedSectionContext();
      await waitForInitialSectionScroll(persistedContext?.sectionId);
      const shouldRestore = isOffline || await showCustomConfirm(_t('A local draft is available for this form. Restore it?'));
      if (!shouldRestore) {
        authDraftLog('restore_skip', { ok: true, reason: 'user_declined' });
        return;
      }
      const sectionContext = getActiveSectionContext();
      const viewportFallback = captureViewportAnchor();
      const draftData = restorableData;
      authDraftLog('restore_start', {
        ok: true,
        fieldCount: Object.keys(draftData).length,
        diffBased: !!record.diffBased,
        legacyConverted: !record.diffBased,
        sectionId: sectionContext?.sectionId || '',
      });
      ensureRepeatEntriesFromDraftData(draftData);
      restoreFormData(form, draftData);
      try {
        if (window.matrixHandler && typeof window.matrixHandler.syncFromDraftRestore === 'function') {
          await window.matrixHandler.syncFromDraftRestore();
        }
      } catch (e) {
        authDraftLog('restore_matrix', { ok: false, err: (e && e.message) || String(e), name: e && e.name });
      }
      try {
        dispatchRestoredFieldEvents(form, draftData);
      } catch (_) { /* no-op */ }
      scheduleSectionContextRestore(sectionContext, viewportFallback);
      authDraftLog('restore_done', { ok: true });
      if (typeof window.showFlashMessage === 'function') window.showFlashMessage(_t('Draft restored'), 'info');
    } catch (e) {
      authDraftLog('restore_chain', { ok: false, err: (e && e.message) || String(e), name: e && e.name });
    } finally {
      if (restorePending) setFormRestorePending(form, false);
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
      saveDraftNow('draft_button').then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage(_t('Draft saved'), 'success'); });
    });
  }

  try {
    window.__ifrcAuthDrafts = {
      saveNow: () => saveDraftNow('api_save_now'),
      setOffline,
      /** Current unsaved diff vs the page-load baseline (debugging). */
      getPendingDiff: () => collectDraftData(),
    };
  } catch (e) { /* no-op */ }

  // ── Debounced draft auto-save on every input change ────────────────────
  // Saves to IndexedDB silently (no toast) within 2 seconds of the user
  // stopping interaction.  Works while online or offline.  A 2-minute fallback
  // timer catches changes from rich widgets (Select2, matrix, plugins) that
  // may not fire standard DOM input events.

  let autoSaveDebounceTimer = null;
  let autoSaveFallbackTimer = null;

  const AUTO_SAVE_DEBOUNCE_MS = 2000;
  const AUTO_SAVE_FALLBACK_MS = 2 * 60 * 1000;

  async function runSilentDraftSave() {
    if (window.__ifrcConditionsIsClearing === true) return;
    try {
      await saveDraftNow('auto');
      authDraftLog('auto_save', { ok: true });
    } catch (e) {
      authDraftLog('auto_save', { ok: false, err: (e && e.message) || String(e) });
    }
  }

  function scheduleFallbackSave() {
    if (autoSaveFallbackTimer) clearTimeout(autoSaveFallbackTimer);
    autoSaveFallbackTimer = setTimeout(async () => {
      await runSilentDraftSave();
      scheduleFallbackSave(); // keep the safety-net ticking
    }, AUTO_SAVE_FALLBACK_MS);
  }

  function onFormActivity() {
    if (window.__ifrcConditionsIsClearing === true) return;
    if (autoSaveDebounceTimer) clearTimeout(autoSaveDebounceTimer);
    autoSaveDebounceTimer = setTimeout(runSilentDraftSave, AUTO_SAVE_DEBOUNCE_MS);
    scheduleFallbackSave();
  }

  void waitForFormInitialized().then(() => {
    form.addEventListener('input', onFormActivity);
    form.addEventListener('change', onFormActivity);
    scheduleFallbackSave();
  });

  function flushDraftOnHide(source) {
    if (autoSaveDebounceTimer) {
      clearTimeout(autoSaveDebounceTimer);
      autoSaveDebounceTimer = null;
    }
    try {
      const data = collectDraftData();
      if (data && Object.keys(data).length > 0) {
        spillDraftSync(key, data, Date.now(), true);
      }
    } catch (_) { /* no-op */ }
    void saveDraftNow(source);
  }

  window.addEventListener('pagehide', () => flushDraftOnHide('pagehide'));
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushDraftOnHide('visibility_hidden');
  });

  // Drop the local draft only after a confirmed server save (explicit Save or presave).
  document.addEventListener('formSubmitted', (e) => {
    const action = e && e.detail && e.detail.action;
    const result = e && e.detail && e.detail.result;
    if (action !== 'save' || !result || result.success === false) return;
    if (autoSaveDebounceTimer) { clearTimeout(autoSaveDebounceTimer); autoSaveDebounceTimer = null; }
    captureBaseline('server_save');
    hasSavedChangesThisSession = false;
    void deleteDraft(key);
    scheduleFallbackSave();
  });

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
    authDraftLog('intercept_save', { ok: true, source: 'button_or_submit' });
    saveDraftNow('offline_intercept').then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage(_t('You are offline. Draft saved locally.'), 'warning'); });
  };

  const submitBtn = document.querySelector('button[name="action"][value="submit"]');
  if (saveBtn) saveBtn.addEventListener('click', interceptIfOffline, true);
  if (submitBtn) submitBtn.addEventListener('click', interceptIfOffline, true);

  form.addEventListener('submit', (e) => {
    if (!isOffline) return;
    e.preventDefault();
    authDraftLog('intercept_save', { ok: true, source: 'form_submit' });
    saveDraftNow('offline_form_submit').then(() => { if (typeof window.showFlashMessage === 'function') window.showFlashMessage(_t('You are offline. Draft saved locally.'), 'warning'); });
  }, true);
}

/** @internal Vitest hooks for IndexedDB persistence (not a public form API). */
export {
  saveDraft,
  loadDraft,
  deleteDraft,
  spillDraftSync,
  readSpilledDraft,
  clearSpilledDraft,
  invalidateDbCache,
};
