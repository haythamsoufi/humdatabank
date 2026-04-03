/**
 * Plugin Field Loader
 * Handles loading and rendering of plugin fields in the entry form
 */

// Import debug utilities
import { debugLog, debugError, debugWarn, isDebugEnabled } from './modules/debug.js';

class PluginFieldLoader {
    constructor() {
        this.pluginFields = new Map();
        this.loadedPlugins = new Set();
        this._formsBoundForSerialize = new WeakSet();
        this.diagnostics = new Map(); // key: `${pluginType}:${fieldId}`
        this.init();
    }

    _safeIdPart(value) {
        // Used for DOM ids and attribute tokens; keep it strict.
        return String(value ?? '').replace(/[^a-zA-Z0-9_-]/g, '');
    }

    _isDangerousUrl(value) {
        const v = String(value ?? '').trim().toLowerCase();
        return (
            v.startsWith('javascript:') ||
            v.startsWith('data:') ||
            v.startsWith('vbscript:') ||
            v.startsWith('file:') ||
            v.startsWith('about:')
        );
    }

    _sanitizeAndAppendHtml(container, html) {
        if (!container) return;
        container.replaceChildren();

        if (typeof html !== 'string' || !html.trim()) return;

        // Parse without using innerHTML assignment (CSP/XSS-friendly).
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const root = doc.body;
        if (!root) return;

        // Remove dangerous elements.
        // NOTE: Some plugins legitimately embed JSON config via <script type="application/json">.
        // We allow those (no src, no event handlers) and strip all other scripts.
        root.querySelectorAll('iframe, object, embed, style, meta, link').forEach((el) => el.remove());
        root.querySelectorAll('script').forEach((el) => {
            const type = String(el.getAttribute('type') || '').toLowerCase();
            const hasSrc = el.hasAttribute('src');
            if (type === 'application/json' && !hasSrc) {
                return; // keep safe JSON blobs
            }
            el.remove();
        });

        // Strip dangerous attributes
        root.querySelectorAll('*').forEach((el) => {
            [...el.attributes].forEach((attr) => {
                const name = String(attr.name || '').toLowerCase();
                const value = String(attr.value || '').trim();

                // Inline event handlers
                if (name.startsWith('on')) {
                    el.removeAttribute(attr.name);
                    return;
                }

                // Dangerous URL protocols
                if (name === 'href' || name === 'src' || name === 'xlink:href' || name === 'formaction') {
                    if (this._isDangerousUrl(value)) {
                        el.removeAttribute(attr.name);
                        return;
                    }
                }
            });
        });

        const fragment = document.createDocumentFragment();
        while (root.firstChild) fragment.appendChild(root.firstChild);
        container.appendChild(fragment);
    }

    init() {
        // Find all plugin field containers
        this.findPluginFields();

        // Load plugin fields
        this.loadPluginFields();
    }

    findPluginFields() {
        const pluginContainers = document.querySelectorAll('.plugin-field-container');
        debugLog('plugin-field-loader', `Found ${pluginContainers.length} plugin field containers`);

        pluginContainers.forEach((container, index) => {
            const pluginType = container.dataset.pluginType;
            const fieldId = container.dataset.fieldId;

            debugLog('plugin-field-loader', `Container ${index + 1}: type=${pluginType}, fieldId=${fieldId}`, container);

            if (pluginType && fieldId) {
                this.pluginFields.set(fieldId, {
                    container,
                    pluginType,
                    fieldId
                });
            }
        });
    }

    async loadPluginFields() {
        debugLog('plugin-field-loader', `Loading ${this.pluginFields.size} plugin fields`);

        for (const [fieldId, fieldData] of this.pluginFields) {
            try {
                await this.loadPluginField(fieldData);
            } catch (error) {
                debugError('plugin-field-loader', `Error loading plugin field ${fieldId}:`, error);
                this.showError(fieldData.container, `Failed to load plugin: ${error.message}`);
            }
        }

        this._renderDiagnosticsPanelIfEnabled();
    }

    _diagKey(pluginType, fieldId) {
        return `${String(pluginType || '')}:${String(fieldId || '')}`;
    }

    _recordDiagnostic(diag) {
        try {
            const key = this._diagKey(diag.pluginType, diag.fieldId);
            this.diagnostics.set(key, diag);
            window.PluginDiagnostics = window.PluginDiagnostics || {};
            window.PluginDiagnostics.fields = window.PluginDiagnostics.fields || {};
            window.PluginDiagnostics.fields[key] = diag;
        } catch (e) {
            // ignore
        }
    }

    _shouldShowDiagnosticsPanel() {
        try {
            const qs = new URLSearchParams(window.location.search || '');
            if (qs.get('plugin_diagnostics') === '1') return true;
        } catch (e) { /* ignore */ }
        return isDebugEnabled('plugins') || isDebugEnabled('plugin-field-loader');
    }

