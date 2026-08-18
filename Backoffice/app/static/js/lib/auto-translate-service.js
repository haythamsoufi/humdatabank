/**
 * Shared AutoTranslateService for /admin/api/auto-translate.
 * Use this instead of inline fetch calls to centralize CSRF, headers, and error handling.
 *
 * Also owns the preferred translation service (localStorage) and the split-button
 * picker used by individual translation modals.
 *
 * Depends on: csrf.js (csrfFetch), TranslationModalUtils.handleAutoTranslateResponse (optional)
 *
 * Usage:
 *   const data = await AutoTranslateService.translate({
 *     type: 'form_item',
 *     text: 'Label text',
 *     target_languages: ['fr', 'es'],
 *     permission_context: 'indicator_bank',
 *     permission_code: 'admin.indicator_bank.edit'
 *   });
 */
(function() {
    'use strict';

    const AUTO_TRANSLATE_URL = '/admin/api/auto-translate';
    const SERVICES_URL = '/admin/api/translation_services';
    const STORAGE_KEY = 'hd.autoTranslate.preferredService';
    const STATUS_STORAGE_KEY = 'hd.autoTranslate.serviceStatus';
    const CHANGE_EVENT = 'autoTranslateServiceChange';

    function resolveFetchFn() {
        if (typeof window !== 'undefined' && window.getFetch && typeof window.getFetch === 'function') {
            return window.getFetch();
        }
        return typeof fetch !== 'undefined' ? fetch : null;
    }

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function handleResponse(response) {
        if (!response) {
            return Promise.reject(new Error('No response from translation service'));
        }
        const parseJsonSafe = () =>
            response.clone().json().catch(() => ({}));

        if (!response.ok) {
            return parseJsonSafe().then(data => {
                const message = (data && (data.error || data.message)) ||
                    `HTTP ${response.status}: ${response.statusText || 'Unknown error'}`;
                throw (window.httpErrorSync && window.httpErrorSync(response, message)) || new Error(message);
            });
        }
        return response.json().then(data => {
            if (!data || !data.success) {
                throw new Error((data && (data.error || data.message)) || 'Translation failed');
            }
            return data;
        });
    }

    let servicesCache = null;
    let servicesPromise = null;
    let preferredService = null;
    let documentListenersBound = false;

    function getStoredPreference() {
        try {
            return String(localStorage.getItem(STORAGE_KEY) || '').trim();
        } catch (_) {
            return '';
        }
    }

    function setStoredPreference(value) {
        try {
            if (value) localStorage.setItem(STORAGE_KEY, value);
            else localStorage.removeItem(STORAGE_KEY);
        } catch (_) { /* ignore quota / private mode */ }
    }

    function getPreferredService() {
        if (preferredService) return preferredService;
        return getStoredPreference();
    }

    function findAvailable(services, value) {
        if (!value || !Array.isArray(services)) return null;
        return services.find(s => s && s.value === value && s.is_available) || null;
    }

    function isServiceKnownOffline(value) {
        if (!value || !servicesCache) return false;
        const match = (servicesCache.services || []).find(s => s && s.value === value);
        return !!(match && match.is_available === false);
    }

    function getServiceForTranslate() {
        const stored = getStoredPreference();
        if (stored && !isServiceKnownOffline(stored)) return stored;
        return '';
    }

    function resolvePreferredFromCache() {
        if (!servicesCache) return getPreferredService();
        const services = servicesCache.services || [];
        const stored = getStoredPreference();
        const storedOk = findAvailable(services, stored);
        if (storedOk) {
            preferredService = storedOk.value;
            return preferredService;
        }
        if (stored && services.some(s => s && s.value === stored && s.is_available === false)) {
            preferredService = '';
            setStoredPreference('');
        }
        const serverDefault = findAvailable(services, servicesCache.default_service)
            || services.find(s => s && s.is_default && s.is_available)
            || services.find(s => s && s.is_available);
        preferredService = serverDefault ? serverDefault.value : '';
        return preferredService;
    }

    function syncBulkSelect(value) {
        const select = document.getElementById('translation-service-select');
        if (!select || !value || select.value === value) return;
        const opt = Array.from(select.options).find(o => o.value === value && !o.disabled);
        if (opt) select.value = value;
    }

    function refreshPickerChrome(wrapper) {
        if (!wrapper) return;
        const toggle = wrapper.querySelector('.js-auto-translate-service-toggle');
        if (!toggle) return;
        const heading = wrapper.dataset.i18nHeading || 'Translation service';
        const selected = getPreferredService();
        const match = servicesCache && (servicesCache.services || []).find(s => s && s.value === selected);
        const title = match ? `${heading}: ${match.label}` : heading;
        toggle.title = title;
        toggle.setAttribute('aria-label', title);
    }

    function refreshAllPickerChrome() {
        document.querySelectorAll('.js-auto-translate-split').forEach(refreshPickerChrome);
    }

    function setPreferredService(value, options) {
        const next = String(value || '').trim();
        preferredService = next;
        if (next) setStoredPreference(next);
        if (!(options && options.silent)) {
            syncBulkSelect(next);
            refreshAllPickerChrome();
            try {
                document.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: { service: next } }));
            } catch (_) { /* non-fatal */ }
        }
        return next;
    }

    function hydrateStatusCache() {
        if (servicesCache) return servicesCache;
        try {
            const raw = sessionStorage.getItem(STATUS_STORAGE_KEY);
            if (!raw) return null;
            const data = JSON.parse(raw);
            if (!data || !Array.isArray(data.services)) return null;
            servicesCache = {
                services: data.services,
                default_service: data.default_service || '',
                verified: data.verified !== false
            };
            resolvePreferredFromCache();
            return servicesCache;
        } catch (_) {
            return null;
        }
    }

    function persistStatusCache(cache) {
        if (!cache || cache.verified === false) return;
        try {
            sessionStorage.setItem(STATUS_STORAGE_KEY, JSON.stringify({
                services: cache.services || [],
                default_service: cache.default_service || '',
                verified: true
            }));
        } catch (_) { /* ignore quota / private mode */ }
    }

    function servicesUrl(refresh) {
        if (!refresh) return SERVICES_URL;
        return SERVICES_URL + (SERVICES_URL.indexOf('?') === -1 ? '?' : '&') + 'refresh=1';
    }

    function fetchServices(refresh) {
        const url = servicesUrl(refresh);
        if (typeof window !== 'undefined' && typeof window.apiFetch === 'function') {
            return window.apiFetch(url);
        }
        const fetchFn = resolveFetchFn();
        if (!fetchFn) return Promise.reject(new Error('No fetch implementation available'));
        return fetchFn(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(handleResponse);
    }

    function loadServices(options) {
        const force = !!(options && options.refresh);
        if (!servicesCache) hydrateStatusCache();
        if (!force && servicesCache) return Promise.resolve(servicesCache);
        if (servicesPromise && (!force || servicesPromise._isRefresh)) return servicesPromise;

        const request = fetchServices(force);
        servicesPromise = Promise.resolve(request)
            .then(data => {
                if (!data || data.success === false) {
                    throw new Error((data && (data.error || data.message)) || 'Failed to load translation services');
                }
                servicesCache = {
                    services: Array.isArray(data.services) ? data.services : [],
                    default_service: data.default_service || '',
                    verified: data.verified !== false
                };
                persistStatusCache(servicesCache);
                resolvePreferredFromCache();
                refreshAllPickerChrome();
                return servicesCache;
            })
            .catch(err => {
                servicesPromise = null;
                throw err;
            });
        servicesPromise._isRefresh = force;
        return servicesPromise;
    }

    function closeAllMenus() {
        document.querySelectorAll('.js-auto-translate-split').forEach(wrapper => {
            const menu = wrapper.querySelector('.js-auto-translate-service-menu');
            const toggle = wrapper.querySelector('.js-auto-translate-service-toggle');
            if (menu) menu.classList.add('hidden');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
        });
    }

    function renderMenu(wrapper) {
        const menu = wrapper.querySelector('.js-auto-translate-service-menu');
        if (!menu) return;
        const loadingText = wrapper.dataset.i18nLoading || 'Loading services...';
        const emptyText = wrapper.dataset.i18nEmpty || 'No translation services configured';
        const offlineText = wrapper.dataset.i18nOffline || '(offline)';
        const headingText = wrapper.dataset.i18nHeading || 'Translation service';

        menu.replaceChildren();

        const heading = document.createElement('div');
        heading.className = 'auto-translate-service-menu-heading';
        heading.textContent = headingText;
        menu.appendChild(heading);

        if (!servicesCache) {
            const status = document.createElement('div');
            status.className = 'auto-translate-service-menu-status';
            status.textContent = loadingText;
            menu.appendChild(status);
            return;
        }

        const services = servicesCache.services || [];
        if (!services.length) {
            const status = document.createElement('div');
            status.className = 'auto-translate-service-menu-status';
            status.textContent = emptyText;
            menu.appendChild(status);
            return;
        }

        const selected = getPreferredService();
        services.forEach(service => {
            if (!service || !service.value) return;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'auto-translate-service-menu-item';
            btn.setAttribute('role', 'option');
            btn.dataset.service = service.value;
            btn.disabled = !service.is_available;
            btn.setAttribute('aria-selected', service.value === selected ? 'true' : 'false');

            const label = document.createElement('span');
            label.textContent = service.is_available
                ? String(service.label || service.value)
                : `${service.label || service.value} ${offlineText}`;
            btn.appendChild(label);

            if (service.value === selected) {
                const check = document.createElement('i');
                check.className = 'fas fa-check';
                check.setAttribute('aria-hidden', 'true');
                btn.appendChild(check);
            }

            if (service.is_available) {
                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    setPreferredService(service.value);
                    closeAllMenus();
                });
            }
            menu.appendChild(btn);
        });
    }

    function openMenu(wrapper) {
        const menu = wrapper.querySelector('.js-auto-translate-service-menu');
        const toggle = wrapper.querySelector('.js-auto-translate-service-toggle');
        if (!menu || !toggle) return;
        closeAllMenus();
        menu.classList.remove('hidden');
        toggle.setAttribute('aria-expanded', 'true');
        if (!servicesCache) hydrateStatusCache();
        renderMenu(wrapper);
        loadServices({ refresh: true })
            .then(() => renderMenu(wrapper))
            .catch(() => {
                if (servicesCache) {
                    renderMenu(wrapper);
                    return;
                }
                const status = wrapper.querySelector('.auto-translate-service-menu-status');
                if (status) status.textContent = wrapper.dataset.i18nEmpty || 'No translation services configured';
            });
    }

    function attachOne(wrapper) {
        if (!wrapper || wrapper.dataset.servicePickerAttached === 'true') return;
        wrapper.dataset.servicePickerAttached = 'true';
        const toggle = wrapper.querySelector('.js-auto-translate-service-toggle');
        if (!toggle) return;

        toggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const menu = wrapper.querySelector('.js-auto-translate-service-menu');
            const isOpen = menu && !menu.classList.contains('hidden');
            if (isOpen) closeAllMenus();
            else openMenu(wrapper);
        });
        refreshPickerChrome(wrapper);
    }

    function attachPickers(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('.js-auto-translate-split').forEach(attachOne);
        if (!documentListenersBound && typeof document !== 'undefined') {
            documentListenersBound = true;
            document.addEventListener('click', function(e) {
                if (!e.target || !e.target.closest || !e.target.closest('.js-auto-translate-split')) {
                    closeAllMenus();
                }
            });
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') closeAllMenus();
            });
        }
    }

    function initWhenReady() {
        if (typeof document === 'undefined') return;
        const start = function() {
            attachPickers(document);
        };
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', start);
        } else {
            start();
        }
    }

    /**
     * Call the auto-translate API.
     * @param {Object} params
     * @param {string} params.type - API type (e.g. 'template_name', 'form_item', 'section_name', 'page_name', 'question_option')
     * @param {string} params.text - Text to translate
     * @param {string[]} params.target_languages - Target language codes
     * @param {string} [params.permission_context] - Permission context
     * @param {string} [params.permission_code] - Permission code
     * @param {string} [params.translation_service] - hosted service id (falls back to preferred / server default)
     * @param {string} [params.definition] - Optional definition
     * @returns {Promise<{success: boolean, translations: Object}>}
     */
    async function translate(params) {
        const fetchFn = resolveFetchFn();
        if (!fetchFn) {
            throw new Error('No fetch implementation available');
        }
        const bodyObj = {
            type: params.type || 'template_name',
            target_languages: params.target_languages || []
        };
        if (params.permission_context != null) bodyObj.permission_context = params.permission_context;
        if (params.permission_code != null) bodyObj.permission_code = params.permission_code;
        const requested = (params.translation_service != null && String(params.translation_service).trim() !== '')
            ? params.translation_service
            : getServiceForTranslate();
        if (requested && !isServiceKnownOffline(requested)) {
            bodyObj.translation_service = requested;
        }
        if (params.text != null) bodyObj.text = String(params.text);
        if (params.definition != null) bodyObj.definition = String(params.definition);
        if (params.id != null) bodyObj.id = String(params.id);

        // Wrap payload to avoid WAF false positives on rich strings (HTML, "--", quotes, etc.)
        const payloadB64 = btoa(unescape(encodeURIComponent(JSON.stringify(bodyObj))));
        const body = { payload: payloadB64 };

        const response = await fetchFn(AUTO_TRANSLATE_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(body)
        });

        if (typeof window !== 'undefined' && window.TranslationModalUtils && window.TranslationModalUtils.handleAutoTranslateResponse) {
            return window.TranslationModalUtils.handleAutoTranslateResponse(response);
        }
        return handleResponse(response);
    }

    function resetForTests() {
        servicesCache = null;
        servicesPromise = null;
        preferredService = null;
        try { localStorage.removeItem(STORAGE_KEY); } catch (_) {}
        try { sessionStorage.removeItem(STATUS_STORAGE_KEY); } catch (_) {}
        documentListenersBound = false;
    }

    if (typeof window !== 'undefined') {
        window.AutoTranslateService = {
            translate,
            loadServices,
            getPreferredService,
            setPreferredService,
            attachPickers,
            STORAGE_KEY,
            _resetForTests: resetForTests
        };
    }

    initWhenReady();
})();
