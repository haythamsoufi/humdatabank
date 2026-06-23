/**
 * Chatbot Conversations module
 * @module chatbot/conversations
 */

export const ConversationsMixin = {
    _getImmersiveActiveId() {
        try {
            return localStorage.getItem(this.immersiveActiveIdKey) || null;
        } catch (e) { return null; }
    },

    _setImmersiveActiveId(id) {
        this.activeConversationId = id || null;
        try {
            if (id) localStorage.setItem(this.immersiveActiveIdKey, id);
            else localStorage.removeItem(this.immersiveActiveIdKey);
        } catch (e) { /* ignore */ }
    },

    _getImmersiveChatPath() {
        if (!this._isImmersive()) return '/chat';
        const id = this.getActiveConversationId();
        return id ? '/chat/' + encodeURIComponent(id) : '/chat';
    },

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
    },

    _handleImmersivePopstate() {
        if (!this._isImmersive()) return;
        const path = window.location.pathname;
        if (path === '/chat' || path === '/chat/') {
            this.startNewChat();
        } else {
            const m = path.match(/^\/chat\/([^/]+)$/);
            if (m) this.switchChat(m[1]);
        }
    },

    _getFloatingConversationId() {
        try {
            return localStorage.getItem(this.floatingConversationIdKey) || null;
        } catch (e) { return null; }
    },

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
    },

    _updateImmersiveLinkHref() {
        if (this._isImmersive() || !this.elements.immersiveBtn || !this.elements.widget) return;
        let url = this.elements.widget.getAttribute('data-immersive-url') || '/chat';
        const conversationId = this._getFloatingConversationId();
        if (conversationId) {
            url = url.replace(/\/+$/, '') + '/' + encodeURIComponent(conversationId);
        }
        this.elements.immersiveBtn.setAttribute('href', url);
    },

    _toggleFloatingSidebar() {
        if (!this.elements.widget) return;
        const open = this.elements.widget.classList.toggle('chat-sidebar-open');
        if (open && this.elements.floatingChatList) {
            this._renderFloatingConversationList();
        }
    },

    _escapeAttr(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    },

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
    },

    _apiFetch(url, options = {}) {
        const opts = {
            headers: {
                'Content-Type': 'application/json',
                ...(options.headers || {})
            },
            ...options
        };
        return ((window.getFetch && window.getFetch()) || fetch)(url, opts);
    },

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
    },

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
    },

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
    },

    _setupVisibilityChangeHandler() {
        if (this._visibilityHandlerBound) return;
        this._visibilityHandlerBound = true;
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState !== 'visible') return;
            if (!this._isImmersive()) return;
            this._checkAndResumeInflightPoll();
        });
    },

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
    },

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
    },

    _dispatchImmersiveUpdate() {
        if (typeof window.dispatchEvent === 'function') {
            window.dispatchEvent(new CustomEvent('chatbot-immersive-updated'));
        }
    },

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
    },

    _resetFloatingHeaderTitleToDefault() {
        if (this._isImmersive()) return;
        const label = this.elements && this.elements.chatFloatingTitleLabel;
        if (!label) return;
        label.textContent = this._floatingDefaultTitleText || 'Assistant';
    },

    _applyFloatingHeaderTitleText(title) {
        if (this._isImmersive()) return;
        const label = this.elements && this.elements.chatFloatingTitleLabel;
        if (!label) return;
        const t = String(title || '').trim();
        if (t) label.textContent = t;
        else this._resetFloatingHeaderTitleToDefault();
    },
    /**
     * Mirrors server _build_initial_conversation_title: first 80 chars of the user message.
     */

    _buildLocalConversationTitle(message) {
        const text = String(message || '').trim();
        if (!text) {
            return (this._uiString && this._uiString('newChat')) ? this._uiString('newChat') : 'New chat';
        }
        return text.length > 80 ? text.slice(0, 80) + '…' : text;
    },
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
    },

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
    },

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
    },

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
    },
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
    },

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
    },

    loadConversation(messages) {
        if (!this.elements || !this.elements.messages) return;
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
    },

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
    },

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
    },

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
    },

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
    },

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
    },

    getActiveConversationId() {
        if (!this._isImmersive()) {
            return this._getFloatingConversationId();
        }
        return this.activeConversationId || this._getImmersiveActiveId() || null;
    },

    getImmersiveData() {
        return { activeId: this.getActiveConversationId(), conversations: [] };
    },

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
    },

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
    },

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
    },

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
    },

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

};
