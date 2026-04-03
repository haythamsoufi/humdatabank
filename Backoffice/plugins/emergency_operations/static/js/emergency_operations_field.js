import { debugPluginLog, debugPluginError, debugPluginWarn } from '/static/js/forms/modules/debug.js';

export class EmergencyOperationsField {
  constructor(fieldId) {
    this.fieldId = String(fieldId);
    this.pluginName = 'EmergencyOperations'; // Set plugin name for debugging
    this.wrapper = document.querySelector(`[data-field-id="${this.fieldId}"]`);
    this.countryIso = this.wrapper?.dataset?.countryIso || '';
    this.config = {};
    this._placeholderInitTimer = null;
  }

  /**
   * Mark that this plugin's API-backed data has been populated (even if empty/error),
   * so relevance conditions can reliably evaluate measures like `plugin_<id>_eo1`.
   *
   * IMPORTANT: do NOT call this during the initial placeholder setup; call it only
   * after we have rendered from cache/live API or definitively failed.
   */
  markPluginDataReady() {
    if (!this.wrapper) return;
    const set = (el) => {
      try {
        el.setAttribute('data-plugin-data-ready', 'true');
        if (el.dataset) el.dataset.pluginDataReady = 'true';
      } catch (_e) {
        // ignore
      }
    };
    set(this.wrapper);
    const pluginContainer = this.wrapper.closest('.plugin-field-container');
    if (pluginContainer) set(pluginContainer);
    document.querySelectorAll(`[data-field-id="${this.fieldId}"]`).forEach((el) => set(el));

    // Notify listeners (conditions loader waits on this).
    try {
      this.wrapper.dispatchEvent(new CustomEvent('pluginDataReady', {
        detail: { fieldId: this.fieldId, pluginName: 'emergency_operations' },
        bubbles: true
      }));
    } catch (_e) {
      // ignore
    }
  }

  // ---- shared inflight dedupe (per page) ----
  _getInflightMap() {
    try {
      window.__emopsInflight = window.__emopsInflight || new Map();
      return window.__emopsInflight;
    } catch (_) {
      return null;
    }
  }

  _inflightKey(cacheKey, endpointPath) {
    return `${String(endpointPath || '')}::${String(cacheKey || '')}`;
  }

  // ---- cache helpers (session-scoped) ----
  _hashString(str) {
    // Simple stable hash for cache keys (djb2)
    let h = 5381;
    for (let i = 0; i < str.length; i++) {
      h = ((h << 5) + h) ^ str.charCodeAt(i);
    }
    return (h >>> 0).toString(16);
  }

  _cacheKeyForParams(params) {
    const iso = String(this.countryIso || '').toUpperCase();
    const start = params.get('start_date__gte') || '';
    const end = params.get('end_date__gte') || params.get('end_date__gt') || '';
    const raw = JSON.stringify({ v: 1, iso, start, end });
    return `emops_ops_v1_${this._hashString(raw)}`;
  }

