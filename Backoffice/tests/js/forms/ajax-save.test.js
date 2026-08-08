/**
 * Unit tests for ajax-save.js (server save, offline fallback, session expiry).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

vi.mock('../../../app/static/js/forms/modules/entry-form-progress.js', () => ({
  applyEntryFormProgress: vi.fn(),
}));

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
    fetch.mockResolvedValue(mockFetchResponse({ ok: true, status: 200 }));

    const handler = vi.fn();
    document.addEventListener('formSubmitted', handler);

    const mod = await loadAjaxSave();
    mod.initAjaxSave();
    await mod.saveFormBeforeSubmit({ toast: false, buttonState: false });

    expect(handler).toHaveBeenCalled();
    expect(handler.mock.calls[0][0].detail.action).toBe('save');
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