    _renderDiagnosticsPanelIfEnabled() {
        if (!this._shouldShowDiagnosticsPanel()) return;
        try {
            const existing = document.getElementById('plugin-diagnostics-panel');
            if (existing) existing.remove();

            const panel = document.createElement('div');
            panel.id = 'plugin-diagnostics-panel';
            panel.style.position = 'fixed';
            panel.style.right = '12px';
            panel.style.bottom = '12px';
            panel.style.zIndex = '99999';
            panel.style.maxWidth = '420px';
            panel.style.maxHeight = '45vh';
            panel.style.overflow = 'auto';
            panel.style.background = 'rgba(17, 24, 39, 0.95)'; // gray-900
            panel.style.color = '#fff';
            panel.style.border = '1px solid rgba(255,255,255,0.15)';
            panel.style.borderRadius = '10px';
            panel.style.padding = '10px 12px';
            panel.style.fontSize = '12px';

            const header = document.createElement('div');
            header.style.display = 'flex';
            header.style.justifyContent = 'space-between';
            header.style.alignItems = 'center';
            header.style.marginBottom = '8px';
            header.innerHTML = `<div style="font-weight:600">Plugin diagnostics</div>`;

            const closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.textContent = 'Close';
            closeBtn.style.background = 'transparent';
            closeBtn.style.border = '1px solid rgba(255,255,255,0.25)';
            closeBtn.style.color = '#fff';
            closeBtn.style.borderRadius = '8px';
            closeBtn.style.padding = '2px 8px';
            closeBtn.addEventListener('click', () => panel.remove());
            header.appendChild(closeBtn);

            const list = document.createElement('div');
            const entries = Array.from(this.diagnostics.values());
            if (!entries.length) {
                list.textContent = 'No plugin fields found.';
            } else {
                for (const d of entries) {
                    const row = document.createElement('div');
                    row.style.padding = '6px 0';
                    row.style.borderTop = '1px solid rgba(255,255,255,0.08)';
                    const ok = d.status === 'ok';
                    row.innerHTML = `
                        <div style="display:flex;justify-content:space-between;gap:8px">
                          <div style="font-weight:600">${d.pluginType} <span style="opacity:.8">#${d.fieldId}</span></div>
                          <div style="color:${ok ? '#34d399' : '#f87171'}">${ok ? 'OK' : 'ERROR'}</div>
                        </div>
                        <div style="opacity:.85;margin-top:2px">
                          dom=${d.domVerified ? 'yes' : 'no'} • module=${d.moduleImported ? 'yes' : 'no'} • ${Math.round(d.initDurationMs || 0)}ms
                        </div>
                    `;
                    list.appendChild(row);
                }
            }

            panel.append(header, list);
            document.body.appendChild(panel);
        } catch (e) {
            // ignore
        }
    }

    async loadPluginField(fieldData) {
        const { container, pluginType, fieldId } = fieldData;

        debugLog('plugin-field-loader', `Loading plugin field: ${pluginType} for field ${fieldId}`);

        // New contract: plugin HTML should already be present in the DOM (server-rendered).
        // We do NOT wipe container contents up front (that would destroy server-rendered markup).
        // If the DOM is missing, we fall back to fetching the public render endpoint.
        try {
            this.loadedPlugins.add(pluginType);

            // Only show a loading UI if there is no pre-rendered content
            const hasServerDom = container?.dataset?.pluginTemplateRendered === 'true' || (container && container.children && container.children.length > 0);
            if (!hasServerDom) {
                this.showLoading(container);
            }

            const start = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
            const result = await this.renderAndInitPluginField(container, fieldId, pluginType);
            const end = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();

            this._recordDiagnostic({
                pluginType,
                fieldId,
                status: result?.ok ? 'ok' : 'error',
                domVerified: !!result?.domVerified,
                moduleImported: !!result?.moduleImported,
                initDurationMs: Math.max(0, end - start),
                error: result?.error || null,
                templateFetched: !!result?.templateFetched,
            });
        } catch (error) {
            debugError('plugin-field-loader', `Failed to load plugin ${pluginType}:`, error);
            this.showError(container, `Failed to load plugin: ${error.message}`);

            this._recordDiagnostic({
                pluginType,
                fieldId,
                status: 'error',
                domVerified: false,
                moduleImported: false,
                initDurationMs: 0,
                error: String(error?.message || error || ''),
                templateFetched: false,
            });
        }
    }

    shouldUseClientSideRendering(pluginType) {
        // Legacy; kept for backward compatibility. Default is server-rendered DOM.
        return true;
    }

    async handlePluginClientSide(fieldData) {
        const { container, pluginType, fieldId } = fieldData;

        debugLog('plugin-field-loader', `Handling plugin client-side: ${pluginType} for field ${fieldId}`);

        // Mark as loaded
        this.loadedPlugins.add(pluginType);

        // Generic plugin handling only (no plugin-specific branches)
        await this.renderAndInitPluginField(container, fieldId, pluginType);
    }

