/**
 * Integration tests: auth-drafts lifecycle wired through ajax-save events.
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

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

vi.mock('../../../app/static/js/forms/modules/entry-form-progress.js', () => ({
  applyEntryFormProgress: vi.fn(),
}));

const DRAFT_KEY = 'auth:42:100';

function mockFetchResponse({ ok, status, contentType = 'application/json', body = { success: true } }) {
  return {
    ok,
    status,
    headers: {
      get: (name) => (String(name).toLowerCase() === 'content-type' ? contentType : null),
      entries: () => [],
    },
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  };
}

async function initAuthDraftsAndAjaxSave(authMod) {
  await initAuthDraftsForTest(authMod);
  const ajaxMod = await import('../../../app/static/js/forms/modules/ajax-save.js');
  ajaxMod.initAjaxSave();
  return ajaxMod;
}

describe('auth-drafts + ajax-save integration', () => {
  beforeEach(async () => {
    await clearAuthDraftsDatabase();
    localStorage.clear();
    ensureRepeatEntriesFromDraftData.mockReset();
    setupEntryFormDom({ withCsrf: true });
    window.showFlashMessage = vi.fn();
    window.t = (k) => k;
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
    delete window.__ifrcAuthDrafts;
    delete window.__ifrcAuthDraftsActiveKey;
    delete window.showFlashMessage;
    delete window.t;
    document.body.innerHTML = '';
    delete document.body.dataset.formInitialized;
  });

  it('keeps local draft when ajax save fails', async () => {
    const authMod = await prepareAuthDraftsTestEnv();
    const ajaxMod = await initAuthDraftsAndAjaxSave(authMod);

    document.querySelector('[name="indicator_1"]').value = 'edited-locally';
    await window.__ifrcAuthDrafts.saveNow();
    expect((await authMod.loadDraft(DRAFT_KEY))?.data?.indicator_1).toBe('edited-locally');

    fetch.mockResolvedValue(mockFetchResponse({
      ok: false,
      status: 500,
      body: { success: false, message: 'Server error' },
    }));

    await expect(
      ajaxMod.saveFormBeforeSubmit({ toast: false, buttonState: false }),
    ).rejects.toThrow('Server error');

    expect((await authMod.loadDraft(DRAFT_KEY))?.data?.indicator_1).toBe('edited-locally');
  });

  it('clears local draft after successful ajax save via formSubmitted', async () => {
    const authMod = await prepareAuthDraftsTestEnv();
    const ajaxMod = await initAuthDraftsAndAjaxSave(authMod);

    await authMod.saveDraft(DRAFT_KEY, { indicator_1: 'pending-local' }, true);
    expect(await authMod.loadDraft(DRAFT_KEY)).not.toBeNull();

    fetch.mockResolvedValue(mockFetchResponse({ ok: true, status: 200, body: { success: true } }));

    await ajaxMod.saveFormBeforeSubmit({ toast: false, buttonState: false });

    await vi.waitFor(async () => {
      expect(await authMod.loadDraft(DRAFT_KEY)).toBeNull();
    });
  });

  it('does not clear local draft when ajax save succeeds with offline fallback', async () => {
    const authMod = await prepareAuthDraftsTestEnv();
    const ajaxMod = await initAuthDraftsAndAjaxSave(authMod);

    document.querySelector('[name="indicator_1"]').value = 'offline-edit';
    await window.__ifrcAuthDrafts.saveNow();

    fetch.mockRejectedValue(new TypeError('Failed to fetch'));

    const result = await ajaxMod.saveFormBeforeSubmit({ toast: false, buttonState: false });
    expect(result).toEqual({ success: true, offline: true });
    expect((await authMod.loadDraft(DRAFT_KEY))?.data?.indicator_1).toBe('offline-edit');
  });
});
