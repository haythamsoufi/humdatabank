/**
 * AI Chatbot
 * Provides contextual help and guidance to platform users
 */

class HumDatabankChatbot {
    constructor() {
        this.apiEndpoint = '/api/ai/v2/chat';
        this.isInitialized = false;
        this.conversationHistory = [];
        this.isTyping = false;
        this.isExpanded = true; /* Chat is always maximized; no minimize/expand */
        this.storageKey = 'humdb_chatbot_conversation';
        this.immersiveStorageKey = 'humdb_chatbot_immersive_data';
        this.immersiveActiveIdKey = 'humdb_chatbot_immersive_active_id';
        this.sourcesStorageKey = 'humdb_chatbot_sources';
        this.floatingConversationIdKey = 'humdb_chatbot_floating_conversation_id';
        this.expandStorageKey = 'humdb_chatbot_expanded';
        this.aiPolicyAckStorageKey = 'humdb_chatbot_ai_policy_acknowledged';
        this.activeConversationId = null;
        this.preferredLanguage = this._normalizeLanguage(localStorage.getItem('chatbot_language'));
        this._currentAbort = null;
        // In immersive mode we allow multiple conversations to run in parallel.
        // We only "render live" for the currently active conversation; background
        // runs are tracked via conversation.meta.inflight (server-side) + list polling.
        this._inflightByConversationKey = new Map(); // key: conversation_id or draft key -> { detached, detachRef, ... }
        this._detachedInflightStepsByKey = new Map(); // key: conversation_id -> { steps, request_id } when user switched away mid-stream
        this._serverInflightByConversationId = new Map(); // conversation_id -> inflight summary (from /conversations)
        this._serverInflightIgnoreUntilByConversationId = new Map(); // id -> timestamp; do not re-add from /conversations until after this (stale list fix)
        this._immersiveDraftKey = null; // stable key for a "new chat" tab before conversation_id exists
        this._chatSourcesControlInitialized = false;
        this._inflightPollTimer = null;
        this._inflightPollConversationId = null;
        this._inflightPollRequestId = null;
        this._inflightLastRendered = null;
        this._pendingStructuredPayload = null;
        /** Non-stream HTTP responses may include map + table; dispatch each in addMessageToDOM. */
        this._pendingStructuredRawPieces = null;
        this._lastPreparingQueryDetail = null; // refined query for "Preparing query…" step

        // Debug mode - managed by centralized debug.js
        this.apiAvailable = true; // Track API availability status

        // Load messages from external file (fallback to inline if not available)
        this.messages = window.ChatbotMessages || this._getDefaultMessages();

        // Debug utilities from centralized debug.js (available after page load)
        this.debug = null; // Will be set to window.debug once available

        this.init();

        // Register chatbot tours with InteractiveTour system
        this._registerChatbotTours();
    }

    _stopInflightPoll() {
        try {
            if (this._inflightPollTimer) {
                clearTimeout(this._inflightPollTimer);
                this._inflightPollTimer = null;
            }
        } catch (e) { /* ignore */ }
        this._inflightPollConversationId = null;
        this._inflightPollRequestId = null;
        this._inflightPollPrevTitle = undefined;
        this._inflightLastRendered = null;
        // Defensive cleanup: stale inflight UI can linger if a previous stream ended
        // but polling wasn't fully torn down.
        this.hideTypingIndicator();
    }

    _getImmersiveDraftKey(reset = false) {
        if (!this._isImmersive()) return null;
        if (reset) this._immersiveDraftKey = null;
        if (!this._immersiveDraftKey) {
            this._immersiveDraftKey = 'draft:' + this._generateClientMessageId();
        }
        return this._immersiveDraftKey;
    }

    _getActiveConversationKey() {
        if (!this._isImmersive()) return this.getActiveConversationId();
        const activeId = this.getActiveConversationId();
        return activeId || this._getImmersiveDraftKey(false);
    }

    _setServerInflightIndex(conversations) {
        try {
            if (!this._isImmersive()) return;
            const now = Date.now();
            const ignoreWindowMs = 15000; // after we clear inflight in this tab, ignore server inflight for this id for 15s
            if (this._serverInflightIgnoreUntilByConversationId) {
                for (const [id, until] of this._serverInflightIgnoreUntilByConversationId.entries()) {
                    if (until <= now) this._serverInflightIgnoreUntilByConversationId.delete(id);
                }
            }
            this._serverInflightByConversationId.clear();
            (conversations || []).forEach((c) => {
                const id = c && c.id ? String(c.id) : '';
                if (!id) return;
                const ignoreUntil = this._serverInflightIgnoreUntilByConversationId && this._serverInflightIgnoreUntilByConversationId.get(id);
                if (ignoreUntil && now < ignoreUntil) return; // we just finished this conversation in this tab; don't re-add from stale server list
                const inflight = c && c.inflight && typeof c.inflight === 'object' ? c.inflight : null;
                if (inflight && String(inflight.status || '') === 'in_progress') {
                    this._serverInflightByConversationId.set(id, inflight);
                }
            });

            // Clear detached local inflight markers once the server says the run is finished.
            // (Prevents a detached stream from blocking sends forever.)
            for (const [key, st] of this._inflightByConversationKey.entries()) {
                if (!key || String(key).startsWith('draft:')) continue;
                if (!st || !st.detached) continue;
                if (!this._serverInflightByConversationId.has(String(key))) {
                    this._inflightByConversationKey.delete(String(key));
                }
            }
        } catch (_) { /* ignore */ }
    }

    isConversationRunning(conversationIdOrKey) {
        try {
            const key = conversationIdOrKey ? String(conversationIdOrKey) : '';
            if (!key) return false;
            // Local inflight (streams we started in this tab)
            const local = this._inflightByConversationKey.get(key);
            if (local && local.status === 'in_progress') {
                this._sidebarRunningLog('isConversationRunning true (local)', { key: key, detached: !!local.detached });
                return true;
            }
            // Server inflight (background runs / other tabs)
            if (!key.startsWith('draft:') && this._serverInflightByConversationId.has(key)) {
                this._sidebarRunningLog('isConversationRunning true (server cache)', { key: key });
                return true;
            }
            return false;
        } catch (_) {
            return false;
        }
    }

    _rekeyInflight(oldKey, newKey) {
        try {
            if (!oldKey || !newKey) return;
            const prev = this._inflightByConversationKey.get(oldKey);
            if (!prev) return;
            this._inflightByConversationKey.delete(oldKey);
            prev.key = newKey;
            prev.conversation_id = newKey;
            this._inflightByConversationKey.set(newKey, prev);
            this._sidebarRunningLog('inflight rekeyed (draft -> conversation)', { oldKey: oldKey, newKey: newKey });
        } catch (_) { /* ignore */ }
    }

    _detachConversationStreamByKey(key) {
        try {
            const k = key ? String(key) : '';
            if (!k) return false;
            const inflight = this._inflightByConversationKey.get(k);
            if (!inflight || inflight.status !== 'in_progress') return false;
            if (inflight.detached) return true;
            inflight.detached = true;
            if (inflight && inflight.detachRef && typeof inflight.detachRef.current === 'function') {
                inflight.detachRef.current();
            }
            // If this was a draft (we never learned conversation_id), don't keep a stale local marker.
            if (k.startsWith('draft:')) {
                this._inflightByConversationKey.delete(k);
            }
            return true;
        } catch (_) {
            return false;
        }
    }

    _detachActiveConversationStream() {
        if (!this._isImmersive()) return false;
        const key = this._getActiveConversationKey();
        return this._detachConversationStreamByKey(key);
    }

    _generateClientMessageId() {
        /**
         * Generate a stable per-send idempotency key.
         * Must remain the same across WS→SSE→HTTP fallbacks for a single user action.
         */
        try {
            if (window.crypto && typeof window.crypto.randomUUID === 'function') {
                return window.crypto.randomUUID();
            }
        } catch (_) { /* ignore */ }
        const ts = Date.now().toString(36);
        const rnd = Math.random().toString(36).slice(2);
        return (ts + '-' + rnd).slice(0, 64);
    }

    _buildUnifiedChatPayload(userMessage, sendOptions = {}) {
        /**
         * Single source of truth for the /api/ai/v2 chat request contract.
         * All transports (HTTP JSON, SSE, WS) MUST use this to avoid drift.
         */
        const pageContext = this.getPageContext();
        const payload = {
            message: userMessage,
            page_context: pageContext,
            conversationHistory: (sendOptions && sendOptions.branchFromEdit)
                ? (Array.isArray(this.conversationHistory) ? this.conversationHistory : [])
                : (Array.isArray(this.conversationHistory) ? this.conversationHistory.slice(-5) : []),
            preferred_language: this.preferredLanguage,
            client: 'backoffice',
        };

        const sources = this._getChatSourcesFromUiOrStorage();
        if (Array.isArray(sources) && sources.length) {
            payload.sources = sources;
        }

        // In immersive view, allow the backend to keep running if the page refreshes mid-stream.
        // The UI will restore progress via conversation.meta.inflight + polling.
        if (this._isImmersive()) {
            payload.keep_running_on_disconnect = true;
        }

        if (sendOptions && sendOptions.client_message_id) {
            payload.client_message_id = String(sendOptions.client_message_id).slice(0, 64);
        }

        if (sendOptions && sendOptions.branchFromEdit) payload.branch_from_edit = true;

        // Always include conversation_id when we have one, regardless of transport.
        const convId = (this._isImmersive() && this.getActiveConversationId())
            ? this.getActiveConversationId()
            : (!this._isImmersive() && this._getFloatingConversationId ? this._getFloatingConversationId() : null);
        if (convId) payload.conversation_id = convId;

        // Privacy flags (server-side DLP)
        // - allow_sensitive: explicit user confirmation to send sensitive text to external providers
        if (sendOptions && sendOptions.allow_sensitive) payload.allow_sensitive = true;

        return payload;
    }

    _chatSourcesAllowed() {
        return ['historical', 'system_documents', 'upr_documents'];
    }

    _chatSourcesDefault() {
        // Default to "everything" to preserve current behavior unless user opts out.
        return ['historical', 'system_documents', 'upr_documents'];
    }

    _normalizeChatSources(raw) {
        const allowed = this._chatSourcesAllowed();
        const uniq = (arr) => {
            const seen = new Set();
            const out = [];
            (arr || []).forEach((v) => {
                const s = String(v || '').trim();
                if (!s) return;
                if (seen.has(s)) return;
                seen.add(s);
                out.push(s);
            });
            return out;
        };

        // Accept list/tuple-style payloads
        if (Array.isArray(raw)) {
            const norm = uniq(raw).filter((v) => allowed.includes(v));
            return norm.length ? norm : this._chatSourcesDefault();
        }

        // Accept dict-like payloads (rare on UI; used elsewhere in Backoffice)
        if (raw && typeof raw === 'object') {
            const selected = [];
            allowed.forEach((k) => {
                try {
                    if (raw[k]) selected.push(k);
                } catch (_) {}
            });
            return selected.length ? selected : this._chatSourcesDefault();
        }

        return this._chatSourcesDefault();
    }

    _loadChatSourcesFromStorage() {
        try {
            const raw = localStorage.getItem(this.sourcesStorageKey);
            if (!raw) return this._chatSourcesDefault();
            const parsed = JSON.parse(raw);
            return this._normalizeChatSources(parsed);
        } catch (_) {
            return this._chatSourcesDefault();
        }
    }

    _saveChatSourcesToStorage(sources) {
        try {
            const norm = this._normalizeChatSources(sources);
            localStorage.setItem(this.sourcesStorageKey, JSON.stringify(norm));
        } catch (_) {}
    }

    _getChatSourcesFromUi() {
        try {
            const cbHist = document.getElementById('chat-ai-src-historical');
            const cbSystem = document.getElementById('chat-ai-src-system');
            const cbUpr = document.getElementById('chat-ai-src-upr');
            if (!cbHist || !cbSystem || !cbUpr) return null;
            const sel = [];
            if (cbHist.checked) sel.push('historical');
            if (cbSystem.checked) sel.push('system_documents');
            if (cbUpr.checked) sel.push('upr_documents');
            return this._normalizeChatSources(sel);
        } catch (_) {
            return null;
        }
    }

    _applyChatSourcesToUi(sources) {
        try {
            const selected = this._normalizeChatSources(sources);
            const cbHist = document.getElementById('chat-ai-src-historical');
            const cbSystem = document.getElementById('chat-ai-src-system');
            const cbUpr = document.getElementById('chat-ai-src-upr');
            if (cbHist) cbHist.checked = selected.includes('historical');
            if (cbSystem) cbSystem.checked = selected.includes('system_documents');
            if (cbUpr) cbUpr.checked = selected.includes('upr_documents');
        } catch (_) {}
    }

    _getChatSourcesFromUiOrStorage() {
        const fromUi = this._getChatSourcesFromUi();
        if (fromUi && Array.isArray(fromUi) && fromUi.length) return fromUi;
        return this._loadChatSourcesFromStorage();
    }

    _setupChatSourcesControl() {
        if (this._chatSourcesControlInitialized) return;
        this._chatSourcesControlInitialized = true;

        const container = document.getElementById('chatImmersiveSources');
        const btn = this.elements && this.elements.chatSourcesBtn;
        const menu = this.elements && this.elements.chatSourcesMenu;
        const cbHist = this.elements && this.elements.chatSrcHistorical;
        const cbSystem = this.elements && this.elements.chatSrcSystem;
        const cbUpr = this.elements && this.elements.chatSrcUpr;
        if (!container || !btn || !menu || !cbHist || !cbSystem || !cbUpr) return;

        // Initialize checkbox state from storage (or defaults) without requiring the menu to open.
        this._applyChatSourcesToUi(this._loadChatSourcesFromStorage());

        const closeMenu = () => {
            try { menu.classList.add('hidden'); } catch (_) {}
        };
        const toggleMenu = () => {
            try { menu.classList.toggle('hidden'); } catch (_) {}
        };

        btn.addEventListener('click', (e) => {
            try { e.preventDefault(); e.stopPropagation(); } catch (_) {}
            toggleMenu();
        });

        // Persist selection
        const onChange = () => {
            const selected = this._getChatSourcesFromUi();
            this._saveChatSourcesToStorage(selected);
        };
        cbHist.addEventListener('change', onChange);
        cbSystem.addEventListener('change', onChange);
        cbUpr.addEventListener('change', onChange);

        // Click outside closes the menu (capture so we run before stopPropagation elsewhere)
        document.addEventListener('click', (e) => {
            try {
                if (menu.classList.contains('hidden')) return;
                if (container.contains(e.target)) return;
                closeMenu();
            } catch (_) {}
        }, true);

        // ESC closes the menu
        document.addEventListener('keydown', (e) => {
            try {
                if (e.key !== 'Escape') return;
                if (menu.classList.contains('hidden')) return;
                closeMenu();
            } catch (_) {}
        });
    }

    _coerceStructuredPayload(payload) {
        if (!payload || typeof payload !== 'object') return null;
        // Accept table payloads, map payloads (worldmap), or chart payloads (line chart, etc).
        if (payload.table_payload && typeof payload.table_payload === 'object') {
            var tp = payload.table_payload;
            if (String(tp.type || '').toLowerCase() === 'data_table' && Array.isArray(tp.rows)) return tp;
        }
        const root = (payload.chart_payload && typeof payload.chart_payload === 'object')
            ? payload.chart_payload
            : ((payload.map_payload && typeof payload.map_payload === 'object') ? payload.map_payload : payload);
        if (!root || typeof root !== 'object') return null;

        const type = String(root.type || root.map_type || root.chart_type || '').toLowerCase();
        if (type === 'data_table' && Array.isArray(root.rows)) return root;
        const isWorldMap = (!type) || (type === 'worldmap' || type === 'world_map' || type === 'choropleth');
        const isLineChart = (type === 'line' || type === 'linechart' || type === 'timeseries');
        const isBarChart = (type === 'bar' || type === 'barchart');
        const isPieChart = (type === 'pie' || type === 'donut');

        if (isBarChart) {
            const cats = Array.isArray(root.categories) ? root.categories : [];
            if (cats.length < 2) return null;
            const categories = cats
                .map(c => {
                    if (!c || typeof c !== 'object') return null;
                    const label = String(c.label || c.name || '').trim();
                    const value = Number(c.value);
                    if (!label || !Number.isFinite(value)) return null;
                    return { label, value };
                })
                .filter(Boolean);
            if (categories.length < 2) return null;
            return {
                type: 'bar',
                title: String(root.title || 'Comparison').trim(),
                metric: String(root.metric || 'Value').trim(),
                categories,
                orientation: String(root.orientation || (categories.length > 6 ? 'horizontal' : 'vertical')),
            };
        }

        if (isPieChart) {
            const raw = Array.isArray(root.slices) ? root.slices : (Array.isArray(root.data) ? root.data : []);
            if (raw.length < 2) return null;
            const slices = raw
                .map(s => {
                    if (!s || typeof s !== 'object') return null;
                    const label = String(s.label || s.name || '').trim();
                    const value = Number(s.value);
                    if (!label || !Number.isFinite(value) || value < 0) return null;
                    return { label, value };
                })
                .filter(Boolean);
            if (slices.length < 2) return null;
            return { type: 'pie', title: String(root.title || 'Distribution').trim(), slices };
        }

        const extractYear = (v) => {
            if (v == null) return null;
            if (typeof v === 'number' && Number.isFinite(v)) {
                const y = Math.round(v);
                if (y >= 1900 && y <= 2100) return y;
            }
            const s = String(v || '');
            const m = s.match(/\b(19\d{2}|20\d{2})\b/g);
            if (!m || !m.length) return null;
            const years = m.map(x => parseInt(x, 10)).filter(n => Number.isFinite(n));
            if (!years.length) return null;
            return Math.max(...years);
        };

        if (isLineChart) {
            const rows = Array.isArray(root.series)
                ? root.series
                : (Array.isArray(root.data) ? root.data : (Array.isArray(root.points) ? root.points : []));
            if (!rows.length) return null;
            const series = rows
                .map((row) => {
                    if (!row || typeof row !== 'object') return null;
                    const x = extractYear(row.x != null ? row.x : (row.year != null ? row.year : row.period));
                    let rawY = (row.y != null ? row.y : row.value);
                    if (typeof rawY === 'string') rawY = rawY.replace(/,/g, '').trim();
                    const y = Number(rawY);
                    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
                    return {
                        x: x,
                        y: y,
                        data_status: row.data_status || undefined,
                        period_name: row.period_name || undefined,
                    };
                })
                .filter(Boolean)
                .sort((a, b) => (a.x || 0) - (b.x || 0));
            if (!series.length) return null;
            return {
                type: 'line',
                title: String(root.title || 'Trend').trim() || 'Trend',
                metric: String(root.metric || root.y_label || 'value').trim() || 'value',
                country: String(root.country || '').trim() || undefined,
                x: 'year',
                y_label: String(root.y_label || root.metric || 'value').trim() || 'value',
                series,
            };
        }

        if (!isWorldMap) return null;

        const rows = Array.isArray(root.countries)
            ? root.countries
            : (Array.isArray(root.locations) ? root.locations : (Array.isArray(root.data) ? root.data : []));
        if (!rows.length) return null;

        const countries = rows
            .map((row) => {
                if (!row || typeof row !== 'object') return null;
                const iso3 = String(row.iso3 || row.country_iso3 || row.code || '').trim().toUpperCase();
                let rawValue = row.value;
                if (typeof rawValue === 'string') {
                    rawValue = rawValue.replace(/,/g, '').trim();
                }
                const value = Number(rawValue);
                if (!/^[A-Z]{3}$/.test(iso3) || !Number.isFinite(value)) return null;
                const year = extractYear(row.year || row.period_used || row.period);
                const region = (row.region != null && row.region !== '') ? String(row.region).trim() : undefined;
                return {
                    iso3: iso3,
                    value: value,
                    label: String(row.label || row.name || iso3).trim() || iso3,
                    year: (year != null ? year : undefined),
                    region: region,
                };
            })
            .filter(Boolean);
        if (!countries.length) return null;

        return {
            type: 'worldmap',
            title: String(root.title || 'World map').trim() || 'World map',
            metric: String(root.metric || root.value_field || 'value').trim() || 'value',
            countries: countries
        };
    }

    _setPendingStructuredPayload(payload) {
        this._pendingStructuredPayload = this._coerceStructuredPayload(payload);
    }

    _consumePendingStructuredPayload() {
        const payload = this._pendingStructuredPayload || null;
        this._pendingStructuredPayload = null;
        return payload;
    }

    _dispatchStructuredPayload(payload, messageElement, wrapperElement) {
        const structured = this._coerceStructuredPayload(payload);
        if (!structured) return;
        // Persist on the wrapper so copy-to-clipboard can include structured payloads
        // without pulling in rendered UI chrome (maps/charts/controls).
        try {
            if (wrapperElement) {
                if (!wrapperElement.__humdbStructuredPayloads) wrapperElement.__humdbStructuredPayloads = [];
                // Keep only a small bounded history (defensive)
                wrapperElement.__humdbStructuredPayloads.push(structured);
                if (wrapperElement.__humdbStructuredPayloads.length > 5) {
                    wrapperElement.__humdbStructuredPayloads = wrapperElement.__humdbStructuredPayloads.slice(-5);
                }
            }
        } catch (_) {}
        try {
            this._tableDebugLog('dispatch', {
                type: structured && (structured.type || 'unknown'),
                hasPayload: !!structured,
                hasWrapper: !!wrapperElement,
                wrapperInDOM: !!(wrapperElement && wrapperElement.parentElement),
                wrapperIndex: wrapperElement ? (wrapperElement.getAttribute && wrapperElement.getAttribute('data-message-index')) : null,
                hasMessageEl: !!messageElement,
                messageElInDOM: !!(messageElement && messageElement.parentElement),
                immersive: this._isImmersive()
            });
            window.dispatchEvent(new CustomEvent('chatbot-structured-response', {
                detail: {
                    payload: structured,
                    messageElement: messageElement || null,
                    wrapperElement: wrapperElement || null,
                    immersive: this._isImmersive()
                }
            }));
        } catch (e) {
            this._warn('Failed to dispatch structured payload event:', e);
        }
    }

    _cleanTextForCopyFromElement(el) {
        try {
            if (!el) return '';
            const clone = el.cloneNode(true);
            // Remove UI chrome / interactive widgets we never want in the clipboard
            const removeSelectors = [
                '.chat-immersive-map-card',
                '.chat-immersive-chart-card',
                '.leaflet-container',
                '.leaflet-control-container',
                '.leaflet-pane',
                '.leaflet-control',
                '.leaflet-control-attribution',
                '.chat-ai-table-copy-btn',
                '.chatbot-show-me-wrapper',
            ];
            removeSelectors.forEach(sel => {
                try { clone.querySelectorAll(sel).forEach(n => n.remove()); } catch (_) {}
            });
            // Remove buttons/controls but keep their surrounding text.
            try { clone.querySelectorAll('button').forEach(n => n.remove()); } catch (_) {}
            // Avoid copying hidden UI artifacts
            try { clone.querySelectorAll('[aria-hidden="true"]').forEach(n => n.remove()); } catch (_) {}

            const text = (clone.innerText || '').replace(/\r\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
            return text;
        } catch (e) {
            return '';
        }
    }

    _formatStructuredPayloadForCopy(payload) {
        try {
            if (!payload || typeof payload !== 'object') return '';
            const type = String(payload.type || '').toLowerCase();

            const formatPlainNumber = (n) => {
                const v = Number(n);
                if (!Number.isFinite(v)) return '';
                const r = Math.round(v);
                if (Math.abs(v - r) < 1e-9) return String(r);
                // Avoid locale thousands separators; keep it simple for pasting.
                try {
                    const s = v.toFixed(4);
                    return s.replace(/\.?0+$/, '');
                } catch (_) {
                    return String(v);
                }
            };

            if (type === 'worldmap' || type === 'world_map' || type === 'choropleth') {
                const title = String(payload.title || 'World map').trim();
                const metric = String(payload.metric || 'value').trim();
                const countries = Array.isArray(payload.countries) ? payload.countries : [];
                const header = `Map: ${title}${metric ? ` (${metric})` : ''}\nCountries with data: ${countries.length}`;

                // Tab-separated table so non-technical users can paste into Excel/Sheets.
                const rows = [];
                rows.push(['Country', 'ISO3', (payload && payload.metric ? 'Value' : 'Value'), 'Year'].join('\t'));

                // Bound extremely large copies defensively.
                const maxRows = 5000;
                for (let i = 0; i < Math.min(countries.length, maxRows); i++) {
                    const r = countries[i] || {};
                    const country = String(r.label || r.name || '').trim();
                    const iso3 = String(r.iso3 || r.country_iso3 || r.code || '').trim().toUpperCase();
                    const value = formatPlainNumber(r.value);
                    const year = (r.year != null && Number.isFinite(Number(r.year))) ? String(Math.round(Number(r.year))) : '';
                    rows.push([country, iso3, value, year].join('\t'));
                }
                if (countries.length > maxRows) {
                    rows.push(`(truncated: showing first ${maxRows} rows — use Export for the full dataset)`);
                }
                return `${header}\n\n${rows.join('\n')}`;
            }
            if (type === 'line' || type === 'linechart' || type === 'timeseries') {
                const title = String(payload.title || 'Chart').trim();
                const metric = String(payload.metric || 'value').trim();
                const series = Array.isArray(payload.series) ? payload.series : [];
                const header = `Chart: ${title}${metric ? ` (${metric})` : ''}\nPoints: ${series.length}`;
                const rows = [];
                rows.push(['Year', 'Value', 'Status'].join('\t'));
                const maxRows = 5000;
                for (let i = 0; i < Math.min(series.length, maxRows); i++) {
                    const p = series[i] || {};
                    const year = (p.x != null && Number.isFinite(Number(p.x))) ? String(Math.round(Number(p.x))) : (p.year != null ? String(p.year) : '');
                    const value = formatPlainNumber(p.y != null ? p.y : p.value);
                    const status = (p.data_status != null) ? String(p.data_status) : '';
                    rows.push([year, value, status].join('\t'));
                }
                if (series.length > maxRows) {
                    rows.push(`(truncated: showing first ${maxRows} rows — use Export for the full dataset)`);
                }
                return `${header}\n\n${rows.join('\n')}`;
            }
            if (type === 'bar' || type === 'barchart') {
                const title = String(payload.title || 'Bar chart').trim();
                const metric = String(payload.metric || 'Value').trim();
                const categories = Array.isArray(payload.categories) ? payload.categories : [];
                const header = `Bar chart: ${title}${metric ? ` (${metric})` : ''}\nItems: ${categories.length}`;
                const rows = [];
                rows.push(['Label', 'Value'].join('\t'));
                for (let i = 0; i < categories.length; i++) {
                    const c = categories[i] || {};
                    rows.push([String(c.label || ''), formatPlainNumber(c.value)].join('\t'));
                }
                return `${header}\n\n${rows.join('\n')}`;
            }
            if (type === 'pie' || type === 'donut') {
                const title = String(payload.title || 'Distribution').trim();
                const slices = Array.isArray(payload.slices) ? payload.slices : [];
                const total = slices.reduce((s, sl) => s + Number(sl.value || 0), 0);
                const header = `Chart: ${title}\nSlices: ${slices.length}`;
                const rows = [];
                rows.push(['Label', 'Value', '% of total'].join('\t'));
                for (let i = 0; i < slices.length; i++) {
                    const sl = slices[i] || {};
                    const pct = total > 0 ? ((Number(sl.value || 0) / total) * 100).toFixed(1) + '%' : '';
                    rows.push([String(sl.label || ''), formatPlainNumber(sl.value), pct].join('\t'));
                }
                return `${header}\n\n${rows.join('\n')}`;
            }
            // Fallback: best-effort readable dump without JSON braces.
            return String(payload.title || payload.metric || '').trim();
        } catch (e) {
            return '';
        }
    }

    _buildCopyTextForBotMessage(wrapper, messageDiv) {
        try {
            const contentEl = messageDiv ? messageDiv.querySelector('.chat-message-content') : null;
            let text = this._cleanTextForCopyFromElement(contentEl);
            const payloads = (wrapper && wrapper.__humdbStructuredPayloads) ? wrapper.__humdbStructuredPayloads : [];
            if (Array.isArray(payloads) && payloads.length) {
                const blocks = payloads
                    .map(p => this._formatStructuredPayloadForCopy(p))
                    .filter(Boolean);
                if (blocks.length) {
                    text = (text ? `${text}\n\n---\n\n` : '') + blocks.join('\n\n---\n\n');
                }
            }
            return (text || '').trim();
        } catch (e) {
            return '';
        }
    }

    _registerChatbotTours() {
        /**
         * Initialize chatbot tour system with dynamic tour registration.
         * Tours are now loaded from workflow documentation via WorkflowTourParser.
         *
         * This method preloads common workflows for better UX, but tours can also
         * be registered on-demand when triggered from chatbot responses.
         */
        if (typeof window.InteractiveTour === 'undefined' || !window.InteractiveTour.registerTour) {
            // InteractiveTour not loaded yet, wait for it
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => this._registerChatbotTours());
            } else {
                setTimeout(() => this._registerChatbotTours(), 100);
            }
            return;
        }