    _parseEntryFormConfig(container) {
        try {
            const raw = container?.dataset?.entryFormConfig;
            if (!raw) return null;
            return JSON.parse(raw);
        } catch (e) {
            debugWarn('plugin-field-loader', 'Failed to parse data-entry-form-config', e);
            return null;
        }
    }

    _safeJsonParse(raw, fallback = null) {
        try {
            if (raw === undefined || raw === null) return fallback;
            if (typeof raw !== 'string') return raw;
            const s = raw.trim();
            if (!s) return fallback;
            return JSON.parse(s);
        } catch (e) {
            return fallback;
        }
    }

    _buildContext(container, fieldId, pluginType, entryCfg) {
        const dataset = container?.dataset || {};
        const pluginConfig = this._safeJsonParse(dataset.pluginConfig, {}) || {};
        const existingData = this._safeJsonParse(dataset.existingData, {}) || {};
        const canEdit = dataset.canEdit === 'true';
        const countryIso = dataset.countryIso || '';

        return {
            pluginId: String(dataset.pluginId || pluginType || ''),
            fieldType: String(dataset.fieldType || pluginType || ''),
            fieldId: String(fieldId || ''),
            canEdit,
            countryIso,
            pluginConfig,
            existingData,
            entryConfig: entryCfg || {},
            container,
        };
    }

    _bindSerializeOnSubmit(formEl) {
        if (!formEl || this._formsBoundForSerialize.has(formEl)) return;
        this._formsBoundForSerialize.add(formEl);

        formEl.addEventListener('submit', () => {
            try {
                for (const [, fd] of this.pluginFields) {
                    const c = fd?.container;
                    if (!c) continue;
                    if (!formEl.contains(c)) continue;
                    const inst = c.pluginInstance;
                    if (!inst) continue;
                    if (typeof inst.serialize === 'function') {
                        try {
                            inst.serialize();
                        } catch (e) {
                            debugWarn('plugin-field-loader', 'serialize() failed for', fd?.pluginType, fd?.fieldId, e);
                        }
                    }
                }
            } catch (e) {
                // never block form submit
            }
        }, { capture: true });
    }

