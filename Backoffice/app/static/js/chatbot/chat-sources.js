/**
 * Chatbot ChatSources module
 * @module chatbot/chat-sources
 */

export const ChatSourcesMixin = {
    _chatSourcesAllowed() {
        return ['historical', 'system_documents', 'upr_documents'];
    },

    _chatSourcesDefault() {
        // Default to "everything" to preserve current behavior unless user opts out.
        return ['historical', 'system_documents', 'upr_documents'];
    },

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
    },

    _loadChatSourcesFromStorage() {
        try {
            const raw = localStorage.getItem(this.sourcesStorageKey);
            if (!raw) return this._chatSourcesDefault();
            const parsed = JSON.parse(raw);
            return this._normalizeChatSources(parsed);
        } catch (_) {
            return this._chatSourcesDefault();
        }
    },

    _saveChatSourcesToStorage(sources) {
        try {
            const norm = this._normalizeChatSources(sources);
            localStorage.setItem(this.sourcesStorageKey, JSON.stringify(norm));
        } catch (_) {}
    },

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
    },

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
    },

    _getChatSourcesFromUiOrStorage() {
        const fromUi = this._getChatSourcesFromUi();
        if (fromUi && Array.isArray(fromUi) && fromUi.length) return fromUi;
        return this._loadChatSourcesFromStorage();
    },

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

};
