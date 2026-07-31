/**
 * Integration tests for initAuthDrafts (init guards, auto-save, restore, formSubmitted).
 */
import 'fake-indexeddb/auto';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  clearAuthDraftsDatabase,
  initAuthDraftsForTest,
  prepareAuthDraftsTestEnv,
  setupEntryFormDom,
} from './auth-drafts-test-helpers.js';

const ensureRepeatEntriesFromDraftData = vi.fn();

vi.mock('../../../app/static/js/forms/modules/repeat-sections.js', () => ({
  ensureRepeatEntriesFromDraftData,
}));

describe('initAuthDrafts guards', () => {
  beforeEach(async () => {
    await clearAuthDraftsDatabase();
    localStorage.clear();
    ensureRepeatEntriesFromDraftData.mockReset();
  });

  afterEach(() => {
    delete window.__ifrcAuthDrafts;
    delete window.__ifrcAuthDraftsActiveKey;
    document.body.innerHTML = '';
    delete document.body.dataset.formInitialized;
  });

  it('does not initialize on public submission forms', async () => {
    document.body.innerHTML = `
      <div data-is-public-submission="true"></div>
      <div id="presence-bar" data-aes-id="1" data-current-user-id="42"></div>
      <form id="focalDataEntryForm"></form>`;
    document.body.dataset.formInitialized = 'true';
    const mod = await prepareAuthDraftsTestEnv();
    mod.initAuthDrafts();
    expect(window.__ifrcAuthDrafts).toBeUndefined();
  });

  it('does not initialize without authenticated user id', async () => {
    setupEntryFormDom({ userId: '0' });
    const mod = await prepareAuthDraftsTestEnv();
    mod.initAuthDrafts();
    expect(window.__ifrcAuthDrafts).toBeUndefined();
  });

  it('does not initialize without aes id', async () => {
    setupEntryFormDom();
    document.getElementById('presence-bar').removeAttribute('data-aes-id');
    const mod = await prepareAuthDraftsTestEnv();
    mod.initAuthDrafts();
    expect(window.__ifrcAuthDrafts).toBeUndefined();
  });
});

describe('initAuthDrafts save and lifecycle', () => {
  beforeEach(async () => {
    await clearAuthDraftsDatabase();
    localStorage.clear();
    window.showFlashMessage = vi.fn();
    ensureRepeatEntriesFromDraftData.mockReset();
    setupEntryFormDom();
  });

  afterEach(() => {
    vi.useRealTimers();
    delete window.__ifrcAuthDrafts;
    delete window.__ifrcAuthDraftsActiveKey;
    delete window.showFlashMessage;
    document.body.innerHTML = '';
    delete document.body.dataset.formInitialized;
  });

  it('saveNow stores diff vs baseline, not full form snapshot', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    await initAuthDraftsForTest(mod);
    document.getElementById('focalDataEntryForm').querySelector('[name="indicator_1"]').value = 'edited';
    await window.__ifrcAuthDrafts.saveNow();
    const loaded = await mod.loadDraft('auth:42:100');
    expect(loaded.data).toEqual({ indicator_1: 'edited' });
    expect(loaded.diffBased).toBe(true);
  });

  it('deletes draft on successful formSubmitted save only', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    await initAuthDraftsForTest(mod);
    await mod.saveDraft('auth:42:100', { indicator_1: 'local' }, true);

    document.dispatchEvent(new CustomEvent('formSubmitted', {
      detail: { action: 'submit' },
    }));
    expect(await mod.loadDraft('auth:42:100')).not.toBeNull();

    document.dispatchEvent(new CustomEvent('formSubmitted', {
      detail: { action: 'save', result: { success: true } },
    }));
    await vi.waitFor(async () => {
      expect(await mod.loadDraft('auth:42:100')).toBeNull();
    });
  });

  it('skips save while relevance bulk-clear flag is set', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    await initAuthDraftsForTest(mod);
    document.getElementById('focalDataEntryForm').querySelector('[name="indicator_1"]').value = 'edited';
    window.__ifrcConditionsIsClearing = true;
    await window.__ifrcAuthDrafts.saveNow();
    expect(await mod.loadDraft('auth:42:100')).toBeNull();
    delete window.__ifrcConditionsIsClearing;
  });

  it('auto-saves after debounced input', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    await initAuthDraftsForTest(mod);
    const input = document.getElementById('focalDataEntryForm').querySelector('[name="indicator_1"]');
    input.value = 'typed';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise((r) => setTimeout(r, 2200));
    const loaded = await mod.loadDraft('auth:42:100');
    expect(loaded?.data?.indicator_1).toBe('typed');
  }, 10000);

  it('deletes draft when user reverts all changes back to baseline', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    await initAuthDraftsForTest(mod);
    const input = document.getElementById('focalDataEntryForm').querySelector('[name="indicator_1"]');
    input.value = 'edited';
    await window.__ifrcAuthDrafts.saveNow();
    expect((await mod.loadDraft('auth:42:100'))?.data?.indicator_1).toBe('edited');

    input.value = 'server-value';
    await window.__ifrcAuthDrafts.saveNow();
    await vi.waitFor(async () => {
      expect(await mod.loadDraft('auth:42:100')).toBeNull();
    });
  });

  it('deletes draft after auto-save when user reverts to baseline', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    await initAuthDraftsForTest(mod);
    const input = document.getElementById('focalDataEntryForm').querySelector('[name="indicator_1"]');
    input.value = 'typed';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise((r) => setTimeout(r, 2200));
    expect((await mod.loadDraft('auth:42:100'))?.data?.indicator_1).toBe('typed');

    input.value = 'server-value';
    await window.__ifrcAuthDrafts.saveNow();
    await vi.waitFor(async () => {
      expect(await mod.loadDraft('auth:42:100')).toBeNull();
    });
  }, 10000);
});