    async renderAndInitPluginField(container, fieldId, pluginType) {
        debugLog('plugin-field-loader', `renderAndInitPluginField: ${pluginType} field ${fieldId}`);

        const entryCfg = this._parseEntryFormConfig(container) || {};
        const templateName = entryCfg.template || null;
        const cssFiles = Array.isArray(entryCfg.css_files) ? entryCfg.css_files : [];
        const esModulePath = entryCfg.es_module_path || null;
        const esModuleClass = entryCfg.es_module_class || null;
        let moduleImported = false;
        let templateFetched = false;

        const hasInjectedTemplateDom = () => {
            if (!container) return false;
            // Strong signals for InteractiveMap-like plugins
            if (container.querySelector(`#map-${fieldId}`)) return true;
            if (container.querySelector(`.interactive-map-field[data-field-id="${fieldId}"]`)) return true;
            // Generic signals: form inputs for this field
            if (container.querySelector(`input[name="${CSS.escape(String(fieldId))}"], textarea[name="${CSS.escape(String(fieldId))}"], select[name="${CSS.escape(String(fieldId))}"]`)) return true;
            // Common id conventions
            if (container.querySelector(`#field-${CSS.escape(String(fieldId))}`)) return true;
            // Generic: allow a child element with matching field id, but NOT the container itself
            const matches = Array.from(container.querySelectorAll(`[data-field-id="${fieldId}"]`))
                .filter((el) => el !== container);
            return matches.length > 0;
        };

        // Ensure the plugin's entry template is rendered (generic).
        // In entry forms we often start with a placeholder-only container; plugins expect their HTML structure.
        let templateInjected = false;
        if (templateName && container && container.dataset.pluginTemplateRendered !== 'true') {
            try {
                debugLog('plugin-field-loader', `Fetching entry template for ${pluginType} (${templateName}) field ${fieldId}`);
                const html = await this.fetchPluginTemplatePublic(pluginType, fieldId);
                templateFetched = true;

                if (!html || html.trim().length === 0) {
                    throw new Error('Template fetch returned empty HTML');
                }

                container.replaceChildren();
                this._sanitizeAndAppendHtml(container, html);
                container.dataset.pluginTemplateRendered = 'true';

                // Verify the template was actually injected by checking for expected elements.
                // For map-like plugins we expect a stable container id (#map-<fieldId>).
                // Keep this check broad enough for other plugins (wrapper + field id attributes).
                templateInjected = hasInjectedTemplateDom();
                if (!templateInjected) {
                    debugError(
                        'plugin-field-loader',
                        `Template injection did not produce expected DOM for ${pluginType} field ${fieldId}. Container HTML:`,
                        container.innerHTML.substring(0, 800)
                    );
                    throw new Error('Template injection did not produce expected DOM structure');
                }

                debugLog('plugin-field-loader', `Injected entry template for ${pluginType} field ${fieldId}`);

                // Wait a tick to ensure DOM is ready before initialization
                await new Promise(resolve => {
                    // Use requestAnimationFrame to ensure DOM is fully rendered
                    requestAnimationFrame(() => {
                        setTimeout(resolve, 0);
                    });
                });
            } catch (e) {
                debugError('plugin-field-loader', `Failed to fetch entry template for ${pluginType} field ${fieldId}:`, e);
                this.showError(container, `Failed to load plugin template: ${e.message}`);
                return { ok: false, domVerified: false, moduleImported, templateFetched, error: e?.message || String(e) };
            }
        } else if (container.dataset.pluginTemplateRendered === 'true') {
            // Template was already rendered, check if it's still there
            templateInjected = hasInjectedTemplateDom();
            if (!templateInjected) {
                debugWarn('plugin-field-loader', `Template marked as rendered but expected element not found. Re-rendering...`);
                container.dataset.pluginTemplateRendered = 'false';
                // Retry template injection
                return this.renderAndInitPluginField(container, fieldId, pluginType);
            } else {
                debugLog('plugin-field-loader', `Template already rendered and verified for field ${fieldId}`);
            }
        } else if (!templateName) {
            // No template name specified - check if container already has the expected structure
            templateInjected = hasInjectedTemplateDom();
            if (templateInjected) {
                debugLog('plugin-field-loader', `No template name but found expected structure in container for field ${fieldId}`);
            }
        }

        // If template is required but wasn't injected, don't proceed
        if (templateName && !templateInjected) {
            debugError('plugin-field-loader', `Template injection failed for ${pluginType} field ${fieldId}. Cannot initialize.`);
            this.showError(container, `Plugin template failed to load. Please refresh the page.`);
            return { ok: false, domVerified: false, moduleImported, templateFetched, error: 'Template missing' };
        }

        // Load declared CSS files (generic)
        for (const cssHref of cssFiles) {
            if (typeof cssHref === 'string' && cssHref.trim()) {
                try {
                    await this.loadCSS(cssHref);
                } catch (e) {
                    debugWarn('plugin-field-loader', `Failed to load plugin CSS: ${cssHref}`, e);
                }
            }
        }

        // Load ES module and assign global class (generic)
        let mod = null;
        if (esModulePath) {
            try {
                debugLog('plugin-field-loader', 'dynamic importing', esModulePath, 'for', pluginType);
                mod = await import(esModulePath);
                moduleImported = true;

                // Optional schema migration hook (host-owned):
                // If module exports `migrate(payload, { toVersion })`, call it when schema versions differ.
                try {
                    const desiredVersion = entryCfg?.schema_version || null;
                    const migrateFn = mod && typeof mod.migrate === 'function' ? mod.migrate : null;
                    if (desiredVersion && migrateFn && container?.dataset?.existingData) {
                        const raw = container.dataset.existingData;
                        const payload = this._safeJsonParse(raw, null);
                        if (payload && typeof payload === 'object') {
                            const currentVersion = payload._schema_version || null;
                            if (!currentVersion) {
                                payload._schema_version = desiredVersion;
                                container.dataset.existingData = JSON.stringify(payload);
                            } else if (currentVersion !== desiredVersion) {
                                const migrated = migrateFn(payload, { toVersion: desiredVersion });
                                if (migrated && typeof migrated === 'object') {
                                    container.dataset.existingData = JSON.stringify(migrated);
                                }
                            }
                        }
                    }
                } catch (e) {
                    debugWarn('plugin-field-loader', `Schema migration failed for ${pluginType}`, e);
                }

                // Optional generic hook: allow plugin to register ActionRouter handlers.
                if (mod && typeof mod.registerActions === 'function' && window.ActionRouter) {
                    const key = `__plugin_actions_${pluginType}`;
                    if (window[key] !== true) {
                        window[key] = true;
                        try {
                            mod.registerActions(window.ActionRouter);
                        } catch (e) {
                            debugWarn('plugin-field-loader', `registerActions failed for ${pluginType}`, e);
                        }
                    }
                }

                // Make configured class globally available for legacy init flows
                if (esModuleClass) {
                    const PluginClass = mod[esModuleClass] || mod.default || null;
                    if (PluginClass) {
                        window[esModuleClass] = PluginClass;
                        debugLog('plugin-field-loader', 'assigned global', esModuleClass, 'for', pluginType);
                    } else {
                        debugWarn('plugin-field-loader', `ES module loaded but class not found: ${esModuleClass}`);
                    }
                }
            } catch (e) {
                debugError('plugin-field-loader', `Failed to import ES module for ${pluginType}`, e);
            }
        }

        // Initialize instance if we have a class (generic)
        const className = esModuleClass || this.getExpectedClassName(pluginType);
        const Ctor = window[className] || null;
        if (!Ctor) {
            debugWarn('plugin-field-loader', `No plugin class available for ${pluginType} (expected ${className})`);
            return { ok: false, domVerified: !!templateInjected, moduleImported, templateFetched, error: `Missing class ${className}` };
        }

        try {
            const instance = new Ctor(fieldId);
            // Store instance on the container for debugging/interop
            container.pluginInstance = instance;

            const context = this._buildContext(container, fieldId, pluginType, entryCfg);

            // Host-owned lifecycle (preferred)
            if (typeof instance.mount === 'function') {
                await instance.mount(container, context);
            } else if (typeof instance.initialize === 'function') {
                instance.initialize();
            } else if (typeof instance.initField === 'function') {
                instance.initField(pluginType, fieldId);
            }

            // Hook serialization into form submission (best-effort)
            try {
                const formEl = container.closest('form');
                if (formEl) this._bindSerializeOnSubmit(formEl);
            } catch (e) { /* ignore */ }

            debugLog('plugin-field-loader', `${pluginType} field ${fieldId} initialized successfully`);
            return { ok: true, domVerified: !!templateInjected, moduleImported, templateFetched };
        } catch (e) {
            debugError('plugin-field-loader', `Error initializing ${pluginType} field ${fieldId}`, e);
            return { ok: false, domVerified: !!templateInjected, moduleImported, templateFetched, error: e?.message || String(e) };
        }
    }

