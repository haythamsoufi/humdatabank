/**
 * Integration tests for public-drafts.js (IndexedDB save / restore for public forms).
 *
 * saveDraft / loadDraft are not exported. Tests go through initPublicDrafts
 * (save button, restore on init, offline submit). The module's upgrade handler
 * is async, which can stall fake-indexeddb; tests pre-create version-2 stores
 * so open() hits onsuccess without onupgradeneeded.
 */
import 'fake-indexeddb/auto';
import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from 'vitest';

const DB_NAME = 'ifrc_public_forms';
const DB_VERSION = 2;

function ensureCssEscape() {
  if (!globalThis.CSS) globalThis.CSS = {};
  if (typeof globalThis.CSS.escape !== 'function') {
    globalThis.CSS.escape = (ident) => String(ident).replace(/[^a-zA-Z0-9_\-]/g, (ch) => `\\${ch}`);
  }
}

async function loadPublicDrafts() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/public-drafts.js');
}

function setupPublicForm({
  name = '',
  agree = false,
  tags = [],
  country = '',
  withSaveButton = true,
} = {}) {
  const tagA = tags.includes('a') ? 'checked' : '';
  const tagB = tags.includes('b') ? 'checked' : '';
  document.body.innerHTML = `
    <form id="focalDataEntryForm">
      <input name="full_name" type="text" value="${name}">
      <input name="agree" type="checkbox" value="yes" ${agree ? 'checked' : ''}>
      <input name="tags" type="checkbox" value="a" ${tagA}>
      <input name="tags" type="checkbox" value="b" ${tagB}>
      <select name="country">
        <option value=""></option>
        <option value="CH" ${country === 'CH' ? 'selected' : ''}>Switzerland</option>
        <option value="KE" ${country === 'KE' ? 'selected' : ''}>Kenya</option>
      </select>
      ${withSaveButton ? '<button type="button" id="public-save-draft-btn">Save draft</button>' : ''}
    </form>`;
}

function formValues() {
  const form = document.getElementById('focalDataEntryForm');
  return {
    full_name: form.elements.namedItem('full_name').value,
    agree: form.elements.namedItem('agree').checked,
    tags: Array.from(form.querySelectorAll('[name="tags"]'))
      .filter((n) => n.checked)
      .map((n) => n.value),
    country: form.elements.namedItem('country').value,
  };
}

function openDb(version = DB_VERSION) {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, version);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function ensureDraftStores(storeNames) {
  await new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (event) => {
      const db = event.target.result;
      for (const name of storeNames) {
        if (!db.objectStoreNames.contains(name)) {
          db.createObjectStore(name, { keyPath: 'key' });
        }
      }
    };
    req.onsuccess = () => {
      req.result.close();
      resolve();
    };
    req.onerror = () => reject(req.error);
  });
}

async function readDraftRecord(storeName, key) {
  const db = await openDb();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readonly');
      const req = tx.objectStore(storeName).get(key);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
  } finally {
    db.close();
  }
}

async function waitForFlash(...args) {
  await vi.waitFor(() => {
    expect(window.showFlashMessage).toHaveBeenCalledWith(...args);
  });
}

describe('initPublicDrafts', () => {
  beforeAll(async () => {
    await ensureDraftStores(['drafts_test-public-v1', 'drafts_asset-42', 'drafts_v1']);
  });

  beforeEach(() => {
    ensureCssEscape();
    localStorage.clear();
    document.body.innerHTML = '';
    window.t = (k) => k;
    window.showFlashMessage = vi.fn();
    window.ASSET_VERSION = 'test-public-v1';
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    vi.stubGlobal('caches', undefined);
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.t;
    delete window.showFlashMessage;
    delete window.ASSET_VERSION;
    localStorage.clear();
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
  });

  it('returns early without #focalDataEntryForm (no public form marker)', async () => {
    const { initPublicDrafts } = await loadPublicDrafts();
    document.body.innerHTML = '<div id="not-a-public-form"></div>';
    initPublicDrafts({ publicToken: 'tok-abc' });
    expect(document.getElementById('offline-status-banner')).toBeNull();
    expect(window.showFlashMessage).not.toHaveBeenCalled();
  });

  it('does not treat a missing token as a separate early-return (form is the only guard)', async () => {
    const { initPublicDrafts } = await loadPublicDrafts();
    setupPublicForm();
    initPublicDrafts({});
    expect(document.getElementById('offline-status-banner')).not.toBeNull();
  });

  it('saves and restores text, checkbox, and select values via the save button', async () => {
    const token = 'tok-roundtrip';
    const first = await loadPublicDrafts();
    setupPublicForm({
      name: 'Ada Lovelace',
      agree: true,
      tags: ['a', 'b'],
      country: 'CH',
    });
    first.initPublicDrafts({ publicToken: token });

    document.getElementById('public-save-draft-btn').click();
    await waitForFlash('Draft saved', 'success');

    setupPublicForm();
    window.showFlashMessage.mockClear();
    const second = await loadPublicDrafts();
    second.initPublicDrafts({ publicToken: token });

    await waitForFlash('Draft restored', 'info');
    expect(formValues()).toEqual({
      full_name: 'Ada Lovelace',
      agree: true,
      tags: ['a', 'b'],
      country: 'CH',
    });
  });

  it('uses window.ASSET_VERSION as the IndexedDB store version', async () => {
    window.ASSET_VERSION = 'asset-42';
    const { initPublicDrafts } = await loadPublicDrafts();
    setupPublicForm({ name: 'Versioned', country: 'KE' });
    initPublicDrafts({ publicToken: 'tok-ver' });

    document.getElementById('public-save-draft-btn').click();
    await waitForFlash('Draft saved', 'success');

    const record = await readDraftRecord('drafts_asset-42', 'public_tok-ver');
    expect(record).toBeTruthy();
    expect(record.data.full_name).toBe('Versioned');
    expect(record.data.country).toBe('KE');
  });

  it('falls back to drafts_v1 when ASSET_VERSION is unset', async () => {
    delete window.ASSET_VERSION;
    const { initPublicDrafts } = await loadPublicDrafts();
    setupPublicForm({ name: 'Legacy' });
    initPublicDrafts({ publicToken: 'tok-v1' });

    document.getElementById('public-save-draft-btn').click();
    await waitForFlash('Draft saved', 'success');

    const record = await readDraftRecord('drafts_v1', 'public_tok-v1');
    expect(record).toBeTruthy();
    expect(record.data.full_name).toBe('Legacy');
  });

  it('saves a draft on submit when offline', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    const { initPublicDrafts } = await loadPublicDrafts();
    setupPublicForm({ name: 'Offline User', country: 'KE' });
    initPublicDrafts({ publicToken: 'tok-off' });

    const form = document.getElementById('focalDataEntryForm');
    const submitted = form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    expect(submitted).toBe(false);
    await waitForFlash('You are offline. Draft saved; submit when online.', 'warning');

    setupPublicForm();
    window.showFlashMessage.mockClear();
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
    const again = await loadPublicDrafts();
    again.initPublicDrafts({ publicToken: 'tok-off' });
    await vi.waitFor(() => {
      expect(formValues().full_name).toBe('Offline User');
      expect(formValues().country).toBe('KE');
    });
  });
});
