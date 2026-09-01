/**
 * Unit tests for ajax-save.js (server save, offline fallback, session expiry).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

vi.mock('../../../app/static/js/forms/modules/entry-form-progress.js', () => ({
  applyEntryFormProgress: vi.fn(),
  coerceCompletionRate: (value) => (
    typeof value === 'number' && Number.isFinite(value) ? value : null
  ),
  refreshVisibleCompletionRate: vi.fn().mockResolvedValue(undefined),
}));

import { applyEntryFormProgress, refreshVisibleCompletionRate } from '../../../app/static/js/forms/modules/entry-form-progress.js';

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

function setupSaveForm() {
  document.body.innerHTML = `
    <form id="focalDataEntryForm" action="/forms/entry/1">
      <input name="csrf_token" value="tok">
      <input name="indicator_1" value="server-value">
      <button type="submit" name="action" value="save"><span>Save</span></button>
    </form>`;
  window.showFlashMessage = vi.fn();
  window.t = (k) => k;
}

async function loadAjaxSave() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/ajax-save.js');
}

describe('ajax-save', () => {
  beforeEach(() => {
    setupSaveForm();
    applyEntryFormProgress.mockClear();
    refreshVisibleCompletionRate.mockClear();
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete window.showFlashMessage;
    delete window.__ifrcAuthDrafts;
    delete window.t;
    document.body.innerHTML = '';
  });

  it('dispatches formSubmitted on successful save', async () => {
    fetch.mockResolvedValue(mockFetchResponse({
      ok: true,
      status: 200,
      body: { success: true, completion_rate: 55.5, section_statuses: { 7: 'in_progress' } },
    }));

    const handler = vi.fn();
    document.addEventListener('formSubmitted', handler);

    const mod = await loadAjaxSave();
    mod.initAjaxSave();
    await mod.saveFormBeforeSubmit({ toast: false, buttonState: false });

    expect(handler).toHaveBeenCalled();
    expect(handler.mock.calls[0][0].detail.action).toBe('save');
    expect(applyEntryFormProgress).toHaveBeenCalledWith(expect.objectContaining({
      success: true,
      completion_rate: 55.5,
      section_statuses: { 7: 'in_progress' },
    }));
    expect(refreshVisibleCompletionRate).not.toHaveBeenCalled();
  });

  it('refetches completion rate when the save response omits it', async () => {
    document.body.innerHTML += '<button id="completion-gap-btn" data-aes-id="9"></button>';
    fetch.mockResolvedValue(mockFetchResponse({
      ok: true,
      status: 200,
      body: { success: true },
    }));

    const mod = await loadAjaxSave();
    mod.initAjaxSave();
    await mod.saveFormBeforeSubmit({ toast: false, buttonState: false });

    expect(applyEntryFormProgress).toHaveBeenCalled();
    expect(refreshVisibleCompletionRate).toHaveBeenCalledWith('9');
  });

  it('saves draft on 401 without dispatching formSubmitted', async () => {
    const saveNow = vi.fn(async () => {});
    window.__ifrcAuthDrafts = { saveNow };

    fetch.mockResolvedValue(mockFetchResponse({
      ok: false,
      status: 401,
      contentType: 'text/html',
      body: '',
    }));

    const handler = vi.fn();
    document.addEventListener('formSubmitted', handler);

    const mod = await loadAjaxSave();
    mod.initAjaxSave();
    await expect(
      mod.saveFormBeforeSubmit({ toast: false, buttonState: false }),
    ).rejects.toThrow('Session expired');

    expect(saveNow).toHaveBeenCalled();
    expect(handler).not.toHaveBeenCalled();
  });

  it('falls back to local draft on network fetch failure', async () => {
    const saveNow = vi.fn(async () => {});
    const setOffline = vi.fn();
    window.__ifrcAuthDrafts = { saveNow, setOffline };

    fetch.mockRejectedValue(new TypeError('Failed to fetch'));

    const mod = await loadAjaxSave();
    mod.initAjaxSave();
    const result = await mod.saveFormBeforeSubmit({ toast: false, buttonState: false });

    expect(result).toEqual({ success: true, offline: true });
    expect(saveNow).toHaveBeenCalled();
    expect(setOffline).toHaveBeenCalledWith(true);
  });

  it('does not treat unrelated TypeError as offline', async () => {
    const saveNow = vi.fn(async () => {});
    window.__ifrcAuthDrafts = { saveNow };

    fetch.mockRejectedValue(new TypeError('Cannot read properties of undefined'));

    const mod = await loadAjaxSave();
    mod.initAjaxSave();
    await expect(
      mod.saveFormBeforeSubmit({ toast: false, buttonState: false }),
    ).rejects.toThrow('Cannot read properties of undefined');

    expect(saveNow).not.toHaveBeenCalled();
  });

  it('saves on Ctrl+S and prevents the browser save dialog', async () => {
    fetch.mockResolvedValue(mockFetchResponse({ ok: true, status: 200 }));

    const mod = await loadAjaxSave();
    mod.initAjaxSave();

    const event = new KeyboardEvent('keydown', {
      key: 's',
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    });
    const preventDefault = vi.spyOn(event, 'preventDefault');
    document.dispatchEvent(event);

    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(preventDefault).toHaveBeenCalled();
  });

  it('does not leave b64: visible in textareas while save is in flight', async () => {
    document.body.innerHTML = `
      <form id="focalDataEntryForm" action="/forms/entry/1">
        <input name="csrf_token" value="tok">
        <div class="form-item-block" data-item-type="question" data-question-type="textarea">
          <textarea name="field_value[2]">Narrative with punctuation;</textarea>
        </div>
        <button type="submit" name="action" value="save"><span>Save</span></button>
      </form>`;
    window.showFlashMessage = vi.fn();
    window.t = (k) => k;

    const originalText = 'Narrative with punctuation;';
    let releaseFetch;
    const fetchStarted = new Promise((resolve) => {
      fetch.mockImplementation(() => {
        resolve();
        return new Promise((resolveFetch) => {
          releaseFetch = resolveFetch;
        });
      });
    });

    const mod = await loadAjaxSave();
    mod.initAjaxSave();
    const savePromise = mod.saveFormBeforeSubmit({ toast: false, buttonState: false });

    await fetchStarted;

    const textarea = document.querySelector('textarea[name="field_value[2]"]');
    expect(textarea.value).toBe(originalText);

    const posted = fetch.mock.calls[0][1].body;
    expect(posted.get('field_value[2]').startsWith('b64:')).toBe(true);
    expect(posted.get('field_value[2]')).not.toBe(originalText);

    releaseFetch(mockFetchResponse({ ok: true, status: 200 }));
    await savePromise;
    expect(textarea.value).toBe(originalText);
  });

  it('shows friendly error when ok response body is HTML not JSON', async () => {
    fetch.mockResolvedValue(mockFetchResponse({
      ok: true,
      status: 200,
      contentType: 'text/html',
      body: '<!DOCTYPE html><html><body>502 Bad Gateway</body></html>',
    }));

    const mod = await loadAjaxSave();
    mod.initAjaxSave();
    await expect(
      mod.saveFormBeforeSubmit({ toast: false, buttonState: false }),
    ).rejects.toThrow(/Save failed/);
  });
});