    async renderGenericPluginField(container, fieldId, pluginType) {
        debugLog('plugin-field-loader', `Rendering generic plugin field: ${pluginType}`);

        // Clear loading state
        container.replaceChildren();

        // Create generic plugin HTML
        const displayName = pluginType.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        const safePluginType = this._safeIdPart(pluginType);
        const safeFieldId = this._safeIdPart(fieldId);

        const wrapperEl = document.createElement('div');
        wrapperEl.className = 'plugin-field-generic';
        wrapperEl.dataset.fieldType = safePluginType;
        wrapperEl.dataset.fieldId = safeFieldId;

        const content = document.createElement('div');
        content.className = 'plugin-field-content';
        const center = document.createElement('div');
        center.className = 'text-center py-8 text-gray-500';
        const icon = document.createElement('i');
        icon.className = 'fas fa-cog fa-spin text-2xl mb-2';
        const p = document.createElement('p');
        p.textContent = `Loading ${displayName} plugin...`;
        center.append(icon, p);
        content.appendChild(center);

        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = `plugin_${safePluginType}_${safeFieldId}`;
        hidden.id = `plugin-data-${safeFieldId}`;
        hidden.value = '';

        const validation = document.createElement('div');
        validation.className = 'invalid-feedback';
        validation.id = `plugin-validation-${safeFieldId}`;

        wrapperEl.append(content, hidden, validation);
        container.appendChild(wrapperEl);
        try {
            // Propagate useful data attributes from the plugin container to the wrapper element
            const wrapper = container.querySelector('.plugin-field-generic');
            if (wrapper) {
                const d = container.dataset || {};
                debugLog('plugin-field-loader', 'plugin container dataset →', d);
                // Common country identifiers
                if (d.countryIso) wrapper.dataset.countryIso = d.countryIso;
                if (d.countryIso3) wrapper.dataset.countryIso = wrapper.dataset.countryIso || d.countryIso3;
                if (d.countryIso2) wrapper.dataset.countryIso = wrapper.dataset.countryIso || d.countryIso2;
                // Also accept snake_case variants if present
                if (d.country_iso) wrapper.dataset.countryIso = wrapper.dataset.countryIso || d.country_iso;
                if (d.country_iso3) wrapper.dataset.countryIso = wrapper.dataset.countryIso || d.country_iso3;
                if (d.country_iso2) wrapper.dataset.countryIso = wrapper.dataset.countryIso || d.country_iso2;
                debugLog('plugin-field-loader', 'wrapper dataset after propagation →', wrapper.dataset);
            }
        } catch (e) {
            debugWarn('plugin-field-loader', 'Failed to propagate container dataset to wrapper', e);
        }

        // Try to load plugin assets and initialize
        try {
            await this.loadPluginAssets(pluginType);
            await this.initializeGenericPlugin(pluginType, fieldId);
        } catch (error) {
            debugError('plugin-field-loader', `Failed to load assets for ${pluginType}:`, error);
            this.showPluginError(container, `Failed to load ${displayName} plugin: ${error.message}`);
        }
    }

    async loadPluginAssets(pluginType) {
        // Must match plugin_static_bp: /plugins/static/<plugin>/<path-under-plugin/static/>
        const assetVersion = (typeof window !== 'undefined' && window.ASSET_VERSION)
            ? encodeURIComponent(String(window.ASSET_VERSION))
            : '';
        const v = assetVersion ? `?v=${assetVersion}` : '';
        const cssPath = `/plugins/static/${pluginType}/css/${pluginType}_field.css${v}`;
        const jsPath = `/plugins/static/${pluginType}/js/${pluginType}_field.js${v}`;
        debugLog('plugin-field-loader', `attempting to load assets for ${pluginType}`, { cssPath, jsPath });

        // Load CSS if available
        try {
            await this.loadCSS(cssPath);
            debugLog('plugin-field-loader', `CSS loaded for ${pluginType}`);
        } catch (error) {
            debugWarn('plugin-field-loader', `CSS not found for ${pluginType}:`, cssPath, error);
        }

        // Try to load JS module
        try {
            await this.loadESModule(jsPath, pluginType);
            debugLog('plugin-field-loader', `JS module import attempted for ${pluginType}`);
        } catch (error) {
            debugWarn('plugin-field-loader', `JS module not found for ${pluginType}:`, jsPath, error);
        }
    }