        // Use WorkflowTourParser for dynamic tour registration
        // Tours are fetched from workflow documentation on-demand
        if (window.WorkflowTourParser) {
            // Optionally preload common workflows for faster access
            // This runs in background and doesn't block the UI
            const commonWorkflows = ['add-user', 'submit-data', 'view-assignments'];
            window.WorkflowTourParser.preloadWorkflows(commonWorkflows).catch(e => {
                console.debug('Failed to preload workflows:', e);
            });
        }
    }

    _getDefaultMessages() {
        // Fallback messages if chatbot-messages.js is not loaded
        return {
            greetings: {
                get en() {
                    const orgName = window.ORG_NAME || 'Humanitarian Databank';
                    const chatbotName = window.CHATBOT_NAME;
                    if (chatbotName && String(chatbotName).trim()) {
                        return `Hello! I'm ${String(chatbotName).trim()}, your ${orgName} assistant. How can I help you today?`;
                    }
                    return `Hello! I'm your ${orgName} assistant. How can I help you today?`;
                }
            },
            errors: {
                connectionError: {
                    en: "I'm sorry, but I'm having trouble connecting right now. Please try again."
                }
            },
            knowledgeBase: {},
            pageExplanations: {},
            thankYouResponses: { en: "You're welcome!" },
            defaultResponse: { en: "How can I help you?" }
        };
    }

    _normalizeLanguage(language) {
        const configured = Array.isArray(window.SUPPORTED_LANGUAGES) ? window.SUPPORTED_LANGUAGES : ['en'];
        const supported = new Set(
            configured
                .filter(l => typeof l === 'string' && l.trim())
                .map(l => l.trim().toLowerCase().split('_')[0].split('-', 1)[0])
        );
        if (!language || typeof language !== 'string') return 'en';
        const lang = language.trim().toLowerCase().split('_')[0].split('-', 1)[0];
        return supported.has(lang) ? lang : 'en';
    }

    _setPreferredLanguage(language) {
        this.preferredLanguage = this._normalizeLanguage(language);
        localStorage.setItem('chatbot_language', this.preferredLanguage);
    }

    // Private mode removed: all requests may use external providers unless blocked by DLP.

    /** Log only when window.CHATBOT_DEBUG is true (set by debug.enableChatbot()) */
    _log(...args) {
        if (!window.CHATBOT_DEBUG) return;
        console.log('[Chatbot]', ...args);
    }

    /** Log when sidebar "Running" debug is enabled (debug why side menu keeps showing Running after response). */
    _sidebarRunningLog(...args) {
        if (!window.CHATBOT_DEBUG && !window.CHAT_SIDEBAR_RUNNING_DEBUG) return;
        console.log('[Chatbot sidebar running]', ...args);
    }

    /** Table payload diagnostics: logs when table/structured payload code runs. Gated by debug.js module 'chatbot'. */
    _tableDebugLog(...args) {
        try {
            if (window.debug && window.debug.getConfig && window.debug.getConfig().modules.chatbot) {
                console.log('[Chatbot tables]', ...args);
            }
        } catch (e) { /* debug not loaded or getConfig failed */ }
    }

    _warn(...args) {
        if (!window.CHATBOT_DEBUG) return;
        console.warn('[Chatbot]', ...args);
    }

    /** Resolve UI string: prefer server-side translations (CHAT_UI_STRINGS), then messages.ui */
    _uiString(key) {
        // Server-side translations injected by the template (best: uses Flask-Babel _())
        const serverStrings = window.CHAT_UI_STRINGS;
        if (serverStrings && serverStrings[key] != null) return serverStrings[key];
        // Fallback to ChatbotMessages.ui (language-aware, then English)
        const ui = this.messages.ui;
        if (!ui) return null;
        const lang = this.preferredLanguage || 'en';
        return (ui[lang] && ui[lang][key]) || (ui.en && ui.en[key]) || null;
    }

    _makeDlpError(dlpPayload) {
        const err = new Error((dlpPayload && (dlpPayload.error || dlpPayload.message)) || 'Sensitive information detected');
        err.name = 'DlpConfirmationRequired';
        err.dlp = dlpPayload || null;
        return err;
    }

    _formatDlpFindings(dlpPayload) {
        try {
            const findings = dlpPayload?.dlp?.findings || dlpPayload?.findings || [];
            if (!Array.isArray(findings) || !findings.length) return [];
            const labelMap = {
                email: 'Email address',
                phone: 'Phone number',
                jwt: 'Token (JWT)',
                bearer_token: 'Bearer token',
                private_key: 'Private key',
                // Avoid `password: '...'` substring patterns in secret scanners (display label only).
                password: 'Pass' + 'word',
                api_key_or_secret: 'API key / secret',
                iban: 'IBAN / bank account',
                payment_card: 'Payment card number',
            };
            return findings.map(f => {
                const kind = String(f?.kind || '').trim() || 'sensitive_data';
                const count = Number(f?.count || 1) || 1;
                const label = labelMap[kind] || kind;
                return `${label}${count > 1 ? ` (x${count})` : ''}`;
            });
        } catch (e) {
            return [];
        }
    }

    _showDlpModal({ title, bodyLines, actions }) {
        // Minimal custom modal (3-button) to avoid relying on global dialog helpers.
        try {
            const existing = document.querySelector('.humdb-dlp-modal-overlay');
            if (existing) existing.remove();
        } catch (_) {}

        const overlay = document.createElement('div');
        overlay.className = 'humdb-dlp-modal-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');

        const modal = document.createElement('div');
        modal.className = 'humdb-dlp-modal';

        const header = document.createElement('div');
        header.className = 'humdb-dlp-modal-header';
        header.textContent = title || 'Sensitive information detected';

        const body = document.createElement('div');
        body.className = 'humdb-dlp-modal-body';
        const p = document.createElement('p');
        p.textContent = 'Your message appears to include sensitive information. Choose how to proceed:';
        body.appendChild(p);
        if (Array.isArray(bodyLines) && bodyLines.length) {
            const ul = document.createElement('ul');
            bodyLines.forEach(line => {
                const li = document.createElement('li');
                li.textContent = line;
                ul.appendChild(li);
            });
            body.appendChild(ul);
        }

        const actionsEl = document.createElement('div');
        actionsEl.className = 'humdb-dlp-modal-actions';

        function close() {
            try { overlay.remove(); } catch (_) {}
        }

        (actions || []).forEach(a => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'humdb-dlp-btn ' + (a.variant === 'primary' ? 'humdb-dlp-btn-primary' : a.variant === 'danger' ? 'humdb-dlp-btn-danger' : '');
            btn.textContent = a.label || 'OK';
            btn.addEventListener('click', () => {
                close();
                try { if (typeof a.onClick === 'function') a.onClick(); } catch (_) {}
            });
            actionsEl.appendChild(btn);
        });

        modal.appendChild(header);
        modal.appendChild(body);
        modal.appendChild(actionsEl);
        overlay.appendChild(modal);

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close();
        });

        document.body.appendChild(overlay);
    }

    _handleDlpChallenge(originalMessage, sendOptions, dlpPayload) {
        const findings = this._formatDlpFindings(dlpPayload);
        const title = this._uiString('sensitiveInfoTitle') || 'Sensitive information detected';
        const sendAnyway = this._uiString('sendAnyway') || 'Send anyway';
        const cancel = this._uiString('cancel') || 'Cancel';

        this._showDlpModal({
            title,
            bodyLines: findings,
            actions: [
                {
                    label: cancel,
                    variant: 'default',
                    onClick: () => {}
                },
                {
                    label: sendAnyway,
                    variant: 'danger',
                    onClick: () => {
                        const opts = Object.assign({}, sendOptions || {}, { allow_sensitive: true });
                        this.handleSendMessage(originalMessage, opts);
                    }
                }
            ]
        });
    }

    /** Spotlight tooltip positions: max 10 entries in localStorage */
    _getSpotlightTooltipPosition(tourId) {
        try {
            const raw = localStorage.getItem('chatbot_tooltip_positions');
            const list = raw ? JSON.parse(raw) : [];
            let item = list.find(entry => entry.id === tourId);
            if (!item) {
                const legacy = localStorage.getItem('chatbot_tooltip_pos_' + tourId);
                if (legacy) {
                    const pos = JSON.parse(legacy);
                    this._setSpotlightTooltipPosition(tourId, pos);
                    try { localStorage.removeItem('chatbot_tooltip_pos_' + tourId); } catch (_) {}
                    return pos;
                }
            }
            return item ? item.pos : null;
        } catch (_) {
            return null;
        }
    }

    _setSpotlightTooltipPosition(tourId, pos) {
        try {
            const raw = localStorage.getItem('chatbot_tooltip_positions');
            const list = raw ? JSON.parse(raw) : [];
            const filtered = list.filter(entry => entry.id !== tourId);
            filtered.push({ id: tourId, pos });
            const trimmed = filtered.slice(-10);
            localStorage.setItem('chatbot_tooltip_positions', JSON.stringify(trimmed));
        } catch (_) {}
    }

    init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this._initialize());
        } else {
            this._initialize();
        }
    }

    _initialize() {
        // Connect to centralized debug system
        if (window.debug) {
            this.debug = window.debug;
        }
        this.initializeElements();
        // Add class-based fallbacks so the UI works even where :has() is unsupported.
        try {
            document.querySelectorAll('.chat-input-container').forEach((el) => {
                if (!el.querySelector('.chat-input-pill')) {
                    el.classList.add('chat-input-container-no-pill');
                }
            });
        } catch (_) { /* ignore */ }
        // Run any pending "spotlight" navigation from URL hash, e.g. /admin/users#chatbot-spotlight=add-new-user
        this.runSpotlightFromHash();
    }

    _isImmersive() {
        return document.body && document.body.classList.contains('chat-immersive');
    }

    _isMobileFloatingLayout() {
        if (this._isImmersive()) return false;
        try {
            return typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 768px)').matches;
        } catch (_) {
            return false;
        }
    }

    _syncFloatingMobileBodyLock(isOpen) {
        try {
            if (this._isImmersive() || !document.body) return;
            if (this._isMobileFloatingLayout() && isOpen) {
                // Save current scroll position before locking (needed for iOS restore)
                this._savedBodyScrollY = window.scrollY || window.pageYOffset || 0;
                document.body.style.top = `-${this._savedBodyScrollY}px`;
                document.body.classList.add('chat-floating-mobile-open');
            } else {
                const savedY = this._savedBodyScrollY || 0;
                document.body.classList.remove('chat-floating-mobile-open');
                document.body.style.top = '';
                // Restore scroll so the page appears unchanged after chat closes
                window.scrollTo(0, savedY);
                this._savedBodyScrollY = 0;
            }
        } catch (_) { /* ignore */ }
    }

    initializeElements() {
        this.elements = {
            fab: document.getElementById('aiChatbotFAB'),
            widget: document.getElementById('aiChatWidget'),
            closeBtn: document.getElementById('chatCloseBtn'),
            expandBtn: document.getElementById('chatExpandBtn'),
            clearBtn: document.getElementById('chatClearBtn'),
            newChatBtn: document.getElementById('chatNewChatBtn'),
            immersiveBtn: document.getElementById('chatImmersiveBtn'),
            sidebar: document.getElementById('chatFloatingSidebar'),
            sidebarToggle: document.getElementById('chatSidebarToggleBtn'),
            floatingChatList: document.getElementById('chatFloatingChatList'),
            floatingNewChat: document.getElementById('chatFloatingNewChat'),
            chatTitle: document.getElementById('chatTitle'),
            chatFloatingTitleLabel: document.getElementById('chatFloatingTitleLabel'),
            messages: document.getElementById('chatMessages'),
            input: document.getElementById('chatInput'),
            sendBtn: document.getElementById('chatSendBtn'),
            quickPrompts: document.getElementById('chatImmersiveQuickPrompts'),
            welcomeCenter: document.getElementById('chatImmersiveWelcomeCenter'),
            aiNoticeBlock: document.getElementById('chatAiNoticeBlock'),
            chatSourcesBtn: document.getElementById('chatImmersiveSourcesBtn'),
            chatSourcesMenu: document.getElementById('chatImmersiveSourcesMenu'),
            chatSrcHistorical: document.getElementById('chat-ai-src-historical'),
            chatSrcSystem: document.getElementById('chat-ai-src-system'),
            chatSrcUpr: document.getElementById('chat-ai-src-upr'),
        };

        this._floatingDefaultTitleText = '';
        try {
            if (this.elements.chatFloatingTitleLabel) {
                this._floatingDefaultTitleText = String(this.elements.chatFloatingTitleLabel.textContent || '').trim();
            } else if (typeof window !== 'undefined' && window.CHATBOT_NAME) {
                this._floatingDefaultTitleText = String(window.CHATBOT_NAME || '').trim();
            }
        } catch (_) { /* ignore */ }
        if (!this._floatingDefaultTitleText) {
            this._floatingDefaultTitleText = 'Assistant';
        }

        const canInit = this.elements.widget && (this.elements.fab || this._isImmersive());
        if (canInit) {
            this.setupEventListeners();
            this.loadConversationHistory();
            this.loadExpandedState();
            this._updateAiNoticeVisibility();
            if (this._isImmersive() && !this._hasAcknowledgedAiPolicy()) {
                this._showAiPolicyModal();
            }
            this._setupChatSourcesControl();
            if (this._isImmersive()) {
                this.elements.widget.classList.add('chat-open');
                this.setExpanded(true);
                if (this.conversationHistory.length === 0) {
                    this.showWelcomeMessage();
                }
                this.elements.input.focus();
                window.addEventListener('popstate', this._handleImmersivePopstate.bind(this));
                this._setupVisibilityChangeHandler();
            } else {
                this._updateImmersiveLinkHref();
                if (this._getFloatingConversationId()) {
                    void this._refreshFloatingHeaderTitleFromServer();
                }
            }
            this.isInitialized = true;
        }
    }

    _hasAcknowledgedAiPolicy() {
        try {
            return localStorage.getItem(this.aiPolicyAckStorageKey) === '1';
        } catch (_) {
            return false;
        }
    }

    _setAcknowledgedAiPolicy() {
        try {
            localStorage.setItem(this.aiPolicyAckStorageKey, '1');
        } catch (_) {}
    }

    _showAiPolicyModal() {
        const overlay = document.getElementById('chatAiPolicyModalOverlay');
        if (!overlay) return;
        overlay.removeAttribute('hidden');
        overlay.setAttribute('aria-hidden', 'false');
        const ackBtn = document.getElementById('chatAiPolicyModalAckBtn');
        if (ackBtn) {
            try { ackBtn.focus(); } catch (_) {}
        }
    }

    _hideAiPolicyModal() {
        const overlay = document.getElementById('chatAiPolicyModalOverlay');
        if (!overlay) return;
        overlay.setAttribute('aria-hidden', 'true');
        overlay.setAttribute('hidden', '');
    }

    _updateAiNoticeVisibility() {
        const el = this.elements && this.elements.aiNoticeBlock;
        if (!el) return;
        const isEmptyChat = Array.isArray(this.conversationHistory) && this.conversationHistory.length === 0;
        const isImmersive = this._isImmersive();
        const notAcked = !this._hasAcknowledgedAiPolicy();
        const show = isImmersive ? (isEmptyChat || notAcked) : (isEmptyChat || notAcked);
        el.style.display = show ? '' : 'none';
        try { el.setAttribute('aria-hidden', show ? 'false' : 'true'); } catch (_) {}
        const acked = this._hasAcknowledgedAiPolicy();
        if (isImmersive) this._updateImmersiveChatControls(acked);
        else this._updateFloatingChatControls(acked);
    }

    _triggerPolicyNoticeAttention() {
        if (this._isImmersive()) return;
        const notice = this.elements && this.elements.aiNoticeBlock;
        const block = notice?.matches?.('.chat-ai-notice-block') ? notice : notice?.querySelector('.chat-ai-notice-block');
        if (!notice || !block) return;
        block.classList.remove('chat-ai-notice-attention');
        void block.offsetWidth;
        block.classList.add('chat-ai-notice-attention');
        setTimeout(() => block.classList.remove('chat-ai-notice-attention'), 600);
    }

    _updateImmersiveChatControls(acked) {
        if (!this._isImmersive()) return;
        const disabled = !acked;
        const input = this.elements && this.elements.input;
        const sendBtn = this.elements && this.elements.sendBtn;
        if (input) {
            input.disabled = disabled;
            input.placeholder = disabled ? (this._uiString('aiPolicyAckRequired') || 'Please acknowledge the AI policy to continue.') : 'Ask anything';
        }
        if (sendBtn) sendBtn.disabled = disabled;
        const addBtn = document.getElementById('chatImmersiveAddBtn');
        const sourcesBtn = document.getElementById('chatImmersiveSourcesBtn');
        const quickPrompts = this.elements.quickPrompts;
        if (addBtn) addBtn.disabled = disabled;
        if (sourcesBtn) sourcesBtn.disabled = disabled;
        if (quickPrompts) {
            quickPrompts.querySelectorAll('.chat-immersive-quick-prompt').forEach((b) => { b.disabled = disabled; });
            quickPrompts.style.pointerEvents = disabled ? 'none' : '';
        }
        const ackBtn = document.getElementById('chatAiPolicyAckBtn');
        if (ackBtn) ackBtn.style.display = acked ? 'none' : '';
        const container = this.elements.widget?.querySelector('.chat-immersive-input-container');
        const wrapper = this.elements.widget?.querySelector('.chat-input-wrapper-immersive');
        if (container) container.classList.toggle('chat-immersive-input-disabled', disabled);
        if (wrapper) wrapper.classList.toggle('chat-immersive-input-disabled', disabled);
        let overlay = document.getElementById('chatAiPolicyInputOverlay');
        if (disabled && container) {
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.id = 'chatAiPolicyInputOverlay';
                overlay.className = 'chat-ai-policy-input-overlay';
                overlay.setAttribute('aria-hidden', 'true');
                overlay.addEventListener('click', () => this._triggerImmersivePolicyNoticeAttention());
                container.style.position = 'relative';
                container.appendChild(overlay);
            }
            overlay.style.display = '';
        } else if (overlay) overlay.style.display = 'none';
    }

    _triggerImmersivePolicyNoticeAttention() {
        if (!this._isImmersive()) return;
        const notice = this.elements && this.elements.aiNoticeBlock;
        const block = notice?.matches?.('.chat-ai-notice-block') ? notice : notice?.querySelector('.chat-ai-notice-block');
        if (!notice || !block) return;
        block.classList.remove('chat-ai-notice-attention', 'chat-ai-notice-attention-bounce');
        void block.offsetWidth;
        block.classList.add('chat-ai-notice-attention-bounce');
        setTimeout(() => block.classList.remove('chat-ai-notice-attention-bounce'), 600);
    }

    _updateFloatingChatControls(acked) {
        if (this._isImmersive()) return;
        const input = this.elements && this.elements.input;
        const sendBtn = this.elements && this.elements.sendBtn;
        const attachBtn = document.querySelector('#aiChatWidget .chat-input-attach');
        const disabled = !acked;
        if (input) {
            input.disabled = disabled;
            input.placeholder = disabled ? (this._uiString('aiPolicyAckRequired') || 'Please acknowledge the AI policy to continue.') : 'Ask anything';
        }
        if (sendBtn) sendBtn.disabled = disabled;
        if (attachBtn) attachBtn.disabled = disabled;
        const ackBtn = document.getElementById('chatAiPolicyAckBtn');
        if (ackBtn) ackBtn.style.display = acked ? 'none' : '';

        const container = this.elements.widget?.querySelector('.chat-input-container');
        let overlay = document.getElementById('chatAiPolicyInputOverlay');
        if (disabled) {
            if (!overlay && container) {
                overlay = document.createElement('div');
                overlay.id = 'chatAiPolicyInputOverlay';
                overlay.className = 'chat-ai-policy-input-overlay';
                overlay.setAttribute('aria-hidden', 'true');
                overlay.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this._triggerPolicyNoticeAttention();
                });
                container.style.position = 'relative';
                container.appendChild(overlay);
            }
            if (overlay) overlay.style.display = '';
        } else {
            if (overlay) overlay.style.display = 'none';
        }
    }

    setupEventListeners() {
        if (!this.elements.input || !this.elements.sendBtn || !this.elements.messages) {
            return;
        }
        const isImmersive = this._isImmersive();

        // Toggle chat widget (floating FAB only)
        if (this.elements.fab) {
            this.elements.fab.addEventListener('click', () => this.toggleChat());
        }

        // Close / Back: in widget close; in immersive closeBtn is a link, no handler
        if (this.elements.closeBtn && !isImmersive) {
            this.elements.closeBtn.addEventListener('click', () => this.toggleChat(false));
        }

        // Immersive view: open full-page chat in a new tab (same conversation if one is active)
        if (this.elements.immersiveBtn && !isImmersive) {
            this.elements.immersiveBtn.addEventListener('click', (e) => {
                let url = this.elements.widget.getAttribute('data-immersive-url') || '/chat';
                const conversationId = this._getFloatingConversationId();
                if (conversationId) {
                    url = url.replace(/\/+$/, '') + '/' + encodeURIComponent(conversationId);
                }
                e.preventDefault();
                window.open(url, '_blank', 'noopener,noreferrer');
            });
        }

        // Conversations sidebar toggle (floating only)
        if (this.elements.sidebarToggle && !isImmersive) {
            this.elements.sidebarToggle.addEventListener('click', () => this._toggleFloatingSidebar());
        }

        // New chat (floating only – starts a fresh conversation)
        if (this.elements.floatingNewChat && !isImmersive) {
            this.elements.floatingNewChat.addEventListener('click', () => this.startNewChat());
        }
        if (this.elements.newChatBtn && !isImmersive) {
            this.elements.newChatBtn.addEventListener('click', () => this.startNewChat());
        }

        // AI policy: immersive = modal, floating = inline I understand
        const modalAckBtn = document.getElementById('chatAiPolicyModalAckBtn');
        if (modalAckBtn) {
            modalAckBtn.addEventListener('click', () => {
                this._setAcknowledgedAiPolicy();
                this._hideAiPolicyModal();
                this._updateAiNoticeVisibility();
            });
        }
        const policyLinkBtn = document.getElementById('chatAiPolicyLinkBtn');
        if (policyLinkBtn) {
            policyLinkBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this._showAiPolicyModal();
            });
        }
        const policyOverlay = document.getElementById('chatAiPolicyModalOverlay');
        if (policyOverlay) {
            policyOverlay.addEventListener('click', (e) => {
                if (e.target === policyOverlay) this._hideAiPolicyModal();
            });
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && policyOverlay.getAttribute('aria-hidden') === 'false') {
                    this._hideAiPolicyModal();
                }
            });
        }
        const inlineAckBtn = document.getElementById('chatAiPolicyAckBtn');
        if (inlineAckBtn) {
            inlineAckBtn.addEventListener('click', () => {
                this._setAcknowledgedAiPolicy();
                this._updateAiNoticeVisibility();
            });
        }

        // Floating: when user clicks/ taps anywhere in chat before acking, animate the policy notice
        if (!isImmersive) {
            const mainArea = this.elements.widget?.querySelector('.chat-floating-main');
            if (mainArea) {
                const onPointer = (e) => {
                    if (!this._hasAcknowledgedAiPolicy()) {
                        const isAckAction = e.target.closest('#chatAiPolicyAckBtn, #chatAiPolicyLinkBtn');
                        if (!isAckAction) this._triggerPolicyNoticeAttention();
                    }
                };
                mainArea.addEventListener('pointerdown', onPointer, true);
                mainArea.addEventListener('click', onPointer, true);
            }
        }

        // Immersive: when user clicks anywhere in chat before acking, bounce the policy notice
        if (isImmersive) {
            const inner = this.elements.widget?.querySelector('.chat-immersive-widget-inner');
            if (inner) {
                const onPointer = (e) => {
                    if (!this._hasAcknowledgedAiPolicy()) {
                        const isAckAction = e.target.closest('#chatAiPolicyAckBtn, #chatAiPolicyLinkBtn');
                        if (!isAckAction) this._triggerImmersivePolicyNoticeAttention();
                    }
                };
                inner.addEventListener('pointerdown', onPointer, true);
                inner.addEventListener('click', onPointer, true);
            }
        }

        // Immersive quick prompts: click to send
        if (isImmersive && this.elements.quickPrompts) {
            this.elements.quickPrompts.addEventListener('click', (e) => {
                const btn = e.target.closest('.chat-immersive-quick-prompt');
                if (btn) {
                    const text = (btn.getAttribute('data-prompt') || btn.textContent || '').trim();
                    if (text) {
                        this.elements.input.value = text;
                        this.handleSendMessage();
                    }
                }
            });
        }

        // Clear conversation
        if (this.elements.clearBtn) {
            this.elements.clearBtn.addEventListener('click', () => this.handleClearConversation());
        }

        // Send message handlers (click = send when idle, stop when loading; button must stay enabled so Stop is clickable)
        this.elements.sendBtn.addEventListener('click', () => {
            if (this.isTyping) {
                this._log('Send button clicked while loading -> stop');
                this.stopCurrentRequest();
            } else {
                this.handleSendMessage();
            }
        });
        this.elements.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSendMessage();
            }
        });

        // Auto-resize textarea as user types (grow up to max-height, then scroll)
        if (this.elements.input && this.elements.input.nodeName === 'TEXTAREA') {
            this.elements.input.addEventListener('input', () => this._resizeChatInput());
        }

        // Re-sync body scroll lock when crossing the mobile/desktop breakpoint with chat open
        if (!isImmersive && typeof window.matchMedia === 'function') {
            const mq = window.matchMedia('(max-width: 768px)');
            const onViewportChange = () => this._syncFloatingMobileBodyLock(this.isOpen());
            if (typeof mq.addEventListener === 'function') {
                mq.addEventListener('change', onViewportChange);
            } else if (typeof mq.addListener === 'function') {
                mq.addListener(onViewportChange);
            }
        }

        // Close chat when clicking outside (floating only)
        if (!isImmersive && this.elements.fab) {
            document.addEventListener('click', (e) => {
                if (this.isOpen() &&
                    !this.elements.widget.contains(e.target) &&
                    this.elements.fab && !this.elements.fab.contains(e.target)) {
                // Don't close if clicking on a modal/confirmation dialog
                // Check if click target is within a modal (high z-index element)
                let isWithinModal = false;
                let element = e.target;
                while (element && element !== document.body) {
                    const style = window.getComputedStyle(element);
                    const zIndex = parseInt(style.zIndex, 10);
                    // Modals typically have z-index >= 1000
                    if (zIndex >= 1000 || element.getAttribute('role') === 'dialog') {
                        isWithinModal = true;
                        break;
                    }
                    element = element.parentElement;
                }

                if (!isWithinModal) {
                    this.toggleChat(false);
                }
            }
            });
        }

        // Prevent chat from closing when clicking inside
        this.elements.widget.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        // When sidebar is open, clicking the chat area (messages or input) closes the sidebar
        if (!isImmersive && this.elements.widget) {
            const main = this.elements.widget.querySelector('.chat-floating-main');
            if (main) {
                main.addEventListener('click', (e) => {
                    if (!this.elements.widget.classList.contains('chat-sidebar-open')) return;
                    const inMessages = this.elements.messages && this.elements.messages.contains(e.target);
                    const inInput = this.elements.widget.querySelector('.chat-input-container')?.contains(e.target);
                    if (inMessages || inInput) {
                        this._toggleFloatingSidebar();
                    }
                });
            }
        }

        // Handle interactive elements inside chatbot messages (event delegation)
        this.elements.messages.addEventListener('click', (e) => {
            const tourButton = e.target.closest('.chatbot-tour-trigger');
            if (tourButton) {
                e.preventDefault();
                e.stopPropagation();

                // Check for workflow-based tour (new dynamic system)
                const workflowId = tourButton.getAttribute('data-workflow');
                const href = tourButton.getAttribute('href') || '';

                if (workflowId || href.includes('chatbot-tour=')) {
                    // Handle workflow-based tour trigger
                    const targetPage = href.split('#')[0] || window.location.pathname;

                    // Close chatbot before starting tour
                    this.toggleChat(false);

                    // Use WorkflowTourParser if available for dynamic registration
                    if (window.WorkflowTourParser && workflowId) {
                        setTimeout(() => {
                            window.WorkflowTourParser.handleTourTrigger(workflowId, targetPage);
                        }, 300);
                    } else if (href) {
                        // Fallback: navigate directly with tour hash
                        setTimeout(() => {
                            window.location.href = href;
                        }, 300);
                    }
                    return;
                }

                // Legacy: entry form tour with step number
                const stepNumber = parseInt(tourButton.getAttribute('data-step'), 10);
                if (!isNaN(stepNumber) && typeof window.startEntryFormTour === 'function') {
                    // Close chatbot before starting tour
                    this.toggleChat(false);
                    // Start tour at specific step
                    setTimeout(() => {
                        window.startEntryFormTour(stepNumber);
                    }, 300);
                }
                return;
            }

            // "Show me" onboarding links (styled like buttons)
            const showMeLink = e.target.closest('a.chatbot-show-me');
            if (showMeLink) {
                const href = showMeLink.getAttribute('href') || '';
                if (!href) return;
                e.preventDefault();
                // Close chatbot before navigating
                this.toggleChat(false);
                window.location.href = href;
            }
        });

    }

    toggleChat(forceOpen) {
        const isOpen = typeof forceOpen === 'boolean' ? forceOpen : !this.isOpen();

        this.elements.widget.classList.toggle('chat-open', isOpen);
        if (this.elements.fab) {
            this.elements.fab.classList.toggle('chat-open', isOpen);
            this.elements.fab.setAttribute('aria-expanded', isOpen.toString());
        }

        if (isOpen) {
            // Only show greeting if chat is opened AND there's no conversation history
            if (this.conversationHistory.length === 0) {
                this.showWelcomeMessage();
            }
            this.elements.input.focus();
        }

        this._syncFloatingMobileBodyLock(isOpen);
    }

    isOpen() {
        return this.elements.widget.classList.contains('chat-open');
    }

    scrollToBottom() {
        // Immersive page: scroll the messages scroll container and respect auto-scroll flag
        if (this._isImmersive()) {
            if (typeof window.humdbChatImmersiveAutoScroll !== 'undefined' && window.humdbChatImmersiveAutoScroll === false) return;
            const scrollEl = this.elements.messages && this.elements.messages.parentElement;
            if (scrollEl && scrollEl.classList && scrollEl.classList.contains('chat-immersive-messages-scroll')) {
                scrollEl.scrollTop = scrollEl.scrollHeight;
                return;
            }
        }
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
    }

    _resizeChatInput() {
        const ta = this.elements.input;
        if (!ta || ta.nodeName !== 'TEXTAREA') return;
        const maxHeight = 200;
        const minHeight = this._isImmersive() ? 36 : 34;
        ta.style.height = '0';
        const h = Math.min(Math.max(ta.scrollHeight, minHeight), maxHeight);
        ta.style.height = h + 'px';
    }

    addMessage(message, isUser = false, opts = {}) {
        // Add to conversation history first so index is correct
        const entry = {
            message: message,
            isUser: isUser,
            timestamp: new Date().toISOString()
        };
        if (!isUser && opts.structuredPayload) entry.structuredPayload = opts.structuredPayload;
        this.conversationHistory.push(entry);

        // Limit conversation history to prevent memory issues (immersive: keep full history for DB-backed convos)
        const maxHistory = this._isImmersive() ? 500 : 20;
        if (this.conversationHistory.length > maxHistory) {
            this.conversationHistory = this.conversationHistory.slice(-maxHistory);
        }

        // Add to DOM with index for edit/rewind
        this.addMessageToDOM(message, isUser, this.conversationHistory.length - 1, opts);

        // Save conversation to localStorage
        this.saveConversationHistory();
    }

    addErrorMessage(errorMessage, retryMessage) {
        this.conversationHistory.push({
            message: errorMessage,
            isUser: false,
            timestamp: new Date().toISOString(),
            isError: true,
            retryMessage: retryMessage || ''
        });
        const maxHistory = this._isImmersive() ? 500 : 20;
        if (this.conversationHistory.length > maxHistory) {
            this.conversationHistory = this.conversationHistory.slice(-maxHistory);
        }
        this.addMessageToDOM(errorMessage, false, this.conversationHistory.length - 1, { isError: true, retryMessage: retryMessage || '' });
        this.saveConversationHistory();
        if (this._isImmersive()) {
            const cid = this.getActiveConversationId && this.getActiveConversationId();
            if (cid) {
                this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(cid)}/messages`, {
                    method: 'POST',
                    body: JSON.stringify({
                        role: 'assistant',
                        content: errorMessage,
                        meta: { is_error: true, retry_message: retryMessage || '' }
                    })
                }).then(() => { if (this._dispatchImmersiveUpdate) this._dispatchImmersiveUpdate(); }).catch(() => {});
            }
        }
    }

    showTypingIndicator() {
        if (document.getElementById('typingIndicator')) return; // Already showing

        const typingDiv = document.createElement('div');
        typingDiv.className = 'chat-progress-panel';
        typingDiv.id = 'typingIndicator';
        typingDiv.setAttribute('aria-live', 'polite');

        const stepsList = document.createElement('ul');
        stepsList.className = 'chat-progress-steps';
        stepsList.setAttribute('aria-live', 'polite');
        stepsList.setAttribute('aria-label', this._uiString('stepsInProgress') || 'Steps in progress');

        const initialLi = document.createElement('li');
        initialLi.className = 'chat-progress-step chat-progress-step-active';
        const initialIcon = document.createElement('i');
        initialIcon.className = 'fas fa-spinner fa-spin chat-progress-step-icon';
        initialIcon.setAttribute('aria-hidden', 'true');
        const initialLabel = document.createElement('span');
        initialLabel.className = 'chat-progress-step-label';
        initialLabel.textContent = this._uiString('preparingQuery') || 'Preparing query…';
        initialLi.append(initialIcon, initialLabel);
        stepsList.appendChild(initialLi);

        typingDiv.appendChild(stepsList);
        this.elements.messages.appendChild(typingDiv);
        this.scrollToBottom();
    }

    addStepToProgress(stepMessage, detail) {
        if (!stepMessage || typeof stepMessage !== 'string') return;
        const trimmed = String(stepMessage).trim();
        if (!trimmed) return;
        const typingIndicator = document.getElementById('typingIndicator');
        if (!typingIndicator) return;
        const stepsList = typingIndicator.querySelector('.chat-progress-steps');
        if (!stepsList) return;
        const lastItem = stepsList.querySelector('.chat-progress-step:last-child');
        const lastLabel = lastItem ? (lastItem.querySelector('.chat-progress-step-label') || lastItem).textContent : '';
        if (lastItem && (lastLabel || '').trim() === trimmed) {
            if (detail && String(detail).trim()) {
                this._updateStepDetail(lastItem, String(detail).trim());
            }
            return;
        }
        // If the backend streams progress ticks (e.g. "Processing documents: 10/64"),
        // update the current step label in-place instead of appending many near-identical steps.
        const progressRe = /^(.+?):\s*(\d+)\s*\/\s*(\d+)\s*$/;
        const newProgress = trimmed.match(progressRe);
        const lastProgress = ((lastLabel || '').trim()).match(progressRe);
        if (lastItem && newProgress && lastProgress) {
            const newPrefix = String(newProgress[1] || '').trim();
            const lastPrefix = String(lastProgress[1] || '').trim();
            // Only coalesce if the "prefix" matches; counts may change.
            if (newPrefix && lastPrefix && newPrefix === lastPrefix) {
                const labelEl = lastItem.querySelector('.chat-progress-step-label') || lastItem;
                labelEl.textContent = trimmed;
                if (detail && String(detail).trim()) {
                    this._updateStepDetail(lastItem, String(detail).trim());
                }
                this.scrollToBottom();
                return;
            }
        }
        // Mark previous step as done (check) and collapse its detail when next step is shown
        if (lastItem) {
            const prevDetailEl = lastItem.querySelector('.chat-progress-step-detail');
            // If the previous step had no meaningful detail (empty or placeholder), show "Done." or refined query for "Preparing query…"
            if (prevDetailEl) {
                const prevDetailText = String(prevDetailEl.textContent || '').trim();
                const hasNoMeaningfulDetail = !prevDetailText;
                if (hasNoMeaningfulDetail) {
                    const prevLabel = (lastItem.querySelector('.chat-progress-step-label') || lastItem).textContent || '';
                    const preparingLabel = (this._uiString && this._uiString('preparingQuery')) || 'Preparing query…';
                    if (prevLabel.trim() === String(preparingLabel || '').trim() && this._lastPreparingQueryDetail) {
                        prevDetailEl.textContent = String(this._lastPreparingQueryDetail).trim();
                        this._lastPreparingQueryDetail = null;
                    } else {
                        prevDetailEl.textContent = 'Done.';
                    }
                }
            }
            const prevIcon = lastItem.querySelector('.chat-progress-step-icon');
            if (prevIcon) {
                prevIcon.className = 'fas fa-check chat-progress-step-icon chat-progress-step-done';
                prevIcon.setAttribute('aria-hidden', 'true');
            }
            if (lastItem.querySelector('.chat-progress-step-detail')) {
                lastItem.classList.add('chat-progress-step-detail-collapsed');
                const prevToggle = lastItem.querySelector('.chat-progress-step-detail-toggle');
                const prevRow = lastItem.querySelector('.chat-progress-step-row');
                if (prevToggle) prevToggle.className = 'fas fa-chevron-right chat-progress-step-detail-toggle';
                if (prevRow) prevRow.setAttribute('aria-expanded', 'false');
            }
        }
        const li = document.createElement('li');
        li.className = 'chat-progress-step chat-progress-step-active';
        const stepIcon = document.createElement('i');
        stepIcon.className = 'fas fa-spinner fa-spin chat-progress-step-icon';
        stepIcon.setAttribute('aria-hidden', 'true');
        const stepLabel = document.createElement('span');
        stepLabel.className = 'chat-progress-step-label';
        stepLabel.textContent = trimmed;
        if (detail && String(detail).trim()) {
            const row = document.createElement('div');
            row.className = 'chat-progress-step-row';
            row.append(stepIcon, stepLabel);
            const toggleIcon = document.createElement('i');
            toggleIcon.className = 'fas fa-chevron-down chat-progress-step-detail-toggle';
            toggleIcon.setAttribute('aria-hidden', 'true');
            row.appendChild(toggleIcon);
            const detailEl = document.createElement('div');
            detailEl.className = 'chat-progress-step-detail';
            detailEl.textContent = String(detail).trim();
            li.append(row, detailEl);
            row.setAttribute('role', 'button');
            row.setAttribute('tabIndex', '0');
            row.setAttribute('aria-expanded', 'true');
            row.addEventListener('click', () => {
                li.classList.toggle('chat-progress-step-detail-collapsed');
                const collapsed = li.classList.contains('chat-progress-step-detail-collapsed');
                row.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
                toggleIcon.className = collapsed ? 'fas fa-chevron-right chat-progress-step-detail-toggle' : 'fas fa-chevron-down chat-progress-step-detail-toggle';
            });
            row.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    row.click();
                }
            });
        } else {
            li.append(stepIcon, stepLabel);
        }
        stepsList.appendChild(li);
        this.scrollToBottom();
    }

    appendStepDetail(detailLine) {
        if (!detailLine || typeof detailLine !== 'string') return;
        const trimmed = String(detailLine).trim();
        if (!trimmed) return;
        const typingIndicator = document.getElementById('typingIndicator');
        if (!typingIndicator) return;
        const stepsList = typingIndicator.querySelector('.chat-progress-steps');
        if (!stepsList) return;
        const lastItem = stepsList.querySelector('.chat-progress-step:last-child');
        if (!lastItem) return;
        const detailEl = lastItem.querySelector('.chat-progress-step-detail');
        if (detailEl) {
            // Avoid duplicate consecutive detail lines (common when backend re-emits last progress)
            const existing = String(detailEl.textContent || '');
            const lastLine = existing.split('\n').slice(-1)[0]?.trim() || '';
            if (lastLine === trimmed) return;

            // Coalesce "progress tick" lines like "Processing documents: 10/64" by replacing the last tick
            // instead of appending many near-identical lines.
            const progressRe = /^(.+?):\s*(\d+)\s*\/\s*(\d+)\s*$/;
            const newProgress = trimmed.match(progressRe);
            const lastProgress = lastLine.match(progressRe);
            if (newProgress && lastProgress) {
                const newPrefix = String(newProgress[1] || '').trim();
                const lastPrefix = String(lastProgress[1] || '').trim();
                if (newPrefix && lastPrefix && newPrefix === lastPrefix) {
                    const lines = existing.split('\n');
                    lines[lines.length - 1] = trimmed;
                    detailEl.textContent = lines.join('\n');
                    this._log('Coalesced step_detail progress tick:', { from: lastLine, to: trimmed });
                    this.scrollToBottom();
                    return;
                }
            }

            detailEl.textContent = detailEl.textContent ? detailEl.textContent + '\n' + trimmed : trimmed;
            this._log('Appended step_detail line:', trimmed);
        } else {
            this._updateStepDetail(lastItem, trimmed);
            this._log('Created step_detail block with first line:', trimmed);
        }
        this.scrollToBottom();
    }

    _updateStepDetail(stepLi, detailText) {
        const detailEl = stepLi.querySelector('.chat-progress-step-detail');
        if (detailEl) {
            detailEl.textContent = detailText;
            return;
        }
        const icon = stepLi.querySelector('.chat-progress-step-icon');
        const label = stepLi.querySelector('.chat-progress-step-label');
        if (!icon || !label) return;
        const row = document.createElement('div');
        row.className = 'chat-progress-step-row';
        row.append(icon, label);
        const toggleIcon = document.createElement('i');
        toggleIcon.className = 'fas fa-chevron-down chat-progress-step-detail-toggle';
        toggleIcon.setAttribute('aria-hidden', 'true');
        row.appendChild(toggleIcon);
        const detailElNew = document.createElement('div');
        detailElNew.className = 'chat-progress-step-detail';
        detailElNew.textContent = detailText;
        stepLi.append(row, detailElNew);
        row.setAttribute('role', 'button');
        row.setAttribute('tabIndex', '0');
        row.setAttribute('aria-expanded', 'true');
        row.addEventListener('click', () => {
            stepLi.classList.toggle('chat-progress-step-detail-collapsed');
            const collapsed = stepLi.classList.contains('chat-progress-step-detail-collapsed');
            row.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
            toggleIcon.className = collapsed ? 'fas fa-chevron-right chat-progress-step-detail-toggle' : 'fas fa-chevron-down chat-progress-step-detail-toggle';
        });
        row.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                row.click();
            }
        });
    }

    updateTypingIndicator(message, detail) {
        const typingIndicator = document.getElementById('typingIndicator');
        if (!typingIndicator) return;
        if (typingIndicator.classList.contains('chat-progress-panel')) {
            const preparingLabel = (this._uiString && this._uiString('preparingQuery')) || 'Preparing query…';
            if (String(message || '').trim() === String(preparingLabel || '').trim() && detail && String(detail).trim()) {
                this._lastPreparingQueryDetail = String(detail).trim();
            }
            this.addStepToProgress(message, detail);
            return;
        }
        const textSpan = typingIndicator.querySelector('.typing-indicator-text, .text-sm.text-gray-500');
        if (textSpan) {
            textSpan.textContent = message || this._uiString('assistantIsTyping') || 'Assistant is typing';
        }
    }

    hideTypingIndicator() {
        this._lastPreparingQueryDetail = null;
        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    _setSendButtonStop(isStop) {
        const btn = this.elements.sendBtn;
        if (!btn) return;
        const icon = btn.querySelector('i');
        const stopLabel = btn.getAttribute('data-stop-label') || this._uiString('stop') || 'Stop';
        const sendLabel = btn.getAttribute('data-send-label') || this._uiString('send') || 'Send';
        if (isStop) {
            btn.setAttribute('aria-label', stopLabel);
            btn.setAttribute('title', stopLabel);
            btn.classList.add('chat-send-is-stop');
            if (icon) {
                icon.classList.remove('fa-arrow-up');
                icon.classList.add('fa-stop');
            }
        } else {
            btn.setAttribute('aria-label', sendLabel);
            btn.setAttribute('title', sendLabel);
            btn.classList.remove('chat-send-is-stop');
            if (icon) {
                icon.classList.remove('fa-stop');
                icon.classList.add('fa-arrow-up');
            }
        }
    }

    stopCurrentRequest() {
        this._log('stopCurrentRequest called, isTyping=', this.isTyping, ', _currentAbort=', typeof this._currentAbort);
        if (typeof this._currentAbort === 'function') {
            try {
                this._currentAbort();
            } catch (e) {
                this._warn('stopCurrentRequest error:', e);
            }
            this._currentAbort = null;
        } else {
            this._warn('stopCurrentRequest: no abort callback (nothing to stop)');
        }
    }

    _updateImmersiveQuickPromptsVisibility() {
        if (!this._isImmersive()) return;
        const hasUserMessage = this.conversationHistory.some(entry => entry.isUser);
        const showEmpty = !hasUserMessage;
        if (this.elements.quickPrompts) {
            this.elements.quickPrompts.style.display = showEmpty ? 'block' : 'none';
        }
        if (this.elements.welcomeCenter) {
            this.elements.welcomeCenter.style.display = showEmpty ? 'flex' : 'none';
            this.elements.welcomeCenter.setAttribute('aria-hidden', showEmpty ? 'false' : 'true');
        }
    }

    async handleSendMessage(overrideMessage, opts = {}) {
        if (!this._hasAcknowledgedAiPolicy()) {
            if (this._isImmersive()) this._showAiPolicyModal();
            return;
        }
        const message = overrideMessage !== undefined
            ? String(overrideMessage || '').trim()
            : this.elements.input.value.trim();
        if (!message) return;
        if (this._isImmersive()) {
            const activeKey = this._getActiveConversationKey();
            if (this.isConversationRunning(activeKey)) {
                const bypassServerInflight = !!(opts && opts.allowServerInflightBypass);
                if (!bypassServerInflight) return;
                // Only bypass *server* inflight markers (which can be briefly stale).
                // If this tab has a real in-progress run for this conversation, still block.
                const local = this._inflightByConversationKey.get(activeKey);
                if (local && local.status === 'in_progress') return;
            }
        } else {
            if (this.isTyping) return;
        }

        // If we were passively polling an "in-flight" request restored after refresh,
        // stop polling now to avoid UI races with the new outgoing request.
        this._stopInflightPoll();

        if (overrideMessage === undefined) {
            this.addMessage(message, true);
            this.elements.input.value = '';
            this._resizeChatInput();
        }
        // New user message -> hide "new chat" notices immediately.
        this._updateAiNoticeVisibility();
        this._updateImmersiveQuickPromptsVisibility();

        // Show typing indicator and switch send button to stop (keep button enabled so Stop is clickable)
        this.isTyping = true;
        this.showTypingIndicator();
        this._setSendButtonStop(true);

        const abortRef = { current: null };
        const detachRef = { current: null };
        const sendOptions = Object.assign({}, opts);
        if (!sendOptions.client_message_id) {
            sendOptions.client_message_id = this._generateClientMessageId();
        }
        const inflightKey = this._isImmersive() ? this._getActiveConversationKey() : (this.getActiveConversationId() || null);
        const inflightState = this._isImmersive()
            ? {
                key: inflightKey,
                status: 'in_progress',
                detached: false,
                detachRef: detachRef,
                conversation_id: (this.getActiveConversationId() || null),
                request_id: null,
                client_message_id: sendOptions.client_message_id,
                started_at_ms: Date.now(),
            }
            : null;
        if (inflightState && inflightKey) {
            this._inflightByConversationKey.set(inflightKey, inflightState);
            this._sidebarRunningLog('inflight set at send start', { key: inflightKey, mapSize: this._inflightByConversationKey.size });
            // Prompt sidebar refresh so spinners can appear quickly.
            this._dispatchImmersiveUpdate();
        }
        // Sidebar / header title: show immediately (same rule as server _build_initial_conversation_title).
        // Refined title still arrives from background thread + polling; no need to wait for any API.
        try {
            const instantTitle = this._buildLocalConversationTitle(message);
            this._applyInstantChatTitles(instantTitle);
        } catch (_e) { /* ignore */ }
        this._currentAbort = () => {
            if (abortRef.current) {
                this._log('Stop requested, calling abort callback');
                abortRef.current();
            } else {
                this._warn('Stop requested but no abort callback set (abortRef.current is null)');
            }
        };

        try {
            // Prefer data attribute (set by server per-page) over global to avoid cache/order issues.
            const wsFromPage = document.body && document.body.getAttribute('data-chat-websocket-enabled');
            const wsEnabled = wsFromPage !== null ? (wsFromPage === 'true') : (window.CHAT_WEBSOCKET_ENABLED !== false);
            // Always use streaming when possible: WS if enabled, else SSE. This ensures step events (progress) are sent.
            const useStreaming = true;
            const useWebSocket = wsEnabled && (typeof WebSocket !== 'undefined');
            let streamSucceeded = false;

            if (!wsEnabled) {
                console.info('[Chatbot] Transport: WebSocket disabled by server config (WEBSOCKET_ENABLED=false), using SSE');
            } else if (!useWebSocket) {
                console.info('[Chatbot] Transport: WebSocket not available in this browser, using SSE');
            }

            if (useWebSocket) {
                console.info('[Chatbot] Transport: attempting WebSocket (wss://)');
                try {
                    await this.streamResponseWithWebSocket(message, sendOptions, abortRef, detachRef, inflightKey);
                    streamSucceeded = true;
                    console.info('[Chatbot] Transport: WebSocket succeeded');
                } catch (wsError) {
                    const isAbort = wsError && (wsError.name === 'AbortError' || /aborted|cancelled|canceled/i.test(String(wsError.message || '')));
                    if (isAbort) {
                        throw wsError;
                    }
                    console.warn('[Chatbot] Transport: WebSocket failed, falling back to SSE:', wsError);
                    this.isTyping = true;
                    this.showTypingIndicator();
                    this._setSendButtonStop(true);
                }
            }

            if (useStreaming && !streamSucceeded) {
                console.info('[Chatbot] Transport: SSE (event-stream)');
                try {
                    await this.streamResponseWithSSE(message, sendOptions, abortRef, detachRef, inflightKey);
                    streamSucceeded = true;
                    console.info('[Chatbot] Transport: SSE succeeded');
                } catch (sseError) {
                    const isUserAbort = sseError && (sseError.name === 'AbortError' || /aborted|cancelled|canceled/i.test(String(sseError.message || '')));
                    if (isUserAbort) {
                        throw sseError;
                    }
                    console.warn('[Chatbot] Transport: SSE failed, falling back to HTTP JSON:', sseError);
                    this.isTyping = true;
                    this.showTypingIndicator();
                    this._setSendButtonStop(true);
                }
            }

            if (!streamSucceeded) {
                const response = await this.getAIResponse(message, sendOptions, abortRef);
                this.hideTypingIndicator();
                if (this._isServiceUnavailableResponse(response)) {
                    const plainText = (typeof response === 'string')
                        ? response.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim()
                        : 'AI service unavailable. Please try again in a moment.';
                    this.addErrorMessage(plainText || 'AI service unavailable. Please try again in a moment.', message);
                    const cid = this.getActiveConversationId && this.getActiveConversationId();
                    if (cid) {
                        this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(cid)}/clear-inflight`, { method: 'POST' }).catch(() => {});
                        if (this._dispatchImmersiveUpdate) this._dispatchImmersiveUpdate();
                    }
                } else {
                    const _confidence = this._pendingConfidence || {};
                    this._pendingConfidence = null;
                    let _spEntry = null;
                    if (this._pendingStructuredRawPieces && this._pendingStructuredRawPieces.length) {
                        for (const _p of this._pendingStructuredRawPieces) {
                            const _c = this._coerceStructuredPayload(_p);
                            if (_c) {
                                _spEntry = _c;
                                break;
                            }
                        }
                    } else {
                        _spEntry = this._consumePendingStructuredPayload();
                    }
                    this.addMessage(response, false, {
                        structuredPayload: _spEntry,
                        confidence: _confidence.confidence || null,
                        grounding_score: _confidence.grounding_score != null ? _confidence.grounding_score : null,
                    });
                }
            }

        } catch (error) {
            this.hideTypingIndicator();
            if (error && error.name === 'DlpConfirmationRequired') {
                try {
                    this._handleDlpChallenge(message, sendOptions, error.dlp || null);
                } catch (e) {
                    console.debug('DLP dialog failed:', e);
                }
                // Do not show generic connection error or fall back.
                return;
            }
            const isAbort = error && (error.name === 'AbortError' || /aborted|cancelled|canceled/i.test(String(error.message || '')));
            if (isAbort) {
                this._log('Request was stopped by user (abort/cancel)');
            } else {
                console.error('[Chatbot]', error);
            }
            if (!isAbort) {
                // Show error message in user's preferred language
                const errorMessages = this.messages.errors?.connectionError || {
                    en: "I'm sorry, but I'm having trouble connecting right now. Please check your internet connection and try again."
                };
                const errorMessage = errorMessages[this.preferredLanguage] || errorMessages.en;
                this.addErrorMessage(errorMessage, message);
                const cid = this.getActiveConversationId && this.getActiveConversationId();
                if (cid) {
                    this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(cid)}/clear-inflight`, { method: 'POST' }).catch(() => {});
                    if (this._dispatchImmersiveUpdate) this._dispatchImmersiveUpdate();
                }
            }
        } finally {
            this._currentAbort = null;
            this.isTyping = false;
            this._setSendButtonStop(false);
            this._log('Send button reset to ready');
            if (inflightState) {
                try {
                    // If the stream was detached (user switched to another chat), keep it marked in-progress.
                    // It will be cleared once the server reports inflight is gone (sidebar polling updates the index).
                    const keyToClear = inflightState.key;
                    const sizeBefore = this._inflightByConversationKey.size;
                    if (!inflightState.detached && keyToClear) {
                        const convId = String(keyToClear);
                        this._inflightByConversationKey.delete(keyToClear);
                        // Clear server inflight cache for this conversation so sidebar spinner stops
                        // and the next send is not blocked by isConversationRunning().
                        if (!convId.startsWith('draft:')) {
                            this._serverInflightByConversationId.delete(convId);
                            this._serverInflightIgnoreUntilByConversationId.set(convId, Date.now() + 15000);
                        }
                        const sizeAfter = this._inflightByConversationKey.size;
                        this._sidebarRunningLog('inflight cleared in finally', { key: keyToClear, detached: !!inflightState.detached, mapSizeBefore: sizeBefore, mapSizeAfter: sizeAfter });
                    } else {
                        this._sidebarRunningLog('inflight NOT cleared (detached or no key)', { key: keyToClear, detached: !!inflightState.detached });
                        // Stream was detached (user switched conversation, SSE timed out,
                        // or page visibility changed).  Start polling the backend so the
                        // UI picks up the completed response when the worker finishes.
                        if (inflightState.detached && this._isImmersive()) {
                            const pollConvId = inflightState.conversation_id
                                || (keyToClear && !String(keyToClear).startsWith('draft:') ? String(keyToClear) : null);
                            // Always start polling the detached run: pollOnce stops itself if the user
                            // is viewing another conversation: do not require activeId === pollConvId here
                            // (that prevented any poll after switch-away, so re-open showed no steps).
                            if (pollConvId) {
                                this._startInflightPoll(pollConvId, inflightState.request_id || null);
                            }
                        }
                    }
                } catch (_) { /* ignore */ }
                this._sidebarRunningLog('dispatching chatbot-immersive-updated after finally');
                this._dispatchImmersiveUpdate();
            }
        }
    }

    _scheduleStreamingFlush(ctx, force = false) {
        if (ctx._streamFlushScheduled && !force) return;
        if (ctx._streamDone) return;
        ctx._streamFlushScheduled = true;
        const self = this;
        requestAnimationFrame(function flush() {
            ctx._streamFlushScheduled = false;
            if (ctx._streamDone) return;
            if (ctx._streamFlushPendingTimeout) {
                clearTimeout(ctx._streamFlushPendingTimeout);
                ctx._streamFlushPendingTimeout = null;
            }
            if (ctx.contentElement && ctx.buffer !== undefined) {
                const safeHtml = self.getStreamingSafeHtml(ctx.buffer);
                ctx.contentElement.innerHTML = safeHtml;
                ctx.contentElement.classList.add('streaming-cursor');
                ctx.lastFlushLength = ctx.buffer.length;
                ctx.lastFlushTime = Date.now();
                self.scrollToBottom();
            }
        });
    }

    _scheduleStreamingFlushBatched(ctx) {
        const minChars = 40;
        const maxDelayMs = 80;
        const lastLen = ctx.lastFlushLength != null ? ctx.lastFlushLength : 0;
        const unflushed = ctx.buffer.length - lastLen;
        const hasNewline = unflushed > 0 && ctx.buffer.slice(lastLen).indexOf('\n') !== -1;
        if (unflushed >= this._streamFlushMinChars || hasNewline) {
            if (ctx._streamFlushPendingTimeout) {
                clearTimeout(ctx._streamFlushPendingTimeout);
                ctx._streamFlushPendingTimeout = null;
            }
            this._scheduleStreamingFlush(ctx);
            return;
        }
        if (unflushed > 0 && !ctx._streamFlushPendingTimeout) {
            const self = this;
            ctx._streamFlushPendingTimeout = setTimeout(() => {
                ctx._streamFlushPendingTimeout = null;
                self._scheduleStreamingFlush(ctx, true);
            }, maxDelayMs);
        }
    }

    processStreamingMessage(msg, ctx) {
        if (!msg || !msg.type || !ctx) return;

        if (msg.type === 'step') {
            console.info('[Chatbot] WS step:', msg.message || '(detail-only)', msg.detail ? '| detail: ' + String(msg.detail).slice(0, 80) : '');
        } else if (msg.type === 'meta') {
            console.info('[Chatbot] WS meta: request_id=' + (msg.request_id || '?') + ' conversation_id=' + (msg.conversation_id || '?'));
        } else if (msg.type === 'done') {
            console.info('[Chatbot] WS done: deduped=' + (msg.deduped || false) + ' provider=' + (msg.provider || '?'));
        } else if (msg.type === 'error') {
            console.warn('[Chatbot] WS error from server:', msg.message || msg.error || '(no message)');
        } else if (msg.type === 'cancelled') {
            console.info('[Chatbot] WS: request cancelled by server');
        } else if (msg.type !== 'delta' && msg.type !== 'step_detail' && msg.type !== 'pong') {
            this._log('Stream Received:', msg.type, '');
        }

        switch (msg.type) {
            case 'meta':
                // Request acknowledged
                this._log('Stream Request acknowledged, request_id:', msg.request_id);
                try {
                    if (msg.request_id) ctx.request_id = msg.request_id;
                    if (msg.conversation_id) ctx.conversation_id = msg.conversation_id;
                } catch (e) { /* ignore */ }
                if (this._isImmersive() && msg.initial_conversation_title) {
                    try {
                        window.dispatchEvent(new CustomEvent('chatbot-optimistic-title', {
                            detail: {
                                title: String(msg.initial_conversation_title || '').trim(),
                                conversationId: msg.conversation_id || null,
                            }
                        }));
                    } catch (_e) { /* ignore */ }
                }
                // Track local inflight request id (for debug + later cancel).
                try {
                    if (this._isImmersive() && ctx && ctx._inflight_key) {
                        const curKey = String(ctx._inflight_key || '');
                        const local = curKey ? this._inflightByConversationKey.get(curKey) : null;
                        if (local && msg.request_id) local.request_id = String(msg.request_id);
                    }
                } catch (_) { /* ignore */ }
                // When starting a brand-new chat, the backend now includes conversation_id in meta.
                // Adopt it immediately so we can update the URL and refresh the immersive sidebar list
                // without waiting for the full answer (and without requiring a reload).
                if (msg.conversation_id) {
                    // If this request started as a draft (no conversation_id yet), re-key local inflight tracking.
                    try {
                        if (this._isImmersive() && ctx && ctx._inflight_key) {
                            const k = String(ctx._inflight_key || '');
                            if (k && k.startsWith('draft:')) {
                                this._rekeyInflight(k, String(msg.conversation_id));
                                ctx._inflight_key = String(msg.conversation_id);
                                // Draft has now become a real conversation.
                                this._getImmersiveDraftKey(true);
                            }
                        }
                    } catch (_) { /* ignore */ }
                    if (this._isImmersive()) {
                        const active = this.getActiveConversationId();
                        if (!active) {
                            this._setImmersiveActiveId(msg.conversation_id);
                            this._dispatchImmersiveUpdate();
                            this._updateImmersiveUrl(true);
                        }
                    } else if (this._getFloatingConversationId && !this._getFloatingConversationId()) {
                        this._setFloatingConversationId(msg.conversation_id);
                    }
                    // Background title refine commits well before the assistant stream ends; refresh
                    // the sidebar a few times early so the list does not wait for `done` + debounce.
                    try {
                        this._queueConversationTitleBurst(String(msg.conversation_id));
                    } catch (_) { /* ignore */ }
                }
                break;

            case 'step':
                if (msg.message) {
                    this._log('STEP payload:', { message: msg.message, detail: msg.detail });
                    this.updateTypingIndicator(msg.message, msg.detail);
                    if (!ctx.steps) ctx.steps = [];
                    const stepMsg = String(msg.message || '').trim();
                    const stepDetail = msg.detail != null ? String(msg.detail).trim() : '';
                    const last = ctx.steps[ctx.steps.length - 1];
                    if (last && (last.message || '').trim() === stepMsg) {
                        if (stepDetail) (last.detail_lines = last.detail_lines || []).push(stepDetail);
                    } else {
                        ctx.steps.push({ message: stepMsg, detail_lines: stepDetail ? [stepDetail] : [] });
                    }
                } else if (msg.detail) {
                    this._log('STEP (detail-only) payload:', { detail: msg.detail });
                    this.appendStepDetail(msg.detail);
                    if (ctx.steps && ctx.steps.length) {
                        const last = ctx.steps[ctx.steps.length - 1];
                        if (!last.detail_lines) last.detail_lines = [];
                        last.detail_lines.push(String(msg.detail || '').trim());
                    }
                } else {
                    this._warn('Stream Step event has no message:', msg);
                }
                break;
            case 'step_detail':
                if (msg.detail) {
                    this._log('STEP_DETAIL payload:', { detail: msg.detail });
                    this.appendStepDetail(msg.detail);
                    if (!ctx.steps) ctx.steps = [];
                    if (!ctx.steps.length) {
                        ctx.steps.push({ message: (this._uiString && this._uiString('preparingQuery')) || 'Preparing query…', detail_lines: [] });
                    }
                    const lastStep = ctx.steps[ctx.steps.length - 1];
                    if (!lastStep.detail_lines) lastStep.detail_lines = [];
                    lastStep.detail_lines.push(String(msg.detail || '').trim());
                }
                break;

            case 'delta':
                if (msg.text) {
                    ctx.buffer += msg.text;

                    this.hideTypingIndicator();

                    if (!ctx.messageElement) {
                        ctx.messageElement = this.createStreamingMessageElement();
                        ctx.contentElement = ctx.messageElement.querySelector('.chat-message-content');
                    }

                    if (ctx.contentElement) {
                        this._scheduleStreamingFlushBatched(ctx);
                    }
                }
                break;

            case 'done': {
                if (ctx._streamFlushPendingTimeout) {
                    clearTimeout(ctx._streamFlushPendingTimeout);
                    ctx._streamFlushPendingTimeout = null;
                }
                ctx._streamDone = true;
                const rawFromServer = (msg.response != null && String(msg.response).trim() !== '') ? String(msg.response).trim() : '';
                const finalResponse = rawFromServer || ctx.buffer || '';
                ctx.buffer = finalResponse;

                if (!ctx.messageElement) {
                    ctx.messageElement = this.createStreamingMessageElement();
                    ctx.contentElement = ctx.messageElement.querySelector('.chat-message-content');
                }

                let wrapperEl = null;
                if (ctx.contentElement && finalResponse) {
                    const sanitizedHtml = this.sanitizeHtml(finalResponse);
                    ctx.contentElement.innerHTML = sanitizedHtml;
                    ctx.contentElement.classList.remove('streaming-cursor');

                    if (window.WorkflowTourParser && typeof window.WorkflowTourParser.processMessage === 'function') {
                        try {
                            window.WorkflowTourParser.processMessage(ctx.contentElement);
                        } catch (e) {
                            console.debug('WorkflowTourParser error:', e);
                        }
                    }
                    this._formatChatResponseSources(ctx.contentElement);
                    this._addTableCopyButtons(ctx.contentElement);
                    this._collapseLongTables(ctx.contentElement);

                    // Confidence badge for streamed responses (skip for pure pleasantries)
                    if (msg.meta || msg.confidence || msg.grounding_score != null) {
                        const _conf = (msg.meta && msg.meta.confidence) || msg.confidence || null;
                        const _gs = (msg.meta && msg.meta.grounding_score != null) ? msg.meta.grounding_score
                                  : (msg.grounding_score != null ? msg.grounding_score : null);
                        if (!this._shouldSuppressConfidenceBadgeForUserPrompt(ctx._userMessage)) {
                            const badge = this._buildConfidenceBadge(_conf, _gs);
                            if (badge) ctx.contentElement.appendChild(badge);
                        }
                    }

                    if (ctx.messageElement && this._createMessageActionBar) {
                        const parent = ctx.messageElement.parentNode;
                        const wrapper = document.createElement('div');
                        wrapper.className = 'chat-message-wrapper is-bot';
                        if (msg.trace_id != null) wrapper.setAttribute('data-trace-id', String(msg.trace_id));
                        if (parent) parent.insertBefore(wrapper, ctx.messageElement);
                        wrapper.appendChild(ctx.messageElement);
                        const getTextFn = () => ctx.contentElement?.innerText ?? '';
                        const actionBar = this._createMessageActionBar(ctx.messageElement, false, getTextFn);
                        wrapper.appendChild(actionBar);
                        wrapperEl = wrapper;
                    }

                    this.scrollToBottom();
                }
                // The backend may emit BOTH:
                // - a standalone `{type:"structured", map_payload: ...}` event, AND
                // - `map_payload` inside the final `{type:"done", ...}` envelope.
                //
                // Always consume the pending payload here so it can't leak into the next message.
                const pendingStructured = this._consumePendingStructuredPayload();
                // Backend often sends map + table together (e.g. heatmap + data table). Do not use
                // table||chart||map — that drops the map. Dispatch every coercible payload.
                const rawPieces = [];
                if (msg.map_payload && typeof msg.map_payload === 'object') rawPieces.push(msg.map_payload);
                if (msg.chart_payload && typeof msg.chart_payload === 'object') rawPieces.push(msg.chart_payload);
                if (msg.table_payload && typeof msg.table_payload === 'object') rawPieces.push(msg.table_payload);
                if (!rawPieces.length && pendingStructured) rawPieces.push(pendingStructured);
                let primaryCoerced = null;
                for (const piece of rawPieces) {
                    const c = this._coerceStructuredPayload(piece);
                    if (c) {
                        if (!primaryCoerced) primaryCoerced = c;
                        this._dispatchStructuredPayload(piece, ctx.messageElement, wrapperEl);
                    }
                }
                ctx.structuredPayload = primaryCoerced;

                if (msg.detected_language && msg.detected_language !== this.preferredLanguage) {
                    this._setPreferredLanguage(msg.detected_language);
                }

                if (this._isImmersive() && msg.conversation_id && !this.getActiveConversationId()) {
                    this._setImmersiveActiveId(msg.conversation_id);
                    this._dispatchImmersiveUpdate();
                } else if (!this._isImmersive() && msg.conversation_id && !this._getFloatingConversationId()) {
                    this._setFloatingConversationId(msg.conversation_id);
                }
                try {
                    this._cancelConversationTitleBurst(msg.conversation_id || ctx.conversation_id);
                } catch (_) { /* ignore */ }
                this._scheduleConversationTitleRefresh(
                    msg.conversation_id || ctx.conversation_id || this.getActiveConversationId(),
                    400
                );

                this._stopInflightPoll();
                this.hideTypingIndicator();
                if (typeof ctx.finish === 'function') ctx.finish(true);
                break;
            }

            case 'error':
                // DLP challenge is handled by the caller (handleSendMessage) so we can offer
                // resend options (send anyway / private mode) without duplicating the user message.
                if (msg.error_type && String(msg.error_type).startsWith('dlp_')) {
                    ctx._dlp_error = msg;
                    try {
                        this._cancelConversationTitleBurst(ctx.conversation_id || this.getActiveConversationId());
                    } catch (_) { /* ignore */ }
                    this._stopInflightPoll();
                    this.hideTypingIndicator();
                    if (typeof ctx.finish === 'function') ctx.finish(false, msg.message || msg.error || 'Sensitive information detected');
                    break;
                }
                console.error('Chatbot stream error:', msg.message);
                try {
                    this._cancelConversationTitleBurst(ctx.conversation_id || this.getActiveConversationId());
                } catch (_) { /* ignore */ }
                this._stopInflightPoll();
                this.hideTypingIndicator();
                if (typeof ctx.finish === 'function') ctx.finish(false, msg.message || this._uiString('serverError') || 'Server error');
                break;

            case 'pong':
                break;

            case 'structured':
                // `done` carries the same payloads; avoid storing only table (table||… hid map+chart).
                this._setPendingStructuredPayload(null);
                this._log('Stream structured payload received');
                break;

            case 'cancelled':
                try {
                    this._cancelConversationTitleBurst(ctx.conversation_id || this.getActiveConversationId());
                } catch (_) { /* ignore */ }
                this._stopInflightPoll();
                this.hideTypingIndicator();
                if (typeof ctx.finish === 'function') ctx.finish(false, this._uiString('requestCancelled') || 'Request cancelled');
                break;
        }
    }

    async streamResponseWithWebSocket(userMessage, sendOptions = {}, abortRef, detachRef, inflightKey) {
        return new Promise((resolve, reject) => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/api/ai/v2/ws`;

            let ws;
            try {
                ws = new WebSocket(wsUrl);
            } catch (e) {
                reject(new Error('WebSocket not supported'));
                return;
            }

            let done = false;
            const ctx = {
                buffer: '',
                messageElement: null,
                contentElement: null,
                finish: null,
                conversation_id: null,
                _inflight_key: inflightKey || null,
                steps: [],
                _streamDone: false,
                _dlp_error: null,
                _userMessage: userMessage,
            };
            // Match SSE/agent run tolerance (5 min) so long tool+LLM runs don't hit client timeout first.
            const closeWsQuietly = () => {
                try {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.close(1000, 'client_done');
                    }
                } catch (_) { /* ignore */ }
            };

            const timeout = setTimeout(() => {
                if (!done) {
                    done = true;
                    closeWsQuietly();
                    reject(new Error('WebSocket timeout'));
                }
            }, 300000); // 5 minute timeout

            const makeAbortError = (message) => {
                try {
                    return new DOMException(message || 'Aborted', 'AbortError');
                } catch (_) {
                    const e = new Error(message || 'Aborted');
                    e.name = 'AbortError';
                    return e;
                }
            };

            const abortClient = (opts = {}) => {
                const cancelBackend = !!opts.cancelBackend;
                const isDetach = !!opts.detached; // user switched conversation, not Stop
                if (done) return;
                done = true;
                clearTimeout(timeout);
                try {
                    if (cancelBackend && (ws.readyState === WebSocket.OPEN || ws.readyState === 1)) {
                        ws.send(JSON.stringify({ type: 'cancel' }));
                    }
                } catch (e) {
                    if (cancelBackend) this._warn('WS Failed to send cancel:', e);
                }
                try {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.close(1000, 'client_abort');
                    }
                } catch (_) {}
                if (!isDetach) {
                    try {
                        if (ctx.messageElement && ctx.messageElement.parentNode) {
                            ctx.messageElement.parentNode.removeChild(ctx.messageElement);
                        }
                    } catch (_) {}
                }
                this._stopInflightPoll();
                this.hideTypingIndicator();
                if (isDetach) {
                    this._log('Stream detached (user switched conversation), request continues on server');
                    const steps = Array.isArray(ctx.steps) && ctx.steps.length ? ctx.steps.map(s => ({ message: s.message || '', detail_lines: Array.isArray(s.detail_lines) ? s.detail_lines.slice() : [] })) : null;
                    if (steps) {
                        const key = ctx.conversation_id || (ctx._inflight_key && String(ctx._inflight_key).startsWith('draft:') ? null : ctx._inflight_key);
                        if (key) {
                            this._detachedInflightStepsByKey.set(key, { steps, request_id: ctx.request_id || null });
                        }
                    }
                    resolve(ctx.buffer || '');
                } else {
                    reject(makeAbortError(cancelBackend ? 'Cancelled' : 'Aborted'));
                }
            };

            if (detachRef && typeof detachRef === 'object') {
                detachRef.current = () => abortClient({ cancelBackend: false, detached: true });
            }

            if (abortRef && typeof abortRef === 'object') {
                abortRef.current = () => abortClient({ cancelBackend: true });
            }

            const finish = (success = true, errorMsg = 'WebSocket error') => {
                if (done) return;
                done = true;
                if (success) {
                    console.info('[Chatbot] WS: finished successfully');
                } else {
                    console.warn('[Chatbot] WS: finished with error:', errorMsg);
                }
                clearTimeout(timeout);
                closeWsQuietly();

                // Remove cursor from streaming element
                if (ctx.contentElement) {
                    ctx.contentElement.classList.remove('streaming-cursor');
                }

                if (success) {
                    this.hideTypingIndicator();

                    // Update conversation history with final response
                    if (ctx.buffer) {
                        const entry = {
                            message: ctx.buffer,
                            isUser: false,
                            timestamp: new Date().toISOString()
                        };
                        if (ctx.structuredPayload) entry.structuredPayload = ctx.structuredPayload;
                        this.conversationHistory.push(entry);

                        const maxHistory = this._isImmersive() ? 500 : 20;
                        if (this.conversationHistory.length > maxHistory) {
                            this.conversationHistory = this.conversationHistory.slice(-maxHistory);
                        }

                        this.saveConversationHistory();
                    }

                    this.isTyping = false;
                    this.elements.sendBtn.disabled = false;
                    resolve(ctx.buffer);
                } else {
                    // On failure, remove any partial message element we created
                    if (ctx.messageElement && ctx.messageElement.parentNode) {
                        ctx.messageElement.parentNode.removeChild(ctx.messageElement);
                    }
                    // Don't reset isTyping or button state - let caller handle fallback
                    if (ctx && ctx._dlp_error) {
                        reject(this._makeDlpError(ctx._dlp_error));
                    } else {
                        reject(new Error(errorMsg));
                    }
                }
            };
            ctx.finish = finish;

            ws.onopen = () => {
                console.info('[Chatbot] WS: connection opened, sending message');
                const payload = Object.assign(
                    { type: 'message' },
                    this._buildUnifiedChatPayload(userMessage, sendOptions)
                );
                ws.send(JSON.stringify(payload));
            };

            ws.onmessage = (event) => {
                let msg;
                try {
                    msg = JSON.parse(event.data);
                } catch (e) {
                    this._warn('WS Failed to parse message:', event.data);
                    return;
                }

                this.processStreamingMessage(msg, ctx);
            };

            ws.onerror = (error) => {
                // After a successful stream we call ws.close(); some browsers still emit `error`
                // then `close` with 1006. That is not a user-facing failure.
                if (done) {
                    try {
                        console.debug('[Chatbot] WS: error event after stream finished (ignored)', error);
                    } catch (_) { /* ignore */ }
                    return;
                }
                console.error('[Chatbot] WS: connection error:', error);
                finish(false, 'WebSocket connection error');
            };

            ws.onclose = (event) => {
                if (done) {
                    try {
                        console.debug(
                            '[Chatbot] WS: socket closed after completion code=' + event.code +
                            (event.reason ? ' reason=' + event.reason : '')
                        );
                    } catch (_) { /* ignore */ }
                    return;
                }
                console.info('[Chatbot] WS: closed code=' + event.code + (event.reason ? ' reason=' + event.reason : ''));
                if (ctx.buffer) {
                    // We got some data, consider it a success
                    finish(true);
                } else {
                    // Connection closed before any response - fall back to HTTP
                    finish(false, `Connection closed (${event.code})`);
                }
            };
        });
    }

    async streamResponseWithSSE(userMessage, sendOptions = {}, abortRef, detachRef, inflightKey) {
        const startTime = performance.now();

        const payload = this._buildUnifiedChatPayload(userMessage, sendOptions);
        this._log('SSE starting fetch', {
            conversation_id: payload.conversation_id || null,
            client_message_id: payload.client_message_id || null,
            preferred_language: payload.preferred_language,
            message_preview: String(userMessage || '').slice(0, 120)
        });

        const controller = new AbortController();
        // IMPORTANT: agent/tool queries can exceed 5 minutes; keep this generous.
        // If you want to tune this without editing JS, set `window.CHAT_SSE_TIMEOUT_MS` in a template.
        const timeoutMs = (typeof window.CHAT_SSE_TIMEOUT_MS === 'number' && window.CHAT_SSE_TIMEOUT_MS > 0)
            ? window.CHAT_SSE_TIMEOUT_MS
            : 600000; // 10 minutes
        let timedOut = false;
        let userAborted = false;
        let detached = false; // true when user switched conversation (detachRef), not a cancel
        const timeout = setTimeout(() => {
            timedOut = true;
            controller.abort();
        }, timeoutMs);
        const ctx = {
            buffer: '',
            messageElement: null,
            contentElement: null,
            finish: null,
            request_id: null,
            conversation_id: payload.conversation_id || null,
            _inflight_key: inflightKey || null,
            steps: [], // mirror of step/step_detail for restore after conversation switch
            lastFlushLength: 0,
            lastFlushTime: 0,
            _streamDone: false,
            _streamFlushPendingTimeout: null,
            _dlp_error: null,
            _userMessage: userMessage,
        };

        if (detachRef && typeof detachRef === 'object') {
            detachRef.current = () => {
                // Client-side disconnect only (do NOT signal server cancel). User switched conversation.
                detached = true;
                controller.abort();
            };
        }

        if (abortRef && typeof abortRef === 'object') {
            abortRef.current = () => {
                userAborted = true;
                // Best-effort: tell backend to cancel this request before aborting the fetch.
                // (When keep_running_on_disconnect=true, a pure abort would otherwise keep running.)
                try {
                    const reqId = ctx && ctx.request_id;
                    if (reqId) {
                        this._apiFetch('/api/ai/v2/chat/cancel', {
                            method: 'POST',
                            body: JSON.stringify({
                                request_id: String(reqId),
                                conversation_id: (ctx && ctx.conversation_id) ? String(ctx.conversation_id) : null,
                            })
                        }).catch(() => {});
                    }
                } catch (e) { /* ignore */ }
                console.log('[Chatbot SSE] Stop: aborting fetch');
                controller.abort();
            };
            this._log('SSE abortRef.current set (SSE abort)');
        }

        return new Promise(async (resolve, reject) => {
            let done = false;
            const finish = (success = true, errorMsg = 'SSE error') => {
                if (done) return;
                done = true;
                clearTimeout(timeout);
                const elapsed = (performance.now() - startTime).toFixed(0);
                this._log('SSE finish', success ? 'SUCCESS' : 'FAILED', { elapsed_ms: elapsed, error: success ? null : errorMsg });

                if (ctx.contentElement) ctx.contentElement.classList.remove('streaming-cursor');

                if (success) {
                    this.hideTypingIndicator();
                    if (ctx.buffer) {
                        const entry = {
                            message: ctx.buffer,
                            isUser: false,
                            timestamp: new Date().toISOString()
                        };
                        if (ctx.structuredPayload) entry.structuredPayload = ctx.structuredPayload;
                        this.conversationHistory.push(entry);
                        const maxHistory = this._isImmersive() ? 500 : 20;
                        if (this.conversationHistory.length > maxHistory) {
                            this.conversationHistory = this.conversationHistory.slice(-maxHistory);
                        }
                        this.saveConversationHistory();
                    }
                    this.isTyping = false;
                    this.elements.sendBtn.disabled = false;
                    resolve(ctx.buffer);
                } else {
                    if (ctx.messageElement && ctx.messageElement.parentNode) {
                        ctx.messageElement.parentNode.removeChild(ctx.messageElement);
                    }
                    if (ctx && ctx._dlp_error) {
                        reject(this._makeDlpError(ctx._dlp_error));
                    } else {
                        reject(new Error(errorMsg));
                    }
                }
            };
            ctx.finish = finish;

            try {
                const resp = await fetch('/api/ai/v2/chat/stream', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'text/event-stream',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content'),
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify(payload),
                    signal: controller.signal,
                });

                if (!resp.ok || !resp.body) {
                    throw (window.httpErrorSync && window.httpErrorSync(resp, `SSE HTTP error! status: ${resp.status}`)) || new Error(`SSE HTTP error! status: ${resp.status}`);
                }
                this._log('SSE response open', { status: resp.status, content_type: resp.headers.get('content-type') });

                const reader = resp.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let sseBuffer = '';
                let parsedEvents = 0;

                while (true) {
                    const { value, done: streamDone } = await reader.read();
                    if (streamDone) break;
                    sseBuffer += decoder.decode(value, { stream: true });

                    // Process complete SSE events separated by blank line
                    const parts = sseBuffer.split('\n\n');
                    sseBuffer = parts.pop() || '';

                    for (const part of parts) {
                        const lines = part.split('\n');
                        const dataLines = lines
                            .filter(l => l.startsWith('data:'))
                            .map(l => l.slice(5).trim());
                        if (!dataLines.length) continue;
                        const dataStr = dataLines.join('\n');
                        let msg;
                        try {
                            msg = JSON.parse(dataStr);
                        } catch (e) {
                            console.warn('[Chatbot SSE] Failed to parse event:', dataStr);
                            continue;
                        }
                        parsedEvents += 1;
                        if (parsedEvents <= 5 || (parsedEvents % 50 === 0)) {
                            this._log('SSE event parsed', { n: parsedEvents, type: msg?.type, keys: msg ? Object.keys(msg) : [] });
                        }
                        this.processStreamingMessage(msg, ctx);
                    }
                }

                // If the stream ended without a done event:
                // In immersive mode the server may still be running (keep_running_on_disconnect),
                // so treat as detach and let polling pick up the result.
                if (!done) {
                    if (this._isImmersive()) {
                        done = true;
                        clearTimeout(timeout);
                        if (ctx.contentElement) ctx.contentElement.classList.remove('streaming-cursor');
                        this._log('SSE stream ended without done in immersive mode; treating as detach');
                        if (inflightKey) {
                            const inflight = this._inflightByConversationKey.get(inflightKey);
                            if (inflight) inflight.detached = true;
                        }
                        const steps = Array.isArray(ctx.steps) && ctx.steps.length ? ctx.steps.map(s => ({ message: s.message || '', detail_lines: Array.isArray(s.detail_lines) ? s.detail_lines.slice() : [] })) : null;
                        if (steps) {
                            const key = ctx.conversation_id || (ctx._inflight_key && String(ctx._inflight_key).startsWith('draft:') ? null : ctx._inflight_key);
                            if (key) {
                                this._detachedInflightStepsByKey.set(key, { steps, request_id: ctx.request_id || null });
                            }
                        }
                        resolve(ctx.buffer || '');
                    } else {
                        const elapsed = (performance.now() - startTime).toFixed(0);
                        finish(false, `SSE stream ended unexpectedly (${elapsed}ms)`);
                    }
                }
            } catch (e) {
                const isAbort = e && (e.name === 'AbortError' || /aborted|cancelled|canceled/i.test(String(e.message || '')));
                if (isAbort) {
                    if (detached) {
                        // User switched conversation: stop updating UI but do not treat as cancel.
                        done = true;
                        clearTimeout(timeout);
                        if (ctx.contentElement) ctx.contentElement.classList.remove('streaming-cursor');
                        this._log('Stream detached (user switched conversation), request continues on server');
                        const steps = Array.isArray(ctx.steps) && ctx.steps.length ? ctx.steps.map(s => ({ message: s.message || '', detail_lines: Array.isArray(s.detail_lines) ? s.detail_lines.slice() : [] })) : null;
                        if (steps) {
                            const key = ctx.conversation_id || (ctx._inflight_key && String(ctx._inflight_key).startsWith('draft:') ? null : ctx._inflight_key);
                            if (key) {
                                this._detachedInflightStepsByKey.set(key, { steps, request_id: ctx.request_id || null });
                            }
                        }
                        resolve(ctx.buffer || '');
                    } else if (timedOut && !userAborted) {
                        if (this._isImmersive()) {
                            // In immersive mode the server continues (keep_running_on_disconnect);
                            // treat timeout like a detach so polling picks up the result instead of
                            // falling back to a new HTTP request (which would duplicate the agent execution).
                            done = true;
                            clearTimeout(timeout);
                            if (ctx.contentElement) ctx.contentElement.classList.remove('streaming-cursor');
                            this._log('SSE timed out in immersive mode; treating as detach (server continues)');
                            if (inflightKey) {
                                const inflight = this._inflightByConversationKey.get(inflightKey);
                                if (inflight) inflight.detached = true;
                            }
                            const steps = Array.isArray(ctx.steps) && ctx.steps.length ? ctx.steps.map(s => ({ message: s.message || '', detail_lines: Array.isArray(s.detail_lines) ? s.detail_lines.slice() : [] })) : null;
                            if (steps) {
                                const key = ctx.conversation_id || (ctx._inflight_key && String(ctx._inflight_key).startsWith('draft:') ? null : ctx._inflight_key);
                                if (key) {
                                    this._detachedInflightStepsByKey.set(key, { steps, request_id: ctx.request_id || null });
                                }
                            }
                            resolve(ctx.buffer || '');
                        } else {
                            finish(false, `SSE request timed out after ${timeoutMs}ms`);
                        }
                    } else {
                        // Treat as user cancellation (Stop button).
                        done = true;
                        clearTimeout(timeout);
                        if (ctx.contentElement) ctx.contentElement.classList.remove('streaming-cursor');
                        if (ctx.messageElement && ctx.messageElement.parentNode) {
                            ctx.messageElement.parentNode.removeChild(ctx.messageElement);
                        }
                        reject(e);
                    }
                } else {
                    finish(false, e?.message || 'SSE error');
                }
            }
        });
    }

    createStreamingMessageElement() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message bot';
        messageDiv.setAttribute('dir', 'auto');

        const wrap = document.createElement('div');
        wrap.className = 'flex items-start gap-2';

        const content = document.createElement('div');
        content.className = 'chat-message-content streaming-cursor';

        wrap.appendChild(content);
        messageDiv.appendChild(wrap);

        this.elements.messages.appendChild(messageDiv);
        this.scrollToBottom();

        return messageDiv;
    }

    getStreamingSafeHtml(html) {
        /**
         * Prepare HTML for progressive rendering during streaming.
         * Handles incomplete tags by closing any open tags at the end.
         * This allows formatted text to appear progressively like ChatGPT.
         */
        if (!html) return '';

        // First, sanitize the HTML for safety
        let safe = this.sanitizeHtml(html);

        // Check if we have an incomplete tag at the end (e.g., "<str" or "<a href=")
        const lastOpenBracket = safe.lastIndexOf('<');
        const lastCloseBracket = safe.lastIndexOf('>');

        if (lastOpenBracket > lastCloseBracket) {
            // We have an incomplete tag - remove it for now
            safe = safe.substring(0, lastOpenBracket);
        }

        // Track open tags and close them
        const openTags = [];
        const tagRegex = /<\/?([a-zA-Z][a-zA-Z0-9]*)[^>]*\/?>/g;
        let match;

        while ((match = tagRegex.exec(safe)) !== null) {
            const fullTag = match[0];
            const tagName = match[1].toLowerCase();

            // Skip self-closing tags and void elements
            const voidElements = ['br', 'hr', 'img', 'input', 'meta', 'link', 'area', 'base', 'col', 'embed', 'param', 'source', 'track', 'wbr'];
            if (voidElements.includes(tagName) || fullTag.endsWith('/>')) {
                continue;
            }

            if (fullTag.startsWith('</')) {
                // Closing tag - remove from stack if matches
                const idx = openTags.lastIndexOf(tagName);
                if (idx !== -1) {
                    openTags.splice(idx, 1);
                }
            } else {
                // Opening tag - add to stack
                openTags.push(tagName);
            }
        }

        // Close any remaining open tags (in reverse order)
        for (let i = openTags.length - 1; i >= 0; i--) {
            safe += `</${openTags[i]}>`;
        }

        return safe;
    }

    async getAIResponse(userMessage, sendOptions = {}, abortRef) {
        // Try to get response from backend API first
        try {
            const response = await this.callBackendAPI(userMessage, sendOptions, abortRef);
            if (response) {
                this.apiAvailable = true;
                if (this.debug) this.debug.chatbotAPI('success', 'Backoffice API Available', {status: '🟢 Available'});
                return response;
            }
        } catch (error) {
            this.apiAvailable = false;
            this._lastAPIError = error;
            if (this.debug) this.debug.chatbotAPI('failure', 'Backoffice API Unavailable', {status: '🔴 Unavailable', error: error.message});
            console.warn('Backoffice API unavailable:', error);
        }

        // OpenAI-only: no local/provider fallbacks. Return a clear error message.
        // Caller must treat this as an error (addErrorMessage with retry), not a normal bubble.
        return "⚠️ <strong>AI service unavailable.</strong><br><br>Please try again in a moment.";
    }

    _isServiceUnavailableResponse(response) {
        if (response == null || typeof response !== 'string') return false;
        const s = response.trim();
        return s.includes('AI service unavailable') || /service\s+unavailable/i.test(s);
    }

    async callBackendAPI(userMessage, sendOptions = {}, abortRef) {
        const startTime = performance.now();

        try {
            // Debug log: Context collection
            if (this.debug) {
                this.debug.chatbotContext(this.getPageContext());
            }

            const payload = this._buildUnifiedChatPayload(userMessage, sendOptions);

            // Debug log: Request payload
            if (this.debug) {
                const payloadSize = new Blob([JSON.stringify(payload)]).size;
                this.debug.chatbotAPI('request', 'API Call Starting', {
                    Endpoint: this.apiEndpoint,
                    Timestamp: new Date().toISOString(),
                    Message: userMessage,
                    Language: this.preferredLanguage,
                    'Conversation History Length': this.conversationHistory.length,
                    'Payload Size': `${(payloadSize / 1024).toFixed(2)} KB`,
                    'Full Payload': payload
                });
            }

            // Long timeout for agent runs (tool calls + LLM); 5 min to avoid "trouble connecting" on slow answers
            const controller = new AbortController();
            const timeoutMs = 300000;
            const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
            if (abortRef && typeof abortRef === 'object') {
                abortRef.current = () => {
                    this._log('HTTP Stop: aborting fetch');
                    controller.abort();
                };
                this._log('HTTP abortRef.current set (callBackendAPI abort)');
            }
            let response;
            try {
                response = await fetch(this.apiEndpoint, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content'),
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify(payload),
                    signal: controller.signal
                });
            } finally {
                clearTimeout(timeoutId);
            }

            if (!response.ok) {
                // Try to parse JSON error bodies (e.g. DLP confirmation) before throwing.
                let errBody = null;
                try {
                    const ct = response.headers.get('content-type') || '';
                    if (ct.includes('application/json')) {
                        errBody = await response.json();
                    }
                } catch (_) { /* ignore */ }
                if (errBody && errBody.error_type && String(errBody.error_type).startsWith('dlp_')) {
                    throw this._makeDlpError(errBody);
                }
                throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            const endTime = performance.now();
            const duration = (endTime - startTime).toFixed(2);

            if (this._isImmersive() && data.conversation_id && !this.getActiveConversationId()) {
                this._setImmersiveActiveId(data.conversation_id);
                this._dispatchImmersiveUpdate();
                this._updateImmersiveUrl(true);
            } else if (!this._isImmersive() && data.conversation_id && !this._getFloatingConversationId()) {
                this._setFloatingConversationId(data.conversation_id);
            }
            this._scheduleConversationTitleRefresh(data.conversation_id || this.getActiveConversationId(), 400);

            const _meta = data.meta && typeof data.meta === 'object' ? data.meta : {};
            const _httpPieces = [];
            const _mp = data.map_payload || _meta.map_payload;
            const _cp = data.chart_payload || _meta.chart_payload;
            const _tp = data.table_payload || _meta.table_payload;
            if (_mp && typeof _mp === 'object') _httpPieces.push(_mp);
            if (_cp && typeof _cp === 'object') _httpPieces.push(_cp);
            if (_tp && typeof _tp === 'object') _httpPieces.push(_tp);
            this._pendingStructuredRawPieces = _httpPieces.length ? _httpPieces : null;
            this._setPendingStructuredPayload(null);

            // Store confidence / grounding metadata for the next addMessage call
            if (data.meta && (data.meta.confidence || data.meta.grounding_score != null)) {
                this._pendingConfidence = {
                    confidence: data.meta.confidence || null,
                    grounding_score: data.meta.grounding_score != null ? data.meta.grounding_score : null,
                };
            } else {
                this._pendingConfidence = null;
            }

            // Debug log: Response data
            if (this.debug) {
                const responseSize = new Blob([JSON.stringify(data)]).size;
                this.debug.chatbotAPI('response', 'API Call Successful', {
                    Duration: `${duration}ms`,
                    'Response Size': `${(responseSize / 1024).toFixed(2)} KB`,
                    'Detected Language': data.detected_language,
                    'Response Text': data.response,
                    'Full Response': data
                });
            }

            // Update preferred language if it was detected/changed (v2 may not send this)
            if (data.detected_language && data.detected_language !== this.preferredLanguage) {
                this._setPreferredLanguage(data.detected_language);
                if (this.debug) this.debug.chatbot(`Language preference updated to: ${this.preferredLanguage}`);
            }

            // Unified API returns reply (v2); legacy chatbot returned response
            return data.reply != null ? data.reply : data.response;
        } catch (error) {
            const endTime = performance.now();
            const duration = (endTime - startTime).toFixed(2);

            // Debug log: API error
            if (this.debug) {
                this.debug.chatbotAPI('error', 'API Call Failed', {
                    Duration: `${duration}ms`,
                    'Error Type': error.name,
                    'Error Message': error.message,
                    'Full Error': error
                });
            }

            console.error('Backoffice API error:', error);
            throw error;
        }
    }

    getPageContext() {
        /**
         * Collect comprehensive context about the current page
         * This helps the AI understand what page the user is on and provide relevant help
         */
        const context = {
            // Basic page info
            currentPage: window.location.pathname,
            currentUrl: window.location.href,
            pageTitle: document.title,
            userAgent: navigator.userAgent,
            timestamp: new Date().toISOString(),

            // Page content analysis
            pageContent: {},

            // User interface elements
            uiElements: {},

            // Page-specific data
            pageData: {}
        };

        try {
            // Extract page content
            const mainContent = document.querySelector('#pageContentContainer, main, [role="main"]');
            if (mainContent) {
                // Get headings to understand page structure (sanitized)
                const headings = Array.from(mainContent.querySelectorAll('h1, h2, h3')).map(h => ({
                    level: h.tagName.toLowerCase(),
                    text: this.escapeHtml(h.textContent.trim())
                })).slice(0, 10); // Limit to first 10 headings

                context.pageContent.headings = headings;
                context.pageContent.mainHeading = this.escapeHtml(document.querySelector('h1')?.textContent?.trim() || '');
            }

            // Detect page type based on URL patterns
            const path = window.location.pathname.toLowerCase();
            const pageTitle = context.pageTitle || '';

            if (path.includes('/admin/dashboard')) {
                context.pageData.pageType = 'admin_dashboard';
                context.pageData.description = 'Administrative dashboard with system overview and management tools';
            } else if (path.includes('/dashboard') || (path === '/' && pageTitle.includes('Dashboard'))) {
                // Detect dashboard type based on page content or user role
                const mainHeading = context.pageContent?.mainHeading || '';
                const headings = context.pageContent?.headings || [];
                const hasAssignmentHeading = headings.some(h => h.text && h.text.includes('Assignments for'));
                const hasCountrySpecificContent = headings.some(h => h.text && (h.text.includes('for Afghanistan') || h.text.includes('for ') || h.text.includes('Focal Points')));

                if (path.includes('/admin') || pageTitle.includes('Admin')) {
                    context.pageData.pageType = 'admin_dashboard';
                    context.pageData.description = 'Administrative dashboard with system overview and management tools';
                } else if (mainHeading === 'Dashboard' && (hasAssignmentHeading || hasCountrySpecificContent)) {
                    context.pageData.pageType = 'user_dashboard';
                    context.pageData.description = 'Focal point dashboard showing assignments and country-specific data';
                } else {
                    context.pageData.pageType = 'user_dashboard';
                    context.pageData.description = 'User dashboard showing assignments and personal data';
                }
            } else if (path.includes('/templates') || path.includes('/manage_templates')) {
                context.pageData.pageType = 'template_management';
                context.pageData.description = 'Template management page for creating and editing form templates';
            } else if (path.includes('/assignments') || path.includes('/manage_assignments')) {
                context.pageData.pageType = 'assignment_management';
                context.pageData.description = 'Assignment management page for creating and managing form assignments';
            } else if (path.includes('/users') || path.includes('/manage_users')) {
                context.pageData.pageType = 'user_management';
                context.pageData.description = 'User management page for administering user accounts and permissions';
            } else if (path.includes('/countries') || path.includes('/manage_countries')) {
                context.pageData.pageType = 'country_management';
                context.pageData.description = 'Country management page for managing country data and assignments';
            } else if (path.includes('/indicator_bank') || path.includes('/manage_indicator_bank') || path.includes('/indicator-bank')) {
                context.pageData.pageType = 'indicator_bank';
                context.pageData.description = 'Indicator bank for managing data collection indicators';
            } else if (path.includes('/analytics') || path.includes('/audit')) {
                context.pageData.pageType = 'analytics';
                context.pageData.description = 'Analytics dashboard showing platform usage and data insights';
            } else if (path.includes('/forms/assignment/') || path.includes('/forms/public-submission/') ||
                       path.includes('/entry_form') || path.includes('/form/') ||
                       path.includes('/public/') || path.includes('/assignment_status/')) {
                context.pageData.pageType = 'data_entry_form';
                context.pageData.description = 'Data entry form for submitting information';
            } else if (path.includes('/documents') || path.includes('/manage_documents')) {
                context.pageData.pageType = 'document_management';
                context.pageData.description = 'Document management system for file uploads and organization';
            } else if (path.includes('/api_management') || path.includes('/api-management') || path.includes('/admin/api-management')) {
                context.pageData.pageType = 'api_management';
                context.pageData.description = 'API management console for monitoring and configuring API access';
            } else if (path.includes('/public_assignments') || path.includes('/public-assignments') || path.includes('/public_forms')) {
                context.pageData.pageType = 'public_assignment_management';
                context.pageData.description = 'Public form link management for external data collection';
            } else if (path.includes('/account_settings') || path.includes('/account-settings')) {
                context.pageData.pageType = 'account_settings';
                context.pageData.description = 'Account settings page for managing personal preferences and profile';
            } else {
                context.pageData.pageType = 'unknown';
                context.pageData.description = 'General platform page';
            }

            // Extract visible tables/data grids for context (native tables and generic grid roles)
            const genericGrids = document.querySelectorAll('[role="grid"], [role="treegrid"], .data-grid, .table-responsive [data-grid]');
            const tables = document.querySelectorAll('table');
            const allDataGrids = genericGrids.length > 0 ? genericGrids : tables;

            if (allDataGrids.length > 0) {
                context.uiElements.hasDataTables = true; // Keep name for backward compatibility
                context.uiElements.tableCount = allDataGrids.length;

                // Try to get table headers for context (sanitized)
                let headers = [];
                if (genericGrids.length > 0) {
                    // Generic grid: look for header cells first, then fallback to columnheader role
                    const firstGrid = genericGrids[0];
                    const headerCells = firstGrid.querySelectorAll('th, [role="columnheader"], .grid-header, .table-header');
                    headers = Array.from(headerCells).map(cell =>
                        this.escapeHtml(cell.textContent.trim())
                    ).filter(text => text.length > 0).slice(0, 8);
                } else if (tables.length > 0) {
                    // Regular table: get th elements
                    const firstTable = tables[0];
                    headers = Array.from(firstTable.querySelectorAll('th')).map(th =>
                        this.escapeHtml(th.textContent.trim())
                    ).filter(text => text.length > 0).slice(0, 8);
                }

                if (headers.length > 0) {
                    context.uiElements.tableHeaders = headers;
                }
            }

            // Check for forms
            const forms = document.querySelectorAll('form');
            if (forms.length > 0) {
                context.uiElements.hasForms = true;
                context.uiElements.formCount = forms.length;

                // Get form field types for context
                const fieldTypes = Array.from(document.querySelectorAll('input, select, textarea')).map(field =>
                    field.type || field.tagName.toLowerCase()
                ).filter((type, index, arr) => arr.indexOf(type) === index).slice(0, 10);

                if (fieldTypes.length > 0) {
                    context.uiElements.formFieldTypes = fieldTypes;
                }
            }

            // Check for buttons and action elements (sanitized)
            const actionButtons = Array.from(document.querySelectorAll('button, .btn, [data-action]')).map(btn =>
                this.escapeHtml(btn.textContent.trim() || btn.getAttribute('title') || btn.getAttribute('aria-label') || '')
            ).filter(text => text && text.length > 0 && text.length < 50).slice(0, 10);

            if (actionButtons.length > 0) {
                context.uiElements.actionButtons = actionButtons;
            }

            // Get breadcrumb information if available (sanitized)
            const breadcrumbs = document.querySelector('.breadcrumb, [role="navigation"] ol, .breadcrumbs');
            if (breadcrumbs) {
                const breadcrumbItems = Array.from(breadcrumbs.querySelectorAll('li, a')).map(item =>
                    this.escapeHtml(item.textContent.trim())
                ).filter(text => text.length > 0).slice(0, 6);

                if (breadcrumbItems.length > 0) {
                    context.uiElements.breadcrumbs = breadcrumbItems;
                }
            }

            // Check for flash messages or alerts
            const alerts = document.querySelectorAll('.alert, .flash-message, [role="alert"]');
            if (alerts.length > 0) {
                context.uiElements.hasAlerts = true;
                context.uiElements.alertCount = alerts.length;
            }

            // Check if we're in a modal or overlay (sanitized)
            const modals = document.querySelectorAll('.modal.show, .overlay.active, [aria-modal="true"]');
            if (modals.length > 0) {
                context.uiElements.inModal = true;
                const modalTitle = modals[0].querySelector('.modal-title, h1, h2, h3')?.textContent?.trim();
                if (modalTitle) {
                    context.uiElements.modalTitle = this.escapeHtml(modalTitle);
                }
            }

            // Add entry form tour step information if available
            if (context.pageData.pageType === 'data_entry_form' && typeof window.getEntryFormTourSteps === 'function') {
                try {
                    const tourSteps = window.getEntryFormTourSteps();
                    if (tourSteps && tourSteps.length > 0) {
                        context.pageData.tourSteps = tourSteps;
                        context.pageData.hasTour = true;
                        // Add helper text for chatbot
                        context.pageData.tourHelpText = 'Tour steps available for this page. User can start tour with window.startEntryFormTour() or window.startEntryFormTour(stepIndex) to go to specific step.';

                        // Debug log
                        if (this.debug) {
                            console.log('✅ Entry form tour detected:', tourSteps.length, 'steps available');
                        }
                    }
                } catch (e) {
                    // Tour steps not available
                    console.warn('Failed to get entry form tour steps:', e);
                }
            } else if (context.pageData.pageType === 'data_entry_form') {
                // Debug: page detected as entry form but tour not available
                if (this.debug) {
                    console.warn('⚠️ Page detected as data_entry_form but tour not available. window.getEntryFormTourSteps:', typeof window.getEntryFormTourSteps);
                }
            }

        } catch (error) {
            console.warn('Error collecting page context:', error);
        }

        return context;
    }

    getLocalPageExplanation() {
        /**
         * Provide local page explanation when backend is unavailable
         */
        try {
            const context = this.getPageContext();
            const pageData = context.pageData || {};
            const pageType = pageData.pageType || 'unknown';
            const pageTitle = context.pageTitle || 'Current Page';

            if (this.debug) this.debug.chatbot(`Generating local explanation for page type: ${pageType}`);

            let explanation = `<strong>📍 Current Page: ${pageTitle}</strong><br><br>`;

            // Get page explanation from external messages file
            const pageExplanations = this.messages.pageExplanations || {};
            const orgName = window.ORG_NAME || 'Humanitarian Databank';
            const pageInfo = pageExplanations[pageType] || pageExplanations.unknown || {
                title: 'Platform Page',
                emoji: '🎯',
                description: `You're viewing a page within the ${orgName} platform.`
            };

            explanation += `<strong>${pageInfo.emoji} ${pageInfo.title}</strong><br>${pageInfo.description}`;

            // Add UI context if available
            const uiElements = context.uiElements || {};
            if (uiElements.hasDataTables) {
                explanation += `<br><strong>📊 Data Tables:</strong> This page has ${uiElements.tableCount || 1} data table(s) for managing information.`;
            }
            if (uiElements.hasForms) {
                explanation += `<br><strong>📝 Forms:</strong> This page contains ${uiElements.formCount || 1} form(s) for data input.`;
            }
            if (uiElements.actionButtons && uiElements.actionButtons.length > 0) {
                const buttons = uiElements.actionButtons.slice(0, 3).join(', ');
                explanation += `<br><strong>⚡ Available Actions:</strong> ${buttons}`;
            }

            return explanation;

        } catch (error) {
            console.warn('Error generating local page explanation:', error);
            return `I can see you're asking about this page! While I can't analyze all the details right now, you're currently on: <strong>${document.title}</strong><br><br>What specific aspect of this page would you like to know about?`;
        }
    }

    getLocalResponse(userMessage, apiError = null) {
        // Legacy local response helper (not used in OpenAI-only mode)
        const message = userMessage.toLowerCase();

        if (this.debug) this.debug.chatbot('Using legacy local response helper');

        // If the API failed with a connection/network error, prepend a short notice so the user knows the server was unreachable
        const connectionNotice = (() => {
            if (!apiError) return '';
            const msg = (apiError.message || String(apiError)).toLowerCase();
            const isConnectionError = msg.includes('failed to fetch') || msg.includes('network') || msg.includes('connection') || msg.includes('reset') || (apiError.name && apiError.name.toLowerCase().includes('typeerror'));
            if (!isConnectionError) return '';
            const notices = this.messages.errors?.serverUnavailable || {
                en: 'The Backoffice server could not be reached (connection reset or server not running).'
            };
            const notice = notices[this.preferredLanguage] || notices.en;
            return `<p class="mb-2 text-amber-700 dark:text-amber-400"><strong>${notice}</strong></p>`;
        })();

        // Handle page-specific requests locally
        const pagePatterns = this.messages.pageExplanationPatterns || ['explain this page', 'what is this page'];
        if (pagePatterns.some(pattern => message.includes(pattern))) {
            return connectionNotice + this.getLocalPageExplanation();
        }

        // Use knowledge base from external messages file
        const knowledgeBase = this.messages.knowledgeBase || {};

        // Find best match
        let bestMatch = null;
        let maxScore = 0;

        for (const [key, data] of Object.entries(knowledgeBase)) {
            const score = data.keywords.reduce((acc, keyword) => {
                return acc + (message.includes(keyword) ? keyword.length : 0);
            }, 0);

            if (score > maxScore) {
                maxScore = score;
                bestMatch = data;
            }
        }

        if (bestMatch && maxScore > 0) {
            if (this.debug) this.debug.chatbot(`Matched knowledge base topic: ${bestMatch.keywords[0]}`);
            return connectionNotice + bestMatch.response;
        }

        // Handle greetings
        const greetingPatterns = this.messages.greetingPatterns || ['hello', 'hi', 'hey'];
        if (greetingPatterns.some(pattern => message.includes(pattern))) {
            const greetings = this.messages.greetings || {};
            return connectionNotice + (greetings[this.preferredLanguage] || greetings.en || "Hello! How can I help you?");
        }

        // Handle thank you
        const thankPatterns = this.messages.thankYouPatterns || ['thank', 'thanks'];
        if (thankPatterns.some(pattern => message.includes(pattern))) {
            const thankYouResponses = this.messages.thankYouResponses || {};
            return connectionNotice + (thankYouResponses[this.preferredLanguage] || thankYouResponses.en || "You're welcome!");
        }

        // Default helpful response
        const defaultResponses = this.messages.defaultResponse || {};
        return connectionNotice + (defaultResponses[this.preferredLanguage] || defaultResponses.en || "How can I help you?");
    }

    setExpanded(expanded) {
        this.isExpanded = true; /* Always maximized */
        if (expanded) {
            setTimeout(() => this.scrollToBottom(), 100);
        }
    }

    saveConversationHistory() {
        try {
            if (this._isImmersive()) {
                // Backend persists via /api/ai/v2/chat; just notify sidebar to refresh list/title
                this._dispatchImmersiveUpdate();
                return;
            }
            localStorage.setItem(this.storageKey, JSON.stringify(this.conversationHistory));
        } catch (error) {
            console.warn('Failed to save conversation history:', error);
        }
    }

    loadConversationHistory() {
        try {
            if (this._isImmersive()) {
                this._loadImmersiveConversation();
                return;
            }
            const saved = localStorage.getItem(this.storageKey);
            if (saved) {
                this.conversationHistory = JSON.parse(saved);

                // Clear existing messages
                this.elements.messages.replaceChildren();

                // Restore conversation
                this.conversationHistory.forEach((entry, index) => {
                    const opts = entry.isError ? { isError: true, retryMessage: entry.retryMessage || '' } : {};
                    if (!entry.isError && entry.structuredPayload) opts.structuredPayload = entry.structuredPayload;
                    if (entry.traceId != null) opts.traceId = entry.traceId;
                    this.addMessageToDOM(entry.message, entry.isUser, index, opts);
                });
            }
            // Don't show welcome message automatically on page load
            this._updateAiNoticeVisibility();
        } catch (error) {
            console.warn('Failed to load conversation history:', error);
            // Don't show welcome message as fallback on page load
        }
    }

    _getImmersiveActiveId() {
        try {
            return localStorage.getItem(this.immersiveActiveIdKey) || null;
        } catch (e) { return null; }
    }

    _setImmersiveActiveId(id) {
        this.activeConversationId = id || null;
        try {
            if (id) localStorage.setItem(this.immersiveActiveIdKey, id);
            else localStorage.removeItem(this.immersiveActiveIdKey);
        } catch (e) { /* ignore */ }
    }

    _getImmersiveChatPath() {
        if (!this._isImmersive()) return '/chat';
        const id = this.getActiveConversationId();
        return id ? '/chat/' + encodeURIComponent(id) : '/chat';
    }

    _updateImmersiveUrl(useReplace) {
        if (!this._isImmersive()) return;
        const path = this._getImmersiveChatPath();
        const url = window.location.origin + path + (window.location.search || '') + (window.location.hash || '');
        try {
            if (useReplace) {
                history.replaceState({ chatPath: path }, '', url);
            } else {
                history.pushState({ chatPath: path }, '', url);
            }
        } catch (e) { /* ignore */ }
    }

    _handleImmersivePopstate() {
        if (!this._isImmersive()) return;
        const path = window.location.pathname;
        if (path === '/chat' || path === '/chat/') {
            this.startNewChat();
        } else {
            const m = path.match(/^\/chat\/([^/]+)$/);
            if (m) this.switchChat(m[1]);
        }
    }

    _getFloatingConversationId() {
        try {
            return localStorage.getItem(this.floatingConversationIdKey) || null;
        } catch (e) { return null; }
    }

    _setFloatingConversationId(id) {
        try {
            if (id) localStorage.setItem(this.floatingConversationIdKey, id);
            else localStorage.removeItem(this.floatingConversationIdKey);
        } catch (e) { /* ignore */ }
        this._updateImmersiveLinkHref();
        if (!this._isImmersive()) {
            if (id) void this._refreshFloatingHeaderTitleFromServer();
            else this._resetFloatingHeaderTitleToDefault();
        }
    }

    _updateImmersiveLinkHref() {
        if (this._isImmersive() || !this.elements.immersiveBtn || !this.elements.widget) return;
        let url = this.elements.widget.getAttribute('data-immersive-url') || '/chat';
        const conversationId = this._getFloatingConversationId();
        if (conversationId) {
            url = url.replace(/\/+$/, '') + '/' + encodeURIComponent(conversationId);
        }
        this.elements.immersiveBtn.setAttribute('href', url);
    }

    _toggleFloatingSidebar() {
        if (!this.elements.widget) return;
        const open = this.elements.widget.classList.toggle('chat-sidebar-open');
        if (open && this.elements.floatingChatList) {
            this._renderFloatingConversationList();
        }
    }

    _escapeAttr(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    _renderFloatingConversationList() {
        const listEl = this.elements.floatingChatList;
        if (!listEl || this._isImmersive()) return;

        listEl.innerHTML = '<li class="chat-floating-chat-list-loading">Loading…</li>';

        this._apiFetch('/api/ai/v2/conversations')
            .then(res => res.ok ? res.json() : { conversations: [] })
            .then(data => {
                const conversations = data.conversations || [];
                const activeId = this.getActiveConversationId();

                try { listEl.replaceChildren(); } catch (_) { listEl.innerHTML = ''; }

                if (!conversations.length) {
                    this._syncFloatingHeaderTitleFromConversationList([]);
                    return;
                }

                const newChatLabel = this._uiString('newChat') || 'New chat';
                const deleteChatLabel = this._uiString('deleteChat') || 'Delete chat';

                conversations.forEach((chat) => {
                    if (!chat || !chat.id) return;
                    const chatId = String(chat.id);
                    const titleText = String(chat.title || newChatLabel || '');
                    const isActive = chat.id === activeId;

                    const li = document.createElement('li');
                    li.className = 'chat-floating-chat-item' + (isActive ? ' is-active' : '');
                    li.setAttribute('data-chat-id', chatId);

                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'chat-floating-chat-item-btn';
                    btn.addEventListener('click', () => this.switchChat(chatId));

                    const icon = document.createElement('i');
                    icon.className = 'fas fa-message chat-floating-chat-item-icon';
                    icon.setAttribute('aria-hidden', 'true');

                    const span = document.createElement('span');
                    span.className = 'chat-floating-chat-item-title';
                    span.textContent = titleText;

                    btn.appendChild(icon);
                    btn.appendChild(document.createTextNode(' '));
                    btn.appendChild(span);

                    const del = document.createElement('button');
                    del.type = 'button';
                    del.className = 'chat-floating-chat-item-delete';
                    del.setAttribute('aria-label', deleteChatLabel);
                    del.title = deleteChatLabel;
                    del.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        const msg = this._uiString('deleteConversationConfirm');
                        const title = this._uiString('deleteConversationTitle');
                        const deleteLabel = this._uiString('delete');
                        const cancelLabel = this._uiString('cancel');
                        if (typeof window.showDangerConfirmation === 'function') {
                            window.showDangerConfirmation(
                                msg,
                                () => this.deleteChat(chatId),
                                null,
                                deleteLabel,
                                cancelLabel,
                                title
                            );
                        } else if (window.showConfirmation) {
                            window.showConfirmation(msg, () => this.deleteChat(chatId), null, deleteLabel, cancelLabel, title);
                        }
                    });

                    const delIcon = document.createElement('i');
                    delIcon.className = 'fas fa-trash';
                    delIcon.setAttribute('aria-hidden', 'true');
                    del.appendChild(delIcon);

                    li.appendChild(btn);
                    li.appendChild(del);
                    listEl.appendChild(li);
                });
                this._syncFloatingHeaderTitleFromConversationList(conversations);
            })
            .catch(() => { listEl.innerHTML = ''; });
    }

    _apiFetch(url, options = {}) {
        const opts = {
            headers: {
                'Content-Type': 'application/json',
                ...(options.headers || {})
            },
            ...options
        };
        return ((window.getFetch && window.getFetch()) || fetch)(url, opts);
    }

    _renderInflightProgress(inflight) {
        try {
            if (!inflight || typeof inflight !== 'object') return false;
            if (inflight.status && String(inflight.status) !== 'in_progress') return false;
            const steps = inflight.steps;
            if (!Array.isArray(steps) || steps.length === 0) return false;

            if (!document.getElementById('typingIndicator')) {
                this.showTypingIndicator();
            }
            const panel = document.getElementById('typingIndicator');
            if (!panel) return false;
            const stepsList = panel.querySelector('.chat-progress-steps');
            if (!stepsList) return false;

            // Server-persisted inflight.steps can lag behind WebSocket step events. Replacing the
            // whole list would flash back to "Preparing query…" until the DB catches up.
            const domStepCount = stepsList.querySelectorAll('.chat-progress-step').length;
            const preparingLabel = (this._uiString && this._uiString('preparingQuery')) || 'Preparing query…';
            const firstMsg = steps[0] && typeof steps[0] === 'object' ? String((steps[0].message || '')).trim() : '';
            const serverOnlyPreparing = steps.length === 1 && firstMsg === preparingLabel;
            if (domStepCount > steps.length || (serverOnlyPreparing && domStepCount > 1)) {
                return true;
            }

            // Avoid re-render when no change (best-effort)
            const hash = (() => {
                try { return JSON.stringify({ steps, updated_at: inflight.updated_at || null }); } catch (e) { return null; }
            })();
            if (hash && this._inflightLastRendered === hash) return true;
            if (hash) this._inflightLastRendered = hash;

            stepsList.replaceChildren();

            const lastIdx = steps.length - 1;
            for (let i = 0; i < steps.length; i++) {
                const s = steps[i] || {};
                const msg = (typeof s === 'string') ? s : (s.message || '');
                const message = String(msg || '').trim();
                if (!message) continue;

                const li = document.createElement('li');
                const isLast = i === lastIdx;
                li.className = 'chat-progress-step ' + (isLast ? 'chat-progress-step-active' : 'chat-progress-step-done');

                const icon = document.createElement('i');
                icon.className = isLast
                    ? 'fas fa-spinner fa-spin chat-progress-step-icon'
                    : 'fas fa-check chat-progress-step-icon chat-progress-step-done';
                icon.setAttribute('aria-hidden', 'true');

                const label = document.createElement('span');
                label.className = 'chat-progress-step-label';
                label.textContent = message;

                const detailLines = (s && typeof s === 'object') ? (Array.isArray(s.detail_lines) ? s.detail_lines : []) : [];
                const detailText = detailLines.map(x => String(x || '').trim()).filter(Boolean).join('\n');
                if (detailText) {
                    const row = document.createElement('div');
                    row.className = 'chat-progress-step-row';
                    row.append(icon, label);
                    const toggleIcon = document.createElement('i');
                    toggleIcon.className = 'fas fa-chevron-down chat-progress-step-detail-toggle';
                    toggleIcon.setAttribute('aria-hidden', 'true');
                    row.appendChild(toggleIcon);
                    const detailEl = document.createElement('div');
                    detailEl.className = 'chat-progress-step-detail';
                    detailEl.textContent = detailText;
                    li.append(row, detailEl);
                    row.setAttribute('role', 'button');
                    row.setAttribute('tabIndex', '0');
                    row.setAttribute('aria-expanded', 'true');
                    row.addEventListener('click', () => {
                        li.classList.toggle('chat-progress-step-detail-collapsed');
                        const collapsed = li.classList.contains('chat-progress-step-detail-collapsed');
                        row.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
                        toggleIcon.className = collapsed ? 'fas fa-chevron-right chat-progress-step-detail-toggle' : 'fas fa-chevron-down chat-progress-step-detail-toggle';
                    });
                    row.addEventListener('keydown', (e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            row.click();
                        }
                    });
                } else {
                    li.append(icon, label);
                }
                stepsList.appendChild(li);
            }
            this.scrollToBottom();
            return true;
        } catch (e) {
            return false;
        }
    }

    _maybeRestoreInflightFromConversationResponse(convData, conversationId) {
        // convData comes from GET /api/ai/v2/conversations/:id
        try {
            let inflight = convData && convData.conversation && convData.conversation.meta
                ? convData.conversation.meta.inflight
                : null;
            let cached = conversationId ? this._detachedInflightStepsByKey.get(conversationId) : null;
            // If server meta lost inflight (e.g. rare race) but we still have steps from a detach, recover UI + poll.
            if ((!inflight || typeof inflight !== 'object') && cached && Array.isArray(cached.steps) && cached.steps.length) {
                const clonedSteps = cached.steps.map((s) => ({
                    message: (s && s.message) || '',
                    detail_lines: Array.isArray(s && s.detail_lines) ? s.detail_lines.slice() : [],
                }));
                inflight = {
                    status: 'in_progress',
                    request_id: cached.request_id || null,
                    started_at: new Date().toISOString(),
                    steps: clonedSteps,
                };
                if (conversationId) this._detachedInflightStepsByKey.delete(conversationId);
                cached = null;
                this._log('Restore inflight: using detached step cache (server meta had no inflight)');
            }
            if (!inflight || typeof inflight !== 'object') {
                this._log('Restore inflight: no inflight in conversation meta');
                return false;
            }
            if (inflight.status && String(inflight.status) !== 'in_progress') {
                this._log('Restore inflight: status is not in_progress (status=' + inflight.status + ')');
                return false;
            }

            // Basic staleness guard (client-side): ignore inflight snapshots older than 30 minutes.
            const startedAt = inflight.started_at ? Date.parse(String(inflight.started_at)) : NaN;
            if (!isNaN(startedAt)) {
                const ageMs = Date.now() - startedAt;
                if (ageMs > 30 * 60 * 1000) {
                    this._log('Restore inflight: snapshot is stale (age=' + Math.round(ageMs / 1000) + 's), ignoring');
                    return false;
                }
            }

            // When user switched away mid-stream we saved steps to _detachedInflightStepsByKey.
            // Prefer that cache if the server returned only "Preparing query…" so steps don't disappear.
            const serverSteps = Array.isArray(inflight.steps) ? inflight.steps : [];
            const preparingLabel = (this._uiString && this._uiString('preparingQuery')) || 'Preparing query…';
            const serverOnlyPreparing = serverSteps.length === 1 && (serverSteps[0].message || '').trim() === preparingLabel;
            const useCachedSteps = cached && Array.isArray(cached.steps) && cached.steps.length > 0 &&
                (serverOnlyPreparing || cached.steps.length > serverSteps.length);
            if (useCachedSteps) {
                this._log('Restore inflight: using in-memory cached steps (' + cached.steps.length + ') over server steps (' + serverSteps.length + ')');
                inflight.steps = cached.steps;
                this._detachedInflightStepsByKey.delete(conversationId);
            } else {
                this._log('Restore inflight: using server steps (' + serverSteps.length + ') — steps:', serverSteps.map(s => s.message || '').join(' → '));
            }
            // Also clear any other key that might point to this conversation (e.g. draft key)
            if (conversationId) {
                for (const [k, v] of this._detachedInflightStepsByKey.entries()) {
                    if (k === conversationId) continue;
                    if (v && v.request_id && inflight.request_id && String(v.request_id) === String(inflight.request_id)) {
                        this._detachedInflightStepsByKey.delete(k);
                        break;
                    }
                }
            }

            const rendered = this._renderInflightProgress(inflight);
            this._log('Restore inflight: rendered=' + rendered + ' steps=' + (Array.isArray(inflight.steps) ? inflight.steps.length : 0) + ' request_id=' + (inflight.request_id || '?'));
            if (rendered) {
                const reqId = inflight.request_id ? String(inflight.request_id) : null;
                this._startInflightPoll(conversationId, reqId);
            }
            return rendered;
        } catch (e) {
            this._warn('Restore inflight: exception:', e);
            return false;
        }
    }

    _startInflightPoll(conversationId, requestId) {
        if (!this._isImmersive()) return;
        if (!conversationId) return;

        // Already polling this request
        if (this._inflightPollConversationId === conversationId && this._inflightPollRequestId === requestId && this._inflightPollTimer) {
            return;
        }

        this._stopInflightPoll();
        this._inflightPollConversationId = conversationId;
        this._inflightPollRequestId = requestId || null;
        this._inflightPollPrevTitle = undefined;

        const pollOnce = async () => {
            // Poll until inflight is cleared and assistant message is persisted.
            // Keep interval modest to avoid load; server commits progress at a throttled rate.
            const activeId = this.getActiveConversationId();
            if (!activeId || activeId !== conversationId) {
                this._stopInflightPoll();
                return;
            }
            try {
                const res = await this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(conversationId)}`);
                if (!res.ok) {
                    // Retry later; don't kill the poll immediately on transient errors
                    this._inflightPollTimer = setTimeout(pollOnce, 2500);
                    return;
                }
                const data = await res.json();
                const inflight = data && data.conversation && data.conversation.meta ? data.conversation.meta.inflight : null;
                if (inflight && typeof inflight === 'object') {
                    // If request_id is set, ensure we only keep polling the same run.
                    if (this._inflightPollRequestId && inflight.request_id && String(inflight.request_id) !== String(this._inflightPollRequestId)) {
                        // Different request started; stop this poll and let normal UI handle it.
                        this._stopInflightPoll();
                        return;
                    }
                    this._renderInflightProgress(inflight);
                    const convObj = data && data.conversation ? data.conversation : null;
                    const polledTitle = convObj && convObj.title != null ? String(convObj.title).trim() : '';
                    if (this._inflightPollPrevTitle !== undefined && polledTitle && polledTitle !== this._inflightPollPrevTitle) {
                        this._refreshConversationSidebarTitles();
                    }
                    if (polledTitle || this._inflightPollPrevTitle !== undefined) {
                        this._inflightPollPrevTitle = polledTitle;
                    }
                    this._inflightPollTimer = setTimeout(pollOnce, 2000);
                    return;
                }

                // Inflight cleared: reload messages and hide progress.
                if (conversationId) this._detachedInflightStepsByKey.delete(conversationId);
                const messages = this._mapApiMessages(data.messages || []);
                this.conversationHistory = messages;
                this.elements.messages.replaceChildren();
                this.conversationHistory.forEach((entry, index) => {
                    const opts = entry.isError ? { isError: true, retryMessage: entry.retryMessage || '' } : (entry.structuredPayload ? { structuredPayload: entry.structuredPayload } : {});
                    if (entry.traceId != null) opts.traceId = entry.traceId;
                    this.addMessageToDOM(entry.message, entry.isUser, index, opts);
                });
                this.hideTypingIndicator();
                this._updateImmersiveQuickPromptsVisibility();
                this.scrollToBottom();
                this._stopInflightPoll();
                // Refresh the sidebar list once so spinners clear after page-reload recovery.
                this._dispatchImmersiveUpdate();
            } catch (e) {
                this._inflightPollTimer = setTimeout(pollOnce, 2500);
            }
        };

        // Start quickly
        this._inflightPollTimer = setTimeout(pollOnce, 800);
    }

    _setupVisibilityChangeHandler() {
        if (this._visibilityHandlerBound) return;
        this._visibilityHandlerBound = true;
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState !== 'visible') return;
            if (!this._isImmersive()) return;
            this._checkAndResumeInflightPoll();
        });
    }

    async _checkAndResumeInflightPoll() {
        if (this._inflightPollTimer) return;
        const activeId = this.getActiveConversationId();
        if (!activeId) return;
        try {
            const res = await this._apiFetch(
                `/api/ai/v2/conversations/${encodeURIComponent(activeId)}`
            );
            if (!res.ok) return;
            const data = await res.json();
            const inflight =
                data && data.conversation && data.conversation.meta
                    ? data.conversation.meta.inflight
                    : null;
            if (
                inflight &&
                typeof inflight === 'object' &&
                String(inflight.status || '') === 'in_progress'
            ) {
                const reqId = inflight.request_id
                    ? String(inflight.request_id)
                    : null;
                this._renderInflightProgress(inflight);
                this._startInflightPoll(activeId, reqId);
            } else if (!inflight) {
                const messages = this._mapApiMessages(data.messages || []);
                if (
                    messages.length > 0 &&
                    messages.length !== this.conversationHistory.length
                ) {
                    this.conversationHistory = messages;
                    this.elements.messages.replaceChildren();
                    this.conversationHistory.forEach((entry, index) => {
                        const opts = entry.isError
                            ? {
                                  isError: true,
                                  retryMessage: entry.retryMessage || '',
                              }
                            : entry.structuredPayload
                            ? { structuredPayload: entry.structuredPayload }
                            : {};
                        if (entry.traceId != null) opts.traceId = entry.traceId;
                        this.addMessageToDOM(
                            entry.message,
                            entry.isUser,
                            index,
                            opts
                        );
                    });
                    this.hideTypingIndicator();
                    this._updateImmersiveQuickPromptsVisibility();
                    this.scrollToBottom();
                }
            }
        } catch (_) {
            /* ignore */
        }
    }

    async _loadImmersiveConversation() {
        try {
            const path = window.location.pathname.replace(/\/+$/, '') || '/chat';
            const pathMatch = path.match(/^\/chat\/([^/]+)$/);
            const urlIsNewChat = path === '/chat';

            if (pathMatch) {
                this._setImmersiveActiveId(pathMatch[1]);
            } else if (urlIsNewChat) {
                this._setImmersiveActiveId(null);
            }
            this.activeConversationId = this._getImmersiveActiveId();

            const listRes = await this._apiFetch('/api/ai/v2/conversations');
            if (!listRes.ok) {
                this.loadConversation([]);
                this._dispatchImmersiveUpdate();
                this._updateImmersiveUrl(true);
                return;
            }
            const listData = await listRes.json();
            const conversations = (listData.conversations || []);
            let activeId = this._getImmersiveActiveId();
            if (activeId && !conversations.some(c => c.id === activeId)) {
                activeId = null;
                this._setImmersiveActiveId(null);
            }
            if (!activeId && conversations.length > 0 && !urlIsNewChat) {
                activeId = conversations[0].id;
                this._setImmersiveActiveId(activeId);
            }
            if (!activeId) {
                // Before showing the welcome screen, check if any conversation has
                // an in-progress backend run (e.g. user navigated away mid-query
                // and came back to /chat).  Auto-navigate to that conversation so
                // the user sees the running progress instead of a blank chat.
                const inflightConvo = conversations.find(c =>
                    c && c.inflight && typeof c.inflight === 'object' && String(c.inflight.status || '') === 'in_progress'
                );
                if (inflightConvo) {
                    activeId = inflightConvo.id;
                    this._setImmersiveActiveId(activeId);
                    // fall through to load this conversation below
                } else {
                    this.conversationHistory = [];
                    this.elements.messages.replaceChildren();
                    this.showWelcomeMessage();
                    this._dispatchImmersiveUpdate();
                    this._updateImmersiveUrl(true);
                    return;
                }
            }
            const convRes = await this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(activeId)}`);
            if (!convRes.ok) {
                this.loadConversation([]);
                this._dispatchImmersiveUpdate();
                this._updateImmersiveUrl(true);
                return;
            }
            const convData = await convRes.json();
            const messages = this._mapApiMessages(convData.messages || []);
            this.conversationHistory = messages;
            this.elements.messages.replaceChildren();
            this.conversationHistory.forEach((entry, index) => {
                const opts = entry.isError ? { isError: true, retryMessage: entry.retryMessage || '' } : (entry.structuredPayload ? { structuredPayload: entry.structuredPayload } : {});
                if (entry.traceId != null) opts.traceId = entry.traceId;
                this.addMessageToDOM(entry.message, entry.isUser, index, opts);
            });
            if (this.conversationHistory.length === 0) {
                this.showWelcomeMessage();
            }
            // If a request is still running server-side, restore progress panel + start polling.
            this._maybeRestoreInflightFromConversationResponse(convData, activeId);
            this._updateImmersiveQuickPromptsVisibility();
            this._dispatchImmersiveUpdate();
            this._updateImmersiveUrl(true);
        } catch (e) {
            console.warn('Failed to load immersive conversation from API:', e);
            this.loadConversation([]);
            this._dispatchImmersiveUpdate();
            this._updateImmersiveUrl(true);
        }
    }

    _dispatchImmersiveUpdate() {
        if (typeof window.dispatchEvent === 'function') {
            window.dispatchEvent(new CustomEvent('chatbot-immersive-updated'));
        }
    }

    _refreshConversationSidebarTitles() {
        try {
            if (this._isImmersive()) {
                this._dispatchImmersiveUpdate();
            } else {
                if (this.elements && this.elements.widget && this.elements.widget.classList.contains('chat-sidebar-open') && this.elements.floatingChatList) {
                    this._renderFloatingConversationList();
                } else {
                    void this._refreshFloatingHeaderTitleFromServer();
                }
            }
        } catch (_) { /* ignore */ }
    }

    _resetFloatingHeaderTitleToDefault() {
        if (this._isImmersive()) return;
        const label = this.elements && this.elements.chatFloatingTitleLabel;
        if (!label) return;
        label.textContent = this._floatingDefaultTitleText || 'Assistant';
    }

    _applyFloatingHeaderTitleText(title) {
        if (this._isImmersive()) return;
        const label = this.elements && this.elements.chatFloatingTitleLabel;
        if (!label) return;
        const t = String(title || '').trim();
        if (t) label.textContent = t;
        else this._resetFloatingHeaderTitleToDefault();
    }

    /**
     * Mirrors server _build_initial_conversation_title: first 80 chars of the user message.
     */
    _buildLocalConversationTitle(message) {
        const text = String(message || '').trim();
        if (!text) {
            return (this._uiString && this._uiString('newChat')) ? this._uiString('newChat') : 'New chat';
        }
        return text.length > 80 ? text.slice(0, 80) + '…' : text;
    }

    /**
     * Update visible titles immediately on send (client-only). Immersive listens to chatbot-optimistic-title.
     */
    _applyInstantChatTitles(instantTitle) {
        const t = String(instantTitle || '').trim();
        if (!t) return;
        if (this._isImmersive()) {
            let cid = null;
            try {
                if (this.getActiveConversationId) cid = this.getActiveConversationId();
            } catch (_) { /* ignore */ }
            try {
                window.dispatchEvent(new CustomEvent('chatbot-optimistic-title', {
                    detail: {
                        title: t,
                        conversationId: cid || null,
                    }
                }));
            } catch (_ev) { /* ignore */ }
            return;
        }
        this._applyFloatingHeaderTitleText(t);
    }

    _syncFloatingHeaderTitleFromConversationList(conversations) {
        if (this._isImmersive()) return;
        const cid = this.getActiveConversationId();
        if (!cid) {
            this._resetFloatingHeaderTitleToDefault();
            return;
        }
        const list = Array.isArray(conversations) ? conversations : [];
        const active = list.find((c) => c && String(c.id) === String(cid));
        if (active && String(active.title || '').trim()) {
            this._applyFloatingHeaderTitleText(active.title);
            return;
        }
        void this._refreshFloatingHeaderTitleFromServer();
    }

    async _refreshFloatingHeaderTitleFromServer() {
        if (this._isImmersive()) return;
        const label = this.elements && this.elements.chatFloatingTitleLabel;
        if (!label) return;
        const cid = this._getFloatingConversationId();
        if (!cid) {
            this._resetFloatingHeaderTitleToDefault();
            return;
        }
        try {
            const res = await this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(cid)}`);
            if (!res.ok) return;
            const data = await res.json();
            const t = data && data.conversation && data.conversation.title != null
                ? String(data.conversation.title).trim()
                : '';
            if (t) this._applyFloatingHeaderTitleText(t);
        } catch (_) { /* ignore */ }
    }

    _cancelConversationTitleBurst(conversationId) {
        const cid = conversationId ? String(conversationId) : '';
        if (!cid) return;
        const by = this._titleBurstTimersByConversationId;
        if (!by || !by[cid]) return;
        const tids = by[cid];
        if (Array.isArray(tids)) {
            for (const t of tids) {
                try {
                    clearTimeout(t);
                } catch (_) { /* ignore */ }
            }
        }
        delete by[cid];
    }

    /**
     * While SSE is still streaming, the server may already commit a refined title.
     * Re-fetch the conversation list a few times so the sidebar updates without waiting for `done`.
     */
    _queueConversationTitleBurst(conversationId) {
        const cid = conversationId ? String(conversationId) : '';
        if (!cid) return;
        this._cancelConversationTitleBurst(cid);
        if (!this._titleBurstTimersByConversationId) {
            this._titleBurstTimersByConversationId = {};
        }
        const self = this;
        const delays = [450, 1100, 2400, 5200];
        const tids = delays.map((ms) => setTimeout(() => {
            self._refreshConversationSidebarTitles();
        }, ms));
        this._titleBurstTimersByConversationId[cid] = tids;
    }

    _scheduleConversationTitleRefresh(conversationId, delayMs = 1500) {
        const id = conversationId ? String(conversationId) : '';
        if (!id) return;
        if (!this._pendingTitleRefreshTimers) this._pendingTitleRefreshTimers = {};
        if (this._pendingTitleRefreshTimers[id]) {
            clearTimeout(this._pendingTitleRefreshTimers[id]);
        }
        const wait = Math.max(50, Math.min(Number(delayMs) || 1500, 10000));
        this._pendingTitleRefreshTimers[id] = setTimeout(() => {
            delete this._pendingTitleRefreshTimers[id];
            this._refreshConversationSidebarTitles();
        }, wait);
    }

    loadConversation(messages) {
        this.conversationHistory = Array.isArray(messages) ? messages.slice() : [];
        this.elements.messages.replaceChildren();
                this.conversationHistory.forEach((entry, index) => {
                    const opts = entry.isError
                        ? { isError: true, retryMessage: entry.retryMessage || '' }
                        : (entry.structuredPayload ? { structuredPayload: entry.structuredPayload } : {});
                    if (entry.traceId != null) opts.traceId = entry.traceId;
                    this.addMessageToDOM(entry.message, entry.isUser, index, opts);
                });
        if (this.conversationHistory.length === 0) {
            this.showWelcomeMessage();
        }
        this._updateImmersiveQuickPromptsVisibility();
        this._updateAiNoticeVisibility();
        this.scrollToBottom();
    }

    _mapApiMessages(rawMessages) {
        return (rawMessages || []).map(m => {
            const meta = m && m.meta && typeof m.meta === 'object' ? m.meta : {};
            const tablePayload = meta.table_payload || m.table_payload;
            const chartPayload = meta.chart_payload || m.chart_payload;
            const mapPayload = meta.map_payload || m.map_payload;
            const structuredPayload = (tablePayload && typeof tablePayload === 'object') ? tablePayload
                : ((chartPayload && typeof chartPayload === 'object') ? chartPayload
                : ((mapPayload && typeof mapPayload === 'object') ? mapPayload : null));
            const traceId = m.role === 'assistant' && meta.trace_id != null ? meta.trace_id : undefined;
            const isError = m.role === 'assistant' && meta.is_error === true;
            const retryMessage = isError && meta.retry_message ? String(meta.retry_message) : '';
            return {
                message: m.content || '',
                isUser: m.role === 'user',
                timestamp: (m.created_at || new Date().toISOString()),
                structuredPayload: structuredPayload,
                traceId: traceId,
                isError: isError,
                retryMessage: retryMessage
            };
        });
    }

    async startNewChat() {
        if (this._isImmersive()) {
            // Allow multiple chats to run: detach current stream (don't cancel server).
            this._detachActiveConversationStream();
            this._stopInflightPoll();
            this._currentAbort = null;
            this.isTyping = false;
            this._setSendButtonStop(false);
            this.hideTypingIndicator();
            this._setImmersiveActiveId(null);
            this._getImmersiveDraftKey(true);
            this.loadConversation([]);
            this._dispatchImmersiveUpdate();
            this._updateImmersiveUrl(true);
            return;
        }
        this._setFloatingConversationId(null);
        this.loadConversation([]);
        if (this.elements.floatingChatList) this._renderFloatingConversationList();
    }

    async switchChat(chatId) {
        if (this._isImmersive()) {
            try {
                // Detach the currently running stream so we can safely replace the message DOM.
                this._detachActiveConversationStream();
                this._stopInflightPoll();
                this._currentAbort = null;
                this.isTyping = false;
                this._setSendButtonStop(false);
                this.hideTypingIndicator();
                const res = await this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(chatId)}`);
                if (!res.ok) return;
                const data = await res.json();
                const messages = this._mapApiMessages(data.messages || []);
                this._setImmersiveActiveId(chatId);
                this._getImmersiveDraftKey(true);
                this.loadConversation(messages);
                this._maybeRestoreInflightFromConversationResponse(data, chatId);
                this._dispatchImmersiveUpdate();
                this._updateImmersiveUrl(true);
            } catch (e) {
                console.warn('Failed to switch conversation:', e);
            }
            return;
        }
        try {
            const res = await this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(chatId)}`);
            if (!res.ok) return;
            const data = await res.json();
            const messages = this._mapApiMessages(data.messages || []);
            const convTitle = data && data.conversation && data.conversation.title != null
                ? String(data.conversation.title).trim()
                : '';
            this._setFloatingConversationId(chatId);
            if (convTitle) this._applyFloatingHeaderTitleText(convTitle);
            this.saveConversationHistory();
            this.loadConversation(messages);
            if (this.elements.floatingChatList) this._renderFloatingConversationList();
        } catch (e) {
            console.warn('Failed to switch conversation:', e);
        }
    }

    async deleteChat(chatId) {
        if (this._isImmersive()) {
            try {
                const res = await this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(chatId)}`, { method: 'DELETE' });
                if (!res.ok) return;
                const wasActive = this.activeConversationId === chatId;
                const listRes = await this._apiFetch('/api/ai/v2/conversations');
                if (!listRes.ok) {
                    if (wasActive) {
                        this._setImmersiveActiveId(null);
                        this.loadConversation([]);
                    }
                    this._dispatchImmersiveUpdate();
                    this._updateImmersiveUrl(true);
                    return;
                }
                const listData = await listRes.json();
                const conversations = listData.conversations || [];
                if (conversations.length === 0) {
                    this._setImmersiveActiveId(null);
                    this.loadConversation([]);
                } else if (wasActive) {
                    const nextId = conversations[0].id;
                    this._setImmersiveActiveId(nextId);
                    const convRes = await this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(nextId)}`);
                    if (convRes.ok) {
                        const convData = await convRes.json();
                        const messages = this._mapApiMessages(convData.messages || []);
                        this.loadConversation(messages);
                    } else {
                        this.loadConversation([]);
                    }
                }
                this._dispatchImmersiveUpdate();
                this._updateImmersiveUrl(true);
            } catch (e) {
                console.warn('Failed to delete conversation:', e);
            }
            return;
        }
        try {
            const res = await this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(chatId)}`, { method: 'DELETE' });
            if (!res.ok) return;
            const wasActive = this._getFloatingConversationId() === chatId;
            if (wasActive) {
                this._setFloatingConversationId(null);
                this.loadConversation([]);
            }
            if (this.elements.floatingChatList) this._renderFloatingConversationList();
        } catch (e) {
            console.warn('Failed to delete conversation:', e);
        }
    }

    async deleteAllChats() {
        if (this._isImmersive()) {
            try {
                const res = await this._apiFetch('/api/ai/v2/conversations?confirm=true', {
                    method: 'DELETE'
                });
                if (!res.ok) {
                    console.warn('deleteAllChats: server returned', res.status);
                    return;
                }
                this._setImmersiveActiveId(null);
                this.loadConversation([]);
                this._dispatchImmersiveUpdate();
                this._updateImmersiveUrl(true);
            } catch (e) {
                console.warn('Failed to delete all conversations:', e);
            }
            return;
        }
        try {
            const res = await this._apiFetch('/api/ai/v2/conversations?confirm=true', {
                method: 'DELETE'
            });
            if (!res.ok) {
                console.warn('deleteAllChats: server returned', res.status);
                return;
            }
            this._setFloatingConversationId(null);
            this.loadConversation([]);
            if (this.elements.floatingChatList) this._renderFloatingConversationList();
        } catch (e) {
            console.warn('Failed to delete all conversations:', e);
        }
    }

    getActiveConversationId() {
        if (!this._isImmersive()) {
            return this._getFloatingConversationId();
        }
        return this.activeConversationId || this._getImmersiveActiveId() || null;
    }

    getImmersiveData() {
        return { activeId: this.getActiveConversationId(), conversations: [] };
    }

    rewindToMessageIndex(index) {
        if (index < 0 || index >= this.conversationHistory.length) return;
        const entry = this.conversationHistory[index];
        if (!entry || !entry.isUser) return;
        const textToEdit = entry.message || '';
        this.conversationHistory = this.conversationHistory.slice(0, index);
        this.loadConversation(this.conversationHistory);
        if (this.elements.input) {
            this.elements.input.value = textToEdit;
            this._resizeChatInput();
            this.elements.input.focus();
        }
        this.saveConversationHistory();
    }

    enterEditModeInBubble(wrapper, messageIndex) {
        if (typeof messageIndex !== 'number' || messageIndex < 0 || messageIndex >= this.conversationHistory.length) return;
        const entry = this.conversationHistory[messageIndex];
        if (!entry || !entry.isUser) return;

        const messageDiv = wrapper.querySelector('.chat-message.user');
        const actionBar = wrapper.querySelector('.chat-message-actions');
        const contentDiv = messageDiv && messageDiv.querySelector('div');
        if (!messageDiv || !contentDiv) return;

        const originalText = contentDiv.textContent || '';
        const editWrap = document.createElement('div');
        editWrap.className = 'chat-message-edit-inline';
        try {
            wrapper.classList.add('chat-message-wrapper-editing');
            messageDiv.classList.add('chat-message-editing');
        } catch (_) { /* ignore */ }

        const textarea = document.createElement('textarea');
        textarea.className = 'chat-message-edit-textarea';
        const lineCount = Math.min(12, Math.max(4, (originalText.match(/\n/g) || []).length + 1));
        textarea.rows = lineCount;
        textarea.value = originalText;
        textarea.setAttribute('aria-label', this._uiString('editMessage') || 'Edit message');

        const btnRow = document.createElement('div');
        btnRow.className = 'chat-message-edit-actions';

        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'chat-message-edit-cancel';
        cancelBtn.textContent = this._uiString('cancel') || 'Cancel';
        cancelBtn.setAttribute('aria-label', this._uiString('cancelEdit') || 'Cancel edit');

        const submitBtn = document.createElement('button');
        submitBtn.type = 'button';
        submitBtn.className = 'chat-message-edit-submit';
        submitBtn.textContent = this._uiString('send') || 'Send';
        submitBtn.setAttribute('aria-label', this._uiString('send') || 'Send');

        cancelBtn.addEventListener('click', () => {
            contentDiv.textContent = originalText;
            if (contentDiv.parentNode) {
                editWrap.remove();
                contentDiv.style.display = '';
            }
            if (actionBar) actionBar.style.display = '';
            try {
                wrapper.classList.remove('chat-message-wrapper-editing');
                messageDiv.classList.remove('chat-message-editing');
            } catch (_) { /* ignore */ }
        });

        submitBtn.addEventListener('click', () => {
            const newText = textarea.value.trim();
            editWrap.remove();
            if (actionBar) actionBar.style.display = '';
            try {
                wrapper.classList.remove('chat-message-wrapper-editing');
                messageDiv.classList.remove('chat-message-editing');
            } catch (_) { /* ignore */ }
            if (newText) this.submitEditedMessage(messageIndex, newText);
            else {
                contentDiv.style.display = '';
                contentDiv.textContent = originalText;
            }
        });

        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                cancelBtn.click();
            }
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submitBtn.click();
            }
        });

        btnRow.appendChild(cancelBtn);
        btnRow.appendChild(submitBtn);
        editWrap.appendChild(textarea);
        editWrap.appendChild(btnRow);

        contentDiv.style.display = 'none';
        contentDiv.parentNode.insertBefore(editWrap, contentDiv.nextSibling);
        if (actionBar) actionBar.style.display = 'none';

        textarea.focus();
        textarea.setSelectionRange(originalText.length, originalText.length);
    }

    submitEditedMessage(messageIndex, newText) {
        if (typeof messageIndex !== 'number' || messageIndex < 0 || !newText || this.isTyping) return;
        const before = this.conversationHistory.slice(0, messageIndex);
        this.conversationHistory = before.concat([
            { message: newText, isUser: true, timestamp: new Date().toISOString() }
        ]);
        this.loadConversation(this.conversationHistory);
        this.saveConversationHistory();
        this._dispatchImmersiveUpdate();
        // Submit with branch flag so backend discards later messages in this conversation
        this.handleSendMessage(newText, { branchFromEdit: true, allowServerInflightBypass: true });
    }

    _retryFromUserMessage(wrapper, messageIndex, messageText) {
        if (this.isTyping || !wrapper || messageIndex < 0 || !messageText) return;
        const keepCount = messageIndex + 1;
        this.conversationHistory = this.conversationHistory.slice(0, keepCount);
        let next = wrapper.nextElementSibling;
        while (next) {
            const toRemove = next;
            next = next.nextElementSibling;
            toRemove.remove();
        }
        this.saveConversationHistory();
        this._dispatchImmersiveUpdate();
        this.handleSendMessage(messageText, { branchFromEdit: true, allowServerInflightBypass: true });
    }

    _createMessageActionBar(messageDiv, isUser, getTextFn, messageIndex) {
        const bar = document.createElement('div');
        bar.className = 'chat-message-actions';

        const copyLabel = this._uiString('copy') || 'Copy';
        const copiedLabel = this._uiString('copied') || 'Copied!';
        const copyBtn = document.createElement('button');
        copyBtn.type = 'button';
        copyBtn.className = 'chat-message-action chat-message-action-copy';
        copyBtn.setAttribute('aria-label', copyLabel);
        copyBtn.title = copyLabel;
        copyBtn.innerHTML = '<i class="fas fa-copy" aria-hidden="true"></i>';
        copyBtn.addEventListener('click', () => {
            const text = typeof getTextFn === 'function' ? getTextFn() : '';
            if (!text) return;
            navigator.clipboard.writeText(text).then(() => {
                copyBtn.setAttribute('aria-label', copiedLabel);
                copyBtn.title = copiedLabel;
                const icon = copyBtn.querySelector('i');
                if (icon) icon.className = 'fas fa-check';
                setTimeout(() => {
                    copyBtn.setAttribute('aria-label', copyLabel);
                    copyBtn.title = copyLabel;
                    if (icon) icon.className = 'fas fa-copy';
                }, 2000);
            }).catch(() => {});
        });

        bar.appendChild(copyBtn);

        // Error bubbles (service unavailable, etc.) are not trace-backed feedback targets.
        const skipLikeDislike = messageDiv.classList.contains('chat-message-error');

        if (!isUser && !skipLikeDislike) {
            const likeLabel = this._uiString('like') || 'Like';
            const dislikeLabel = this._uiString('dislike') || 'Dislike';
            const likeBtn = document.createElement('button');
            likeBtn.type = 'button';
            likeBtn.className = 'chat-message-action chat-message-action-like';
            likeBtn.setAttribute('aria-label', likeLabel);
            likeBtn.title = likeLabel;
            likeBtn.innerHTML = '<i class="far fa-thumbs-up" aria-hidden="true"></i>';
            const dislikeBtn = document.createElement('button');
            dislikeBtn.type = 'button';
            dislikeBtn.className = 'chat-message-action chat-message-action-dislike';
            dislikeBtn.setAttribute('aria-label', dislikeLabel);
            dislikeBtn.title = dislikeLabel;
            dislikeBtn.innerHTML = '<i class="far fa-thumbs-down" aria-hidden="true"></i>';
            const showFeedbackToast = (text) => {
                const toast = document.createElement('span');
                toast.className = 'chat-feedback-toast';
                toast.setAttribute('role', 'status');
                toast.textContent = text;
                bar.appendChild(toast);
                toast.offsetHeight;
                toast.classList.add('chat-feedback-toast-visible');
                setTimeout(() => {
                    toast.classList.remove('chat-feedback-toast-visible');
                    setTimeout(() => toast.remove(), 300);
                }, 2200);
            };
            const submitFeedback = (rating) => {
                const wrapper = messageDiv.closest('.chat-message-wrapper');
                if (!wrapper) return;
                const traceId = wrapper.getAttribute('data-trace-id');
                if (!traceId) {
                    showFeedbackToast(this._uiString('feedbackUnavailable') || "Feedback isn't available for this message.");
                    return;
                }
                const current = wrapper.getAttribute('data-user-rating');
                if (current === rating) return;
                likeBtn.disabled = true;
                dislikeBtn.disabled = true;
                this._apiFetch('/api/ai/v2/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ trace_id: parseInt(traceId, 10), rating }),
                }).then((res) => {
                    if (res.ok) {
                        wrapper.setAttribute('data-user-rating', rating);
                        likeBtn.classList.toggle('active', rating === 'like');
                        dislikeBtn.classList.toggle('active', rating === 'dislike');
                        const likeIcon = likeBtn.querySelector('i');
                        const dislikeIcon = dislikeBtn.querySelector('i');
                        if (likeIcon) likeIcon.className = rating === 'like' ? 'fas fa-thumbs-up' : 'far fa-thumbs-up';
                        if (dislikeIcon) dislikeIcon.className = rating === 'dislike' ? 'fas fa-thumbs-down' : 'far fa-thumbs-down';
                        showFeedbackToast(this._uiString('feedbackReceived') || 'Thanks, feedback received.');
                    } else {
                        showFeedbackToast(this._uiString('feedbackSendFailed') || "Couldn't send feedback.");
                    }
                }).catch(() => {
                    showFeedbackToast(this._uiString('feedbackSendFailed') || "Couldn't send feedback.");
                }).finally(() => {
                    likeBtn.disabled = false;
                    dislikeBtn.disabled = false;
                });
            };
            likeBtn.addEventListener('click', () => submitFeedback('like'));
            dislikeBtn.addEventListener('click', () => submitFeedback('dislike'));
            bar.appendChild(likeBtn);
            bar.appendChild(dislikeBtn);
        }

        if (isUser) {
            const retryLabel = this._uiString('retry') || 'Retry';
            const retryBtn = document.createElement('button');
            retryBtn.type = 'button';
            retryBtn.className = 'chat-message-action chat-message-action-retry';
            retryBtn.setAttribute('aria-label', retryLabel);
            retryBtn.title = retryLabel;
            retryBtn.innerHTML = '<i class="fas fa-rotate-right" aria-hidden="true"></i>';
            retryBtn.addEventListener('click', () => {
                if (this.isTyping) return;
                const wrapper = messageDiv.closest('.chat-message-wrapper');
                const idx = typeof messageIndex === 'number' && messageIndex >= 0
                    ? messageIndex
                    : (wrapper && wrapper.getAttribute('data-message-index') !== null
                        ? parseInt(wrapper.getAttribute('data-message-index'), 10)
                        : -1);
                const text = typeof getTextFn === 'function' ? getTextFn() : '';
                if (!text.trim() || idx < 0) return;
                this._retryFromUserMessage(wrapper, idx, text.trim());
            });
            bar.appendChild(retryBtn);

            const editLabel = this._uiString('edit') || 'Edit';
            const editBtn = document.createElement('button');
            editBtn.type = 'button';
            editBtn.className = 'chat-message-action chat-message-action-edit';
            editBtn.setAttribute('aria-label', editLabel);
            editBtn.title = editLabel;
            editBtn.innerHTML = '<i class="fas fa-pen" aria-hidden="true"></i>';
            editBtn.addEventListener('click', () => {
                const wrapper = messageDiv.closest('.chat-message-wrapper');
                const idx = typeof messageIndex === 'number' && messageIndex >= 0
                    ? messageIndex
                    : (wrapper && wrapper.getAttribute('data-message-index') !== null
                        ? parseInt(wrapper.getAttribute('data-message-index'), 10)
                        : -1);
                if (wrapper && !isNaN(idx) && idx >= 0 && idx < this.conversationHistory.length) {
                    this.enterEditModeInBubble(wrapper, idx);
                } else {
                    const text = typeof getTextFn === 'function' ? getTextFn() : '';
                    if (this.elements.input) {
                        this.elements.input.value = text;
                        this._resizeChatInput();
                        this.elements.input.focus();
                    }
                }
            });
            bar.appendChild(editBtn);
        }

        return bar;
    }

    addMessageToDOM(message, isUser = false, messageIndex = undefined, opts = {}) {
        const isError = opts.isError === true;
        const retryMessage = opts.retryMessage || '';
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${isUser ? 'user' : 'bot'}${isError ? ' chat-message-error' : ''}`;

        // Auto-detect text direction so LTR text reads correctly on RTL pages and vice-versa
        messageDiv.setAttribute('dir', 'auto');

        if (isUser) {
            // User messages are always escaped (no HTML allowed)
            const inner = document.createElement('div');
            inner.textContent = String(message ?? '');
            messageDiv.appendChild(inner);
        } else {
            // Bot/AI messages are sanitized to allow safe HTML formatting
            let sanitizedMessage = this.sanitizeHtml(message);

            // Auto-convert tour step references to interactive buttons
            // Universal patterns that work in any language
            if (typeof window.getEntryFormTourSteps === 'function') {
                // Pattern: Detect action phrase followed by parentheses with step keyword and number
                // Works for: "Show me (Step 3)", "Montrez-moi (Étape 3)", "Ver (Paso 3)", etc.
                sanitizedMessage = sanitizedMessage.replace(
                    /([^.!?\n]*?)\b(show\s+me|montrez-moi|ver|voir|zeig|mostra|toon|pokaż|見せ|显示|muestra|voir|ver\s+paso|show)\s*\(([^)]*?)(\d+)([^)]*?)\)/gi,
                    (match, beforeText, actionPhrase, beforeNum, stepNum, afterNum) => {
                        // Verify it contains step keywords
                        const lowerMatch = match.toLowerCase();
                        const tourKeywords = ['step', 'étape', 'paso', 'schritt', 'passo', 'stap', 'krok', 'ステップ', '步骤'];
                        const hasTourKeyword = tourKeywords.some(keyword => lowerMatch.includes(keyword));

                        if (hasTourKeyword) {
                            // Extract and capitalize the action phrase properly
                            let buttonText = actionPhrase.trim();
                            // Capitalize first letter
                            buttonText = buttonText.charAt(0).toUpperCase() + buttonText.slice(1);

                            // Return just the button, removing the original text
                            const safeBefore = this.escapeHtml((beforeText || '').trim());
                            const safeLabel = this.escapeHtml(buttonText);
                            const safeStep = String(stepNum).replace(/[^0-9]/g, '');
                            return `${safeBefore}<br><button class="chatbot-tour-trigger" data-step="${safeStep}"><i class="fas fa-compass"></i>${safeLabel}</button>`;
                        }
                        return match; // Return unchanged if not a tour reference
                    }
                );
            }

            const wrap = document.createElement('div');
            wrap.className = 'flex items-start gap-2';
            const content = document.createElement('div');
            content.className = 'chat-message-content';
            try {
                const doc = new DOMParser().parseFromString(String(sanitizedMessage || ''), 'text/html');
                const root = doc.body;
                if (root) {
                    // Inject lightweight onboarding affordances (e.g. add "Show me" next to key admin links)
                    const showMeLink = this._augmentOnboardingActions(root);

                    const fragment = document.createDocumentFragment();
                    while (root.firstChild) fragment.appendChild(root.firstChild);
                    content.appendChild(fragment);

                    // If we created a "Show me" link, append it to the content wrapper with proper spacing
                    if (showMeLink) {
                        // Add a wrapper div for the button to ensure it's positioned correctly
                        const buttonWrapper = document.createElement('div');
                        buttonWrapper.className = 'chatbot-show-me-wrapper';
                        buttonWrapper.appendChild(showMeLink);
                        content.appendChild(buttonWrapper);
                    }
                } else {
                    // Parsed but empty body: still render sanitized HTML so <strong>, <br> etc. display correctly
                    content.innerHTML = String(sanitizedMessage || '');
                }
            } catch (_) {
                // Fallback: message was already sanitized, so safe to render as HTML (avoids showing raw tags)
                content.innerHTML = String(sanitizedMessage || '');
            }
            wrap.appendChild(content);

            // Confidence badge (shown when agent returns a grounding/confidence score)
            const confidence = opts.confidence || null;
            const groundingScore = opts.grounding_score != null ? opts.grounding_score : null;
            let userPromptForConfidence = opts._confidenceUserPrompt;
            if (userPromptForConfidence === undefined && !isUser && typeof messageIndex === 'number' && messageIndex > 0) {
                const prev = this.conversationHistory[messageIndex - 1];
                if (prev && prev.isUser) userPromptForConfidence = prev.message;
            }
            if (confidence || groundingScore != null) {
                if (!this._shouldSuppressConfidenceBadgeForUserPrompt(userPromptForConfidence)) {
                    const badge = this._buildConfidenceBadge(confidence, groundingScore);
                    if (badge) content.appendChild(badge);
                }
            }

            messageDiv.appendChild(wrap);

            // Process message for workflow tour triggers
            if (window.WorkflowTourParser && typeof window.WorkflowTourParser.processMessage === 'function') {
                try {
                    window.WorkflowTourParser.processMessage(content);
                } catch (e) {
                    console.debug('WorkflowTourParser error:', e);
                }
            }
            this._formatChatResponseSources(content);
            this._addTableCopyButtons(content);
            this._collapseLongTables(content);
            this._tableDebugLog('Rendered assistant message tables:', {
                tables_in_dom: content.querySelectorAll('table').length,
                ai_tables_in_dom: content.querySelectorAll('.chat-ai-table').length
            });
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'chat-message-wrapper';
        if (isError) wrapper.classList.add('chat-message-wrapper-error');
        wrapper.classList.add(isUser ? 'is-user' : 'is-bot');
        if (typeof messageIndex === 'number') wrapper.setAttribute('data-message-index', String(messageIndex));
        if (!isUser && opts.traceId != null) wrapper.setAttribute('data-trace-id', String(opts.traceId));
        wrapper.appendChild(messageDiv);

        const getTextFn = isUser
            ? () => messageDiv.querySelector('div')?.textContent ?? ''
            : () => this._buildCopyTextForBotMessage(wrapper, messageDiv);
        const actionBar = this._createMessageActionBar(messageDiv, isUser, getTextFn, messageIndex);

        if (isError && retryMessage) {
            const errorRetryLabel = this._uiString('retry') || 'Retry';
            const retryBtn = document.createElement('button');
            retryBtn.type = 'button';
            retryBtn.className = 'chat-message-action chat-message-action-retry';
            retryBtn.setAttribute('aria-label', errorRetryLabel);
            retryBtn.title = errorRetryLabel;
            retryBtn.innerHTML = '<i class="fas fa-rotate-right" aria-hidden="true"></i>';
            retryBtn.addEventListener('click', () => {
                if (this.isTyping) return;
                wrapper.remove();
                if (this.conversationHistory.length && this.conversationHistory[this.conversationHistory.length - 1].isError) {
                    this.conversationHistory.pop();
                    this.saveConversationHistory();
                }
                this.handleSendMessage(retryMessage, { allowServerInflightBypass: true });
            });
            actionBar.appendChild(retryBtn);
        }

        wrapper.appendChild(actionBar);

        this.elements.messages.appendChild(wrapper);
        if (!isUser && !isError) {
            const pieces = this._pendingStructuredRawPieces;
            if (pieces && pieces.length) {
                this._pendingStructuredRawPieces = null;
                this._tableDebugLog('addMessageToDOM', {
                    messageIndex,
                    hasStructuredPayload: true,
                    payloadType: 'multi',
                    fromOpts: !!opts.structuredPayload,
                    wrapperInDOM: !!(wrapper && wrapper.parentElement),
                    messageDivInDOM: !!(messageDiv && messageDiv.parentElement),
                    totalWrappers: this.elements.messages ? this.elements.messages.querySelectorAll('.chat-message-wrapper').length : 0
                });
                for (const p of pieces) {
                    this._dispatchStructuredPayload(p, messageDiv, wrapper);
                }
            } else {
                const structuredPayload = opts.structuredPayload || this._consumePendingStructuredPayload();
                this._tableDebugLog('addMessageToDOM', {
                    messageIndex,
                    hasStructuredPayload: !!structuredPayload,
                    payloadType: structuredPayload && (structuredPayload.type || (structuredPayload.table_payload && 'table_payload') || 'unknown'),
                    fromOpts: !!opts.structuredPayload,
                    wrapperInDOM: !!(wrapper && wrapper.parentElement),
                    messageDivInDOM: !!(messageDiv && messageDiv.parentElement),
                    totalWrappers: this.elements.messages ? this.elements.messages.querySelectorAll('.chat-message-wrapper').length : 0
                });
                this._dispatchStructuredPayload(structuredPayload, messageDiv, wrapper);
            }
        }
        this.scrollToBottom();
    }

    /**
     * Whether to hide grounding/confidence for the user turn (e.g. "hi", "thanks") — not meaningful for RAG.
     * @param {string} [userPrompt]
     * @returns {boolean}
     */
    _shouldSuppressConfidenceBadgeForUserPrompt(userPrompt) {
        const raw = String(userPrompt || '').trim();
        if (!raw || raw.length > 56) return false;
        const compact = raw
            .toLowerCase()
            .replace(/[\u2018\u2019`']/g, "'")
            .replace(/[!?.…,:;'"()]+/g, ' ')
            .replace(/[^a-z0-9\u00c0-\u024f\s'-]/gi, ' ')
            .replace(/\s+/g, ' ')
            .trim();
        if (!compact) return false;

        if (/^(?:\b(?:hi|hello|hey|heya|hiya|howdy|yo|greetings)\b\s*)+$/i.test(compact)) return true;
        if (/^(?:hi|hey|hello|heya|hiya)\s+(there|everyone|all)\s*$/i.test(compact)) return true;
        if (/^(?:good\s+(?:morning|afternoon|evening|day))\.?\s*$/i.test(compact)) return true;
        if (/^(?:thanks?|thank\s+you|thx|ty|merci|danke|gracias)\s*!?\s*$/i.test(compact)) return true;
        if (/^(?:ok+|okay|kk)\s*!?\s*$/i.test(compact)) return true;
        if (/^(?:bye|goodbye|ciao|cheers)\s*!?\s*$/i.test(compact)) return true;
        if (/^how\s+are\s+you\??$/i.test(compact)) return true;
        if (/^what'?s\s+up\??$/i.test(compact)) return true;

        return false;
    }

    /**
     * Build a small confidence/grounding badge element to append to an AI message.
     * @param {string|null} confidence - 'high', 'medium', or 'low'
     * @param {number|null} groundingScore - 0.0–1.0
     * @returns {HTMLElement|null}
     */
    _buildConfidenceBadge(confidence, groundingScore) {
        const level = confidence || (
            groundingScore != null
                ? (groundingScore >= 0.7 ? 'high' : groundingScore >= 0.4 ? 'medium' : 'low')
                : null
        );
        if (!level) return null;

        const colorMap = {
            high:   { bg: '#dcfce7', color: '#166534', icon: '●', label: 'High confidence' },
            medium: { bg: '#fef9c3', color: '#854d0e', icon: '●', label: 'Medium confidence' },
            low:    { bg: '#fee2e2', color: '#991b1b', icon: '●', label: 'Low confidence' },
        };
        const cfg = colorMap[level] || colorMap.medium;

        const badge = document.createElement('div');
        badge.className = 'chat-confidence-badge';
        badge.style.cssText = [
            'display:inline-flex',
            'align-items:center',
            'gap:4px',
            'margin-top:8px',
            'padding:2px 8px',
            'border-radius:9999px',
            `background:${cfg.bg}`,
            `color:${cfg.color}`,
            'font-size:0.7rem',
            'font-weight:500',
            'opacity:0.85',
            'cursor:default',
        ].join(';');

        const scoreText = groundingScore != null ? ` (${Math.round(groundingScore * 100)}%)` : '';
        badge.title = `Source grounding score${groundingScore != null ? `: ${Math.round(groundingScore * 100)}%` : ''}`;
        badge.innerHTML = `<span aria-hidden="true" style="font-size:0.55rem">${cfg.icon}</span> ${cfg.label}${scoreText}`;
        return badge;
    }

    saveExpandedState() {
        /* No-op: chat is always maximized */
    }

    loadExpandedState() {
        this.isExpanded = true; /* Chat is always maximized */
    }

    showWelcomeMessage() {
        /* No auto welcome message; if AI is unavailable the user will see that when they send a message. */
        this._updateImmersiveQuickPromptsVisibility();
    }

    // Get API status
    getAPIStatus() {
        const debugModules = this.debug && this.debug.getConfig ? this.debug.getConfig().modules : {};
        const chatbotDebugEnabled = debugModules['chatbot'] || debugModules['chatbot-api'] || debugModules['chatbot-context'];

        return {
            available: this.apiAvailable,
            status: this.apiAvailable ? '🟢 Available' : '🔴 Unavailable',
            endpoint: this.apiEndpoint,
            debugMode: chatbotDebugEnabled,
            language: this.preferredLanguage,
            conversationLength: this.conversationHistory.length,
            debugSystem: 'Managed by centralized debug.js - Use window.debug.enableChatbot() to enable'
        };
    }

    clearConversation() {
        try {
            localStorage.removeItem(this.storageKey);
            if (!this._isImmersive()) this._setFloatingConversationId(null);
            this.conversationHistory = [];

            // Clear all messages
            this.elements.messages.replaceChildren();

            // Show welcome message
            this.showWelcomeMessage();
            this._updateAiNoticeVisibility();
        } catch (error) {
            console.warn('Failed to clear conversation:', error);
        }
    }

    handleClearConversation() {
        if (this._isImmersive()) {
            this.startNewChat();
            return;
        }
        // Show confirmation dialog
        const msg = this._uiString('clearConversationConfirm') || 'Are you sure you want to clear the entire conversation? This action cannot be undone.';
        const clearLabel = this._uiString('clear') || 'Clear';
        const cancelLabel = this._uiString('cancel') || 'Cancel';
        const clearTitle = this._uiString('clearConversationTitle') || 'Clear Conversation?';
        const doClear = () => {
            // Clear conversation history and localStorage (and floating conversation id so next send starts a new DB thread)
            try {
                localStorage.removeItem(this.storageKey);
                this._setFloatingConversationId(null);
                this.conversationHistory = [];

                // Clear all messages completely
                this.elements.messages.replaceChildren();

                // Add a fresh welcome message
                this.showWelcomeMessage();
                this._updateAiNoticeVisibility();
            } catch (error) {
                console.warn('Failed to clear conversation:', error);
            }
        };

        if (window.showDangerConfirmation) {
            window.showDangerConfirmation(msg, doClear, null, clearLabel, cancelLabel, clearTitle);
            return;
        }
        if (window.showConfirmation) {
            window.showConfirmation(msg, doClear, null, clearLabel, cancelLabel, clearTitle);
            return;
        }
        console.warn('Custom confirmation dialog not available:', msg);
    }

    escapeHtml(text) {
        if (typeof text !== 'string') return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    _safeSameOriginUrl(rawHref) {
        try {
            const href = String(rawHref == null ? '' : rawHref).trim();
            if (!href) return null;
            if (href.startsWith('#')) return href;
            if (href.startsWith('/')) return href;
            const url = new URL(href, window.location.href);
            if (!window.location || !window.location.origin) return null;
            if (url.origin !== window.location.origin) return null;
            return url.pathname + url.search + url.hash;
        } catch (_) {
            return null;
        }
    }

    /**
     * Decode HTML entities so backend-escaped content (e.g. &lt;strong&gt;, &lt;br&gt;)
     * renders as HTML instead of showing raw tags. Run before sanitizeHtml.
     */
    decodeHtmlEntities(html) {
        if (typeof html !== 'string') return '';
        return html
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'")
            .replace(/&#x27;/g, "'")
            .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(parseInt(n, 10)))
            .replace(/&#x([0-9a-fA-F]+);/g, (_, n) => String.fromCharCode(parseInt(n, 16)));
    }

    /**
     * Linkify markdown-style links [label](url) in cell content. Escapes HTML first, then
     * converts links. Used for table cells so document links become clickable.
     */
    _linkifyCellContent(cell) {
        if (cell == null || cell === '') return '';
        const escaped = this.escapeHtml(String(cell));
        const mdLinkRe = /\[([^\]]*)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/g;
        return escaped.replace(mdLinkRe, (_, label, href) => {
            const safe = this._safeSameOriginUrl(href);
            if (!safe) return this.escapeHtml(label || '');
            return '<a href="' + this.escapeHtml(safe) + '" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener">' + this.escapeHtml(label || '') + '</a>';
        });
    }

    /**
     * Convert markdown table blocks (e.g. "| A | B |\n|---|---|\n| 1 | 2 |") to HTML tables.
     * Handles optional trailing pipe so "| A | B" works. Safe: cell content is escaped and linkified.
     */
    markdownTablesToHtml(text) {
        if (typeof text !== 'string') return '';
        let normalized = String(text || '');
        const inputLength = normalized.length;
        const stripInvisible = (s) => String(s == null ? '' : s)
            .replace(/[\u0000-\u001F\u007F-\u009F\u00AD\u061C\u200B-\u200F\u202A-\u202E\u2060\u2066-\u2069\uFEFF]/g, '');
        const stripHtmlBreaks = (s) => String(s == null ? '' : s).replace(/<br\s*\/?>/gi, '');
        const normalizeDashAndSpace = (s) => stripInvisible(s)
            .replace(/<br\s*\/?>/gi, '')
            .replace(/[—–−]/g, '-')
            .replace(/\u00A0/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
        const splitMarkdownRow = (ln) => {
            const lnNorm = normalizeDashAndSpace(stripHtmlBreaks(ln));
            const parts = lnNorm.split('|').map((s) => normalizeDashAndSpace(s));
            let start = 0;
            let end = parts.length;
            while (start < end && !parts[start]) start++;
            while (end > start && !parts[end - 1]) end--;
            return parts.slice(start, end);
        };
        // Normalize line endings first so markdown rows are split consistently.
        normalized = normalized.replace(/\r\n?/g, '\n');
        // Some persisted responses can contain literal "\n" sequences.
        if (!normalized.includes('\n') && /\\n/.test(normalized) && /\|/.test(normalized)) {
            normalized = normalized.replace(/\\n/g, '\n');
        }
        const lines = normalized.split('\n');
        const out = [];
        let i = 0;
        let candidateBlocks = 0;
        let renderedTables = 0;
        const separatorCellLooksValid = (cell) => {
            const raw = normalizeDashAndSpace(cell);
            // Normalize common invisible/unicode chars that can appear in streamed text.
            const cleaned = raw
                .replace(/\s+/g, '')
                .trim();
            // Markdown separator cell: --- , :--- , ---: , :---:
            return /^:?-{3,}:?$/.test(cleaned);
        };
        const separatorLineLooksValid = (line) => {
            const raw = normalizeDashAndSpace(stripHtmlBreaks(line));
            if (!raw || raw.indexOf('|') === -1) return false;
            const syntaxOnly = raw.replace(/[|:\-\s]/g, '');
            if (syntaxOnly) return false;
            return ((raw.match(/\|/g) || []).length >= 2) && ((raw.match(/-/g) || []).length >= 3);
        };
        const separatorRowLooksValid = (row, expectedCols) => {
            if (!Array.isArray(row) || row.length < 2) return false;
            if (Number.isFinite(expectedCols) && expectedCols > 0 && row.length !== expectedCols) return false;
            return row.every((cell) => separatorCellLooksValid(cell));
        };
        const looksLikeTableLine = (line) => {
            const trimmed = String(line || '').trim();
            if (!trimmed) return false;
            // Ignore rendered HTML tags; only process markdown-ish lines.
            if (trimmed.startsWith('<') && trimmed.endsWith('>')) return false;
            if (/^\s*\|/.test(line)) return true;
            // Support rows without leading/trailing pipes: "A | B | C"
            const pipeCount = (trimmed.match(/\|/g) || []).length;
            return pipeCount >= 2;
        };
        while (i < lines.length) {
            const line = lines[i];
            if (!looksLikeTableLine(line)) {
                out.push(line);
                i++;
                continue;
            }
            const block = [];
            while (i < lines.length && looksLikeTableLine(lines[i])) {
                block.push(lines[i]);
                i++;
            }
            candidateBlocks++;
            if (block.length < 2) {
                out.push(...block);
                continue;
            }
            const rows = block.map((ln) => splitMarkdownRow(ln));
            // Find the first valid markdown separator row anywhere in the block,
            // then treat the previous row as header. This is resilient to
            // pipe-containing preface lines that can appear in stored messages.
            let sepIndex = -1;
            for (let r = 1; r < rows.length; r++) {
                const prev = rows[r - 1] || [];
                const cur = rows[r] || [];
                if ((prev.length >= 2) && separatorRowLooksValid(cur, prev.length)) {
                    sepIndex = r;
                    break;
                }
            }
            // Fallback: separator may include odd chars that survive cell parsing; test raw line.
            if (sepIndex < 1) {
                for (let r = 1; r < block.length; r++) {
                    const prev = rows[r - 1] || [];
                    if (prev.length < 2) continue;
                    if (separatorLineLooksValid(block[r])) {
                        sepIndex = r;
                        break;
                    }
                }
            }
            if (sepIndex < 1) {
                const rejectPayload = {
                    block_preview: block.slice(0, 4),
                    header_cells: rows[0] || [],
                    separator_cells: rows[1] || [],
                    header_len: rows[0] ? rows[0].length : 0,
                    separator_len: rows[1] ? rows[1].length : 0,
                    separator_valid_flags: (rows[1] || []).map((c) => separatorCellLooksValid(c)),
                    separator_line_raw_valid: separatorLineLooksValid(block[1] || ''),
                };
                this._warn('Markdown table block rejected:', rejectPayload);
                this._warn('Markdown table reject payload JSON:', JSON.stringify(rejectPayload));
                out.push(...block);
                continue;
            }
            const headerRow = rows[sepIndex - 1] || [];
            const headerCols = headerRow.length;
            const separatorRow = rows[sepIndex] || [];
            const colAligns = separatorRow.map(cell => {
                const c = normalizeDashAndSpace(cell).replace(/\s+/g, '');
                if (c.startsWith(':') && c.endsWith(':')) return 'center';
                if (c.endsWith(':')) return 'right';
                return '';
            });
            while (colAligns.length < headerCols) colAligns.push('');
            const bodyRows = rows.length > (sepIndex + 1) ? rows.slice(sepIndex + 1) : [];
            let table = '<table class="chat-ai-table"><thead><tr>';
            headerRow.forEach((cell, ci) => {
                const align = colAligns[ci] ? ' style="text-align:' + colAligns[ci] + '"' : '';
                table += '<th' + align + '>' + this._linkifyCellContent(cell || '') + '</th>';
            });
            table += '</tr></thead><tbody>';
            bodyRows.forEach(row => {
                const adjusted = (row || []).slice(0, headerCols);
                while (adjusted.length < headerCols) adjusted.push('');
                table += '<tr>';
                adjusted.forEach((cell, ci) => {
                    const align = colAligns[ci] ? ' style="text-align:' + colAligns[ci] + '"' : '';
                    table += '<td' + align + '>' + this._linkifyCellContent(cell || '') + '</td>';
                });
                table += '</tr>';
            });
            table += '</tbody></table>';
            out.push(table);
            renderedTables++;
        }
        this._tableDebugLog('Markdown table formatting:', {
            input_length: inputLength,
            lines: lines.length,
            candidate_blocks: candidateBlocks,
            rendered_tables: renderedTables
        });
        return out.join('\n');
    }

    /**
     * If text contains "## Sources" (markdown), extract that section and replace it with
     * the same <details class="chat-response-sources"> structure the backend uses.
     * Ensures sources are always formatted whether response is HTML (from stream) or markdown (e.g. from DB on refresh).
     */
    markdownSourcesToHtml(text) {
        if (typeof text !== 'string') return text;
        if (text.includes('chat-response-sources') && text.includes('chat-response-sources-body')) {
            return text;
        }
        if (!/^(?:#{2,3}\s*)?Sources\s*:?\s*$/im.test(text)) {
            return text;
        }
        const stopAt = '(?=\\n\\s*\\n\\s*(?:If you want, I can|If you\'d like|Which would you prefer\\?|Which format do you prefer\\?|\\*\\*Notes?\\s*\\/\\s*next steps\\b)|\\n\\s*(?:If you want, I can|If you\'d like)|$(?![\\s\\S]))';
        const sourcesRegex = new RegExp('(?m)^((?:#{2,3}\\s*)?Sources\\s*:?\\s*)\\s*$(.+?)' + stopAt, 'is');
        const sourcesMatch = text.match(sourcesRegex);
        if (!sourcesMatch) return text;
        const sourcesBlockRaw = sourcesMatch[2].trim();
        const mainPart = text.slice(0, sourcesMatch.index).trim();
        const placeholder = '__HUMDATABANK_AI_SOURCES__';
        let combined = mainPart + '\n\n' + placeholder;
        // Escape and format sources block: newlines -> <br>, markdown links -> <a>
        let sourcesEsc = this.escapeHtml(sourcesBlockRaw);
        sourcesEsc = sourcesEsc.replace(/\n+/g, '<br>').replace(/(<br>){2,}/g, '<br><br>');
        sourcesEsc = sourcesEsc.replace(/\[([^\]]*)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/g, (_, label, href) => {
            const safe = this._safeSameOriginUrl(href);
            if (!safe) return this.escapeHtml(label || '');
            return '<a href="' + this.escapeHtml(safe) + '" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener">' + this.escapeHtml(label || '') + '</a>';
        });
        const sourcesHtml = (
            '<details class="chat-response-sources mt-2 border border-gray-200 rounded p-2 bg-gray-50">' +
            '<summary class="cursor-pointer font-medium text-gray-700">Sources</summary>' +
            '<div class="chat-response-sources-body mt-2 text-sm text-gray-600">' + sourcesEsc + '</div></details>'
        );
        return combined.replace(placeholder, sourcesHtml);
    }

    // Enhanced HTML sanitization for AI responses
    sanitizeHtml(html) {
        if (typeof html !== 'string') return '';
        const originalHtml = String(html || '');

        // Decode entities first so escaped markdown (e.g., &lt; and &#124;) can be parsed.
        html = this.decodeHtmlEntities(html);

        // Parse ## Sources from markdown so sources are always a proper block (fixes markdown from DB on refresh)
        html = this.markdownSourcesToHtml(html);

        // Convert markdown tables to HTML so they render as tables (backend may send markdown or we get raw from history)
        html = this.markdownTablesToHtml(html);

        // Normalize bullets: avoid "• - " (double bullet) and orphan "•" on its own
        html = html.replace(/•\s*-\s+/g, '• ');
        html = html.replace(/(<br\s*\/?>)\s*•\s*(<br\s*\/?>|$)/gi, '$1$2');

        // Parse into a detached document without assigning innerHTML
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const tempDiv = doc.body;
        if (!tempDiv) return '';

        // Remove all script tags and event handlers
        const scripts = tempDiv.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            scripts[i].parentNode.removeChild(scripts[i]);
        }

        // Remove dangerous protocols and all event handler attributes
        const allElements = tempDiv.getElementsByTagName('*');
        for (let i = allElements.length - 1; i >= 0; i--) {
            const element = allElements[i];

            // Remove dangerous protocols from any attributes
            for (let j = element.attributes.length - 1; j >= 0; j--) {
                const attr = element.attributes[j];
                const v = (attr.value || '').toLowerCase().trim();
                if (!v) continue;
                if (
                    v.includes('javascript:') ||
                    v.includes('data:') ||
                    v.includes('vbscript:') ||
                    v.includes('file:') ||
                    v.includes('about:')
                ) {
                    element.removeAttribute(attr.name);
                    continue;
                }
            }

            // Remove event handler and style attributes
            for (let j = element.attributes.length - 1; j >= 0; j--) {
                const attr = element.attributes[j];
                const attrName = attr.name.toLowerCase();
                if (attrName.startsWith('on') || attrName === 'style') {
                    element.removeAttribute(attr.name);
                }
            }
        }

        // Only allow safe HTML tags (including <a> for links, table for data, details/summary for collapsible Sources)
        const allowedTags = ['p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'details', 'summary'];
        const allTags = tempDiv.getElementsByTagName('*');

        for (let i = allTags.length - 1; i >= 0; i--) {
            const element = allTags[i];
            if (!allowedTags.includes(element.tagName.toLowerCase())) {
                // Replace unsafe tags with their text content
                const textNode = document.createTextNode(element.textContent);
                element.parentNode.replaceChild(textNode, element);
            }
        }

        // Ensure every <table> has chat-ai-table so model-generated HTML tables are styled like markdown-rendered ones
        const tables = tempDiv.getElementsByTagName('table');
        for (let t = 0; t < tables.length; t++) {
            const tbl = tables[t];
            if (tbl.classList && !tbl.classList.contains('chat-ai-table')) {
                tbl.classList.add('chat-ai-table');
            }
        }

        // Attribute allowlist + safe links only
        const allowedAttrsByTag = {
            a: new Set(['href', 'title', 'class', 'target', 'rel']), // target/rel for new-tab links
            table: new Set(['class']),
            thead: new Set(['class']),
            tbody: new Set(['class']),
            tr: new Set(['class']),
            th: new Set(['class']),
            td: new Set(['class']),
            details: new Set(['class']),
            summary: new Set(['class']),
            div: new Set(['class']),
            span: new Set(['class']),
        };
        const allTags2 = tempDiv.getElementsByTagName('*');
        for (let i = allTags2.length - 1; i >= 0; i--) {
            const el = allTags2[i];
            const tag = el.tagName.toLowerCase();
            const allowed = allowedAttrsByTag[tag] || new Set();

            // Clean attributes
            for (let j = el.attributes.length - 1; j >= 0; j--) {
                const attr = el.attributes[j];
                if (!allowed.has(attr.name.toLowerCase())) {
                    el.removeAttribute(attr.name);
                }
            }

            // Special-case: safe href for links (same-origin/relative only)
            if (tag === 'a') {
                const href = el.getAttribute('href') || '';
                let safe;
                if (window.SafeDom) {
                    safe = window.SafeDom.safeUrl(href, { allowSameOrigin: true });
                } else {
                    safe = this._safeSameOriginUrl(href);
                }
                if (!safe) {
                    el.removeAttribute('href');
                } else {
                    el.setAttribute('href', safe);
                }
            }
        }
        const finalHtml = tempDiv.innerHTML;
        const tableCount = (finalHtml.match(/<table\b/gi) || []).length;
        this._tableDebugLog('sanitizeHtml result:', {
            input_length: originalHtml.length,
            output_length: finalHtml.length,
            tables_found: tableCount,
            contains_pipe_chars: /\|/.test(originalHtml)
        });
        return finalHtml;
    }

    _tableToMatrix(tableEl) {
        if (!tableEl || tableEl.tagName !== 'TABLE') return [];
        const out = [];
        const trs = tableEl.querySelectorAll('tr');
        trs.forEach((tr) => {
            // Skip UI-only "expand" control row that appears in immersive mode
            if (tr.classList && tr.classList.contains('chat-ai-table-expand-row')) return;
            const cells = tr.querySelectorAll('th, td');
            const values = Array.from(cells).map((cell) => (cell.textContent || '').trim());
            if (values.length) out.push(values);
        });
        return out;
    }

    async _downloadTableAsExcel(tableEl) {
        if (!tableEl || tableEl.tagName !== 'TABLE') return;
        const rows = this._tableToMatrix(tableEl);
        if (!rows || !rows.length) return;

        let resp;
        try {
            resp = await this._apiFetch('/api/ai/v2/table/export', {
                method: 'POST',
                body: JSON.stringify({ rows })
            });
        } catch (_e) {
            return;
        }

        if (!resp || !resp.ok) return;
        const blob = await resp.blob();
        const filename = resp.headers.get('X-hum-databank-Export-Filename') || 'table-data.xlsx';

        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    }

    _addTableCopyButtons(container) {
        if (!container || typeof container.querySelectorAll !== 'function') return;
        const tables = container.querySelectorAll('.chat-ai-table');
        tables.forEach((table) => {
            if (table.closest('.chat-ai-table-wrapper')) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'chat-ai-table-wrapper';
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'chat-ai-table-copy-btn';
            btn.setAttribute('aria-label', 'Download table as Excel');
            btn.title = 'Download table as Excel spreadsheet';
            btn.innerHTML = '<i class="fas fa-file-excel" aria-hidden="true"></i><span>Download Excel</span>';
            btn.addEventListener('click', async () => {
                await this._downloadTableAsExcel(table);
                const span = btn.querySelector('span');
                const orig = span ? span.textContent : '';
                if (span) span.textContent = 'Downloaded!';
                btn.classList.add('chat-ai-table-copy-done');
                setTimeout(() => {
                    if (span) span.textContent = orig;
                    btn.classList.remove('chat-ai-table-copy-done');
                }, 1500);
            });
            wrapper.insertBefore(btn, table);
        });
    }

    _collapseLongTables(container) {
        if (!container || !this._isImmersive()) return;
        const DEFAULT_VISIBLE_ROWS = 5;
        const tables = container.querySelectorAll('.chat-ai-table');
        tables.forEach((table) => {
            if (table.classList.contains('chat-ai-table-collapsible')) return;
            const tbody = table.querySelector('tbody');
            if (!tbody) return;
            const trs = Array.from(tbody.querySelectorAll('tr'));
            if (trs.length <= DEFAULT_VISIBLE_ROWS) return;
            const firstRow = table.querySelector('tr');
            const colCount = firstRow ? firstRow.querySelectorAll('th, td').length : 1;
            table.classList.add('chat-ai-table-collapsible');
            for (let i = DEFAULT_VISIBLE_ROWS; i < trs.length; i++) {
                trs[i].classList.add('chat-ai-table-row-hidden');
            }
            const expandTr = document.createElement('tr');
            expandTr.className = 'chat-ai-table-expand-row';
            expandTr.setAttribute('role', 'button');
            expandTr.setAttribute('tabIndex', '0');
            expandTr.setAttribute('aria-label', 'Show more rows');
            const expandTd = document.createElement('td');
            expandTd.colSpan = colCount;
            expandTd.innerHTML = '<span class="chat-ai-table-expand-label">Show ' + (trs.length - DEFAULT_VISIBLE_ROWS) + ' more rows</span> <i class="fas fa-chevron-down chat-ai-table-expand-icon" aria-hidden="true"></i>';
            expandTr.appendChild(expandTd);
            tbody.appendChild(expandTr);
            expandTr.addEventListener('click', () => {
                tbody.querySelectorAll('.chat-ai-table-row-hidden').forEach((tr) => tr.classList.remove('chat-ai-table-row-hidden'));
                expandTr.remove();
                table.classList.remove('chat-ai-table-collapsible');
                table.classList.add('chat-ai-table-expanded');
            });
            expandTr.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    expandTr.click();
                }
            });
        });
    }

    _normalizeSourcesSection(container) {
        if (!container || typeof container.querySelector !== 'function') return;
        const _buildSourcesBody = (items) => {
            const body = document.createElement('div');
            body.className = 'chat-response-sources-body';
            items.forEach((li, idx) => {
                if (idx > 0) body.appendChild(document.createElement('br'));
                // Clone child nodes (preserves safe links) instead of re-injecting raw innerHTML
                Array.from(li.childNodes).forEach(n => body.appendChild(n.cloneNode(true)));
            });
            return body;
        };

        const headings = container.querySelectorAll('h1, h2, h3, h4');
        headings.forEach((heading) => {
            const title = (heading.textContent || '').trim().toLowerCase();
            if (title !== 'sources') return;
            let list = heading.nextElementSibling;
            if (!list || !/^UL|OL$/i.test(list.tagName)) return;
            const items = Array.from(list.children).filter((c) => c.tagName === 'LI');
            if (!items.length) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'chat-response-sources';
            wrapper.appendChild(_buildSourcesBody(items));
            heading.parentNode.insertBefore(wrapper, heading);
            heading.remove();
            list.remove();
        });

        // Also normalize non-heading variants:
        // <p>Sources</p><ul>...</ul> or <p><strong>Sources:</strong></p><ol>...</ol>
        const paragraphs = container.querySelectorAll('p');
        paragraphs.forEach((p) => {
            const title = (p.textContent || '').trim().toLowerCase().replace(/:$/, '');
            if (title !== 'sources') return;
            let list = p.nextElementSibling;
            if (!list || !/^UL|OL$/i.test(list.tagName)) return;
            const items = Array.from(list.children).filter((c) => c.tagName === 'LI');
            if (!items.length) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'chat-response-sources';
            wrapper.appendChild(_buildSourcesBody(items));
            p.parentNode.insertBefore(wrapper, p);
            p.remove();
            list.remove();
        });
    }

    _formatChatResponseSources(container) {
        if (!container || typeof container.querySelector !== 'function') return;
        this._normalizeSourcesSection(container);
        const isAnswerVerificationCaveatText = (plain) => {
            const t = (plain || '')
                .toLowerCase()
                .replace(/\s+/g, ' ')
                .trim();
            if (!t) {
                return false;
            }
            if (t.includes('could not be verified against the available sources')) {
                return true;
            }
            if (t.startsWith('note:') && t.includes('could not be verified')) {
                return true;
            }
            if (t.startsWith('> note:') && t.includes('could not be verified')) {
                return true;
            }
            return false;
        };
        const countProbe = document.createElement('div');
        const sourcesBlocks = container.querySelectorAll('.chat-response-sources');
        sourcesBlocks.forEach((detailsEl) => {
            const bodyEl = detailsEl.querySelector('.chat-response-sources-body');
            if (!bodyEl) return;
            let html = bodyEl.innerHTML.trim();
            if (!html) return;
            let segments = html.split(/\s*<br\s*\/?>\s*/i).map((s) => s.trim()).filter(Boolean);
            if (segments.length <= 1 && bodyEl.querySelector('ul li, ol li')) {
                const items = bodyEl.querySelectorAll('ul li, ol li');
                const fromList = Array.from(items).map((li) => (li.innerHTML || li.textContent || '').trim()).filter(Boolean);
                if (fromList.length > segments.length) segments = fromList;
            }
            if (!segments.length) return;
            let sourceCountForLabel = 0;
            for (const segment of segments) {
                countProbe.innerHTML = segment;
                const p = (countProbe.textContent || '').replace(/\s+/g, ' ').trim();
                if (p && !isAnswerVerificationCaveatText(p)) {
                    sourceCountForLabel += 1;
                }
            }
            let summaryEl = detailsEl.querySelector('summary');
            if (!summaryEl) {
                summaryEl = document.createElement('summary');
                detailsEl.insertBefore(summaryEl, bodyEl);
            }
            summaryEl.textContent = 'Sources (' + sourceCountForLabel + ')';
            const resolveSourceIcon = (segmentHtml, plainText) => {
                const probe = document.createElement('div');
                probe.innerHTML = segmentHtml;
                const anchor = probe.querySelector('a[href]');
                const href = (anchor?.getAttribute('href') || '').trim();
                const label = ((anchor?.textContent || '') + ' ' + plainText).toLowerCase();
                const hrefLower = href.toLowerCase();
                const normalizedHref = hrefLower.split('#')[0];
                const hrefNoQuery = normalizedHref.split('?')[0];
                const pdfHints = hrefLower + ' ' + label;
                const hasPageCitation = /\bpage\s+\d+\b/i.test(label);
                const isInternalUploadedDoc =
                    /\/ai\/documents(?:\/|$)/i.test(hrefNoQuery) ||
                    /\/uploads\/ai_documents(?:\/|$)/i.test(hrefNoQuery) ||
                    /\/documents\/view(?:\/|$)/i.test(hrefNoQuery);

                const isLikelyLink = /^https?:\/\//i.test(href) || /\bhttps?:\/\//i.test(plainText);
                const isDataRecord = /\b(country record|record:|databank|database|kpi|indicator)\b/i.test(label);
                const isPdf =
                    /\.pdf(\b|$)/i.test(hrefNoQuery) ||
                    /(?:^|[?&])(format|mime|type|content_type)=application\/pdf(?:&|$)/i.test(hrefLower) ||
                    /(?:^|[?&])(format|mime|type)=pdf(?:&|$)/i.test(hrefLower) ||
                    /\/pdf(?:\/|$)/i.test(hrefNoQuery) ||
                    /\bapplication\/pdf\b/i.test(pdfHints) ||
                    (hasPageCitation && !isDataRecord) ||
                    isInternalUploadedDoc ||
                    /\bpdf\b/i.test(label);
                if (isPdf) return { icon: 'fa-file-pdf', iconStyle: 'fas', type: 'pdf', title: 'PDF source' };

                if (isDataRecord && !href) return { icon: 'fa-database', type: 'data', title: 'Data source' };

                const isWord = /\.(doc|docx|odt|rtf)$/i.test(normalizedHref) || /\b(doc|docx|word)\b/i.test(label);
                if (isWord) return { icon: 'fa-file-word', type: 'word', title: 'Document source' };

                const isSheet = /\.(xls|xlsx|csv|ods)$/i.test(normalizedHref) || /\b(xls|xlsx|csv|excel|spreadsheet)\b/i.test(label);
                if (isSheet) return { icon: 'fa-file-excel', type: 'sheet', title: 'Spreadsheet source' };

                const isSlides = /\.(ppt|pptx|odp)$/i.test(normalizedHref) || /\b(ppt|pptx|powerpoint|slides)\b/i.test(label);
                if (isSlides) return { icon: 'fa-file-powerpoint', type: 'slides', title: 'Presentation source' };

                const isImage = /\.(png|jpe?g|gif|webp|svg|bmp|tiff?)$/i.test(normalizedHref) || /\b(image|photo|png|jpg|jpeg|gif|webp|svg)\b/i.test(label);
                if (isImage) return { icon: 'fa-file-image', type: 'image', title: 'Image source' };

                if (isLikelyLink) return { icon: 'fa-link', type: 'link', title: 'Web source' };
                return { icon: 'fa-file-lines', iconStyle: 'fas', type: 'file', title: 'Source file' };
            };
            const self = this;
            const linkifySegment = (seg) => {
                const hasLink = /<a\s[^>]*href\s*=/i.test(seg);
                const hasMdLink = /\[([^\]]*)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/.test(seg);
                if (hasLink) {
                    return seg;
                }
                const out = seg.replace(/\[([^\]]*)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/g, (_, label, href) => {
                    const safe = self._safeSameOriginUrl(href);
                    if (!safe) return self.escapeHtml(label || '');
                    return '<a href="' + self.escapeHtml(safe) + '" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener">' + self.escapeHtml(label || '') + '</a>';
                });
                return out;
            };
            const fragment = document.createDocumentFragment();
            const tempDiv = document.createElement('div');
            segments.forEach((segment) => {
                segment = linkifySegment(segment);
                tempDiv.innerHTML = segment;
                const plainText = (tempDiv.textContent || '').trim();
                const lineEl = document.createElement('div');
                lineEl.className = 'chat-source-line';
                const iconInfo = resolveSourceIcon(segment, plainText);
                const iconSpan = document.createElement('span');
                iconSpan.className = 'chat-source-line-icon chat-source-line-icon-' + iconInfo.type;
                iconSpan.setAttribute('aria-hidden', 'true');
                iconSpan.setAttribute('title', iconInfo.title);
                const iconStyleClass = iconInfo.iconStyle || 'fas';
                iconSpan.innerHTML = '<i class="' + iconStyleClass + ' ' + iconInfo.icon + '" aria-hidden="true"></i>';
                const previewSpan = document.createElement('span');
                previewSpan.className = 'chat-source-line-preview';
                previewSpan.textContent = plainText || '\u00a0';
                const toggleSpan = document.createElement('span');
                toggleSpan.className = 'chat-source-line-toggle';
                toggleSpan.setAttribute('aria-hidden', 'true');
                toggleSpan.textContent = '\u203a';
                const fullSpan = document.createElement('span');
                fullSpan.className = 'chat-source-line-full';
                fullSpan.innerHTML = segment;
                lineEl.appendChild(iconSpan);
                lineEl.appendChild(previewSpan);
                lineEl.appendChild(toggleSpan);
                lineEl.appendChild(fullSpan);
                lineEl.addEventListener('click', (e) => {
                    const link = e.target.closest('a');
                    const insideFull = e.target.closest('.chat-source-line-full');
                    const isLinkClick = !!link;
                    const isInsideExpandedContent = !!insideFull;
                    const shouldNotToggle = isLinkClick || isInsideExpandedContent;
                    if (shouldNotToggle) {
                        if (isLinkClick) e.stopPropagation();
                        return;
                    }
                    lineEl.classList.toggle('expanded');
                    lineEl.setAttribute('aria-expanded', lineEl.classList.contains('expanded'));
                });
                lineEl.setAttribute('role', 'button');
                lineEl.setAttribute('tabIndex', '0');
                lineEl.setAttribute('aria-expanded', 'false');
                lineEl.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        lineEl.classList.toggle('expanded');
                        lineEl.setAttribute('aria-expanded', lineEl.classList.contains('expanded'));
                    }
                });
                fragment.appendChild(lineEl);
            });
            bodyEl.innerHTML = '';
            bodyEl.appendChild(fragment);

            // Prevent link clicks from bubbling to the row (which would toggle expand/collapse)
            if (!bodyEl.hasAttribute('data-sources-link-handler')) {
                bodyEl.setAttribute('data-sources-link-handler', '1');
                bodyEl.addEventListener('click', (e) => {
                    const a = e.target.closest('a');
                    const inSourceLine = a && a.closest('.chat-source-line');
                    if (a && inSourceLine) {
                        e.stopPropagation();
                    }
                }, true);
            }

            const sourceLines = bodyEl.querySelectorAll('.chat-source-line');
            const DEFAULT_VISIBLE_SOURCES = 5;
            if (sourceLines.length > DEFAULT_VISIBLE_SOURCES) {
                for (let i = DEFAULT_VISIBLE_SOURCES; i < sourceLines.length; i++) {
                    sourceLines[i].classList.add('chat-source-line-hidden');
                }
                const expandRow = document.createElement('div');
                expandRow.className = 'chat-sources-expand-row';
                expandRow.setAttribute('role', 'button');
                expandRow.setAttribute('tabIndex', '0');
                expandRow.setAttribute('aria-label', 'Show more sources');
                expandRow.innerHTML = '<span class="chat-sources-expand-label">Show ' + (sourceLines.length - DEFAULT_VISIBLE_SOURCES) + ' more sources</span> <i class="fas fa-chevron-down chat-sources-expand-icon" aria-hidden="true"></i>';
                expandRow.addEventListener('click', () => {
                    bodyEl.querySelectorAll('.chat-source-line-hidden').forEach((el) => el.classList.remove('chat-source-line-hidden'));
                    expandRow.remove();
                    detailsEl.classList.add('chat-response-sources-expanded');
                });
                expandRow.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        expandRow.click();
                    }
                });
                bodyEl.appendChild(expandRow);
            }
        });
    }

    _augmentOnboardingActions(root) {
        /**
         * Add "Take a quick tour" CTA links for workflow-enabled flows.
         *
         * Behavior:
         * 1) If the message already contains a chatbot-tour link, upgrade it to button styling.
         * 2) Else infer a tour link from workflow/page hints and append a CTA button link.
         *
         * Returns the CTA element when a new one is created, so it can be positioned in the wrapper.
         */
        try {
            if (!root || typeof root.querySelector !== 'function') return null;
            const ctaLabel = this._uiString('takeQuickTour') || 'Take a quick tour';

            // If AI already included a tour deep-link, just style it as CTA.
            const existingTourLink = root.querySelector('a[href*="chatbot-tour="]:not(.chatbot-show-me)');
            if (existingTourLink && !existingTourLink.closest('.chat-response-sources')) {
                const safeHref = this._safeSameOriginUrl(existingTourLink.getAttribute('href') || '');
                if (safeHref) {
                    existingTourLink.setAttribute('href', safeHref);
                    existingTourLink.classList.add('chatbot-show-me');
                    if (!(existingTourLink.textContent || '').trim()) {
                        existingTourLink.textContent = ctaLabel;
                    }
                }
                return null;
            }

            if (root.querySelector('a.chatbot-show-me')) return null; // already present

            const tourHref = this._inferWorkflowTourHref(root);
            if (!tourHref) return null;

            const showMe = document.createElement('a');
            showMe.className = 'chatbot-show-me';
            showMe.setAttribute('href', tourHref);
            showMe.textContent = ctaLabel;
            return showMe;
        } catch (error) {
            // Never break message rendering
            console.warn('Failed to augment onboarding actions:', error);
        }
        return null;
    }

    _inferWorkflowTourHref(root) {
        /**
         * Best-effort derivation of a workflow tour deep-link from chatbot message content.
         */
        try {
            if (!root || typeof root.querySelector !== 'function') return null;

            // 1) Explicit chatbot-tour links already present in message.
            const explicitTourLink = root.querySelector('a[href*="chatbot-tour="]');
            if (explicitTourLink && !explicitTourLink.closest('.chat-response-sources')) {
                const safe = this._safeSameOriginUrl(explicitTourLink.getAttribute('href') || '');
                if (safe) return safe;
            }

            // 2) Explicit workflow trigger button/link with workflow id.
            const workflowTrigger = root.querySelector('.chatbot-tour-trigger[data-workflow]');
            if (workflowTrigger && !workflowTrigger.closest('.chat-response-sources')) {
                const workflowId = String(workflowTrigger.getAttribute('data-workflow') || '').trim();
                if (!workflowId) return null;
                const rawHref = String(workflowTrigger.getAttribute('href') || '').trim();
                const targetPath = rawHref ? rawHref.split('#')[0] : window.location.pathname;
                const composed = `${targetPath}#chatbot-tour=${encodeURIComponent(workflowId)}`;
                return this._safeSameOriginUrl(composed);
            }

            // 3) Fallback: infer workflow from known admin pages linked in the response.
            const fallbackByPath = {
                '/admin/users': 'add-user',
                '/admin/assignments': 'create-assignment',
                '/admin/templates': 'create-template',
            };
            const links = Array.from(root.querySelectorAll('a[href]'));
            for (const link of links) {
                if (link.closest('.chat-response-sources')) continue;
                const safeHref = this._safeSameOriginUrl(link.getAttribute('href') || '');
                if (!safeHref) continue;
                const parsed = new URL(safeHref, window.location.origin);
                const path = String(parsed.pathname || '').replace(/\/+$/, '') || '/';
                const workflowId = fallbackByPath[path];
                if (!workflowId) continue;
                return `${path}${parsed.search || ''}#chatbot-tour=${encodeURIComponent(workflowId)}`;
            }
        } catch (error) {
            console.debug('Failed to infer workflow tour href:', error);
        }
        return null;
    }

    runSpotlightFromHash() {
        /**
         * Supports deep-links that trigger a lightweight spotlight or multi-step tour, e.g.:
         *   /admin/users#chatbot-spotlight=add-new-user (single spotlight)
         *   /admin/users#chatbot-tour=add-user (multi-step tour)
         */
        try {
            const hash = window.location.hash || '';

            // Check for tour first (multi-step) - delegate to InteractiveTour
            const tourMatch = hash.match(/chatbot-tour=([^&]+)/i);
            if (tourMatch) {
                // InteractiveTour will handle this via checkUrlHash()
                // Use allowDynamic=true so WorkflowTourParser can register dynamic tours
                if (window.InteractiveTour && typeof window.InteractiveTour.checkUrlHash === 'function') {
                    window.InteractiveTour.checkUrlHash(true);
                    return;
                }
            }

            // Check for single spotlight (still handled by chatbot)
            const spotlightMatch = hash.match(/chatbot-spotlight=([^&]+)/i);
            if (spotlightMatch) {
                const spotlightId = decodeURIComponent(spotlightMatch[1] || '').trim();
                if (spotlightId) {
                    // Clear hash to avoid re-running on refresh/back navigation.
                    try {
                        window.history.replaceState(null, document.title, window.location.pathname + window.location.search);
                    } catch (_) {}

                    // Delay to allow late-rendered page header/actions to appear.
                    setTimeout(() => this.spotlightById(spotlightId), 250);
                }
            }
        } catch (_) {}
    }

    spotlightById(spotlightId) {
        const id = String(spotlightId || '').trim().toLowerCase();
        if (!id) return;

        // Map spotlight IDs to selectors + helper copy.
        const map = {
            'add-new-user': {
                selector: 'a[href="/admin/users/new"]',
                help: 'Click “Add New User” to create a new account.',
            },
        };

        const cfg = map[id];
        if (!cfg || !cfg.selector) return;

        this._spotlightSelector(cfg.selector, cfg.help || '');
    }

    _spotlightSelector(selector, helpText, options = {}) {
        // Retry briefly in case the DOM renders late (AG Grid, macros, etc.)
        const maxAttempts = 30;
        const delayMs = 200;

        const attempt = (n) => {
            const el = document.querySelector(selector);
            if (el) {
                this._spotlightElement(el, helpText, options);
                return;
            }
            if (n >= maxAttempts) return;
            setTimeout(() => attempt(n + 1), delayMs);
        };

        attempt(0);
    }

    _spotlightElement(el, helpText, options = {}) {
        this._clearSpotlight();

        try {
            // Check if we're in a tour (declare once at the top)
            const currentTour = (window.InteractiveTour && window.InteractiveTour.currentTour) || this._currentTour;

            // Scroll into view
            try {
                el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
            } catch (_) {}

            // Apply highlight class
            el.classList.add('chatbot-spotlight-target');

            // Click interception for tours is now handled by InteractiveTour
            // Single spotlights (non-tour) don't need click interception

            // Skip backdrop for tours (no dimming) - only add for single spotlights
            if (!currentTour) {
                // Add a subtle backdrop (does not block clicks) for single spotlights only
                const backdrop = document.createElement('div');
                backdrop.id = 'chatbotSpotlightBackdrop';
                backdrop.className = 'chatbot-spotlight-backdrop';
                document.body.appendChild(backdrop);
            }

            // Build tooltip content
            const hasAction = options.action && typeof options.action === 'function';
            const showEndTour = options.showEndTour === true;
            const actionText = options.actionText || 'Next';

            let tooltipContent = `
                <div class="chatbot-spotlight-tooltip__row">
                    <div class="chatbot-spotlight-tooltip__text">${this.escapeHtml(helpText || 'Here it is.')}</div>
                    <button type="button" class="chatbot-spotlight-tooltip__close" aria-label="Close spotlight">×</button>
                </div>
            `;

            if (hasAction || showEndTour) {
                tooltipContent += '<div class="chatbot-spotlight-tooltip__actions">';
                if (hasAction) {
                    tooltipContent += `<button type="button" class="chatbot-spotlight-tooltip__action-btn" data-action="next">${this.escapeHtml(actionText)}</button>`;
                }
                if (showEndTour) {
                    const endTourText = this.escapeHtml(this._uiString('endTour') || 'End Tour');
                    tooltipContent += `<button type="button" class="chatbot-spotlight-tooltip__end-tour-btn" data-action="end">${endTourText}</button>`;
                }
                tooltipContent += '</div>';
            }

            // Tooltip
            const tip = document.createElement('div');
            tip.id = 'chatbotSpotlightTooltip';
            tip.className = 'chatbot-spotlight-tooltip';
            tip.innerHTML = tooltipContent;
            document.body.appendChild(tip);

            // Check if user has manually positioned this tooltip before (for tours)
            let manualPosition = null;
            if (currentTour) {
                const tourId = currentTour.id || (currentTour.id || '');
                manualPosition = this._getSpotlightTooltipPosition(tourId);
            }

            const positionTip = (useManualPos = false) => {
                try {
                    // If user manually positioned, use that (unless forced to recalculate)
                    if (useManualPos && manualPosition) {
                        tip.style.top = `${manualPosition.top}px`;
                        tip.style.left = `${manualPosition.left}px`;
                        return;
                    }

                    const rect = el.getBoundingClientRect();
                    const tipRect = tip.getBoundingClientRect();
                    const margin = 12;
                    const viewportWidth = window.innerWidth;
                    const viewportHeight = window.innerHeight;

                    const clamp = (v, min, max) => Math.max(min, Math.min(v, max));
                    const maxLeft = Math.max(margin, viewportWidth - tipRect.width - margin);
                    const maxTop = Math.max(margin, viewportHeight - tipRect.height - margin);

                    const centeredLeft = rect.left + (rect.width - tipRect.width) / 2;
                    const centeredTop = rect.top + (rect.height - tipRect.height) / 2;

                    // Candidate positions (prefer bottom, then top, then right/left), but score them
                    // so we keep the tooltip close to the target and avoid overlap when possible.
                    const candidates = [
                        { top: rect.bottom + margin, left: centeredLeft, side: 'bottom' },
                        { top: rect.top - tipRect.height - margin, left: centeredLeft, side: 'top' },
                        { top: centeredTop, left: rect.right + margin, side: 'right' },
                        { top: centeredTop, left: rect.left - tipRect.width - margin, side: 'left' },
                    ];

                    const inflatedTarget = {
                        left: rect.left - margin,
                        right: rect.right + margin,
                        top: rect.top - margin,
                        bottom: rect.bottom + margin,
                    };

                    const intersectionArea = (a, b) => {
                        const x = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
                        const y = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
                        return x * y;
                    };

                    let best = null;
                    let bestScore = Infinity;

                    for (const c of candidates) {
                        const clampedLeft = clamp(c.left, margin, maxLeft);
                        const clampedTop = clamp(c.top, margin, maxTop);

                        const tipBox = {
                            left: clampedLeft,
                            right: clampedLeft + tipRect.width,
                            top: clampedTop,
                            bottom: clampedTop + tipRect.height,
                        };

                        const overlap = intersectionArea(tipBox, inflatedTarget);
                        const moved = Math.abs(clampedLeft - c.left) + Math.abs(clampedTop - c.top);

                        // Strongly prefer not overlapping; secondarily keep it close to the ideal anchor.
                        const score = overlap * 1000 + moved;

                        if (score < bestScore) {
                            bestScore = score;
                            best = { left: clampedLeft, top: clampedTop, side: c.side };
                        }
                    }

                    tip.style.top = `${Math.round((best && best.top) || margin)}px`;
                    tip.style.left = `${Math.round((best && best.left) || margin)}px`;
                } catch (_) {}
            };

            // First position after it renders
            setTimeout(() => positionTip(!!manualPosition), 0);

            // Make tooltip draggable
            let isDragging = false;
            let dragStartX = 0;
            let dragStartY = 0;
            let dragStartLeft = 0;
            let dragStartTop = 0;

            const handleMouseDown = (e) => {
                // Don't start drag if clicking on buttons or close button
                if (e.target.closest('button') || e.target.closest('.chatbot-spotlight-tooltip__close')) {
                    return;
                }

                isDragging = true;
                const rect = tip.getBoundingClientRect();
                dragStartX = e.clientX;
                dragStartY = e.clientY;
                dragStartLeft = rect.left;
                dragStartTop = rect.top;

                tip.classList.add('chatbot-spotlight-tooltip--dragging');
                tip.style.cursor = 'grabbing';

                e.preventDefault();
            };

            const handleMouseMove = (e) => {
                if (!isDragging) return;

                const deltaX = e.clientX - dragStartX;
                const deltaY = e.clientY - dragStartY;

                let newLeft = dragStartLeft + deltaX;
                let newTop = dragStartTop + deltaY;

                // Clamp to viewport
                const tipRect = tip.getBoundingClientRect();
                const margin = 10;
                newLeft = Math.max(margin, Math.min(newLeft, window.innerWidth - tipRect.width - margin));
                newTop = Math.max(margin, Math.min(newTop, window.innerHeight - tipRect.height - margin));

                tip.style.left = `${newLeft}px`;
                tip.style.top = `${newTop}px`;

                // Store manual position for tours (max 10 entries)
                if (currentTour) {
                    const tourId = currentTour.id || '';
                    manualPosition = { left: newLeft, top: newTop };
                    this._setSpotlightTooltipPosition(tourId, manualPosition);
                }
            };

            const handleMouseUp = () => {
                if (isDragging) {
                    isDragging = false;
                    tip.classList.remove('chatbot-spotlight-tooltip--dragging');
                    tip.style.cursor = '';
                }
            };

            // Add drag handlers
            tip.addEventListener('mousedown', handleMouseDown);
            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);

            // Store handlers for cleanup
            this._spotlightDragHandlers = {
                mousedown: handleMouseDown,
                mousemove: handleMouseMove,
                mouseup: handleMouseUp
            };

            // Reposition on resize/scroll (but respect manual position)
            this._spotlightRepositionHandler = () => {
                if (!isDragging && !manualPosition) {
                    positionTip(false);
                }
            };
            window.addEventListener('resize', this._spotlightRepositionHandler, { passive: true });
            window.addEventListener('scroll', this._spotlightRepositionHandler, { passive: true });

            // Close handlers
            tip.querySelector('.chatbot-spotlight-tooltip__close')?.addEventListener('click', () => {
                if (currentTour) {
                    if (window.InteractiveTour && typeof window.InteractiveTour.end === 'function') {
                        window.InteractiveTour.end();
                    } else {
                        this._endTour();
                    }
                } else {
                    this._clearSpotlight();
                }
            });

            // Action button handler
            if (hasAction) {
                tip.querySelector('.chatbot-spotlight-tooltip__action-btn')?.addEventListener('click', () => {
                    if (options.action) {
                        options.action();
                    }
                });
            }

            // End tour button handler
            if (showEndTour) {
                tip.querySelector('.chatbot-spotlight-tooltip__end-tour-btn')?.addEventListener('click', () => {
                    if (window.InteractiveTour && typeof window.InteractiveTour.end === 'function') {
                        window.InteractiveTour.end();
                    } else {
                        this._endTour();
                    }
                });
            }

            this._spotlightEscHandler = (evt) => {
                if (evt && evt.key === 'Escape') {
                    if (currentTour) {
                        if (window.InteractiveTour && typeof window.InteractiveTour.end === 'function') {
                            window.InteractiveTour.end();
                        } else {
                            this._endTour();
                        }
                    } else {
                        this._clearSpotlight();
                    }
                }
            };
            window.addEventListener('keydown', this._spotlightEscHandler);

            // Auto-clear after a while so the UI doesn't stay "stuck" (only for single spotlights, not tours)
            if (!currentTour) {
                this._spotlightTimeout = setTimeout(() => this._clearSpotlight(), 15000);
            }
        } catch (e) {
            console.warn('Failed to spotlight element:', e);
            this._clearSpotlight();
        }
    }

    startTour(tourId, initialStep = null) {
        /**
         * Start a multi-step tour - delegates to InteractiveTour system
         * @param {string} tourId - The ID of the tour to start
         * @param {number|null} initialStep - Optional 0-based step index to start from
         */
        if (window.InteractiveTour && typeof window.InteractiveTour.start === 'function') {
            window.InteractiveTour.start(tourId, initialStep);
        } else {
            console.warn('InteractiveTour not available');
        }
    }

    _showTourStep() {
        // Delegated to InteractiveTour - kept for compatibility
        if (window.InteractiveTour && window.InteractiveTour.currentTour) {
            // Tour is managed by InteractiveTour
            return;
        }
    }

    _advanceTourStep(tourId, stepNumber) {
        /**
         * Advance to a specific step - delegates to InteractiveTour
         */
        if (window.InteractiveTour && typeof window.InteractiveTour.advanceStep === 'function') {
            window.InteractiveTour.advanceStep(tourId, stepNumber);
        }
    }

    _endTour(tourId) {
        /**
         * End the current tour - delegates to InteractiveTour
         */
        if (window.InteractiveTour && typeof window.InteractiveTour.end === 'function') {
            window.InteractiveTour.end(tourId);
        }
    }

    _clearSpotlight() {
        try {
            if (this._spotlightTimeout) {
                clearTimeout(this._spotlightTimeout);
                this._spotlightTimeout = null;
            }
        } catch (_) {}

        try {
            document.querySelectorAll('.chatbot-spotlight-target').forEach((n) => n.classList.remove('chatbot-spotlight-target'));
        } catch (_) {}

        try {
            document.getElementById('chatbotSpotlightBackdrop')?.remove();
            document.getElementById('chatbotSpotlightTooltip')?.remove();
        } catch (_) {}

        try {
            if (this._spotlightRepositionHandler) {
                window.removeEventListener('resize', this._spotlightRepositionHandler);
                window.removeEventListener('scroll', this._spotlightRepositionHandler);
                this._spotlightRepositionHandler = null;
            }
            if (this._spotlightEscHandler) {
                window.removeEventListener('keydown', this._spotlightEscHandler);
                this._spotlightEscHandler = null;
            }
            // Clean up drag handlers
            if (this._spotlightDragHandlers) {
                const tip = document.getElementById('chatbotSpotlightTooltip');
                if (tip) {
                    tip.removeEventListener('mousedown', this._spotlightDragHandlers.mousedown);
                }
                document.removeEventListener('mousemove', this._spotlightDragHandlers.mousemove);
                document.removeEventListener('mouseup', this._spotlightDragHandlers.mouseup);
                this._spotlightDragHandlers = null;
            }
            // Clean up click intercept handlers
            if (this._spotlightClickHandlers) {
                this._spotlightClickHandlers.forEach(({ element, handler }) => {
                    try {
                        element.removeEventListener('click', handler, { capture: true });
                    } catch (_) {}
                });
                this._spotlightClickHandlers = null;
            }
        } catch (_) {}
    }

    // AI service integration method
    // Routes requests through the backend API (OpenAI-only).
    async callAIService(message, context = {}) {
        try {
            // Backward-compatible wrapper: route through the unified v2 request path so
            // transport behavior, DLP, sources, and conversation management can't drift.
            // `context` is intentionally ignored here to preserve the /api/ai/v2 contract.
            return await this.callBackendAPI(String(message ?? ''), {}, null);
        } catch (error) {
            console.error('AI service error:', error);
            throw error;
        }
    }

    showGreeting() {
        const greetings = this.messages.greetings || {};
        const greetingMessage = greetings[this.preferredLanguage] || greetings.en || "Hello! How can I help you?";
        this.addMessage(greetingMessage);
    }

    // Method to manually set language preference
    setLanguagePreference(language) {
        const validLanguages = ['en', 'es', 'fr', 'ar', 'ru', 'zh', 'hi'];
        const normalized = this._normalizeLanguage(language);
        if (validLanguages.includes(normalized)) {
            this._setPreferredLanguage(normalized);

            // Update greeting message
            this.clearConversation();
            //console.log(`Language preference set to: ${language}`);
        } else {
            console.warn(`Invalid language: ${language}. Valid options: ${validLanguages.join(', ')}`);
        }
    }

    resetLaptopPreference() {
        /* No-op: chat is always maximized */
    }
}

