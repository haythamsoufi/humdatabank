/**
 * Chatbot Transport module
 * @module chatbot/transport
 */

export const TransportMixin = {
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
    },

    _keepsRunningOnDisconnect() {
        return this._isImmersive() || !!this._fbAiConfig;
    },

    _isRecoverableStreamFailure(error) {
        if (!error) return false;
        const msg = String(error.message || error);
        return /\b502\b/.test(msg) || /\b503\b/.test(msg) || /\b504\b/.test(msg)
            || /gateway timeout/i.test(msg) || /platform error/i.test(msg);
    },

    _isRecoverableHttpStatus(status) {
        const code = Number(status);
        return code === 502 || code === 503 || code === 504;
    },

    _detachStreamForBackgroundRecovery(ctx, inflightState, inflightKey) {
        if (inflightState) inflightState.detached = true;
        if (inflightKey) {
            const inflight = this._inflightByConversationKey.get(inflightKey);
            if (inflight) inflight.detached = true;
        }
        const steps = ctx && Array.isArray(ctx.steps) && ctx.steps.length
            ? ctx.steps.map((s) => ({
                message: s.message || '',
                detail_lines: Array.isArray(s.detail_lines) ? s.detail_lines.slice() : [],
            }))
            : null;
        const pollConvId = (ctx && ctx.conversation_id)
            || (inflightState && inflightState.conversation_id)
            || this.getActiveConversationId();
        if (steps && pollConvId) {
            this._detachedInflightStepsByKey.set(String(pollConvId), {
                steps,
                request_id: (ctx && ctx.request_id) || null,
            });
        }
        if (pollConvId) {
            this._startInflightPoll(
                String(pollConvId),
                (ctx && ctx.request_id) || (inflightState && inflightState.request_id) || null,
            );
        }
        this.isTyping = true;
        this.showTypingIndicator();
        this._setSendButtonStop(true);
    },

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
        let convId = (this._isImmersive() && this.getActiveConversationId())
            ? this.getActiveConversationId()
            : (!this._isImmersive() && this._getFloatingConversationId ? this._getFloatingConversationId() : null);
        // Form-builder AI uses keep_running_on_disconnect; pre-assign an id so gateway
        // timeouts before SSE meta still allow polling recovery on the server conversation.
        if (!convId && this._fbAiConfig) {
            convId = this._generateClientMessageId();
            try {
                localStorage.setItem(this.floatingConversationIdKey, convId);
            } catch (_) { /* ignore */ }
            this._fbAiConversationId = convId;
        }
        if (convId) payload.conversation_id = convId;

        // Privacy flags (server-side DLP)
        // - allow_sensitive: explicit user confirmation to send sensitive text to external providers
        if (sendOptions && sendOptions.allow_sensitive) payload.allow_sensitive = true;

        if (this._fbAiConfig) {
            // Form-builder AI never queries historical/document sources.
            payload.sources = [];
            payload.keep_running_on_disconnect = true;
        }

        return payload;
    },

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
    },

    _setPendingStructuredPayload(payload) {
        this._pendingStructuredPayload = this._coerceStructuredPayload(payload);
    },

    _consumePendingStructuredPayload() {
        const payload = this._pendingStructuredPayload || null;
        this._pendingStructuredPayload = null;
        return payload;
    },

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
    },

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
    },

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
    },

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
    },

    async handleSendMessage(overrideMessage, opts = {}) {
        if (!this._hasAcknowledgedAiPolicy()) {
            if (this._isImmersive()) this._showAiPolicyModal();
            return;
        }
        const rawInput = overrideMessage !== undefined
            ? String(overrideMessage || '').trim()
            : this.elements.input.value.trim();
        const hasFbAttachment = !!(this._fbAiConfig && this._hasFormBuilderAttachments?.());
        if (!rawInput && !hasFbAttachment) return;
        if (this._fbAiAttachmentBusy) return;
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
        this._clearFormBuilderWelcomeBubble();

        let message = rawInput;
        let displayMessage = rawInput;
        let userMsgOpts = {};
        if (hasFbAttachment && overrideMessage === undefined) {
            const prepared = await this._prepareFormBuilderOutgoingMessage(rawInput);
            if (!prepared.ok) return;
            message = prepared.messageText;
            displayMessage = prepared.displayed;
            if (prepared.previewItems?.length) {
                userMsgOpts.attachmentPreviews = prepared.previewItems;
            } else if (prepared.previewUrl) {
                userMsgOpts.previewUrl = prepared.previewUrl;
            }
            (this._fbAiAttachments || []).forEach((a) => { a.previewUrl = null; });
            this._clearFormBuilderAttachment();
        }
        if (!message) return;

        if (overrideMessage === undefined) {
            this.addMessage(displayMessage, true, userMsgOpts);
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
        if (this._fbAiConfig && !this.getActiveConversationId()) {
            const cid = this._generateClientMessageId();
            try {
                localStorage.setItem(this.floatingConversationIdKey, cid);
            } catch (_) { /* ignore */ }
            this._fbAiConversationId = cid;
        }
        const trackInflight = this._isImmersive() || !!this._fbAiConfig;
        const inflightKey = this._isImmersive()
            ? this._getActiveConversationKey()
            : (this.getActiveConversationId() || null);
        const inflightState = trackInflight
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
            // Opt-in only. Missing flag must not default to WS (prod has WEBSOCKET_ENABLED=false).
            const wsEnabled = wsFromPage !== null
                ? (wsFromPage === 'true')
                : (window.CHAT_WEBSOCKET_ENABLED === true);
            // Always use streaming when possible: WS if enabled, else SSE. This ensures step events (progress) are sent.
            const useStreaming = true;
            const useWebSocket = wsEnabled && (typeof WebSocket !== 'undefined');
            let streamSucceeded = false;

            if (useWebSocket) {
                try {
                    await this.streamResponseWithWebSocket(message, sendOptions, abortRef, detachRef, inflightKey);
                    streamSucceeded = true;
                } catch (wsError) {
                    const isAbort = wsError && (wsError.name === 'AbortError' || /aborted|cancelled|canceled/i.test(String(wsError.message || '')));
                    if (isAbort) {
                        throw wsError;
                    }
                    // The message was already dispatched to the server (agent run started).
                    // Falling back to SSE would send the same query again and produce a
                    // duplicate trace. Propagate as a plain connection error instead.
                    if (wsError && wsError.alreadyDispatchedToServer) {
                        if (this._keepsRunningOnDisconnect()) {
                            console.warn('[Chatbot] Transport: WebSocket dropped after send — detaching for poll recovery');
                            if (inflightState) {
                                inflightState.detached = true;
                                const pollConvId = this.getActiveConversationId();
                                if (pollConvId) {
                                    this._startInflightPoll(pollConvId, inflightState.request_id || null);
                                }
                            }
                            streamSucceeded = true;
                        } else {
                            console.warn('[Chatbot] Transport: WebSocket dropped after send — skipping SSE fallback to prevent duplicate submission');
                            throw wsError;
                        }
                    } else {
                        console.warn('[Chatbot] Transport: WebSocket failed, falling back to SSE:', wsError);
                        this.isTyping = true;
                        this.hideTypingIndicator(); // clear any partial WS steps before SSE retries from scratch
                        this.showTypingIndicator();
                        this._setSendButtonStop(true);
                    }
                }
            }

            if (useStreaming && !streamSucceeded) {
                try {
                    await this.streamResponseWithSSE(message, sendOptions, abortRef, detachRef, inflightKey, inflightState);
                    streamSucceeded = true;
                } catch (sseError) {
                    const isUserAbort = sseError && (sseError.name === 'AbortError' || /aborted|cancelled|canceled/i.test(String(sseError.message || '')));
                    if (isUserAbort) {
                        throw sseError;
                    }
                    if (this._keepsRunningOnDisconnect() && this._isRecoverableStreamFailure(sseError)) {
                        console.warn('[Chatbot] Transport: SSE gateway failure — detaching (server may still run)');
                        if (inflightState) inflightState.detached = true;
                        const pollConvId = this.getActiveConversationId();
                        if (pollConvId) {
                            this._startInflightPoll(pollConvId, inflightState.request_id || null);
                        }
                        streamSucceeded = true;
                    } else {
                        console.warn('[Chatbot] Transport: SSE failed, falling back to HTTP JSON:', sseError);
                        this.isTyping = true;
                        this.hideTypingIndicator(); // clear any partial SSE steps before HTTP fallback
                        this.showTypingIndicator();
                        this._setSendButtonStop(true);
                    }
                }
            }

            if (!streamSucceeded) {
                if (this._keepsRunningOnDisconnect()) {
                    const pollConvId = this.getActiveConversationId();
                    if (pollConvId) {
                        if (inflightState) inflightState.detached = true;
                        this._startInflightPoll(pollConvId, (inflightState && inflightState.request_id) || null);
                        this.isTyping = true;
                        this.showTypingIndicator();
                        return;
                    }
                }
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
            if (!isAbort && !(inflightState && inflightState.detached && this._keepsRunningOnDisconnect())) {
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
            const keepPollingUi = !!(inflightState && inflightState.detached && this._keepsRunningOnDisconnect());
            if (!keepPollingUi) {
                this.isTyping = false;
                this._setSendButtonStop(false);
                this._log('Send button reset to ready');
            }
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
                        if (inflightState.detached && this._keepsRunningOnDisconnect()) {
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
    },

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
    },

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
    },

    processStreamingMessage(msg, ctx) {
        if (!msg || !msg.type || !ctx) return;

        if (msg.type !== 'delta' && msg.type !== 'step_detail' && msg.type !== 'pong'
            && msg.type !== 'step' && msg.type !== 'meta' && msg.type !== 'done'
            && msg.type !== 'error' && msg.type !== 'cancelled') {
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
                    if (this._fbAiConfig && msg.conversation_id) {
                        this._fbAiConversationId = msg.conversation_id;
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
                    const stepDetail = msg.detail != null ? String(msg.detail).trim() : '';
                    const visibleDetail = this._isSuppressedStepDetail(stepDetail) ? '' : stepDetail;
                    this.updateTypingIndicator(msg.message, visibleDetail || undefined);
                    if (!ctx.steps) ctx.steps = [];
                    const stepMsg = String(msg.message || '').trim();
                    const last = ctx.steps[ctx.steps.length - 1];
                    if (last && (last.message || '').trim() === stepMsg) {
                        if (visibleDetail) (last.detail_lines = last.detail_lines || []).push(visibleDetail);
                    } else {
                        ctx.steps.push({ message: stepMsg, detail_lines: visibleDetail ? [visibleDetail] : [] });
                    }
                } else if (msg.detail) {
                    this._log('STEP (detail-only) payload:', { detail: msg.detail });
                    this.appendStepDetail(msg.detail);
                    if (!this._isSuppressedStepDetail(msg.detail) && ctx.steps && ctx.steps.length) {
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
                    if (!this._isSuppressedStepDetail(msg.detail)) {
                        if (!ctx.steps) ctx.steps = [];
                        if (!ctx.steps.length) {
                            ctx.steps.push({ message: (this._uiString && this._uiString('preparingQuery')) || 'Preparing query…', detail_lines: [] });
                        }
                        const lastStep = ctx.steps[ctx.steps.length - 1];
                        if (!lastStep.detail_lines) lastStep.detail_lines = [];
                        lastStep.detail_lines.push(String(msg.detail || '').trim());
                    }
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
                let finalResponse = rawFromServer || ctx.buffer || '';
                ctx.buffer = finalResponse;

                if (!ctx.messageElement) {
                    ctx.messageElement = this.createStreamingMessageElement();
                    ctx.contentElement = ctx.messageElement.querySelector('.chat-message-content');
                }

                let wrapperEl = null;
                if (ctx.contentElement && finalResponse) {
                    if (this._fbAiConfig && this._fbAiConfig.templateId) {
                        finalResponse = this._stripFormBuilderEditAnswerHtml(finalResponse);
                    }
                    const sanitizedHtml = this.sanitizeHtml(finalResponse);
                    ctx.contentElement.innerHTML = sanitizedHtml;
                    ctx.contentElement.classList.remove('streaming-cursor');

                    if (!this._fbAiConfig) {
                        const showMeLink = this._augmentOnboardingActions(ctx.contentElement);
                        if (showMeLink) {
                            const btnWrapper = document.createElement('div');
                            btnWrapper.className = 'chatbot-show-me-wrapper';
                            btnWrapper.appendChild(showMeLink);
                            ctx.contentElement.appendChild(btnWrapper);
                        }
                    }
                    // processMessage after showMeLink is in the DOM so it binds tour triggers on it too
                    if (!this._fbAiConfig && window.WorkflowTourParser && typeof window.WorkflowTourParser.processMessage === 'function') {
                        try {
                            window.WorkflowTourParser.processMessage(ctx.contentElement);
                        } catch (e) {
                            console.debug('WorkflowTourParser error:', e);
                        }
                    }
                    this._formatChatResponseSources(ctx.contentElement);
                    this._enhanceIndicatorActionLinks(ctx.contentElement);
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

                if (this._fbAiConfig && msg.conversation_id) {
                    this._fbAiConversationId = msg.conversation_id;
                }
                if (this._fbAiConfig && msg.form_builder_result) {
                    this._handleFormBuilderResult(
                        msg.form_builder_result,
                        finalResponse,
                        ctx.contentElement
                    );
                }

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
    },

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

            let messageSent = false; // true once ws.send() has dispatched the query to the server
            ws.onopen = () => {
                const payload = Object.assign(
                    { type: 'message' },
                    this._buildUnifiedChatPayload(userMessage, sendOptions)
                );
                ws.send(JSON.stringify(payload));
                messageSent = true;
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
                    return;
                }
                console.error('[Chatbot] WS: connection error:', error);
                // If the message was already sent to the server the agent run has started.
                // Mark the rejection so the caller does NOT re-send via SSE (double-submission).
                if (messageSent && !done) {
                    const err = new Error('WebSocket connection error (message already dispatched)');
                    err.alreadyDispatchedToServer = true;
                    done = true;
                    clearTimeout(timeout);
                    try { ws.close(1000, 'client_error'); } catch (_) {}
                    reject(err);
                } else {
                    finish(false, 'WebSocket connection error');
                }
            };

            ws.onclose = (event) => {
                if (done) {
                    return;
                }
                if (ctx.buffer) {
                    // We got some data, consider it a success
                    finish(true);
                } else if (messageSent) {
                    // Connection dropped after the query was dispatched but before a complete
                    // answer arrived.  The agent run is likely in-flight on the server.
                    // Reject with a flag so handleSendMessage does NOT fall back to SSE —
                    // that would send the same query again and create a duplicate trace.
                    const err = new Error(`WebSocket closed before response (code ${event.code}) — message already dispatched`);
                    err.alreadyDispatchedToServer = true;
                    done = true;
                    clearTimeout(timeout);
                    reject(err);
                } else {
                    // Connection closed before we even sent anything — safe to fall back to SSE.
                    finish(false, `Connection closed (${event.code})`);
                }
            };
        });
    },

    async streamResponseWithSSE(userMessage, sendOptions = {}, abortRef, detachRef, inflightKey, inflightState) {
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
                    if (this._keepsRunningOnDisconnect() && this._isRecoverableHttpStatus(resp.status)) {
                        this._log('SSE gateway failure before stream open; detaching for background recovery', { status: resp.status });
                        this._detachStreamForBackgroundRecovery(ctx, inflightState, inflightKey);
                        resolve(ctx.buffer || '');
                        return;
                    }
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
                    if (this._keepsRunningOnDisconnect()) {
                        done = true;
                        clearTimeout(timeout);
                        if (ctx.contentElement) ctx.contentElement.classList.remove('streaming-cursor');
                        this._log('SSE stream ended without done; treating as detach (server may continue)');
                        if (inflightKey) {
                            const inflight = this._inflightByConversationKey.get(inflightKey);
                            if (inflight) inflight.detached = true;
                        }
                        if (inflightState) inflightState.detached = true;
                        const steps = Array.isArray(ctx.steps) && ctx.steps.length ? ctx.steps.map(s => ({ message: s.message || '', detail_lines: Array.isArray(s.detail_lines) ? s.detail_lines.slice() : [] })) : null;
                        if (steps) {
                            const key = ctx.conversation_id || (ctx._inflight_key && String(ctx._inflight_key).startsWith('draft:') ? null : ctx._inflight_key);
                            if (key) {
                                this._detachedInflightStepsByKey.set(key, { steps, request_id: ctx.request_id || null });
                            }
                        }
                        const pollConvId = ctx.conversation_id || this.getActiveConversationId();
                        if (pollConvId) {
                            this._startInflightPoll(String(pollConvId), ctx.request_id || null);
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
                        if (this._keepsRunningOnDisconnect()) {
                            // Server continues (keep_running_on_disconnect); treat timeout like a detach
                            // so polling picks up the result instead of falling back to HTTP JSON.
                            done = true;
                            clearTimeout(timeout);
                            if (ctx.contentElement) ctx.contentElement.classList.remove('streaming-cursor');
                            this._log('SSE timed out; treating as detach (server continues)');
                            if (inflightKey) {
                                const inflight = this._inflightByConversationKey.get(inflightKey);
                                if (inflight) inflight.detached = true;
                            }
                            if (inflightState) inflightState.detached = true;
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
                    if (this._keepsRunningOnDisconnect() && this._isRecoverableStreamFailure(e)) {
                        done = true;
                        clearTimeout(timeout);
                        if (ctx.contentElement) ctx.contentElement.classList.remove('streaming-cursor');
                        this._log('SSE gateway failure during stream; detaching for background recovery');
                        this._detachStreamForBackgroundRecovery(ctx, inflightState, inflightKey);
                        resolve(ctx.buffer || '');
                    } else {
                        finish(false, e?.message || 'SSE error');
                    }
                }
            }
        });
    },

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
    },

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
    },

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
    },

    _isServiceUnavailableResponse(response) {
        if (response == null || typeof response !== 'string') return false;
        const s = response.trim();
        return s.includes('AI service unavailable') || /service\s+unavailable/i.test(s);
    },

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
    },

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
            } else if (path.includes('/assignment/') || path.includes('/forms/assignment/') || path.includes('/forms/public-submission/') ||
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

            if (this._fbAiConfig) {
                const fb = { enabled: true };
                if (this._fbAiConfig.templateId) fb.template_id = this._fbAiConfig.templateId;
                if (this._fbAiConfig.versionId) fb.version_id = this._fbAiConfig.versionId;
                context.pageData.pageType = this._fbAiConfig.templateId
                    ? 'form_builder_edit'
                    : 'form_builder_create';
                context.formBuilder = fb;
            }

        } catch (error) {
            console.warn('Error collecting page context:', error);
        }

        return context;
    },

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
    },

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

};