    async loadCSS(cssPath) {
        // Check if CSS is already loaded
        if (document.querySelector(`link[href="${cssPath}"]`)) {
            return Promise.resolve();
        }

        return new Promise((resolve, reject) => {
            const cssLink = document.createElement('link');
            cssLink.rel = 'stylesheet';
            cssLink.href = cssPath;
            cssLink.onload = resolve;
            cssLink.onerror = reject;
            document.head.appendChild(cssLink);
        });
    }

    async loadESModule(jsPath, pluginType) {
        const className = this.getExpectedClassName(pluginType);

        // Check if module is already loaded
        if (window[className]) {
            debugLog('plugin-field-loader', `${className} already present on window`);
            return;
        }

        try {
            // Use dynamic import from within this ES module to avoid inline scripts (CSP-friendly)
            debugLog('plugin-field-loader', 'dynamic importing', jsPath, 'for', pluginType);
            const module = await import(jsPath);
            const PluginClass = module[className] || module.default;

            if (PluginClass) {
                window[className] = PluginClass;
                debugLog('plugin-field-loader', 'assigned global', className, 'for', pluginType);
            } else {
                debugWarn('plugin-field-loader', 'ES module loaded but expected class not found:', className);
            }
        } catch (e) {
            debugWarn('plugin-field-loader', 'Failed to load ES module:', e);
            throw e;
        }
    }

    getExpectedClassName(pluginType) {
        // Convert plugin_type to ExpectedClassName
        return pluginType.split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join('') + 'Field';
    }

    async initializeGenericPlugin(pluginType, fieldId) {
        const className = this.getExpectedClassName(pluginType);
        try {
            debugLog('plugin-field-loader', `initializeGenericPlugin → waiting for ${className} for ${pluginType} (field ${fieldId})`);
            await this.waitForGlobalClass(className, 4000);
            debugLog('plugin-field-loader', `initializeGenericPlugin → ${className} is available for ${pluginType}`);
        } catch (e) {
            debugWarn('plugin-field-loader', `${className} class not available for ${pluginType} after waiting`, e);
            this.showSimplePluginInterface(fieldId, pluginType);
            return;
        }
        try {
            debugLog('plugin-field-loader', `creating instance of ${className} for field ${fieldId}`);
            const instance = new window[className](fieldId);
            debugLog('plugin-field-loader', `created instance of ${className}`, instance);
            const wrapper = document.querySelector(`[data-field-id="${fieldId}"]`);
            if (wrapper) {
                wrapper.pluginInstance = instance;
                debugLog('plugin-field-loader', `stored pluginInstance on wrapper for field ${fieldId}`);
            }

            if (typeof instance.initialize === 'function') {
                debugLog('plugin-field-loader', `calling initialize() on ${className}`);
                instance.initialize();
            } else if (typeof instance.initField === 'function') {
                debugLog('plugin-field-loader', `calling initField() on ${className}`);
                instance.initField(pluginType, fieldId);
            }

            debugLog('plugin-field-loader', `${pluginType} field ${fieldId} initialized successfully`);
        } catch (error) {
            debugError('plugin-field-loader', `Error initializing ${pluginType} field ${fieldId}:`, error);
        }
    }

    waitForGlobalClass(className, timeoutMs = 2000) {
        return new Promise((resolve, reject) => {
            const start = Date.now();
            const check = () => {
                if (window[className]) return resolve();
                if (Date.now() - start >= timeoutMs) return reject(new Error(`Timeout waiting for ${className}`));
                setTimeout(check, 100);
            };
            check();
        });
    }

    showSimplePluginInterface(fieldId, pluginType) {
        const container = document.querySelector(`[data-field-id="${fieldId}"] .plugin-field-content`);
        if (container) {
            const displayName = pluginType.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            const safePluginType = this._safeIdPart(pluginType);
            const safeFieldId = this._safeIdPart(fieldId);

            container.replaceChildren();

            const box = document.createElement('div');
            box.className = 'bg-gray-50 border border-gray-200 rounded-lg p-4';
            const center = document.createElement('div');
            center.className = 'text-center';
            const icon = document.createElement('i');
            icon.className = 'fas fa-puzzle-piece text-gray-400 text-2xl mb-2';
            const h5 = document.createElement('h5');
            h5.className = 'text-sm font-medium text-gray-700 mb-2';
            h5.textContent = displayName;
            const p = document.createElement('p');
            p.className = 'text-xs text-gray-500 mb-3';
            p.textContent = 'Plugin interface not available';
            const textarea = document.createElement('textarea');
            textarea.name = `plugin_${safePluginType}_${safeFieldId}`;
            textarea.placeholder = `Enter ${displayName} data...`;
            textarea.className = 'w-full px-3 py-2 border border-gray-300 rounded-md text-sm';
            textarea.rows = 3;

            center.append(icon, h5, p, textarea);
            box.appendChild(center);
            container.appendChild(box);
        }
    }