// Initialize the chatbot when the script loads
const chatbot = new HumDatabankChatbot();
try {
    if (window.debug && window.debug.getConfig && window.debug.getConfig().modules.chatbot) {
        console.log('[Chatbot tables] chatbot.js loaded; HumDatabankChatbot initialized');
    }
} catch (e) { /* debug not loaded */ }

// Make chatbot globally accessible
window.humdatabankChatbot = chatbot;

// Expose language setter to global scope for debugging/manual control
window.setChatbotLanguage = function(language) {
    if (window.humdatabankChatbot) {
        window.humdatabankChatbot.setLanguagePreference(language);
        return `Language preference set to: ${language}`;
    }
    return 'Chatbot not initialized';
};

// Expose language getter for debugging
window.getChatbotLanguage = function() {
    if (window.humdatabankChatbot) {
        return window.humdatabankChatbot.preferredLanguage;
    }
    return 'Chatbot not initialized';
};

// Expose laptop preference reset for debugging/manual control
window.resetChatbotLaptopPreference = function() {
    if (window.humdatabankChatbot) {
        window.humdatabankChatbot.resetLaptopPreference();
        return 'Laptop auto-expansion preference reset.';
    }
    return 'Chatbot not initialized';
};

// Chatbot debug controls - now managed by centralized debug.js
// Use window.debug.enableChatbot() / window.debug.disableChatbot() instead