describe('initAuthDrafts restore flow', () => {
  beforeEach(async () => {
    await clearAuthDraftsDatabase();
    localStorage.clear();
    window.showFlashMessage = vi.fn();
    window.matrixHandler = { syncFromDraftRestore: vi.fn(async () => {}) };
    ensureRepeatEntriesFromDraftData.mockReset();
    setupEntryFormDom();
  });

  afterEach(() => {
    vi.useRealTimers();
    delete window.__ifrcAuthDrafts;
    delete window.showConfirmation;
    delete window.showFlashMessage;
    delete window.matrixHandler;
    document.body.innerHTML = '';
    delete document.body.dataset.formInitialized;
  });

  it('restores diff-based draft when user confirms', async () => {
    window.showConfirmation = (_msg, onConfirm) => onConfirm();
    const mod = await prepareAuthDraftsTestEnv();
    await initAuthDraftsForTest(mod, {
      preSaveDraft: { data: { indicator_1: 'draft-value' }, diffBased: true },
    });
    await vi.waitFor(() => {
      expect(document.querySelector('[name="indicator_1"]').value).toBe('draft-value');
    });
    expect(ensureRepeatEntriesFromDraftData).toHaveBeenCalled();
    expect(window.matrixHandler.syncFromDraftRestore).toHaveBeenCalled();
  });

  it('keeps draft when user declines restore', async () => {
    window.showConfirmation = (_msg, _onConfirm, onCancel) => onCancel();
    const mod = await prepareAuthDraftsTestEnv();
    await initAuthDraftsForTest(mod, {
      preSaveDraft: { data: { indicator_1: 'draft-value' }, diffBased: true },
    });
    await new Promise((r) => setTimeout(r, 50));
    expect(document.querySelector('[name="indicator_1"]').value).toBe('server-value');
    expect(await mod.loadDraft('auth:42:100')).not.toBeNull();
  });

  it('auto-deletes stale legacy snapshot that matches baseline', async () => {
    window.showConfirmation = vi.fn();
    const mod = await prepareAuthDraftsTestEnv();
    await initAuthDraftsForTest(mod, {
      preSaveDraft: {
        data: { indicator_1: 'server-value' },
        diffBased: false,
      },
    });
    await vi.waitFor(async () => {
      expect(await mod.loadDraft('auth:42:100')).toBeNull();
    });
    expect(window.showConfirmation).not.toHaveBeenCalled();
  });

  it('locks the form while restore decision is pending', async () => {
    let confirmRestore;
    window.showConfirmation = (_msg, onConfirm) => {
      confirmRestore = onConfirm;
    };
    const mod = await prepareAuthDraftsTestEnv();
    await initAuthDraftsForTest(mod, {
      preSaveDraft: { data: { indicator_1: 'draft-value' }, diffBased: true },
    });
    const form = document.getElementById('focalDataEntryForm');
    const input = document.querySelector('[name="indicator_1"]');
    await vi.waitFor(() => {
      expect(form.classList.contains('auth-draft-restore-pending')).toBe(true);
      expect(input.disabled).toBe(true);
    });
    confirmRestore();
    await vi.waitFor(() => {
      expect(form.classList.contains('auth-draft-restore-pending')).toBe(false);
      expect(input.disabled).toBe(false);
    });
  });
});
