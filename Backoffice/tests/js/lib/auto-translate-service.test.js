/**
 * Preferred translation service + split-button picker.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

function mockJsonResponse(body, ok = true) {
  return {
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? 'OK' : 'Error',
    headers: { get: () => 'application/json' },
    clone() { return this; },
    json: async () => body,
  };
}

describe('AutoTranslateService preferred service picker', () => {
  beforeEach(async () => {
    vi.resetModules();
    localStorage.clear();
    document.body.innerHTML = '';
    window.getFetch = () => fetch;
    await import('../../../app/static/js/lib/auto-translate-service.js');
    window.AutoTranslateService._resetForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    if (window.AutoTranslateService && window.AutoTranslateService._resetForTests) {
      window.AutoTranslateService._resetForTests();
    }
    localStorage.clear();
    document.body.innerHTML = '';
  });

  it('persists the preferred service and reuses it on translate()', async () => {
    window.AutoTranslateService.setPreferredService('google');
    expect(window.AutoTranslateService.getPreferredService()).toBe('google');
    expect(localStorage.getItem(window.AutoTranslateService.STORAGE_KEY)).toBe('google');

    const fetchMock = vi.fn(async () => mockJsonResponse({ success: true, translations: { fr: 'Bonjour' } }));
    window.getFetch = () => fetchMock;

    await window.AutoTranslateService.translate({
      type: 'template_name',
      text: 'Hello',
      target_languages: ['fr']
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    const payload = JSON.parse(decodeURIComponent(escape(atob(body.payload))));
    expect(payload.translation_service).toBe('google');
  });

  it('loads services on chevron click and selecting one updates the default', async () => {
    document.body.innerHTML = `
      <div class="js-auto-translate-split"
           data-i18n-heading="Translation service"
           data-i18n-loading="Loading services..."
           data-i18n-empty="No translation services configured"
           data-i18n-offline="(offline)">
        <button type="button" id="auto-translate-demo-btn">Auto Translate</button>
        <button type="button" class="js-auto-translate-service-toggle" aria-expanded="false">v</button>
        <div class="js-auto-translate-service-menu hidden"></div>
      </div>
    `;

    const fetchMock = vi.fn(async (url) => {
      if (String(url).includes('translation_services')) {
        return mockJsonResponse({
          success: true,
          default_service: 'ifrc',
          services: [
            { value: 'ifrc', label: 'Hosted translation API', is_default: true, is_available: true },
            { value: 'google', label: 'Google Translate', is_default: false, is_available: true }
          ]
        });
      }
      return mockJsonResponse({ success: true, translations: {} });
    });
    window.getFetch = () => fetchMock;
    window.apiFetch = async (url) => {
      const response = await fetchMock(url);
      return response.json();
    };

    window.AutoTranslateService.attachPickers(document);
    document.querySelector('.js-auto-translate-service-toggle').click();

    await vi.waitFor(() => {
      const items = document.querySelectorAll('.auto-translate-service-menu-item');
      expect(items.length).toBe(2);
    });

    const googleBtn = Array.from(document.querySelectorAll('.auto-translate-service-menu-item'))
      .find(btn => btn.dataset.service === 'google');
    expect(googleBtn).toBeTruthy();
    googleBtn.click();

    expect(window.AutoTranslateService.getPreferredService()).toBe('google');
    expect(localStorage.getItem(window.AutoTranslateService.STORAGE_KEY)).toBe('google');
    expect(document.querySelector('.js-auto-translate-service-menu').classList.contains('hidden')).toBe(true);
    expect(String(fetchMock.mock.calls[0][0])).toContain('refresh=1');
  });

  it('shows last cached status immediately and refreshes on open', async () => {
    sessionStorage.setItem('hd.autoTranslate.serviceStatus', JSON.stringify({
      default_service: 'ifrc',
      verified: true,
      services: [
        { value: 'libre', label: 'LibreTranslate AI', is_default: false, is_available: false },
        { value: 'ifrc', label: 'Hosted translation API', is_default: true, is_available: true }
      ]
    }));

    document.body.innerHTML = `
      <div class="js-auto-translate-split"
           data-i18n-heading="Translation service"
           data-i18n-loading="Loading services..."
           data-i18n-empty="No translation services configured"
           data-i18n-offline="(offline)">
        <button type="button" class="js-auto-translate-service-toggle" aria-expanded="false">v</button>
        <div class="js-auto-translate-service-menu hidden"></div>
      </div>
    `;

    let resolveRefresh;
    const refreshPromise = new Promise((resolve) => { resolveRefresh = resolve; });
    const fetchMock = vi.fn(async (url) => {
      if (String(url).includes('translation_services')) {
        await refreshPromise;
        return mockJsonResponse({
          success: true,
          verified: true,
          default_service: 'ifrc',
          services: [
            { value: 'libre', label: 'LibreTranslate AI', is_default: false, is_available: false },
            { value: 'ifrc', label: 'Hosted translation API', is_default: true, is_available: true }
          ]
        });
      }
      return mockJsonResponse({ success: true, translations: {} });
    });
    window.getFetch = () => fetchMock;
    window.apiFetch = async (url) => {
      const response = await fetchMock(url);
      return response.json();
    };

    window.AutoTranslateService.attachPickers(document);
    document.querySelector('.js-auto-translate-service-toggle').click();

    const items = document.querySelectorAll('.auto-translate-service-menu-item');
    expect(items.length).toBe(2);
    const libreBtn = Array.from(items).find(btn => btn.dataset.service === 'libre');
    expect(libreBtn.disabled).toBe(true);
    expect(libreBtn.textContent).toContain('offline');

    resolveRefresh();
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
      expect(String(fetchMock.mock.calls[0][0])).toContain('refresh=1');
    });
  });

  it('does not send an offline stored service on translate()', async () => {
    localStorage.setItem(window.AutoTranslateService.STORAGE_KEY, 'libre');
    window.apiFetch = async () => ({
      success: true,
      default_service: 'ifrc',
      services: [
        { value: 'libre', label: 'LibreTranslate AI', is_default: false, is_available: false },
        { value: 'ifrc', label: 'Hosted translation API', is_default: true, is_available: true }
      ]
    });
    await window.AutoTranslateService.loadServices();

    const fetchMock = vi.fn(async () => mockJsonResponse({ success: true, translations: { fr: 'Bonjour' } }));
    window.getFetch = () => fetchMock;

    await window.AutoTranslateService.translate({
      type: 'section_name',
      text: 'Volunteers',
      target_languages: ['fr']
    });

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    const payload = JSON.parse(decodeURIComponent(escape(atob(body.payload))));
    expect(payload.translation_service).toBeUndefined();
  });
});