// Legacy compatibility functions (redirect to centralized debug system)
window.enableChatbotDebug = function() {
    if (window.debug && window.debug.enableChatbot) {
        window.debug.enableChatbot();
        window.CHATBOT_DEBUG = true;
        console.log('✅ Chatbot debug enabled via centralized debug.js');
        console.log('Tip: Use window.debug.enableChatbot() directly in the future');
        return true;
    }
    console.warn('Centralized debug system not loaded yet. Debug.js should be loaded before chatbot.js');
    return false;
};

window.disableChatbotDebug = function() {
    if (window.debug && window.debug.disableChatbot) {
        window.debug.disableChatbot();
        window.CHATBOT_DEBUG = false;
        return true;
    }
    console.warn('Centralized debug system not loaded yet');
    return false;
};

window.getChatbotAPIStatus = function() {
    if (window.humdatabankChatbot) {
        const status = window.humdatabankChatbot.getAPIStatus();
        console.table(status);
        return status;
    }
    console.warn('Chatbot not initialized');
    return null;
};

// Helper to check what messages are loaded
window.getChatbotMessages = function() {
    if (window.humdatabankChatbot) {
        console.log('Loaded Messages:', window.humdatabankChatbot.messages);
        return window.humdatabankChatbot.messages;
    }
    console.warn('Chatbot not initialized');
    return null;
};