    showPluginError(container, message) {
        const content = container.querySelector('.plugin-field-content');
        if (content) {
            content.replaceChildren();
            const wrap = document.createElement('div');
            wrap.className = 'text-center py-6';
            const icon = document.createElement('i');
            icon.className = 'fas fa-exclamation-triangle text-red-500 text-2xl mb-3';
            const h4 = document.createElement('h4');
            h4.className = 'text-sm font-medium text-red-700 mb-2';
            h4.textContent = 'Plugin Error';
            const p = document.createElement('p');
            p.className = 'text-xs text-red-600';
            p.textContent = String(message || '');
            wrap.append(icon, h4, p);
            content.appendChild(wrap);
        }
    }

    // NOTE: No plugin-specific rendering/asset logic should live here.
    // Plugins must provide everything they need via get_entry_form_config()
    // and their own static assets.

    async fetchPluginConfig(pluginType) {
        try {
            const fn = (window.getFetch && window.getFetch()) || fetch;
            const response = await fn(`/admin/api/plugins/field-types/${pluginType}`);
            if (!response.ok) {
                throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return await response.json();
        } catch (error) {
            throw new Error(`Failed to fetch plugin config: ${error.message}`);
        }
    }

    async fetchPluginTemplate(pluginType, fieldId) {
        try {
            // Try to include config and existing data if present on container
            const fieldData = this.pluginFields.get(fieldId);
            let params = new URLSearchParams({ field_id: String(fieldId) });
            try {
                const cfg = fieldData?.container?.dataset?.pluginConfig;
                if (cfg) params.set('field_config', cfg);
                const ex = fieldData?.container?.dataset?.existingData;
                if (ex) params.set('existing_data', ex);
            } catch (e) { /* no-op */ }

            const fn = (window.getFetch && window.getFetch()) || fetch;
            const response = await fn(`/admin/api/plugins/field-types/${pluginType}/render-entry?${params.toString()}`, {
                method: 'GET',
                headers: {
                    'Accept': 'text/html',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            if (!response.ok) {
                throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return await response.text();
        } catch (error) {
            throw new Error(`Failed to fetch plugin template: ${error.message}`);
        }
    }

    async fetchPluginTemplatePublic(pluginType, fieldId) {
        try {
            const fieldData = this.pluginFields.get(fieldId);
            let params = new URLSearchParams({ field_id: String(fieldId) });
            try {
                const cfg = fieldData?.container?.dataset?.pluginConfig;
                if (cfg) params.set('field_config', cfg);
                const ex = fieldData?.container?.dataset?.existingData;
                if (ex) params.set('existing_data', ex);
            } catch (e) { /* no-op */ }

            const url = `/api/plugins/field-types/${pluginType}/render-entry?${params.toString()}`;
            debugLog('plugin-field-loader', 'fetchPluginTemplatePublic →', url);
            const fn = (window.getFetch && window.getFetch()) || fetch;
            const response = await fn(url, {
                method: 'GET',
                headers: {
                    'Accept': 'text/html',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            if (!response.ok) {
                throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return await response.text();
        } catch (error) {
            throw new Error(`Failed to fetch plugin template: ${error.message}`);
        }
    }

    renderPluginField(fieldData, pluginConfig = null, pluginTemplate = null) {
        const { container, pluginType, fieldId } = fieldData;

        // Clear loading state
        container.replaceChildren();

        if (pluginTemplate) {
            // Render the plugin template
            this._sanitizeAndAppendHtml(container, pluginTemplate);

            // Initialize the plugin field
            this.initializePluginField(container, pluginType, fieldId, pluginConfig);
        } else {
            // Fallback rendering
            this.renderFallbackField(container, pluginType, fieldId);
        }
    }

    renderFallbackField(container, pluginType, fieldId) {
        const displayName = pluginType.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        container.replaceChildren();
        const wrap = document.createElement('div');
        wrap.className = 'plugin-field-fallback';
        const center = document.createElement('div');
        center.className = 'text-center py-6';
        const icon = document.createElement('i');
        icon.className = 'fas fa-map-marked-alt text-3xl text-blue-500 mb-3';
        const h4 = document.createElement('h4');
        h4.className = 'text-lg font-medium text-gray-700 mb-2';
        h4.textContent = displayName;
        const p = document.createElement('p');
        p.className = 'text-sm text-gray-500 mb-4';
        p.textContent = 'Plugin field loaded successfully';
        const box = document.createElement('div');
        box.className = 'bg-gray-100 border border-gray-200 rounded-lg p-4';
        const p2 = document.createElement('p');
        p2.className = 'text-sm text-gray-600';
        p2.textContent = 'Plugin configuration and rendering will be available when the plugin system is fully integrated.';
        box.appendChild(p2);
        center.append(icon, h4, p, box);
        wrap.appendChild(center);
        container.appendChild(wrap);
    }

    initializePluginField(container, pluginType, fieldId, pluginConfig) {
        // Add field ID to the container for form submission
        const formInputs = container.querySelectorAll('input, select, textarea');
        formInputs.forEach(input => {
            if (!input.name) {
                input.name = `plugin_${pluginType}_${fieldId}`;
            }
            input.id = input.id || `plugin_${pluginType}_${fieldId}_${input.type || 'input'}`;
        });

        // Initialize any plugin-specific JavaScript
        this.initializePluginJavaScript(container, pluginType, fieldId, pluginConfig);

        // Add validation support
        this.addValidationSupport(container, fieldId);
    }

    initializePluginJavaScript(container, pluginType, fieldId, pluginConfig) {
        // Look for plugin-specific initialization
        const initFunction = window[`${pluginType}Plugin`];
        if (initFunction && typeof initFunction.initField === 'function') {
            try {
                initFunction.initField(container, fieldId, pluginConfig);
            } catch (error) {
                debugWarn('plugin-field-loader', `Plugin initialization failed for ${pluginType}:`, error);
            }
        }
    }

    addValidationSupport(container, fieldId) {
        // Add basic validation support
        const formInputs = container.querySelectorAll('input, select, textarea');
        formInputs.forEach(input => {
            input.addEventListener('invalid', (e) => {
                e.preventDefault();
                this.showFieldError(fieldId, input.validationMessage);
            });

            input.addEventListener('input', () => {
                this.clearFieldError(fieldId);
            });
        });
    }

    showLoading(container) {
        if (!container) return;
        container.replaceChildren();
        const wrap = document.createElement('div');
        wrap.className = 'plugin-field-loading';
        const center = document.createElement('div');
        center.className = 'text-center py-8 text-gray-500';
        const spinner = document.createElement('div');
        spinner.className = 'animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2';
        const p = document.createElement('p');
        p.textContent = 'Loading plugin field...';
        center.append(spinner, p);
        wrap.appendChild(center);
        container.appendChild(wrap);
    }

    showError(container, message) {
        if (!container) return;
        container.replaceChildren();
        const safeFieldId = this._safeIdPart(container.dataset.fieldId);

        const wrap = document.createElement('div');
        wrap.className = 'plugin-field-error';
        const center = document.createElement('div');
        center.className = 'text-center py-6';
        const icon = document.createElement('i');
        icon.className = 'fas fa-exclamation-triangle text-3xl text-red-500 mb-3';
        const h4 = document.createElement('h4');
        h4.className = 'text-lg font-medium text-red-700 mb-2';
        h4.textContent = 'Plugin Error';
        const p = document.createElement('p');
        p.className = 'text-sm text-red-600 mb-4';
        p.textContent = String(message || '');
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500';
        btn.dataset.action = 'plugin-field:reload';
        btn.dataset.fieldId = safeFieldId;
        btn.textContent = 'Retry';
        center.append(icon, h4, p, btn);
        wrap.appendChild(center);
        container.appendChild(wrap);
    }

    showFieldError(fieldId, message) {
        const errorElement = document.getElementById(`error-field-${fieldId}`);
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.style.display = 'block';
        }
    }

    clearFieldError(fieldId) {
        const errorElement = document.getElementById(`error-field-${fieldId}`);
        if (errorElement) {
            errorElement.style.display = 'none';
        }
    }

    // Public method to reload a specific plugin field
    reloadPluginField(fieldId) {
        const fieldData = this.pluginFields.get(fieldId);
        if (fieldData) {
            this.loadPluginField(fieldData);
        }
    }

    // Public method to reload all plugin fields
    reloadAllPluginFields() {
        this.loadedPlugins.clear();
        this.loadPluginFields();
    }


}

// Initialize when DOM is ready
// Handle both cases: DOMContentLoaded hasn't fired yet, or it already fired
function initializePluginFieldLoader() {
    debugLog('plugin-field-loader', 'DOM ready, initializing...');
    // Guard against double-loading this script (can happen if bundled twice).
    if (window.pluginFieldLoader) {
        debugWarn('plugin-field-loader', 'PluginFieldLoader already initialized; skipping duplicate init');
        return;
    }
    window.pluginFieldLoader = new PluginFieldLoader();
    debugLog('plugin-field-loader', 'Initialized successfully');
}

if (document.readyState === 'loading') {
    // DOM hasn't finished loading yet, wait for DOMContentLoaded
    document.addEventListener('DOMContentLoaded', initializePluginFieldLoader);
} else {
    // DOM is already ready (interactive or complete), initialize immediately
    initializePluginFieldLoader();
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PluginFieldLoader;
}
