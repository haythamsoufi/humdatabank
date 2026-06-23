/**
 * Chatbot State module
 * @module chatbot/state
 */

export const StateMixin = {
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
    },

    _getImmersiveDraftKey(reset = false) {
        if (!this._isImmersive()) return null;
        if (reset) this._immersiveDraftKey = null;
        if (!this._immersiveDraftKey) {
            this._immersiveDraftKey = 'draft:' + this._generateClientMessageId();
        }
        return this._immersiveDraftKey;
    },

    _getActiveConversationKey() {
        if (!this._isImmersive()) return this.getActiveConversationId();
        const activeId = this.getActiveConversationId();
        return activeId || this._getImmersiveDraftKey(false);
    },

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
    },

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
    },

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
    },

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
    },

    _detachActiveConversationStream() {
        if (!this._isImmersive()) return false;
        const key = this._getActiveConversationKey();
        return this._detachConversationStreamByKey(key);
    },

    setExpanded(expanded) {
        this.isExpanded = true; /* Always maximized */
        if (expanded) {
            setTimeout(() => this.scrollToBottom(), 100);
        }
    },

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
    },

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
    },

    saveExpandedState() {
        /* No-op: chat is always maximized */
    },

    loadExpandedState() {
        this.isExpanded = true; /* Chat is always maximized */
    }

};