  _loadCache(cacheKey) {
    try {
      const raw = window.sessionStorage?.getItem(cacheKey);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !Array.isArray(parsed.results)) return null;
      return parsed;
    } catch (_) {
      return null;
    }
  }

  _saveCache(cacheKey, payload) {
    try {
      window.sessionStorage?.setItem(cacheKey, JSON.stringify({
        results: Array.isArray(payload?.results) ? payload.results : [],
        display_config: payload?.display_config || null,
        saved_at: Date.now()
      }));
    } catch (_) {
      // ignore storage failures (quota / disabled)
    }
  }

  _mergeDisplayConfig(displayConfig) {
    if (!displayConfig || typeof displayConfig !== 'object') return;
    // Ensure field-level config takes precedence over server defaults
    this.config = { ...displayConfig, ...this.config };
  }

  initialize() {
    debugPluginLog(this.pluginName, 'Initializing emergency operations field');
    try {
      debugPluginLog(this.pluginName, 'fieldId:', this.fieldId);
      debugPluginLog(this.pluginName, 'wrapper:', this.wrapper);
      debugPluginLog(this.pluginName, 'wrapper dataset:', this.wrapper?.dataset);
      debugPluginLog(this.pluginName, 'countryIso (from wrapper dataset):', this.countryIso);
      // Generic header markup is not rendered by the loader; no runtime removal needed
      const container = this.wrapper?.closest('.plugin-field-container');
      if (container) {
        const d = container.dataset || {};
        debugPluginLog(this.pluginName, 'plugin-field-container dataset:', d);
        if (!this.countryIso && d.countryIso) {
          this.countryIso = d.countryIso;
          debugPluginLog(this.pluginName, 'countryIso (from plugin container):', this.countryIso);
        }
        if (!this.countryIso && d.countryIso3) {
          this.countryIso = d.countryIso3;
          debugPluginLog(this.pluginName, 'countryIso (from plugin container countryIso3):', this.countryIso);
        }
        if (!this.countryIso && d.countryIso2) {
          this.countryIso = d.countryIso2;
          debugPluginLog(this.pluginName, 'countryIso (from plugin container countryIso2):', this.countryIso);
        }
      }
    } catch (e) {
      debugPluginWarn(this.pluginName, 'init dataset read error:', e);
    }
    try {
      // If plugin config is embedded on field or container
      const cfgSelf = this.wrapper?.dataset?.pluginConfig;
      const cfgContainer = this.wrapper?.closest('.plugin-field-container')?.dataset?.pluginConfig;
      const cfg = cfgSelf || cfgContainer;
      if (cfg) {
        try { this.config = JSON.parse(cfg); } catch (e) { debugPluginWarn(this.pluginName, 'failed to parse pluginConfig:', e, cfg); }
      }
    } catch (_) {}

    debugPluginLog(this.pluginName, 'config:', this.config);
    if (!this.countryIso) {
      debugPluginWarn(this.pluginName, 'No country ISO found. Rendering will proceed but API will fetch unfiltered results.');
    }

    this.render();

    // Initialize operations count to 0 while API call is in-flight.
    // IMPORTANT: guard this so it never overwrites real data (cache/live) that may render quickly.
    // Do NOT call updateOperationsVariables([]) here: that would publish EO1/EO2/EO3 = '' into
    // window.__ifrcPluginVariables via the MutationObserver, which makes isDepsReadyNow() in
    // conditions.js think the variables are "ready" ('' !== null) even though real data hasn't
    // arrived yet, causing relevance conditions to evaluate with stale empty values and incorrectly
    // hide sections that should be visible.
    this._placeholderInitTimer = setTimeout(() => {
      try {
        if (!this.wrapper) return;
        const ready = String(this.wrapper.getAttribute('data-plugin-data-ready') || '').toLowerCase() === 'true';
        const existingCount = this.wrapper.getAttribute('data-operations-count');
        const hasCount = existingCount !== null && String(existingCount).trim() !== '';
        if (ready || hasCount) return;

        // Only set the count; leave EO1/EO2/EO3 attributes absent so the variable registry
        // stays empty (null) until renderList() publishes real values.
        this._setOperationsCountAttributes(0);
      } catch (_e) {
        // ignore
      }
    }, 10);

    this.fetchOperations();
  }

  render() {
    if (!this.wrapper) return;
    // Ensure structure exists even when rendered via generic plugin wrapper
    let fieldRoot = this.wrapper.querySelector('.emops-field');
    if (!fieldRoot) {
      fieldRoot = document.createElement('div');
      fieldRoot.className = 'emops-field';
      fieldRoot.setAttribute('data-field-id', this.fieldId);
      if (this.countryIso) fieldRoot.setAttribute('data-country-iso', this.countryIso);
      fieldRoot.innerHTML = `
        <div class="emops-body"></div>
        <input type="hidden" name="field_value[${this.fieldId}]" value="{}">
      `;
      const content = this.wrapper.querySelector('.plugin-field-content') || this.wrapper;
      content.innerHTML = '';
      content.appendChild(fieldRoot);
    }
    const body = fieldRoot.querySelector('.emops-body');
    if (!body) return;
    body.innerHTML = `<div class="emops-list space-y-2"></div>`;
  }

  async fetchOperations() {
    debugPluginLog(this.pluginName, 'Fetching operations');
    const body = this.wrapper.querySelector('.emops-body');
    const list = this.wrapper.querySelector('.emops-list');
    if (!body || !list) return;

    const params = new URLSearchParams();
    if (this.countryIso) params.set('iso', String(this.countryIso).toUpperCase());

    // Add date range parameters from config (inclusive filtering: >=)
    if (this.config?.start_date) {
      params.set('start_date__gte', this.config.start_date);
      debugPluginLog(this.pluginName, 'start_date from config (inclusive >=):', this.config.start_date);
    }
    if (this.config?.end_date_gt) {
      params.set('end_date__gte', this.config.end_date_gt);  // Use gte for inclusive filtering (>=)
      debugPluginLog(this.pluginName, 'end_date_gt from config (inclusive >=):', this.config.end_date_gt);
    }

    const cacheKey = this._cacheKeyForParams(params);
    const cached = this._loadCache(cacheKey);
    const now = Date.now();
    // Match backend cache TTL (60s) but leave room for backend/network jitter.
    const FRESH_MS = 45 * 1000;
    const cachedAgeMs = (cached && cached.saved_at) ? Math.max(0, now - Number(cached.saved_at)) : null;
    const isCacheFresh = cachedAgeMs !== null && !Number.isNaN(cachedAgeMs) && cachedAgeMs < FRESH_MS;

    // If we have cache, render it immediately (prevents stale cross-country UI)
    // then silently try to refresh from the live endpoint.
    if (cached) {
      this._mergeDisplayConfig(cached.display_config);
      this.renderList(cached.results);
    } else {
      // Show loading only when we have nothing cached
      list.innerHTML = `
        <div class="text-center py-4 text-gray-500">
          <i class="fas fa-spinner fa-spin"></i>
          <span>Loading operations...</span>
        </div>
      `;
    }

    try {
      const tryFetch = async (endpointPath) => {
        const url = `/admin/plugins/emergency_operations/api/${endpointPath}?${params.toString()}`;
        debugPluginLog(this.pluginName, 'fetch URL:', url);
        debugPluginLog(this.pluginName, 'countryIso used:', this.countryIso);
        debugPluginLog(this.pluginName, 'config used:', this.config);

        // Deduplicate concurrent requests across multiple EO fields on the same page.
        const inflight = this._getInflightMap();
        const inflightKey = this._inflightKey(cacheKey, endpointPath);
        if (inflight && inflight.has(inflightKey)) {
          return await inflight.get(inflightKey);
        }

        const p = (async () => {
          const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
          debugPluginLog(this.pluginName, 'response status:', res.status, res.statusText);
          if (!res.ok) {
            let errText = '';
            try { errText = await res.text(); } catch (_) {}
            throw new Error(`HTTP ${res.status} ${res.statusText} ${errText ? '- ' + errText : ''}`);
          }
          const data = await res.json();
          debugPluginLog(this.pluginName, 'payload keys:', Object.keys(data || {}));
          if (!data?.success) throw new Error(data?.error || 'Unknown error');
          return data;
        })();

        if (inflight) inflight.set(inflightKey, p);
        try {
          return await p;
        } finally {
          if (inflight) inflight.delete(inflightKey);
        }
      };

      // If we already have fresh session cache, do not hit backend at all on initial load.
      // This is the biggest win for forms with multiple EO fields.
      if (cached && isCacheFresh) {
        debugPluginLog(this.pluginName, `session cache is fresh (${Math.round(cachedAgeMs / 1000)}s); skipping backend refresh`);
        return;
      }

      let data = null;

      if (cached) {
        // When we have cached UI, prefer the backend cached endpoint first (cheap when server cache hits),
        // then do a best-effort live refresh in the background.
        try {
          data = await tryFetch('operations');
        } catch (cachedErr) {
          debugPluginWarn(this.pluginName, 'Cached endpoint failed; keeping session cache UI and attempting live refresh:', cachedErr);
        }

        // Background live refresh (do not block UI)
        tryFetch('operations/live')
          .then((liveData) => {
            if (!liveData) return;
            if (liveData.display_config) this._mergeDisplayConfig(liveData.display_config);
            const liveResults = Array.isArray(liveData.results) ? liveData.results : [];
            this._saveCache(cacheKey, { results: liveResults, display_config: liveData.display_config });
            this.renderList(liveResults);
          })
          .catch((e) => debugPluginWarn(this.pluginName, 'Background live refresh failed:', e));
      } else {
        // Cold start: try live first, then cached fallback.
        try {
          data = await tryFetch('operations/live');
        } catch (liveErr) {
          debugPluginWarn(this.pluginName, 'Live refresh failed, falling back to cached endpoint:', liveErr);
        }

        if (!data) {
          data = await tryFetch('operations');
        }
      }

      // If we got a foreground response, apply it.
      if (!data) {
        // If we already rendered cached data from sessionStorage, keep it silently.
        if (cached) return;
        throw new Error('No data returned');
      }

      // Update config with display settings from API response
      if (data.display_config) {
        this._mergeDisplayConfig(data.display_config);
        debugPluginLog(this.pluginName, 'updated config with display settings (server defaults merged, field overrides):', this.config);
      }

      const results = Array.isArray(data.results) ? data.results : [];
      debugPluginLog(this.pluginName, 'results count:', results.length);
      this._saveCache(cacheKey, { results, display_config: data.display_config });
      this.renderList(results);
    } catch (e) {
      // If we already rendered cached data, keep it silently.
      if (cached) {
        debugPluginWarn(this.pluginName, 'refresh failed; keeping cached operations list silently:', e);
        return;
      }

      list.innerHTML = `
        <div class="text-center py-4 text-red-600">
          <i class="fas fa-exclamation-triangle"></i>
          <span>Failed to load operations</span>
          <div class="text-xs text-red-500 mt-1">${(e && e.message) ? e.message : 'Unknown error'}</div>
        </div>
      `;
      this.updateOperationsVariables([]);
      this.markPluginDataReady();
      this.updateOperationsCount(0);
      // keep console error for debugging
      debugPluginError(this.pluginName, 'fetch error', e);
    }
  }

  renderList(items) {
    debugPluginLog(this.pluginName, 'renderList - VERSION WITH FIXES - START - TIMESTAMP:', new Date().toISOString());
    debugPluginLog(this.pluginName, 'renderList - items:', items);
    debugPluginLog(this.pluginName, 'renderList - wrapper:', this.wrapper);

    // Check if items is valid
    if (!items) {
      debugPluginError(this.pluginName, 'renderList - items is null/undefined');
      return;
    }

    debugPluginLog(this.pluginName, 'renderList - items length:', items.length);

    // Check if wrapper is valid
    if (!this.wrapper) {
      debugPluginError(this.pluginName, 'renderList - wrapper is null/undefined');
      return;
    }

    debugPluginLog(this.pluginName, 'renderList called with items:', items);
    debugPluginLog(this.pluginName, 'wrapper element:', this.wrapper);

    // Find or create the list container
    debugPluginLog(this.pluginName, 'About to look for .emops-list element...');
    let list = this.wrapper.querySelector('.emops-list');
    debugPluginLog(this.pluginName, 'Found .emops-list:', list);

    if (!list) {
      debugPluginLog(this.pluginName, '.emops-list not found, creating it');
      const body = this.wrapper.querySelector('.emops-body');
      debugPluginLog(this.pluginName, 'Found .emops-body:', body);

      if (body) {
        list = document.createElement('div');
        list.className = 'emops-list';
        body.innerHTML = '';
        body.appendChild(list);
        debugPluginLog(this.pluginName, 'Created .emops-list element');
      } else {
        debugPluginError(this.pluginName, 'No .emops-body found, cannot create list');
        return;
      }
    }
    if (!items.length) {
      list.innerHTML = `
        <div class="text-gray-500 text-sm">No active operations found.</div>
      `;
      debugPluginLog(this.pluginName, 'empty list rendered');
      this.updateOperationsVariables([]);
      this.markPluginDataReady();
      this.updateOperationsCount(0);
      return;
    }

    const maxItems = Number(this.config?.max_items || 10);
    const showReq = this.config?.show_requested_amount !== false;
    const showFund = this.config?.show_funded_amount !== false;
    const showCov = this.config?.show_coverage !== false;

    // Ensure operationTypes is always an array
    let operationTypes = this.config?.operation_types || ['All'];
    if (!Array.isArray(operationTypes)) {
      // Handle case where it might be a single string value or other non-array type
      if (typeof operationTypes === 'string') {
        operationTypes = [operationTypes];
      } else {
        operationTypes = ['All'];
      }
    }

    const resolveCurrencyCode = (item) => {
      // Prefer explicit codes from payload if present; default to CHF
      return (item?.currency || item?.amount_currency || item?.requested_amount_currency || item?.requested_currency || 'CHF');
    };

    const currency = (v, code = 'CHF') => {
      if (typeof v !== 'number') return '';
      try { return new Intl.NumberFormat(undefined, { style: 'currency', currency: String(code || 'CHF'), maximumFractionDigits: 0 }).format(v); } catch (_) { return String(v); }
    };

    // Filter by operation types
    const filterByOperationType = (item) => {
      // Ensure operationTypes is an array before using array methods
      if (!Array.isArray(operationTypes) || operationTypes.length === 0) {
        return true; // Default to showing all if invalid
      }

      if (operationTypes.includes('All')) return true;

      const itemType = item?.atype_display || item?.appeal_type || '';
      return operationTypes.some(type => {
        if (type === 'Emergency Appeal') {
          return itemType.toLowerCase().includes('emergency') || itemType.toLowerCase().includes('appeal');
        } else if (type === 'DREF') {
          return itemType.toLowerCase().includes('dref') || itemType.toLowerCase().includes('disaster relief emergency fund');
        }
        return false;
      });
    };

    list.innerHTML = '';
    const normStatus = (item) => String(item?.status_display || item?.status || '').toLowerCase();
    const isClosed = (item) => {
      const s = normStatus(item);
      return s.includes('closed') || s.includes('ended') || s.includes('complete');
    };
    const isActive = (item) => {
      const s = normStatus(item);
      if (!s) return true;
      return s.includes('active') || s.includes('ongoing') || s.includes('current') || !isClosed(item);
    };

    // Apply operation type filtering first
    const filteredItems = items.filter(filterByOperationType);
    debugPluginLog(this.pluginName, 'operation type filtering:', { original: items.length, filtered: filteredItems.length, types: operationTypes });

    const activeItems = filteredItems.filter(isActive);
    const closedItems = filteredItems.filter(isClosed);
    debugPluginLog(this.pluginName, 'rendering groups:', { active: activeItems.length, closed: closedItems.length, total: filteredItems.length });

    // Update EO1/EO2/EO3 first, then mark data ready, then count (count dispatches update event)
    this.updateOperationsVariables(filteredItems);
    this.markPluginDataReady();
    this.updateOperationsCount(filteredItems.length);

    const renderGroup = (title, group) => {
      if (!group.length) return;
      const header = document.createElement('div');
      header.className = 'text-xs font-semibold text-gray-700 mt-3 mb-1 flex items-center gap-2';
      const iconClass = title === 'Active' ? 'text-green-500' : 'text-gray-400';
      header.innerHTML = `<i class="fas fa-circle ${iconClass}"></i> ${title} <span class="ml-1 text-[10px] text-gray-500">(${group.length})</span>`;
      list.appendChild(header);

      group.slice(0, maxItems).forEach(item => {
        const code = item?.code || '';
        const name = item?.name || '';
        const atype = item?.atype_display || '';
        const status = item?.status_display || '';
        const start = item?.start_date ? new Date(item.start_date).toISOString().slice(0,10) : '';
        const end = item?.end_date ? new Date(item.end_date).toISOString().slice(0,10) : '';
        const requested = item?.amount_requested;
        const funded = item?.amount_funded;
        const ccy = resolveCurrencyCode(item);
        const coverage = (typeof funded === 'number' && typeof requested === 'number' && requested > 0)
          ? Math.round((funded / requested) * 100)
          : null;
        const eventId = (typeof item?.event === 'number' || typeof item?.event === 'string') ? String(item.event) : '';
        const goUrl = eventId ? `https://go.ifrc.org/emergencies/${encodeURIComponent(eventId)}/details` : '';
        const linkEnabled = this.config?.enable_link !== false;

        // Helper function to escape HTML to prevent XSS
        const escapeHtml = (text) => {
          const div = document.createElement('div');
          div.textContent = text;
          return div.innerHTML;
        };

        const row = document.createElement('div');
        row.className = 'emops-item border border-gray-200 rounded-md p-3 bg-white';

        const nameEscaped = escapeHtml(name);
        const codeEscaped = escapeHtml(code);
        const atypeEscaped = escapeHtml(atype);
        const statusEscaped = escapeHtml(status);

        const nameHtml = (goUrl && linkEnabled)
          ? `<a href="${escapeHtml(goUrl)}" target="_blank" rel="noopener noreferrer" class="hover:underline text-gray-800 inline-flex items-center gap-1">${nameEscaped}<i class="fas fa-external-link-alt text-xs opacity-70"></i></a>`
          : nameEscaped;

        row.innerHTML = `
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div class="min-w-0">
              <div class="text-sm font-semibold text-gray-800 truncate">${nameHtml}</div>
              <div class="text-xs text-gray-600 mt-0.5">${codeEscaped} • ${atypeEscaped} • ${statusEscaped}</div>
              <div class="text-xs text-gray-500">${escapeHtml(start || '')} ${end ? '– ' + escapeHtml(end) : ''}</div>
            </div>
            <div class="flex flex-col items-end gap-1 text-right">
              ${showReq && typeof requested === 'number' ? `<span class="inline-flex items-center gap-1 text-xs text-gray-700"><i class="fas fa-hand-holding-usd text-emerald-600"></i> Requested: ${escapeHtml(currency(requested, ccy))}</span>` : ''}
              ${showFund && typeof funded === 'number' ? `<span class="inline-flex items-center gap-1 text-xs text-gray-700"><i class="fas fa-donate text-blue-600"></i> Funded: ${escapeHtml(currency(funded, ccy))}</span>` : ''}
              ${showCov && coverage !== null ? `<span class="inline-flex items-center gap-1 text-xs ${coverage > 70 ? 'text-green-600' : (coverage >= 21 ? 'text-amber-600' : 'text-red-600')}"><i class="fas fa-percentage"></i> Coverage: ${escapeHtml(String(coverage))}%</span>` : ''}
            </div>
          </div>
        `;
        list.appendChild(row);
      });
    };

    renderGroup('Active', activeItems);
    const showClosed = this.config?.show_closed_operations !== false;
    if (showClosed) {
      renderGroup('Closed', closedItems);
    }
  }

  _setOperationsCountAttributes(count) {
    if (!this.wrapper) return;
    const v = String(count);
    this.wrapper.setAttribute('data-operations-count', v);
    this.wrapper.dataset.operationsCount = v;
    const pluginContainer = this.wrapper.closest('.plugin-field-container');
    if (pluginContainer) {
      pluginContainer.setAttribute('data-operations-count', v);
      pluginContainer.dataset.operationsCount = v;
    }
    document.querySelectorAll(`[data-field-id="${this.fieldId}"]`).forEach((el) => {
      el.setAttribute('data-operations-count', v);
      el.dataset.operationsCount = v;
    });
  }

  updateOperationsCount(count, opts = {}) {
    const dispatch = (opts && Object.prototype.hasOwnProperty.call(opts, 'dispatch')) ? !!opts.dispatch : true;
    this._setOperationsCountAttributes(count);
    if (dispatch && this.wrapper) {
      this.wrapper.dispatchEvent(new CustomEvent('operationsCountUpdated', {
        detail: { fieldId: this.fieldId, count, pluginName: 'emergency_operations' },
        bubbles: true
      }));
    }
  }

  /**
   * Set EO1, EO2, EO3 data attributes from the filtered operations list (for section/item labels).
   * Values are "Name (CODE)" e.g. "Bangladesh - Population Movement (MDRBD018)"; empty string when no operation at that position.
   * Uses same item.name / item.code as renderList; sanitizes for safe use in data attributes and text.
   *
   * IMPORTANT: also publishes values synchronously to window.__ifrcPluginVariables so that
   * conditions.js isDepsReadyNow() reads the correct (non-stale) values when pluginDataReady fires.
   * If we only relied on the MutationObserver → plugin-label-variables.js chain, there is a race:
   * markPluginDataReady() fires synchronously after this call, triggering the conditions evaluator,
   * but the MutationObserver callback (which publishes to window.__ifrcPluginVariables) is async
   * and may not have run yet — causing relevance conditions to read stale empty values and
   * incorrectly hide sections. The direct synchronous publish here eliminates that race.
   */
  updateOperationsVariables(filteredItems) {
    if (!this.wrapper) return;
    const values = ['', '', ''];
    for (let i = 0; i < 3 && i < (filteredItems?.length || 0); i++) {
      const item = filteredItems[i];
      const name = (item && (item.name != null)) ? String(item.name).trim() : '';
      const code = (item && (item.code != null)) ? String(item.code).trim() : '';
      if (name) {
        values[i] = code ? name + ' (' + code + ')' : name;
      }
    }
    const setAttr = (el, key, val) => {
      const s = val == null ? '' : String(val);
      el.setAttribute(key, s);
      const camel = key.replace(/^data-/, '').replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      if (el.dataset) el.dataset[camel] = s;
    };
    ['data-eo1', 'data-eo2', 'data-eo3'].forEach((attr, idx) => {
      setAttr(this.wrapper, attr, values[idx]);
      const pluginContainer = this.wrapper.closest('.plugin-field-container');
      if (pluginContainer) setAttr(pluginContainer, attr, values[idx]);
      document.querySelectorAll(`[data-field-id="${this.fieldId}"]`).forEach((el) => setAttr(el, attr, values[idx]));
    });

    // Synchronously publish to window.__ifrcPluginVariables so the conditions evaluator
    // always sees current values when it reads them (avoids MutationObserver async lag).
    // Also add to window.__ifrcPluginVariablesReady so isDepsReadyNow() in conditions.js
    // can distinguish "published by a data-ready plugin" from a spurious empty-string value
    // that might have arrived before real data (belt-and-suspenders after the placeholder fix).
    try {
      window.__ifrcPluginVariables = window.__ifrcPluginVariables || {};
      window.__ifrcPluginVariables['EO1'] = values[0];
      window.__ifrcPluginVariables['EO2'] = values[1];
      window.__ifrcPluginVariables['EO3'] = values[2];
      // Readiness marker: signals conditions.js that these keys were published by a ready plugin.
      if (!(window.__ifrcPluginVariablesReady instanceof Set)) {
        window.__ifrcPluginVariablesReady = new Set();
      }
      window.__ifrcPluginVariablesReady.add('EO1');
      window.__ifrcPluginVariablesReady.add('EO2');
      window.__ifrcPluginVariablesReady.add('EO3');
      debugPluginLog(this.pluginName, 'updateOperationsVariables: published to window.__ifrcPluginVariables', { EO1: values[0], EO2: values[1], EO3: values[2] });
    } catch (_e) {
      // ignore — conditions will fall back to MutationObserver path
    }
  }
}

// Expose globally for plugin-field-loader generic initializer, if needed
window.EmergencyOperationsField = EmergencyOperationsField;