// Export for potential external use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = HumDatabankChatbot;
}

// ---------------------------------------------------------------------------
// Floating chatbot structured-payload renderer
// Handles `chatbot-structured-response` events when NOT in immersive mode.
// chat-immersive.js handles the immersive page; this block covers the widget.
// ---------------------------------------------------------------------------
(function () {
    'use strict';

    function isImmersivePage() {
        return !!(document.body && document.body.classList.contains('chat-immersive'));
    }

    // Find the .chat-message-content element to inject the card into.
    function resolveContentEl(messageElement, wrapperElement) {
        if (messageElement && messageElement.querySelector) {
            var c = messageElement.querySelector('.chat-message-content');
            if (c) return c;
        }
        if (wrapperElement && wrapperElement.querySelector) {
            var c2 = wrapperElement.querySelector('.chat-message.bot .chat-message-content');
            if (c2) return c2;
            // Fallback: last bot message in #chatMessages
            var msgs = document.querySelectorAll('#chatMessages .chat-message-wrapper:not(.is-user)');
            if (msgs.length) {
                var last = msgs[msgs.length - 1];
                var c3 = last.querySelector('.chat-message-content');
                if (c3) return c3;
            }
        }
        return null;
    }

    // Card shell shared by all types
    function makeCard(extraClass) {
        var card = document.createElement('div');
        card.className = 'chat-floating-payload-card' + (extraClass ? ' ' + extraClass : '');
        card.style.cssText = [
            'margin:10px 0 4px',
            'border:1px solid var(--humdb-border,#e2e8f0)',
            'border-radius:10px',
            'overflow:hidden',
            'background:var(--humdb-card-bg,#fff)',
            'font-size:13px'
        ].join(';');
        return card;
    }

    function makeCardHeader(titleText, extraContent) {
        var header = document.createElement('div');
        header.style.cssText = [
            'padding:8px 12px',
            'display:flex',
            'align-items:center',
            'justify-content:space-between',
            'gap:8px',
            'border-bottom:1px solid var(--humdb-border,#e2e8f0)',
            'background:var(--humdb-card-header-bg,#f8fafc)'
        ].join(';');
        var titleEl = document.createElement('span');
        titleEl.style.cssText = 'font-weight:600;font-size:13px;color:var(--humdb-text,#1e293b);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
        titleEl.textContent = titleText || '';
        header.appendChild(titleEl);
        if (extraContent) header.appendChild(extraContent);
        return { header: header, titleEl: titleEl };
    }

    function buildFloatingTableExportRows(columns, rows) {
        var safeColumns = Array.isArray(columns) ? columns : [];
        var safeRows = Array.isArray(rows) ? rows : [];
        if (!safeColumns.length || !safeRows.length) return [];
        var out = [];
        out.push(safeColumns.map(function (c) {
            return String((c && (c.label || c.key)) || '').trim();
        }));
        safeRows.forEach(function (row) {
            out.push(safeColumns.map(function (c) {
                var key = c && c.key ? c.key : '';
                var value = row && key ? row[key] : '';
                return value == null ? '' : String(value);
            }));
        });
        return out;
    }

    async function downloadFloatingTableAsExcel(columns, rows, fileBase) {
        var exportRows = buildFloatingTableExportRows(columns, rows);
        if (!exportRows.length) return false;
        var exportFetch = (window.getFetch && window.getFetch()) || fetch;
        var filename = (fileBase || 'data-table') + '.xlsx';
        try {
            var res = await exportFetch('/api/ai/v2/table/export', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ rows: exportRows })
            });
            if (!res.ok) throw new Error('Excel export failed: ' + res.status);
            var blob = await res.blob();
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
            return true;
        } catch (e) {
            return false;
        }
    }

    // Render a compact data table card inside the floating chatbot.
    function renderFloatingTableCard(payload, contentEl) {
        if (!payload || !Array.isArray(payload.rows) || !payload.rows.length) return;
        if (contentEl.querySelector('.chat-floating-payload-card')) return; // dedup

        var columns = Array.isArray(payload.columns) ? payload.columns : [];
        var allRows = payload.rows.slice();
        var sortBy = payload.sort_by || (columns.length ? columns[0].key : '');
        var sortOrder = payload.sort_order || 'desc';
        var columnWidthByKey = {};
        (function computeColumnWidths() {
            var sampleRows = allRows.slice(0, 180);
            columns.forEach(function (col) {
                var key = col && col.key ? col.key : '';
                if (!key) return;
                var keyLabel = ((col && (col.label || '')) + ' ' + key).toLowerCase();
                var isLinkishCol = col.type === 'link' || /\b(document|source|file|url|link)\b/.test(keyLabel);
                var labelLen = String((col.label || key) || '').trim().length;
                var maxLen = labelLen;
                var sumLen = 0;
                var seen = 0;
                sampleRows.forEach(function (row) {
                    var raw = row ? row[key] : '';
                    if (raw == null) return;
                    var len = String(raw).trim().length;
                    if (!len) return;
                    if (len > maxLen) maxLen = len;
                    sumLen += len;
                    seen += 1;
                });
                var avgLen = seen ? (sumLen / seen) : labelLen;
                var weighted = Math.max(labelLen, Math.min(70, Math.round((avgLen * 1.2) + (maxLen * 0.35))));
                var isNumericCol = col.type === 'number' || col.type === 'percent';
                var baseMin = isNumericCol ? 86 : (isLinkishCol ? 92 : 100);
                var baseMax = isNumericCol ? 170 : (isLinkishCol ? 180 : 250);
                var minWidth = Math.round(Math.max(baseMin, Math.min(baseMax, 50 + (weighted * (isNumericCol ? 2.7 : 3.8)))));
                var maxWidth = Math.round(Math.max(minWidth + 24, Math.min(isLinkishCol ? 210 : 300, minWidth + (isNumericCol ? 40 : (isLinkishCol ? 40 : 85)))));
                columnWidthByKey[key] = {
                    min: minWidth,
                    max: maxWidth
                };
            });
        })();

        var card = makeCard('chat-floating-table-card');

        // Search + export controls
        var searchInput = document.createElement('input');
        searchInput.type = 'search';
        searchInput.placeholder = 'Filter\u2026';
        searchInput.style.cssText = 'padding:3px 7px;border:1px solid var(--humdb-border,#cbd5e1);border-radius:5px;font-size:12px;width:120px;outline:none;flex-shrink:0;';
        var downloadBtn = document.createElement('button');
        downloadBtn.type = 'button';
        downloadBtn.className = 'chat-floating-table-export-btn';
        downloadBtn.textContent = 'Excel';
        downloadBtn.setAttribute('aria-label', 'Download table as Excel');
        downloadBtn.title = 'Download table as Excel';
        downloadBtn.style.cssText = 'padding:3px 8px;border:1px solid var(--humdb-border,#cbd5e1);border-radius:5px;font-size:12px;background:#fff;color:var(--humdb-text,#1e293b);cursor:pointer;flex-shrink:0;';
        var controls = document.createElement('div');
        controls.style.cssText = 'display:flex;align-items:center;gap:6px;';
        controls.appendChild(searchInput);
        controls.appendChild(downloadBtn);

        var hObj = makeCardHeader((payload.title || 'Data Table') + ' (' + allRows.length + ' rows)', controls);
        var titleEl = hObj.titleEl;
        card.appendChild(hObj.header);

        var tableWrap = document.createElement('div');
        tableWrap.style.cssText = 'overflow-x:auto;max-height:300px;overflow-y:auto;';
        var table = document.createElement('table');
        table.style.cssText = 'min-width:100%;border-collapse:collapse;font-size:12px;';

        var thead = document.createElement('thead');
        var headRow = document.createElement('tr');
        headRow.style.cssText = 'position:sticky;top:0;background:var(--humdb-card-header-bg,#f1f5f9);z-index:1;';
        columns.forEach(function (col) {
            var th = document.createElement('th');
            th.dataset.key = col.key;
            var w = columnWidthByKey[col.key] || { min: 100, max: 280 };
            th.style.cssText = 'padding:6px 8px;text-align:left;font-weight:600;font-size:11px;color:var(--humdb-text-muted,#64748b);border-bottom:2px solid var(--humdb-border,#e2e8f0);cursor:pointer;user-select:none;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word;min-width:' + w.min + 'px;max-width:' + w.max + 'px;';
            th.textContent = col.label || col.key;
            if (col.sortable !== false) {
                var arrow = document.createElement('span');
                arrow.className = 'sort-arrow';
                arrow.style.cssText = 'margin-left:3px;font-size:9px;opacity:0.4;';
                arrow.textContent = col.key === sortBy ? (sortOrder === 'asc' ? '\u25B2' : '\u25BC') : '\u25BC';
                if (col.key === sortBy) arrow.style.opacity = '1';
                th.appendChild(arrow);
                th.addEventListener('click', function () {
                    if (sortBy === col.key) {
                        sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
                    } else {
                        sortBy = col.key;
                        sortOrder = (col.type === 'number' || col.type === 'percent') ? 'desc' : 'asc';
                    }
                    renderRows();
                    thead.querySelectorAll('.sort-arrow').forEach(function (a) { a.style.opacity = '0.4'; a.textContent = '\u25BC'; });
                    arrow.style.opacity = '1';
                    arrow.textContent = sortOrder === 'asc' ? '\u25B2' : '\u25BC';
                });
            }
            headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);

        var tbody = document.createElement('tbody');
        table.appendChild(tbody);
        tableWrap.appendChild(table);
        card.appendChild(tableWrap);
        contentEl.appendChild(card);

        var filterText = '';

        function renderRows() {
            var filtered = allRows;
            if (filterText) {
                var ft = filterText.toLowerCase();
                filtered = allRows.filter(function (r) {
                    return columns.some(function (c) {
                        var v = r[c.key];
                        return v != null && String(v).toLowerCase().indexOf(ft) >= 0;
                    });
                });
            }
            var col = columns.find(function (c) { return c.key === sortBy; });
            var isNum = col && (col.type === 'number' || col.type === 'percent');
            filtered.sort(function (a, b) {
                var va = a[sortBy], vb = b[sortBy];
                if (va == null && vb == null) return 0;
                if (va == null) return 1;
                if (vb == null) return -1;
                if (isNum) { va = Number(va) || 0; vb = Number(vb) || 0; }
                else { va = String(va).toLowerCase(); vb = String(vb).toLowerCase(); }
                var cmp = va < vb ? -1 : va > vb ? 1 : 0;
                return sortOrder === 'asc' ? cmp : -cmp;
            });
            tbody.innerHTML = '';
            var even = false;
            filtered.forEach(function (row) {
                var tr = document.createElement('tr');
                tr.style.cssText = even ? 'background:var(--humdb-row-alt,#f8fafc);' : '';
                even = !even;
                columns.forEach(function (col) {
                    var td = document.createElement('td');
                    var w = columnWidthByKey[col.key] || { min: 100, max: 280 };
                    td.style.cssText = 'padding:5px 8px;border-bottom:1px solid var(--humdb-border,#f1f5f9);white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word;min-width:' + w.min + 'px;max-width:' + w.max + 'px;';
                    var val = row[col.key];
                    var isNumeric = (col.type === 'number' || col.type === 'percent') && val != null && Number.isFinite(Number(val));
                    if (col.type === 'link' && val) {
                        var urlKey = col.url_key || (col.key + '_url');
                        var href = row[urlKey];
                        if (href) {
                            var a = document.createElement('a');
                            a.href = href; a.target = '_blank'; a.rel = 'noopener';
                            a.textContent = String(val);
                            a.style.cssText = 'color:var(--humdb-link,#2563eb);text-decoration:none;display:inline-block;max-width:100%;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word;';
                            td.appendChild(a);
                        } else {
                            td.textContent = String(val);
                        }
                    } else if (isNumeric) {
                        td.style.textAlign = 'right';
                        var formatted = Number(val).toLocaleString(undefined, { maximumFractionDigits: 2 });
                        td.textContent = col.type === 'percent' ? formatted + '%' : formatted;
                    } else {
                        td.textContent = val != null ? String(val) : '';
                    }
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
            titleEl.textContent = (payload.title || 'Data Table') + ' (' + filtered.length + (filtered.length !== allRows.length ? ' of ' + allRows.length : '') + ' rows)';
        }

        searchInput.addEventListener('input', function () {
            filterText = (searchInput.value || '').trim();
            renderRows();
        });

        downloadBtn.addEventListener('click', async function () {
            var base = ((payload.title || 'data-table') + '-table')
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .replace(/^-+|-+$/g, '') || 'data-table';
            downloadBtn.disabled = true;
            var original = downloadBtn.textContent;
            var ok = await downloadFloatingTableAsExcel(columns, allRows, base);
            downloadBtn.textContent = ok ? 'Done' : 'Failed';
            setTimeout(function () {
                downloadBtn.textContent = original;
                downloadBtn.disabled = false;
            }, 1200);
        });
        renderRows();
    }

    // Render a summary card for maps and charts (need full page to show interactive viz).
    function renderFloatingVizSummaryCard(payload, contentEl, type) {
        if (contentEl.querySelector('.chat-floating-payload-card')) return; // dedup

        var typeLabels = {
            worldmap: 'World Map', world_map: 'World Map', choropleth: 'World Map',
            line: 'Line Chart', linechart: 'Line Chart', timeseries: 'Line Chart',
            bar: 'Bar Chart', barchart: 'Bar Chart',
            pie: 'Pie Chart', donut: 'Donut Chart'
        };
        var typeIcons = {
            worldmap: 'fa-globe', world_map: 'fa-globe', choropleth: 'fa-globe',
            line: 'fa-chart-line', linechart: 'fa-chart-line', timeseries: 'fa-chart-line',
            bar: 'fa-chart-bar', barchart: 'fa-chart-bar',
            pie: 'fa-chart-pie', donut: 'fa-chart-pie'
        };
        var label = typeLabels[type] || 'Visualization';
        var icon = typeIcons[type] || 'fa-chart-bar';
        var title = payload.title || label;

        var card = makeCard('chat-floating-viz-card');

        var hObj = makeCardHeader(title);
        card.appendChild(hObj.header);

        var body = document.createElement('div');
        body.style.cssText = 'padding:10px 12px;display:flex;flex-direction:column;gap:8px;';

        // Brief metadata line
        var meta = document.createElement('div');
        meta.style.cssText = 'display:flex;align-items:center;gap:6px;color:var(--humdb-text-muted,#64748b);font-size:12px;';
        var iconEl = document.createElement('i');
        iconEl.className = 'fas ' + icon;
        iconEl.setAttribute('aria-hidden', 'true');
        meta.appendChild(iconEl);

        var metaText = document.createTextNode(label);
        meta.appendChild(metaText);

        if (payload.metric) {
            var sep = document.createTextNode(' \u00B7 ');
            meta.appendChild(sep);
            var metricSpan = document.createElement('span');
            metricSpan.textContent = payload.metric;
            meta.appendChild(metricSpan);
        }

        if (type === 'worldmap' || type === 'world_map' || type === 'choropleth') {
            var countries = Array.isArray(payload.countries) ? payload.countries : [];
            if (countries.length) {
                var countEl = document.createTextNode(' \u00B7 ' + countries.length + ' countries');
                meta.appendChild(countEl);
            }
        } else if (Array.isArray(payload.series)) {
            var pts = document.createTextNode(' \u00B7 ' + payload.series.length + ' data points');
            meta.appendChild(pts);
        }

        body.appendChild(meta);

        // "Open in full view" hint
        var immersiveUrl = (function () {
            try {
                var el = document.querySelector('#aiChatWidget');
                return el ? el.getAttribute('data-immersive-url') : null;
            } catch (_) { return null; }
        })();

        var hint = document.createElement('div');
        hint.style.cssText = 'font-size:12px;color:var(--humdb-text-muted,#64748b);';
        if (immersiveUrl) {
            hint.appendChild(document.createTextNode('Interactive visualization available in '));
            var fullViewLink = document.createElement('a');
            fullViewLink.href = immersiveUrl;
            fullViewLink.target = '_blank';
            fullViewLink.rel = 'noopener';
            fullViewLink.textContent = 'full view';
            fullViewLink.style.cssText = 'color:var(--humdb-link,#2563eb);text-decoration:underline;';
            hint.appendChild(fullViewLink);
            hint.appendChild(document.createTextNode('.'));
        } else {
            hint.textContent = 'Open the full view to see the interactive visualization.';
        }
        body.appendChild(hint);

        card.appendChild(body);
        contentEl.appendChild(card);
    }

    window.addEventListener('chatbot-structured-response', function (event) {
        try {
            if (isImmersivePage()) return; // chat-immersive.js handles this
            var detail = event && event.detail ? event.detail : null;
            if (!detail || !detail.payload) return;
            var payload = detail.payload;
            var type = String(payload.type || '').toLowerCase();
            var contentEl = resolveContentEl(detail.messageElement, detail.wrapperElement);
            if (!contentEl) return;

            if (type === 'data_table') {
                renderFloatingTableCard(payload, contentEl);
            } else if (
                type === 'worldmap' || type === 'world_map' || type === 'choropleth' ||
                type === 'line' || type === 'linechart' || type === 'timeseries' ||
                type === 'bar' || type === 'barchart' ||
                type === 'pie' || type === 'donut'
            ) {
                renderFloatingVizSummaryCard(payload, contentEl, type);
            }
        } catch (e) { /* never break the chatbot */ }
    });
})();
