/**
 * Unit tests for session-keepalive.js (idle ping, CSRF refresh, idle warning).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

const KEEPALIVE_INTERVAL_MS = 60 * 60 * 1000;
const WARN_IDLE_MS = 115 * 60 * 1000;
const KEEPALIVE_URL = '/api/forms/session/keepalive';
const FROZEN_NOW = new Date('2026-01-01T12:00:00.000Z');

function mockFetchResponse({ ok = true, status = 200, body = { csrf_token: 'new-tok' } } = {}) {
  return {
    ok,
    status,
    json: async () => body,
  };
}

function setupFixture() {
  document.head.innerHTML = '<meta name="csrf-token" content="old-tok">';
  document.body.innerHTML = `
    <form id="focalDataEntryForm">
      <input name="csrf_token" value="old-tok">
    </form>`;
  window.t = (k) => k;
  window.showFlashMessage = vi.fn();
}

async function loadKeepalive() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/session-keepalive.js');
}

describe('session-keepalive', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(FROZEN_NOW);
    setupFixture();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockFetchResponse()));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    delete window.t;
    delete window.showFlashMessage;
    delete window.getFetch;
    delete window.setCSRFToken;
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  it('is a no-op without #focalDataEntryForm', async () => {
    document.body.innerHTML = '<div></div>';
    const spy = vi.spyOn(document, 'addEventListener');
    const { initSessionKeepalive } = await loadKeepalive();

    initSessionKeepalive();

    const tracked = ['keydown', 'mousedown', 'touchstart', 'input', 'visibilitychange'];
    expect(spy.mock.calls.filter(([evt]) => tracked.includes(evt))).toHaveLength(0);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('is a no-op on a second call', async () => {
    const spy = vi.spyOn(document, 'addEventListener');
    const { initSessionKeepalive } = await loadKeepalive();

    initSessionKeepalive();
    const callsAfterFirst = spy.mock.calls.length;
    initSessionKeepalive();

    expect(spy.mock.calls.length).toBe(callsAfterFirst);
  });

  it('listens for keydown, mousedown, touchstart, input, and visibilitychange', async () => {
    const spy = vi.spyOn(document, 'addEventListener');
    const { initSessionKeepalive } = await loadKeepalive();

    initSessionKeepalive();

    for (const evt of ['keydown', 'mousedown', 'touchstart', 'input']) {
      expect(spy).toHaveBeenCalledWith(evt, expect.any(Function), { passive: true });
    }
    expect(spy).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
  });

  it('getLastActivityTimestamp reflects page-load time before interaction', async () => {
    const { getLastActivityTimestamp } = await loadKeepalive();

    expect(getLastActivityTimestamp()).toBe(FROZEN_NOW.getTime());
  });

  it('records activity on keydown, mousedown, touchstart, and input', async () => {
    const { initSessionKeepalive, getLastActivityTimestamp } = await loadKeepalive();
    initSessionKeepalive();

    const events = [
      new KeyboardEvent('keydown', { bubbles: true }),
      new MouseEvent('mousedown', { bubbles: true }),
      new Event('touchstart', { bubbles: true }),
      new Event('input', { bubbles: true }),
    ];
    for (const event of events) {
      await vi.advanceTimersByTimeAsync(1000);
      const before = getLastActivityTimestamp();
      document.dispatchEvent(event);
      expect(getLastActivityTimestamp()).toBeGreaterThan(before);
    }
  });

  it('records activity on visibilitychange only when the tab is visible', async () => {
    const { initSessionKeepalive, getLastActivityTimestamp } = await loadKeepalive();
    initSessionKeepalive();

    await vi.advanceTimersByTimeAsync(1000);
    const beforeHidden = getLastActivityTimestamp();
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(getLastActivityTimestamp()).toBe(beforeHidden);

    await vi.advanceTimersByTimeAsync(1000);
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
    document.dispatchEvent(new Event('visibilitychange'));
    expect(getLastActivityTimestamp()).toBeGreaterThan(beforeHidden);
  });

  it('POSTs keepalive after the interval when the user was recently active', async () => {
    const { initSessionKeepalive } = await loadKeepalive();
    initSessionKeepalive();

    await vi.advanceTimersByTimeAsync(60 * 1000);
    document.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
    await vi.advanceTimersByTimeAsync(KEEPALIVE_INTERVAL_MS - 60 * 1000);

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(KEEPALIVE_URL, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': 'old-tok',
      },
    });
  });

  it('skips the scheduled POST when idle for the activity window', async () => {
    const { initSessionKeepalive } = await loadKeepalive();
    initSessionKeepalive();

    await vi.advanceTimersByTimeAsync(KEEPALIVE_INTERVAL_MS);

    expect(fetch).not.toHaveBeenCalled();
  });

  it('refreshSessionNow records activity, POSTs keepalive, and updates CSRF', async () => {
    window.setCSRFToken = vi.fn();
    const { initSessionKeepalive, refreshSessionNow, getLastActivityTimestamp } = await loadKeepalive();
    initSessionKeepalive();

    await vi.advanceTimersByTimeAsync(10_000);
    const before = getLastActivityTimestamp();
    await refreshSessionNow();

    expect(getLastActivityTimestamp()).toBeGreaterThan(before);
    expect(fetch).toHaveBeenCalledWith(KEEPALIVE_URL, expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
    }));
    expect(document.querySelector('#focalDataEntryForm input[name="csrf_token"]').value).toBe('new-tok');
    expect(document.querySelector('meta[name="csrf-token"]').getAttribute('content')).toBe('new-tok');
    expect(window.setCSRFToken).toHaveBeenCalledWith('new-tok');
  });

  it('uses window.getFetch() when present instead of fetch', async () => {
    const customFetch = vi.fn().mockResolvedValue(mockFetchResponse());
    window.getFetch = vi.fn(() => customFetch);
    const { initSessionKeepalive, refreshSessionNow } = await loadKeepalive();
    initSessionKeepalive();

    await refreshSessionNow();

    expect(window.getFetch).toHaveBeenCalled();
    expect(customFetch).toHaveBeenCalledWith(KEEPALIVE_URL, expect.objectContaining({
      method: 'POST',
    }));
    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not throw on 401', async () => {
    fetch.mockResolvedValue(mockFetchResponse({ ok: false, status: 401, body: {} }));
    const { initSessionKeepalive, refreshSessionNow } = await loadKeepalive();
    initSessionKeepalive();

    await expect(refreshSessionNow()).resolves.toBeUndefined();
    expect(document.querySelector('input[name="csrf_token"]').value).toBe('old-tok');
  });

  it('does not throw on 429', async () => {
    fetch.mockResolvedValue(mockFetchResponse({ ok: false, status: 429, body: {} }));
    const { initSessionKeepalive, refreshSessionNow } = await loadKeepalive();
    initSessionKeepalive();

    await expect(refreshSessionNow()).resolves.toBeUndefined();
  });

  it('does not throw on network failure', async () => {
    fetch.mockRejectedValue(new TypeError('Failed to fetch'));
    const { initSessionKeepalive, refreshSessionNow } = await loadKeepalive();
    initSessionKeepalive();

    await expect(refreshSessionNow()).resolves.toBeUndefined();
  });

  it('does not throw when the keepalive JSON body is invalid', async () => {
    fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError('Unexpected token');
      },
    });
    const { initSessionKeepalive, refreshSessionNow } = await loadKeepalive();
    initSessionKeepalive();

    await expect(refreshSessionNow()).resolves.toBeUndefined();
    expect(document.querySelector('input[name="csrf_token"]').value).toBe('old-tok');
  });

  it('shows an idle warning after 115 minutes without activity or keepalive', async () => {
    const { initSessionKeepalive } = await loadKeepalive();
    initSessionKeepalive();

    await vi.advanceTimersByTimeAsync(WARN_IDLE_MS);

    expect(window.showFlashMessage).toHaveBeenCalledWith(
      'Your session may expire soon due to inactivity. Save your work to stay signed in.',
      'warning',
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it('does not warn at 115 minutes if a keepalive refreshed the session', async () => {
    const { initSessionKeepalive } = await loadKeepalive();
    initSessionKeepalive();

    await vi.advanceTimersByTimeAsync(60 * 1000);
    document.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
    await vi.advanceTimersByTimeAsync(KEEPALIVE_INTERVAL_MS - 60 * 1000);
    expect(fetch).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(WARN_IDLE_MS - KEEPALIVE_INTERVAL_MS);

    expect(window.showFlashMessage).not.toHaveBeenCalled();
  });
});
